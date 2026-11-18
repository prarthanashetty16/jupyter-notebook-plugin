"""(4b.3) merge: peak of `libjoin.inner_join` alone, with the factorization done in setup.

Same left frame, right frames differing in fan-out / overlap. If the swing between configurations
(36-70 MiB for `get_join_indexers` at n = 1M, nr = 100k) lives in the join step, it shows here.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import probe_lib as P  # noqa: E402
from probe_lib import CACHE, MIB, measure_call  # noqa: E402

from benchmarks import store  # noqa: E402
from benchmarks.datasets import make_join_pair  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402


def setup(dl, dr):
    import pandas.core.reshape.merge as m

    left, right = store.load(pathlib.Path(dl)), store.load(pathlib.Path(dr))
    lk, rk, count = m._factorize_keys(left["k"]._values, right["k"]._values, sort=False, how="outer")
    return {"lk": lk, "rk": rk, "count": count}


def run(state):
    from pandas._libs import join as libjoin

    return libjoin.inner_join(state["lk"], state["rk"], state["count"], sort=False)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    for overlap, fanout, ratio in [(0.25, 2.0, 0.1), (0.25, 6.0, 0.1), (0.25, 10.0, 0.1), (0.2, 10.0, 0.15), (0.9, 6.0, 0.1)]:
        left, right = make_join_pair(BASE.with_(n_rows=n, seed=7), int(n * ratio), overlap=overlap, fanout=fanout, seed=11)
        tag = f"pf{n}_{overlap}_{fanout}_{ratio}"
        dl, dr = str(CACHE / ("mn_" + tag + "L")), str(CACHE / ("mn_" + tag + "R"))
        m = measure_call(run, setup=setup, setup_args=(dl, dr), repeats=2)
        mib = None if m.delta_bytes is None else m.delta_bytes / MIB
        bound = m.bound_bytes / MIB
        print(f"overlap={overlap:<4} fanout={fanout:<5} nr={len(right):>8,}: inner_join step = {mib} MiB (censored bound {bound:.1f})  M={len(left.merge(right, on='k')):,}", flush=True)
