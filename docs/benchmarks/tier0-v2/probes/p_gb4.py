"""groupby / category factorize peak at several n for the same distinct fractions (4b probe)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from p_gb import peak

if __name__ == "__main__":
    rng = np.random.default_rng(41)
    for N in (1_000_000, 3_000_000, 6_000_000):
        vocab = np.array([f"key_{i:09d}" for i in range(int(0.3 * N))], dtype=object)
        for frac in (0.001, 0.01, 0.1, 0.3):
            G = int(frac * N)
            codes = rng.permutation(np.concatenate([np.arange(G), rng.integers(0, G, N - G)]))
            df = pd.DataFrame(
                {"ik": codes.astype(np.int64), "sk": pd.Series(vocab[codes], dtype=object), "f0": rng.random(N)}
            )
            a = peak(df, f"n{N}_{G}", 'df.groupby("sk")["f0"].sum()')
            b = peak(df, f"n{N}_{G}", 'df.groupby("ik")["f0"].sum()')
            print(f"n={N:>8} G/n={frac:<6} str key {a / N:5.1f} B/row   int key {b / N:5.1f} B/row", flush=True)
