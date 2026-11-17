"""(b) Does string CONTENT (not count, not length class) change factorize's resident peak?"""

import sys, pathlib, string, hashlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pb2_generators import *


def vocab_of(kind, U, rng):
    if kind == "seq15":
        return np.array([f"value_{i:09d}" for i in range(U)], dtype=object)
    if kind == "seq12":
        return np.array([f"{i:012d}" for i in range(U)], dtype=object)
    if kind == "rand12":
        a = rng.integers(0, 26, size=(U, 12))
        return np.array(
            ["".join(map(string.ascii_lowercase.__getitem__, r)) for r in a], dtype=object
        )
    if kind == "rand15":
        a = rng.integers(0, 26, size=(U, 15))
        return np.array(
            ["".join(map(string.ascii_lowercase.__getitem__, r)) for r in a], dtype=object
        )
    if kind == "hex12":
        return np.array(
            [hashlib.md5(str(i).encode()).hexdigest()[:12] for i in range(U)], dtype=object
        )


if __name__ == "__main__":
    N, U = 2_000_000, 12_000
    for kind in ("seq15", "seq12", "rand12", "rand15", "hex12"):
        rng = np.random.default_rng(4)
        vocab = vocab_of(kind, U, rng)
        codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)]))
        df = pd.DataFrame({"s0": pd.Series(vocab[codes], dtype=object)})
        p = meas(df, f"c_{kind}_{N}_{U}", 'pd.factorize(df["s0"].to_numpy(), sort=False)')
        print(
            f"{kind:8s} U={U} n={N:,}: factorize peak {p:6.1f} MiB  (len {len(vocab[0])}, first {vocab[0]!r})",
            flush=True,
        )
