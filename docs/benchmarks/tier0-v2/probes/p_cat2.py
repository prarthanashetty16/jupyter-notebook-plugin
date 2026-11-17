import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from p_as import meas

if __name__ == "__main__":
    rng = np.random.default_rng(6)
    for N in (1_000_000, 4_000_000):
        for frac in (None, 0.1, 1.0):
            U = 100 if frac is None else int(frac * N)
            vocab = np.array([f"value_{i:09d}" for i in range(U)], dtype=object)
            codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)])) if U < N else rng.permutation(N)
            df = pd.DataFrame({"c": pd.Series(vocab[codes], dtype=object)})
            m = meas(df, f"cat2_s{N}_{U}", 'df["c"].astype("category")')
            mi = meas(pd.DataFrame({"c": codes.astype(np.int64)}), f"cat2_i{N}_{U}", 'df["c"].astype("category")')
            f = lambda m: None if m.delta_bytes is None else round(m.delta_bytes / N, 1)
            print(f"n={N:>8} U={U:>8} (U/n={U/N:.3f})  text: {f(m)} B/row ({(m.delta_bytes or 0)/MIB:.0f} MiB)   int: {f(mi)} B/row ({(mi.delta_bytes or 0)/MIB:.0f} MiB)", flush=True)
