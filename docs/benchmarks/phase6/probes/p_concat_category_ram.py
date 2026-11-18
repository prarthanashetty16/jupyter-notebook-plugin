"""Probe (RAM, >= 200 MiB, OS peak): concat of frames whose categorical columns have DIFFERENT categories.

HYPOTHESIS (from ``p_concat_category.py``, in-process tracemalloc): when categories differ, pandas
materialises each categorical column as Python-object pointers (``str`` dtype in pandas 3), so the
increment per such column is ~8 B/row of result pointers plus a transient (tracemalloc: 10.7 B/row
in total), instead of the 1-4 B/row of codes the ConcatModel charges (``moved_bytes``). With
identical categories the codes are concatenated (the model is right).

Measured with ``nexus.measure.measure_call`` (fresh spawned process, inputs loaded from disk,
median of 3, OS peak above baseline), frames like the benchmark's category-heavy concat
(int / float / datetime columns + 3 categoricals of 10% cardinality, 12-char strings), sizes such
that the peak is >= 200 MiB.

    python docs/benchmarks/phase6/probes/p_concat_category_ram.py
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20


def make(n: int, seed: int, vocab_seed: int, cat_cols: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    card = max(1, n // 10)
    cols = {
        "k": rng.integers(0, n, n),
        "i0": rng.integers(0, 10**6, n),
        "f0": rng.random(n),
        "d0": (1_500_000_000 + rng.integers(0, 10**8, n)).astype("datetime64[s]"),
    }
    vrng = np.random.default_rng(vocab_seed)
    for j in range(cat_cols):
        vocab = pd.Index([f"{x:012d}" for x in vrng.permutation(card * 50)[:card]])
        cols[f"c{j}"] = pd.Categorical.from_codes(rng.integers(0, card, n), categories=vocab)
    return pd.DataFrame(cols)


def setup(a: str, b: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    out = pd.read_pickle(a), pd.read_pickle(b)
    gc.collect()
    return out


def run(frames: tuple[pd.DataFrame, pd.DataFrame]) -> int:
    return len(pd.concat(list(frames), ignore_index=True))


def moved_bytes(df: pd.DataFrame) -> int:
    return int(df.memory_usage(index=False, deep=False).sum())


def main() -> None:
    print(f"pandas {pd.__version__}")
    print("rows/frame  same   peak MiB   moved MiB   peak-moved B/row/catcol   result dtype")
    with tempfile.TemporaryDirectory() as tmp:
        for n in (4_000_000, 6_000_000):
            for same in (True, False):
                a, b = make(n, 1, 7), make(n, 2, 7 if same else 8)
                pa, pb = str(Path(tmp) / "a.pkl"), str(Path(tmp) / "b.pkl")
                a.to_pickle(pa)
                b.to_pickle(pb)
                moved = moved_bytes(a) + moved_bytes(b)
                dtype = str(pd.concat([a.head(1000), b.head(1000)])["c0"].dtype)
                del a, b
                gc.collect()
                m = measure_call(run, setup=setup, setup_args=(pa, pb), repeats=3)
                peak = m.delta_bytes
                per = None if peak is None else (peak - moved) / (2 * n * 3)
                print(
                    f"{n:>10,}  {same!s:5}  {('censored' if peak is None else f'{peak / MIB:8.0f}'):>9}"
                    f"  {moved / MIB:9.0f}   {('-' if per is None else f'{per:6.2f}'):>10}"
                    f"                {dtype}"
                )


if __name__ == "__main__":
    main()
