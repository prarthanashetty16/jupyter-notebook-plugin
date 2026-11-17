"""(b) Numeric base per row of astype('category') vs pd.factorize, over U and n (random int64 keys)."""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pb2_generators import *

if __name__ == "__main__":
    for n in (600_000, 2_000_000):
        for U in (20, 100, 1000, 5000):
            rng = np.random.default_rng(5)
            vocab = rng.integers(0, 2**62, U)
            col = vocab[
                rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, n - U)]))
            ].astype(np.int64)
            df = pd.DataFrame({"c": col})
            a = meas(df, f"nb_{n}_{U}", 'df["c"].astype("category")')
            f = meas(df, f"nb_{n}_{U}", 'pd.factorize(df["c"].to_numpy(), sort=False)')
            print(
                f"n={n:>9,} U={U:>5}: astype(category) {a:6.1f} MiB ({a * 2**20 / n:5.1f} B/row)   pd.factorize {f:6.1f} MiB ({f * 2**20 / n:5.1f} B/row)",
                flush=True,
            )
