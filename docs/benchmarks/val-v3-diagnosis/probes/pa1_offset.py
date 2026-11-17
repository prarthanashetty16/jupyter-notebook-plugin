"""(a) Is the n=1M excess of astype/groupby a fixed offset? Same op on the val-v3 frame vs
single-column variants, and at several n (isolated probes, project instrument)."""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
from benchmarks.suite import BASE


def show(tag, r, n):
    print(
        f"{tag:46s} n={n:>9,} peak={r['ram_MiB']} MiB ({r['B_per_row']} B/row) bound={r['bound_MiB']} err={r['err']}",
        flush=True,
    )


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for n in (300_000, 1_000_000, 2_000_000):
        full = BASE.with_(n_rows=n, cardinality=12000, seed=317)
        one = BASE.with_(
            n_rows=n,
            n_int=0,
            n_float=0,
            n_object=1,
            n_category=0,
            n_datetime=0,
            cardinality=12000,
            seed=317,
            with_key=False,
        )
        for tag, cfg in (("val-v3 frame (8 cols + key)", full), ("only the s0 column", one)):
            r = probe({"df": cfg}, 'df["s0"].astype("category")', repeats=2)
            show("astype->category " + tag, r, n)
