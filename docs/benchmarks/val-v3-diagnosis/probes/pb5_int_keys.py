"""(b) int64 keys: dense 0..U-1 (like the Phase-4a probes) vs random 63-bit ids; and the benchmark generator."""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pb2_generators import *

if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    for U in (100, 5_000, 12_000, 40_000, 200_000):
        rng = np.random.default_rng(4)
        dense = np.arange(U)
        rand = rng.integers(0, 2**62, U)
        order = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)]))
        out = {}
        for tag, vocab in (("dense", dense), ("random", rand)):
            df = pd.DataFrame({"i0": vocab[order].astype(np.int64)})
            out[tag] = meas(df, f"i_{tag}_{N}_{U}", 'pd.factorize(df["i0"].to_numpy(), sort=False)')
        cfg = BASE.with_(
            n_rows=N,
            n_int=1,
            n_float=0,
            n_object=0,
            n_category=0,
            n_datetime=0,
            cardinality=U,
            seed=11,
            with_key=False,
        )
        g = make_frame(cfg)
        out["make_frame"] = meas(
            g, f"i_make_{N}_{U}", 'pd.factorize(df["i0"].to_numpy(), sort=False)'
        )
        print(
            f"n={N:,} U={U:>7}: "
            + "  ".join(f"{k}={v:6.1f}" for k, v in out.items())
            + f" MiB  (make_frame i0 range {g['i0'].min()}..{g['i0'].max()})",
            flush=True,
        )
