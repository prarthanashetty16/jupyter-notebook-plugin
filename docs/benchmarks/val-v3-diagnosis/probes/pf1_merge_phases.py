"""(4b.3) merge, non-unique right keys, small output: which phase carries the missing bytes?

Same left frame (n unique keys), right frames that differ only in fan-out / overlap; measures
`_factorize_keys` alone, `get_join_indexers`, and the full merge (project instrument, from disk).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P  # noqa: E402
from probe_lib import MIB, measure_call  # noqa: E402
from pc2_merge_nonunique import save  # noqa: E402

from benchmarks.datasets import make_join_pair  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402

CODES = {
    "factorize": '__import__("pandas.core.reshape.merge", fromlist=["x"])._factorize_keys(df["k"]._values, right["k"]._values, sort=False)',
    "indexers": '__import__("pandas.core.reshape.merge", fromlist=["x"]).get_join_indexers([df["k"]._values],[right["k"]._values], how="inner")',
    "full": 'df.merge(right, on="k", how="inner")',
}

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    grid = [(0.25, 2.0, 0.1), (0.25, 6.0, 0.1), (0.25, 10.0, 0.1), (0.2, 10.0, 0.15), (0.9, 6.0, 0.1), (1.0, 1.0, 0.1)]
    for overlap, fanout, ratio in grid:
        left, right = make_join_pair(BASE.with_(n_rows=n, seed=7), int(n * ratio), overlap=overlap, fanout=fanout, seed=11)
        tag = f"pf{n}_{overlap}_{fanout}_{ratio}"
        dl, dr = save(left, tag + "L"), save(right, tag + "R")
        out = {}
        for name, code in CODES.items():
            m = measure_call(P.run, setup=P.setup, setup_args=({"df": dl, "right": dr}, code), summarize=P.summarize, repeats=2)
            out[name] = None if m.delta_bytes is None else m.delta_bytes / MIB
        print(
            f"n={n:,} nr={len(right):>8,} overlap={overlap:<4} fanout={fanout:<5} right distinct={right['k'].nunique():>7,}: "
            + "  ".join(f"{k}={v:6.1f}" for k, v in out.items()) + " MiB",
            flush=True,
        )
