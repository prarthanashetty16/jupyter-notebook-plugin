"""(c) merge with non-unique right keys: which allocation produces the peak?

Measures ``get_join_indexers`` alone and the full merge (project instrument, inputs from disk) on
frames built with the benchmark's own join generator, for a grid of (overlap, fan-out, right rows),
and prints candidate components: a hash table over the UNION of left and right keys (the factorizer
of ``_factorize_keys`` is shared by both sides), the code arrays, and the group-sort arrays of the
sort-based join.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import probe_lib as P  # noqa: E402
from probe_lib import CACHE, MIB, measure_call  # noqa: E402

from benchmarks import store  # noqa: E402
from benchmarks.datasets import make_join_pair  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402
from nexus.models._util import khash_presized_bytes  # noqa: E402


def save(df, tag):
    path = CACHE / ("mn_" + tag)
    if not (path / "meta.json").exists():
        store.save(df, path)
    return str(path)


def measure(dl, dr, how):
    out = {}
    for lab, code in (
        (
            "indexers",
            'get_join_indexers([df["k"]._values],[right["k"]._values], how="%s")' % how,
        ),
        ("full", 'df.merge(right, on="k", how="%s")' % how),
    ):
        setup_code = code.replace(
            "get_join_indexers",
            '__import__("pandas.core.reshape.merge", fromlist=["x"]).get_join_indexers',
        )
        m = measure_call(
            P.run,
            setup=P.setup,
            setup_args=({"df": dl, "right": dr}, setup_code),
            summarize=P.summarize,
            repeats=2,
        )
        out[lab] = None if m.delta_bytes is None else m.delta_bytes / MIB
    return out


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    only = sys.argv[2:]  # optional: 'overlap,fanout,ratio' rows
    grid = [  # (overlap, fanout, right_ratio)
        (1.0, 1.0, 0.5),  # unique right keys (4a-verified path)
        (0.25, 6.0, 0.35),  # the val-v3 failure
        (0.9, 6.0, 0.35),
        (0.25, 2.0, 0.35),
        (0.25, 6.0, 0.1),
        (0.05, 8.0, 0.8),
        (0.5, 3.0, 1.5),
    ]
    if only:
        grid = [tuple(float(x) for x in a.split(",")) for a in only]
    for overlap, fanout, ratio in grid:
        left_cfg = BASE.with_(n_rows=N, seed=7)
        left, right = make_join_pair(
            left_cfg, int(N * ratio), overlap=overlap, fanout=fanout, seed=11
        )
        dl, dr = (
            save(left, f"{N}_{overlap}_{fanout}_{ratio}L"),
            save(right, f"{N}_{overlap}_{fanout}_{ratio}R"),
        )
        m_rows = len(left.merge(right, on="k"))
        r_distinct = right["k"].nunique()
        union = len(set(left["k"].unique()) | set(right["k"].unique())) if N <= 1_000_000 else None
        out = measure(dl, dr, "inner")
        nl, nr = len(left), len(right)
        union = union or (nl + r_distinct * (1 - overlap))
        table_union = khash_presized_bytes(union, max(nl, nr)) / MIB
        table_right = khash_presized_bytes(r_distinct, max(nl, nr)) / MIB
        print(
            f"overlap={overlap:<4} fanout={fanout:<4} nr={nr:>9,} M={m_rows:>9,} right distinct={r_distinct:>8,}  "
            f"indexers={out['indexers']:6.1f} full={out['full']:6.1f} MiB | table(union)={table_union:5.1f} "
            f"table(right only)={table_right:5.1f} codes 8(nl+nr)={8 * (nl + nr) / MIB:5.1f} 16M={16 * m_rows / MIB:5.1f}",
            flush=True,
        )
        from nexus.models.merge import MergeModel

        f = {
            "n_left": nl,
            "n_right": nr,
            "bytes_left": left.memory_usage(index=False, deep=False).sum(),
            "bytes_right": right.memory_usage(index=False, deep=False).sum(),
            "how": "inner",
        }
        f["moved_left"], f["moved_right"] = f["bytes_left"], f["bytes_right"]
        model = (
            MergeModel.ram_at(
                f,
                m_rows,
                left_elided=False,
                right_distinct=r_distinct,
                right_unique=r_distinct == nr,
            )
            / MIB
        )
        print(
            f"{'':10s} current formula at TRUE M: {model:6.1f} MiB   measured/formula = {out['full'] / model:4.2f}",
            flush=True,
        )
