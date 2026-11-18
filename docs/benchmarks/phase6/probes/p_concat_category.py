"""Probe: why is concat of category-heavy frames ~5-10x slower than a copy (and RAM 23% low)?

HYPOTHESIS. ``pd.concat`` of categorical columns whose categories DIFFER cannot concatenate the
codes: pandas falls back to materialising the values (``union_categoricals`` is not used by
``concat``), so the result column is object / str and the cost is one Python-object take per row
per column (pointer write + refcount increment on a random string object), not a memcpy of 1-2
byte codes. With IDENTICAL categories the codes are concatenated and the column stays category.

Synthetic frames (not benchmark data): two frames of n/2 rows with 3 category columns of ``card``
categories (13-char strings), categories identical or drawn independently. Reports result dtype,
wall time (median of 3, in-process) and the tracemalloc peak of the concat call, at 1M / 3M / 6M rows.

    python docs/benchmarks/phase6/probes/p_concat_category.py
"""

from __future__ import annotations

import gc
import statistics
import time
import tracemalloc

import numpy as np
import pandas as pd

MIB = 2**20


def vocab(rng: np.random.Generator, card: int) -> pd.Index:
    return pd.Index([f"{x:013d}" for x in rng.integers(0, 10**13, card)]).unique()


def frame(rng: np.random.Generator, n: int, cats: list[pd.Index]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            f"c{j}": pd.Categorical.from_codes(rng.integers(0, len(c), n), categories=c)
            for j, c in enumerate(cats)
        }
    )


def run(n: int, card: int, same: bool) -> dict:
    rng = np.random.default_rng(1)
    c1 = [vocab(rng, card) for _ in range(3)]
    c2 = c1 if same else [vocab(rng, card) for _ in range(3)]
    a, b = frame(rng, n // 2, c1), frame(rng, n // 2, c2)
    times = []
    for _ in range(3):
        gc.collect()
        t0 = time.perf_counter()
        out = pd.concat([a, b], ignore_index=True)
        times.append(time.perf_counter() - t0)
        del out
    gc.collect()
    tracemalloc.start()
    out = pd.concat([a, b], ignore_index=True)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    moved = sum(int(a[c].cat.codes.nbytes + b[c].cat.codes.nbytes) for c in a.columns)
    return {
        "n": n,
        "card": card,
        "same_categories": same,
        "result_dtype": str(out["c0"].dtype),
        "time_s": statistics.median(times),
        "s_per_row_col": statistics.median(times) / (n * 3),
        "peak_MiB": peak / MIB,
        "peak_B_per_row_col": peak / (n * 3),
        "codes_moved_MiB": moved / MIB,
    }


def main() -> None:
    print(f"pandas {pd.__version__}, numpy {np.__version__}")
    for n in (1_000_000, 3_000_000, 6_000_000):
        for card in (50, 5_000):
            for same in (True, False):
                r = run(n, card, same)
                print(
                    f"n={r['n']:>9,} card={r['card']:>5} same={r['same_categories']!s:5} "
                    f"dtype={r['result_dtype']:10} t={r['time_s']:.3f}s "
                    f"({r['s_per_row_col'] * 1e9:.1f} ns/row/col) "
                    f"peak={r['peak_MiB']:.0f} MiB ({r['peak_B_per_row_col']:.1f} B/row/col) "
                    f"codes={r['codes_moved_MiB']:.0f} MiB"
                )


if __name__ == "__main__":
    main()
