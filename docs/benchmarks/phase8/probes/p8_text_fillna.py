"""v4 item (1a), SECOND ATTEMPT: fillna on pandas-3 ``str`` columns (StringDtype, python storage, no pyarrow).

Probe at >= 200 MiB (OS peak, fresh spawned process, inputs from disk, median of 3; ``nexus.measure``). Adoption bar
(pre-registration, Derivation rule): every variant within +-15% of the derived peak.

DERIVATION (written before this probe ran; pandas 3.1.1 source):

A ``str`` column is its own 1-D extension block. ``ExtensionBlock.fillna`` sends StringDtype to ``Block.fillna``:

* no missing value in the column: ``validate_putmask`` -> noop -> shallow copy: **0**;
* ``mask = isna(values)`` (n bool), then ``Block.where(value, ~mask)`` (cond: n), then ``ExtensionBlock.where``:
  ``icond = ~cond`` (n), then ``StringArray._where`` = ``ExtensionArray._where``: ``result = self.copy()`` (the object
  pointer array, 8 B/row; the string objects are shared) and ``result[~cond] = value`` (n).

  **(A) value is a str:** the setitem succeeds. Peak per column = 8n + 4n = **12 B/row**; the result column (8n)
  stays.
* **(B) value is not a str (e.g. ``0``):** ``StringArray.__setitem__`` raises TypeError AFTER ``result = self.copy()``.
  ``ExtensionBlock.where`` catches it and, INSIDE the except clause, coerces the block to object
  (``coerce_to_target_dtype`` -> ``astype(object)``: 8n) and runs the numpy ``Block.where``: ``icond`` (n) and
  ``np.where`` (result, 8n). The active exception's traceback keeps the failed ``_where`` frame alive: its 8n copy
  and its ``~cond`` argument (n).

  Peak per column = n (mask) + n (cond) + n (icond, EA) + 8n + n (held copy and key) + 8n (astype) + n (icond) + 8n
  (result) = **29 B/row**. The result column (object, 8n) stays.
* Several str columns: the blocks are filled one after another and the results are kept, so
  peak = 8n x (filled columns before the last) + the last column's transient.
* ``fillna({col: v})``: ``copy(deep=False)``, then per key ``result[k].fillna(v)`` (the 1-D path above), then setitem
  (no copy).
* String length does not enter (only pointers move). NA share enters only through "any missing value".

    python docs/benchmarks/phase8/probes/p8_text_fillna.py > docs/benchmarks/phase8/probes/p8_text_fillna.out
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
BAR = 0.15
A_PER_ROW, B_PER_ROW, KEPT_PER_ROW = 12, 29, 8


def frame(n: int, k: int, na: float, long: bool, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    width = 64 if long else 4
    vocab = np.array([f"{i:0{width}d}" for i in range(20_000)], dtype=object)
    cols = {}
    for j in range(k):
        arr = vocab[rng.integers(0, len(vocab), n)]
        if na > 0:
            arr = arr.copy()
            arr[rng.random(n) < na] = None
        cols[f"s{j}"] = pd.array(arr, dtype="str")
    return pd.DataFrame(cols)


def derived(n: int, k_filled: int, value_is_str: bool) -> float:
    if k_filled == 0:
        return 0.0
    last = A_PER_ROW if value_is_str else B_PER_ROW
    return float(n * (KEPT_PER_ROW * (k_filled - 1) + last))


def setup(path: str) -> pd.DataFrame:
    df = pd.read_pickle(path)
    gc.collect()
    return df


def op_scalar_str(df: pd.DataFrame) -> int:
    return len(df.fillna("x"))


def op_scalar_zero(df: pd.DataFrame) -> int:
    return len(df.fillna(0))


def op_dict_str(df: pd.DataFrame) -> int:
    return len(df.fillna({"s0": "x"}))


def op_series_str(df: pd.DataFrame) -> int:
    return len(df["s0"].fillna("x"))


# (label, rows, str columns, NA share, long strings, op, value is str, columns filled)
CASES = [
    ("A scalar 'x', 1 col, NA 10%", 20_000_000, 1, 0.10, False, op_scalar_str, True, 1),
    ("A scalar 'x', 1 col, NA 90%", 20_000_000, 1, 0.90, False, op_scalar_str, True, 1),
    ("A scalar 'x', 1 col, NA 0%", 20_000_000, 1, 0.0, False, op_scalar_str, True, 0),
    ("A scalar 'x', 1 col, long strings", 20_000_000, 1, 0.10, True, op_scalar_str, True, 1),
    ("A scalar 'x', 3 cols", 8_000_000, 3, 0.10, False, op_scalar_str, True, 3),
    ("A dict {'s0': 'x'}, 3 cols", 20_000_000, 3, 0.10, False, op_dict_str, True, 1),
    ("A Series df['s0'].fillna('x')", 20_000_000, 1, 0.10, False, op_series_str, True, 1),
    ("B scalar 0, 1 col, NA 10%", 10_000_000, 1, 0.10, False, op_scalar_zero, False, 1),
    ("B scalar 0, 1 col, long strings", 10_000_000, 1, 0.10, True, op_scalar_zero, False, 1),
    ("B scalar 0, 3 cols", 6_000_000, 3, 0.10, False, op_scalar_zero, False, 3),
]


def main() -> None:
    print(f"pandas {pd.__version__}, numpy {np.__version__}; bar +-{BAR:.0%}")
    print("| variant | rows | measured MiB | derived MiB | ratio | within bar |")
    print("|---|---|---|---|---|---|")
    with tempfile.TemporaryDirectory() as tmp:
        for label, n, k, na, long, fn, is_str, filled in CASES:
            df = frame(n, k, na, long)
            assert all(str(d) == "str" for d in df.dtypes), df.dtypes
            want = derived(n, filled, is_str)
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(fn, setup=setup, setup_args=(path,), repeats=3)
            got = m.delta_bytes
            if got is None:
                print(f"| {label} | {n} | censored | {want / MIB:.0f} | - | no |")
                continue
            if want == 0:
                ok = got < 16 * MIB
                print(
                    f"| {label} | {n} | {got / MIB:.1f} | 0 | - | {'yes' if ok else 'NO'} (< 16 MiB) |"
                )
                continue
            r = got / want
            ok = abs(r - 1) <= BAR
            print(
                f"| {label} | {n} | {got / MIB:.0f} | {want / MIB:.0f} | {r:.3f} | {'yes' if ok else 'NO'} |"
            )


if __name__ == "__main__":
    main()
