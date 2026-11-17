"""(d) Evaluate each term of the drop_duplicates formula at the TRUE statistics of the null-heavy frame
and compare with the probe measurement (pd1): which phase is under-predicted, and by how much?"""

import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from benchmarks.datasets import make_frame
from benchmarks.suite import BASE
from nexus.models._util import khash_presized_bytes, group_ids_overflow

MIB = 2**20


def terms(df, cols, null_cols):
    n, k = len(df), len(cols)
    moved = (
        float(df[cols].memory_usage(index=False, deep=False).sum())
        if False
        else float(df.memory_usage(index=False, deep=False).sum())
    )
    per_key = [df[c].nunique(dropna=False) for c in cols]
    rows = len(df.drop_duplicates(subset=cols))
    table = khash_presized_bytes(max(per_key), n)
    ids_table = khash_presized_bytes(rows, n, key_only=True)
    factorize = 8 * n * (k - 1) + 16 * n + table + 8 * max(per_key)
    ids = 8 * n * k + 16 * n + ids_table + n + 8 * n * null_cols
    compress = 0.0
    shape = sum(np.log2(d + 1) for d in per_key)
    if shape >= 63:
        compress = 8 * n * k + 24 * n + khash_presized_bytes(rows, n) + 8 * n * null_cols
    take = 2 * n + 8 * rows + moved * rows / n + 8 * rows
    return dict(
        factorize=factorize / MIB,
        ids=ids / MIB,
        compress=compress / MIB,
        take=take / MIB,
        distinct_rows=rows,
        per_key=per_key,
        log2_shape=round(float(shape), 1),
        moved_B_row=moved / n,
    )


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    cfg = BASE.with_(
        n_rows=n, dup_rate=0.15, cardinality=0.04, null_rate=0.35, str_len=18, seed=301
    )
    df = make_frame(cfg)
    cols = list(df.columns)
    nn = sum(int(df[c].isna().any()) for c in cols)
    t = terms(df, cols, nn)
    peak = max(t["factorize"], t["ids"], t["compress"], t["take"])
    print(
        f"n={n:,}: terms (MiB) { ({k: round(v, 1) for k, v in t.items() if k in ('factorize', 'ids', 'compress', 'take')}) }  -> formula peak {peak:.1f} MiB ({peak * MIB / n:.1f} B/row)"
    )
    print(
        "   per-key distinct:",
        t["per_key"],
        "distinct rows:",
        t["distinct_rows"],
        "log2 shape:",
        t["log2_shape"],
        "null cols:",
        nn,
        " moved B/row",
        t["moved_B_row"],
    )
