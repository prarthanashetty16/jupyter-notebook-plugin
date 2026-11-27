"""v4 Should ``dropna`` (rows, ``how='any'`` / ``'all'``, optional ``subset``). Probe at >= 200 MiB (OS peak, fresh
process, inputs from disk, median of 3); bar +-15% on the derived peak at each frame's TRUE surviving fraction.

DERIVATION (pandas 3.1.1 ``DataFrame.dropna``, written before this probe ran); n rows, K checked columns (``subset`` or
all), M the frame's moved bytes, f the surviving fraction, k = f n:

* ``subset``: ``agg_obj = self.take(indices, axis=1)``: a view per dtype block when the selected columns are one
  contiguous ascending run, else a take copy (item (1d) ``take_copied_bytes``); 0 here (contiguous subsets);
* ``notna(agg_obj)`` = ``~isna(agg_obj)``: the isna frame (K n bool) and its inverse (K n) alive together: **2 K n**;
  then the isna frame is freed (``astype(bool)`` on a bool frame copies nothing under copy-on-write);
* ``mask = notna_obj.all(axis=1)`` (``any`` for ``how='all'``), ``_reduce_axis1``: per block a reduced row vector and a
  new running result: **K n + 3 n**;
* if every row survives: ``self.copy(deep=False)`` (nothing more); otherwise ``self.loc[mask]`` while ``notna_obj``
  (a local of ``dropna``) and the mask are still alive: ``nonzero`` (8 k), ``RangeIndex.take`` -> Index (8 k), the
  block takes (M f): **K n + n + 16 k + M f**;
* peak = max of the three.

``thresh`` takes ``count(axis=1)`` instead and is not modelled.

    python docs/benchmarks/phase8/probes/p8_dropna.py > docs/benchmarks/phase8/probes/p8_dropna.out
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
BAR = 0.15


def derived(df: pd.DataFrame, cols: list[str], how: str) -> float:
    n = len(df)
    kcols = len(cols)
    m = 8.0 * n * df.shape[1]  # every column here moves 8 B / row (float64, int64, str pointers)
    notna = df[cols].notna()
    keep = notna.all(axis=1) if how == "any" else notna.any(axis=1)
    k = int(keep.sum())
    phases = [2.0 * kcols * n, kcols * n + 3.0 * n]
    if k < n:
        phases.append(kcols * n + n + 16.0 * k + m * k / n)
    return max(phases)


def frame(n: int, seed: int, na_f: float, na_s: float) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols: dict[str, Any] = {f"f{i}": rng.random(n) for i in range(3)}
    cols["i0"] = rng.integers(0, 10**6, n)
    if na_f:
        cols["f0"][rng.random(n) < na_f] = np.nan
    vocab = np.array([f"d{i:05d}" for i in range(20_000)], dtype=object)
    s = vocab[rng.integers(0, len(vocab), n)].copy()
    if na_s:
        s[rng.random(n) < na_s] = None
    cols["s0"] = pd.array(s, dtype="str")
    return pd.DataFrame(cols)


CASES = [
    ("how='any', all columns, 10% + 5% nulls", 8_000_000, 0.10, 0.05, "y = df.dropna()", None, "any"),
    ("subset=['f0'], 30% nulls", 8_000_000, 0.30, 0.0, "y = df.dropna(subset=['f0'])", ["f0"], "any"),
    ("how='all', 50% / 50% nulls in the checked pair", 8_000_000, 0.5, 0.5, "y = df.dropna(how='all', subset=['f0', 'f1'])",
     ["f0", "f1"], "all"),
    ("no null at all (shallow copy path)", 10_000_000, 0.0, 0.0, "y = df.dropna()", None, "any"),
]  # fmt: skip


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "np": np, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "bar": BAR}))
    with tempfile.TemporaryDirectory() as tmp:
        for label, n, na_f, na_s, src, subset, how in CASES:
            df = frame(n, 71, na_f, na_s)
            if "how='all'" in src:
                df["f1"] = df["f1"].where(np.random.default_rng(72).random(n) >= 0.5)
            want = derived(df, subset or list(df.columns), how)
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
            got = m.delta_bytes
            r = None if got is None else got / want
            print(json.dumps({"variant": label, "statement": src, "measured_mib": None if got is None else got / MIB,
                              "censored": got is None, "bound_mib": m.bound_bytes / MIB, "derived_mib": want / MIB,
                              "ratio": r, "within_bar": None if r is None else abs(r - 1) <= BAR}))  # fmt: skip


if __name__ == "__main__":
    main()
