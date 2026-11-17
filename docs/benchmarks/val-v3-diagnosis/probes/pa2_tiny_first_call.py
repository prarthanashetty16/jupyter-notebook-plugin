"""(a) First-call overhead: each operation on tiny inputs in a fresh spawned child.

The instrument reports a delta only when the call exceeds the peak reached while loading the inputs
(otherwise the run is censored with an upper bound = setup_peak - baseline). A fixed first-call cost
of tens of MiB would therefore show as a clearly positive delta even at n = 5k.
"""

import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
from benchmarks.suite import BASE

OPS = {
    "astype->category": ('df["s0"].astype("category")', dict(cardinality=12000)),
    "groupby(str).sum": ('df.groupby("s0")["f0"].sum()', dict(cardinality=0.04)),
    "groupby(2 keys)": ('df.groupby(["i0", "s0"])["f0"].sum()', dict(cardinality=800)),
    "drop_duplicates": (
        "df.drop_duplicates()",
        dict(cardinality=0.04, null_rate=0.35, dup_rate=0.15),
    ),
}

if __name__ == "__main__":
    for name, (code, kw) in OPS.items():
        for n in (5_000, 20_000, 50_000, 200_000):
            r = probe({"df": BASE.with_(n_rows=n, seed=317, **kw)}, code, repeats=3)
            print(
                f"{name:18s} n={n:>8,}: delta={r['ram_MiB']} MiB  (censored bound {r['bound_MiB']} MiB)  time={r['time_s']}s",
                flush=True,
            )
