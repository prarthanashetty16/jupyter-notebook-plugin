"""(b) Same U and n, two generators: the Phase-4a probe frame (shared vocab objects, random order)
vs the benchmark generator (make_frame). Isolates what in the data moves the category peak."""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
import probe_lib as P
from nexus.measure import measure_call
from benchmarks.datasets import make_frame
from benchmarks.suite import BASE
from benchmarks import store


def save_df(df, tag):
    path = CACHE / tag
    if not (path / "meta.json").exists():
        store.save(df, path)
    return str(path)


def meas(df, tag, code):
    d = save_df(df, tag)
    m = measure_call(P.run, setup=P.setup, setup_args=({"df": d}, code), repeats=2)
    return None if m.delta_bytes is None else m.delta_bytes / MIB


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    rng = np.random.default_rng(4)
    for U in (100, 5_000, 12_000, 40_000, 100_000):
        vocab = np.array([f"value_{i:09d}" for i in range(U)], dtype=object)
        codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, N - U)]))
        a = pd.DataFrame({"s0": pd.Series(vocab[codes], dtype=object)})
        pa = meas(a, f"g_vocab_{N}_{U}", 'df["s0"].astype("category")')
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
        pb = meas(b, f"g_make_{N}_{U}", 'df["s0"].astype("category")')
        same = (b["s0"].map(id).nunique(), b["s0"].nunique(), b["s0"].str.len().mean())
        print(
            f"n={N:,} U={U:>7}: vocab-probe={pa} MiB   make_frame={pb} MiB   (make_frame: distinct objects, distinct values, mean len)={same}",
            flush=True,
        )
