"""v4 item (1a), SECOND DERIVATION (pre-registration amendment 1 (C)): fillna on ``str`` columns, NON-STRING value.

The only attempt allowed. If any variant below falls outside +-15%, text-column fillna stays UNKNOWN in v4 and the
string-value path (which passed in ``p8_text_fillna.out``) is NOT adopted either.

SECOND DERIVATION (written before this probe ran; same pandas 3.1.1 path as ``p8_text_fillna.py``, path B). The first
derivation counted the copy ``ExtensionArray._where`` makes before the failed setitem (8n) as held by the active
exception's traceback while the block is coerced. The first probe measured 22 B/row against the derived 29: the copy
is freed. The setitem's key argument ``~cond`` (n) is still counted as held. Per filled column:
n (mask) + n (cond) + n (icond, EA) + n (held key) + 8n (``astype(object)``) + n (icond, numpy ``Block.where``) + 8n
(``np.where`` result) = **21 B/row**. Several filled columns: 8n per column filled before the last, plus 21n.

FRESH VARIANTS (none of the first probe's rows / NA shares / lengths / column counts / values): int 0 and float -1.5
values; 1, 2 and 4 columns; NA 2%, 5%, 30%, 50%; string lengths 16 and 32.

MEASUREMENT FIX (not an attempt): the first probe's dict variant (``fillna({'s0': 'x'})``, string value, path A,
12 B/row) was censored on a 3-column 20M-row frame because its peak stayed below the setup peak. It is rerun on a
1-column frame.

    python docs/benchmarks/phase8/probes/p8_text_fillna_b2.py > docs/benchmarks/phase8/probes/p8_text_fillna_b2.out
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
B_PER_ROW, A_PER_ROW, KEPT_PER_ROW = 21, 12, 8


def frame(n: int, k: int, na: float, width: int, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    vocab = np.array([f"{i:0{width}d}" for i in range(30_000)], dtype=object)
    cols = {}
    for j in range(k):
        arr = vocab[rng.integers(0, len(vocab), n)].copy()
        arr[rng.random(n) < na] = None
        cols[f"s{j}"] = pd.array(arr, dtype="str")
    return pd.DataFrame(cols)


def setup(path: str) -> pd.DataFrame:
    df = pd.read_pickle(path)
    gc.collect()
    return df


def op_zero(df: pd.DataFrame) -> int:
    return len(df.fillna(0))


def op_float(df: pd.DataFrame) -> int:
    return len(df.fillna(-1.5))


def op_dict_str(df: pd.DataFrame) -> int:
    return len(df.fillna({"s0": "x"}))


# (label, rows, columns, NA share, string length, op, per-row term of the last column, kind)
CASES = [
    ("B int 0, 1 col, NA 30%, len 16", 11_000_000, 1, 0.30, 16, op_zero, B_PER_ROW, "attempt 2"),
    (
        "B float -1.5, 1 col, NA 2%, len 32",
        12_000_000,
        1,
        0.02,
        32,
        op_float,
        B_PER_ROW,
        "attempt 2",
    ),
    ("B int 0, 2 cols, NA 50%, len 16", 7_000_000, 2, 0.50, 16, op_zero, B_PER_ROW, "attempt 2"),
    ("B int 0, 4 cols, NA 5%, len 32", 6_000_000, 4, 0.05, 32, op_zero, B_PER_ROW, "attempt 2"),
    (
        "A dict {'s0': 'x'}, 1 col (measurement fix)",
        20_000_000,
        1,
        0.10,
        4,
        op_dict_str,
        A_PER_ROW,
        "fix",
    ),
]


def main() -> None:
    print(f"pandas {pd.__version__}, numpy {np.__version__}; bar +-{BAR:.0%}")
    print("| variant | kind | rows | measured MiB | derived MiB | ratio | within bar |")
    print("|---|---|---|---|---|---|---|")
    with tempfile.TemporaryDirectory() as tmp:
        for label, n, k, na, width, fn, last, kind in CASES:
            df = frame(n, k, na, width)
            assert all(str(d) == "str" for d in df.dtypes), df.dtypes
            filled = k if fn is not op_dict_str else 1
            want = float(n * (KEPT_PER_ROW * (filled - 1) + last))
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(fn, setup=setup, setup_args=(path,), repeats=3)
            if m.delta_bytes is None:
                print(
                    f"| {label} | {kind} | {n} | censored (no measurement) | {want / MIB:.0f} | - | - |"
                )
                continue
            r = m.delta_bytes / want
            ok = "yes" if abs(r - 1) <= BAR else "NO"
            print(
                f"| {label} | {kind} | {n} | {m.delta_bytes / MIB:.0f} | {want / MIB:.0f} | {r:.3f} | {ok} |"
            )


if __name__ == "__main__":
    main()
