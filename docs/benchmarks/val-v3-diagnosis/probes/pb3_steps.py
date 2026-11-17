"""(b) Which step of astype('category') differs between the vocab frame and make_frame data?"""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pb2_generators import *

STEPS = {
    "factorize(sort=False)": 'pd.factorize(df["s0"].to_numpy(), sort=False)',
    "factorize(sort=True)": 'pd.factorize(df["s0"].to_numpy(), sort=True)',
    "Categorical()": 'pd.Categorical(df["s0"])',
    "astype(category)": 'df["s0"].astype("category")',
}

if __name__ == "__main__":
    N, U = 2_000_000, 12_000
    rng = np.random.default_rng(4)
    vocab = np.array([f"value_{i:09d}" for i in range(U)], dtype=object)
    codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)]))
    a = pd.DataFrame({"s0": pd.Series(vocab[codes], dtype=object)})
    cfg = BASE.with_(
        n_rows=N,
        n_int=0,
        n_float=0,
        n_object=1,
        n_category=0,
        n_datetime=0,
        cardinality=U,
        seed=11,
        with_key=False,
    )
    b = make_frame(cfg)
    print("sample vocab:", list(a["s0"][:3]), " make_frame:", list(b["s0"][:3]))
    for name, code in STEPS.items():
        pa = meas(a, f"g_vocab_{N}_{U}", code)
        pb = meas(b, f"g_make_{N}_{U}", code)
        print(f"{name:24s} vocab={pa:6.1f} MiB   make_frame={pb:6.1f} MiB", flush=True)
