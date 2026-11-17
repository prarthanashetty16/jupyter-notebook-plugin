import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from p_as import meas

if __name__ == "__main__":
    N = 2_000_000
    rng = np.random.default_rng(4)
    for U in (100, 5_000, 100_000, 1_000_000, 2_000_000):
        vocab = np.array([f"value_{i:09d}" for i in range(U)], dtype=object)
        codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)])) if U < N else rng.permutation(N)
        df = pd.DataFrame({"c": pd.Series(vocab[codes], dtype=object)})
        m = meas(df, f"cat_s{U}", 'df["c"].astype("category")')
        iv = pd.DataFrame({"c": codes.astype(np.int64)})
        mi = meas(iv, f"cat_i{U}", 'df["c"].astype("category")')
        cat_bytes = 4 if U >= 32768 else 2 if U >= 128 else 1
        f = lambda m: None if m.delta_bytes is None else round(m.delta_bytes / N, 1)
        print(f"U={U:>8} (U/n={U/N:.4f})  text->category: peak={f(m)} B/row (bound {m.bound_bytes/MIB:.0f} MiB)   int->category: peak={f(mi)} B/row   final codes={cat_bytes} B/row + cats", flush=True)
