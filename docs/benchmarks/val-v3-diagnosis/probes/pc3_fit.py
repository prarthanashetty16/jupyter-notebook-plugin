"""(c) Fit the indexer-phase components of a merge with NON-unique right keys to the pc3 probe grid.

Regressors (bytes): the hash table over the union of left and right distinct keys
(2^ceil(log2(U/0.77)) buckets x 16.25 B, the factorizer is shared by both sides), 8 B x (nl + nr)
(code arrays), 8 B x (nl + nr) (group-sort sorters), 8 B x U (per-group counts), 16 B x M (indexers).
Least squares (clipped at 0); coefficients should come out as small multiples of the array widths.
"""

import math, pathlib
import numpy as np, pandas as pd

MIB = 2**20
d = pd.read_csv(pathlib.Path(__file__).with_name("pc3_merge_design.csv"))
d = d[d.fanout > 1.0].copy()  # non-unique right keys only (fan-out 1 is the unique / hash path)
b = 2 ** np.ceil(np.log2(np.maximum(d.union / 0.77, 4)))
X = pd.DataFrame(
    {
        "table_union": b * 16.25,
        "codes 8(nl+nr)": 8 * (d.nl + d.nr),
        "counts 8*union": 8 * d.union,
        "indexers 16M": 16 * d.m,
    }
)
y = d.mib * MIB
coef = np.clip(np.linalg.lstsq(X.to_numpy(), y.to_numpy(), rcond=None)[0], 0, None)
pred = X.to_numpy() @ coef
print("coefficients:", dict(zip(X.columns, np.round(coef, 2))))
print(
    f"fit: median |pred/meas - 1| = {np.median(np.abs(pred / y - 1)):.3f}, max = {np.max(np.abs(pred / y - 1)):.3f} over {len(d)} probes"
)
fixed = np.array(
    [1.0, 2.0, 1.0, 1.0]
)  # the structural hypothesis: table once, codes twice (8 B x2), counts once, indexers once
for name, c in (
    ("hypothesis (1, 2, 1, 1)", fixed),
    ("hypothesis (1, 1, 1, 1)", np.ones(4)),
    ("hypothesis (1, 2, 2, 1)", np.array([1, 2, 2, 1.0])),
):
    p = X.to_numpy() @ c
    print(
        f"{name}: median ratio meas/pred = {np.median(y / p):.3f}  range {np.min(y / p):.2f}..{np.max(y / p):.2f}"
    )
d["pred_fit_MiB"] = pred / MIB
print(
    d[["nl", "nr", "fanout", "overlap", "m", "union", "mib", "pred_fit_MiB"]]
    .round(1)
    .to_string(index=False)
)
