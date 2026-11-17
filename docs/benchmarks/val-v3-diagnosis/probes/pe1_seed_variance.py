"""(e) Estimator variance vs systematic error: Tier 1 distinct-count estimates over 10 sampling seeds
on the failing configurations (n = 1M versions), against the true distinct counts."""

import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import numpy as np, pandas as pd
from benchmarks.datasets import make_frame
from benchmarks.suite import BASE
from nexus import stats

CASES = {  # (frame kwargs, key columns)
    "astype card12000 (s0)": (dict(cardinality=12000, seed=317), ["s0"]),
    "groupby str_card0p04 (s0)": (dict(cardinality=0.04, seed=312), ["s0"]),
    "groupby two_keys_card800 (i0,s0)": (dict(cardinality=800, seed=313), ["i0", "s0"]),
    "groupby int_card20000 (i0)": (dict(cardinality=20000, seed=311), ["i0"]),
    "dd null_heavy rows": (
        dict(dup_rate=0.15, cardinality=0.04, null_rate=0.35, str_len=18, seed=301),
        None,
    ),
}

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    for name, (kw, cols) in CASES.items():
        df = make_frame(BASE.with_(n_rows=n, **kw))
        cols = cols or list(df.columns)
        if len(cols) == 1:
            true = df[cols[0]].nunique(dropna=False)
            est = [stats.distinct_count(df[cols[0]], seed=s) for s in range(10)]
        else:
            true = len(df.drop_duplicates(subset=cols))
            est = [stats.distinct_rows([df[c] for c in cols], seed=s) for s in range(10)]
        v = np.array([e.value for e in est])
        lo = np.array([e.low for e in est])
        hi = np.array([e.high for e in est])
        print(
            f"{name:36s} true={true:>9,}  estimate over 10 seeds: mean/true={v.mean() / true:5.3f} sd/true={v.std() / true:5.3f} "
            f"min..max/true={v.min() / true:5.3f}..{v.max() / true:5.3f}  interval contains truth in {int(((lo <= true) & (true <= hi)).sum())}/10 seeds"
        )
