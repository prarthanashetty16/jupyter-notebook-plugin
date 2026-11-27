"""v4 item (1d): ``X.copy()`` on receivers v3 cannot size. Probe at >= 200 MiB (OS peak, fresh process, inputs from
disk, median of 3); bar +-15% on the DERIVED statement peak (the selected fraction f is known here), and the model's
high must be >= the measured peak (checked after the model exists, from this file's stored measurements).

The analyser detects only the ``copy`` in these statements: the receiver's own cost (mask, take, new index) belongs to
the copy's estimate. DERIVATION (pandas 3.1.1 source, written before this probe ran); n rows, M = the frame's moved
bytes (numeric values + 8 B per text pointer), k = f n selected rows:

* **mask** ``df[<comparisons>]`` (``_getitem_bool_array``) and ``df.loc[<comparisons>]`` (``_getbool_axis``):
  the comparison Series (n bool each; a ``str`` column compares through ``StringArray._cmp_method``: isna mask,
  valid mask, the valid pointer copy 8n, op result and result, about **12n**), ``&`` / ``|`` keep both operands and
  the result alive (3n for two); then ``key.nonzero()`` (8k), ``RangeIndex.take`` -> Index (8k) and the block takes
  (M f); then ``.copy()`` copies the blocks again (M f; the index is viewed). Peak = max(comparison temporaries,
  key n + 16k + M f, 8k + 2 M f).
* **column list** ``df[[...]]``: ``take(axis=1)`` -> ``_slice_take_blocks_ax0``: per numpy block, the selected
  columns' block positions taken in list order; a contiguous ascending run is a VIEW (``getitem_block_columns``),
  anything else ``take_nd`` copies those columns; text (extension) blocks are viewed. Then ``.copy()`` copies every
  selected column. Peak = copied-by-take + selected bytes.
* **row slices** ``df.iloc[a:b]`` and ``df.head(r)``: views; ``.copy()`` copies M r / n.
* **chain on a modelled operation** ``df.sort_values(c).copy()``: the copy of a frame with the same rows and columns:
  M (the sort's own peak is the sort model's).

    python docs/benchmarks/phase8/probes/p8_copy_receivers.py > docs/benchmarks/phase8/probes/p8_copy_receivers.out
"""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
N = 8_000_000
BAR = 0.15


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(31)
    cols: dict[str, Any] = {f"f{i}": rng.random(N) for i in range(4)}
    cols.update({f"i{i}": rng.integers(0, 1_000_000, N) for i in range(2)})
    vocab = np.array([f"x{i:05d}" for i in range(30_000)], dtype=object)
    for j in range(2):
        s = vocab[rng.integers(0, len(vocab), N)].copy()
        s[rng.random(N) < 0.05] = None
        cols[f"s{j}"] = pd.array(s, dtype="str")
    return pd.DataFrame(cols)


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "np": np, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def derived(df: pd.DataFrame, src: str) -> float:
    n = len(df)
    m = 8.0 * n * df.shape[1]  # every column here moves 8 B / row (float64, int64, str pointers)
    if src.startswith("y = df[(df"):  # two numeric comparisons combined
        k = int(((df["f0"] > 0.2) & (df["i0"] < 500_000)).sum())
        f = k / n
        return max(3.0 * n, n + 16.0 * k + m * f, 8.0 * k + 2 * m * f)
    if "df['s0'] ==" in src:
        k = int((df["s0"] == "x00001").sum())
        f = k / n
        return max(12.0 * n, n + 16.0 * k + m * f, 8.0 * k + 2 * m * f)
    if "> 0.5" in src or "> 0.9" in src:
        k = int((df["f0"] > (0.5 if "> 0.5" in src else 0.9)).sum())
        f = k / n
        return max(1.0 * n, n + 16.0 * k + m * f, 8.0 * k + 2 * m * f)
    if "['f0', 'f1', 'f2', 'f3']" in src:
        return 4 * 8.0 * n  # one contiguous run of the float block: view, then the copy
    if "['f2', 'f0', 'f1']" in src:
        return 2 * 3 * 8.0 * n  # taker [2, 0, 1] is not a slice: take_nd copies, then the copy
    if "iloc[:4_000_000]" in src:
        return m * 4_000_000 / n
    if "head(5_000_000)" in src:
        return m * 5_000_000 / n
    raise ValueError(src)


STATEMENTS = [
    "y = df[df['f0'] > 0.5].copy()",
    "y = df.loc[df['f0'] > 0.9].copy()",
    "y = df[(df['f0'] > 0.2) & (df['i0'] < 500_000)].copy()",
    "y = df[df['s0'] == 'x00001'].copy()",
    "y = df[['f0', 'f1', 'f2', 'f3']].copy()",
    "y = df[['f2', 'f0', 'f1']].copy()",
    "y = df.iloc[:4_000_000].copy()",
    "y = df.head(5_000_000).copy()",
    "y = df.sort_values('f0').copy()",  # chain: measured only; checked against the cell model's high later
]


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": BAR}))
    with tempfile.TemporaryDirectory() as tmp:
        df = frame()
        want = {s: (derived(df, s) if "sort_values" not in s else None) for s in STATEMENTS}
        path = str(Path(tmp) / "df.pkl")
        df.to_pickle(path)
        del df
        gc.collect()
        for src in STATEMENTS:
            m = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
            got = m.delta_bytes
            w = want[src]
            ratio = got / w if got is not None and w else None
            print(json.dumps({
                "statement": src, "measured_mib": None if got is None else got / MIB,
                "bound_mib": m.bound_bytes / MIB, "censored": got is None,
                "derived_mib": None if w is None else w / MIB, "ratio": ratio,
                "within_bar": None if ratio is None else abs(ratio - 1) <= BAR,
            }))  # fmt: skip


if __name__ == "__main__":
    main()
