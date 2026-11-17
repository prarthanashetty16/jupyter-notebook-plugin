"""(c) merge, non-unique right keys: a probe grid to derive the indexer-phase terms.

One full ``df.merge(right, on="k")`` per design point (project instrument). Writes
``pc3_merge_design.csv`` next to this script: n_left, n_right, fanout, overlap, true output rows,
right/union distinct keys, measured MiB. The analysis (least squares on 8-byte-array components) is
in pc3_fit.py.
"""

import csv
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P  # noqa: E402
from pc2_merge_nonunique import save  # noqa: E402
from probe_lib import MIB, measure_call  # noqa: E402

from benchmarks.datasets import make_join_pair  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402

OUT = pathlib.Path(__file__).with_name("pc3_merge_design.csv")

if __name__ == "__main__":
    rows = []
    for nl in (500_000, 1_000_000, 2_000_000):
        for ratio in (0.1, 0.35, 1.0):
            for fanout, overlap in ((2.0, 0.25), (6.0, 0.25), (6.0, 0.9), (1.0, 0.5)):
                nr = int(nl * ratio)
                left, right = make_join_pair(
                    BASE.with_(n_rows=nl, seed=7), nr, overlap=overlap, fanout=fanout, seed=11
                )
                tag = f"d{nl}_{ratio}_{fanout}_{overlap}"
                dl, dr = save(left, tag + "L"), save(right, tag + "R")
                m_rows = len(left.merge(right, on="k"))
                r_distinct = int(right["k"].nunique())
                left_distinct = int(left["k"].nunique())
                union = left_distinct + int(round(r_distinct * (1 - overlap)))
                m = measure_call(
                    P.run,
                    setup=P.setup,
                    setup_args=({"df": dl, "right": dr}, 'df.merge(right, on="k")'),
                    summarize=P.summarize,
                    repeats=2,
                )
                mib = None if m.delta_bytes is None else m.delta_bytes / MIB
                rows.append(
                    dict(
                        nl=nl,
                        nr=len(right),
                        fanout=fanout,
                        overlap=overlap,
                        m=m_rows,
                        r_distinct=r_distinct,
                        left_distinct=left_distinct,
                        union=union,
                        row_l=left.memory_usage(index=False, deep=False).sum() / nl,
                        row_r=right.memory_usage(index=False, deep=False).sum() / len(right),
                        mib=mib,
                    )
                )
                print(rows[-1], flush=True)
                with OUT.open("w", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                    w.writeheader()
                    w.writerows(rows)
