"""Probe: does the cost of hash-based operations depend on the number of distinct keys (working set)?

HYPOTHESIS. ``groupby`` and ``astype("category")`` spend their time in ``factorize`` (a khash
table lookup per row). The frozen models charge a constant per row (``num_hash_s`` /
``text_hash_s``, measured at 1M / 300k distinct values). If the per-row cost instead rises with the
table's working set (distinct count G: table slots plus, for text, the string objects that are
compared), low-cardinality cells are over-predicted (table in cache) and high-cardinality ones
under-predicted (cache misses, table growth), which is the observed pattern (groupby 2.6x over at
low G, 0.25-0.5x under at G/n >= 0.75). A second check: groupby time ~= factorize time + aggregation.
Also: object-pointer take (``concat`` of categoricals with different categories materialises values)
as a function of the number of distinct objects.

Synthetic data only. Per-row seconds (median of 3, in-process), n = 2M rows (G <= 2M) or n = G.

    python docs/benchmarks/phase6/probes/p_hash_workingset.py
"""

from __future__ import annotations

import statistics
import time

import numpy as np
import pandas as pd


def t(fn, reps: int = 3) -> float:
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return statistics.median(out)


def main() -> None:
    rng = np.random.default_rng(3)
    print(f"pandas {pd.__version__}, numpy {np.__version__}")
    print("kind     G        n   factorize ns/row  groupby-sum ns/row  astype-category ns/row")
    for kind in ("numeric", "text"):
        for g in (100, 10_000, 100_000, 1_000_000, 3_000_000):
            n = max(2_000_000, g)
            codes = rng.integers(0, g, n)
            if kind == "numeric":
                keys = rng.integers(0, 2**62, g)[codes]
            else:
                vocab = np.array([f"{x:013d}" for x in rng.integers(0, 10**13, g)], dtype=object)
                keys = vocab[codes]
            s = pd.Series(keys)
            df = pd.DataFrame({"k": keys, "v": rng.random(n)})
            f = t(lambda: pd.factorize(keys)) / n
            gb = t(lambda: df.groupby("k")["v"].sum()) / n
            ac = t(lambda: s.astype("category")) / n
            print(f"{kind:7} {g:>9,} {n:>9,} {f * 1e9:12.1f} {gb * 1e9:16.1f} {ac * 1e9:18.1f}")
    print("\nobject take (concat of differing categoricals): ns per element vs distinct objects k")
    n = 2_000_000
    for k in (1_000, 10_000, 100_000, 1_000_000, 3_000_000):
        objs = np.array([f"{x:013d}" for x in rng.integers(0, 10**13, k)], dtype=object)
        idx = rng.integers(0, k, n)
        print(f"k={k:>9,}: {t(lambda: objs.take(idx)) / n * 1e9:.1f} ns/element")


if __name__ == "__main__":
    main()
