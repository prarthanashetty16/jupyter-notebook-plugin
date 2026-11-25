# v4 item C: final upper-bound calibration, DEV

Tree `content:e2333ee0a0bbe2df`. Split conformal, alpha = 0.02, own factor for families with >= 30 configurations, pooled otherwise. **Final v4 factors were computed once from this model tree, per pre-registration Order 5.**

## Factors

| family | configurations | q | at sample max |
|---|---|---|---|
| (pooled) | 239 | 1.184 | False |
| read_csv | 59 | 1.175 | False |
| sort_values | 37 | 1.197 | True |

Configurations per family: read_csv 59, sort_values 37, merge 25, astype 24, concat 21, groupby 18, drop_duplicates 16, copy 14, fillna 11, np_sort 8, matmul 6

## Dev results (v3 = model high; calibrated in sample; LOCO = factor refitted without the configuration)

| source | high | points | configs | above high (points) | above high (configs) | median error | coverage | high/expected median | p90 | W(a) median high_cal/high_v3 |
|---|---|---|---|---|---|---|---|---|---|---|
| all | v3 | 524 | 239 | 20 (3.8%) | 10 (4.2%) | 2.1% | 90.1% | 2.10 | 7.22 | 1 |
| all | calibrated | 524 | 239 | 0 (0.0%) | 0 (0.0%) | 2.1% | 93.9% | 2.10 | 7.22 | 1.000 |
| all | LOCO | 524 | 239 | 0 (0.0%) | 0 (0.0%) | 2.1% | 93.9% | 2.10 | 7.22 | 1.000 |
| single-op | v3 | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.71 | 5.67 | 1 |
| single-op | calibrated | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.71 | 5.67 | 1.000 |
| single-op | LOCO | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.71 | 5.67 | 1.000 |
| multicell v1 | v3 | 60 | 30 | 0 (0.0%) | 0 (0.0%) | 1.3% | 88.3% | 4.33 | 6.57 | 1 |
| multicell v1 | calibrated | 60 | 30 | 0 (0.0%) | 0 (0.0%) | 1.3% | 88.3% | 4.33 | 6.57 | 1.000 |
| multicell v1 | LOCO | 60 | 30 | 0 (0.0%) | 0 (0.0%) | 1.3% | 88.3% | 4.33 | 6.57 | 1.000 |
| multicell v2 | v3 | 44 | 22 | 0 (0.0%) | 0 (0.0%) | 14.2% | 84.1% | 5.71 | 17.81 | 1 |
| multicell v2 | calibrated | 44 | 22 | 0 (0.0%) | 0 (0.0%) | 14.2% | 84.1% | 5.71 | 17.81 | 1.000 |
| multicell v2 | LOCO | 44 | 22 | 0 (0.0%) | 0 (0.0%) | 14.2% | 84.1% | 5.71 | 17.81 | 1.000 |
| multicell v3 | v3 | 132 | 66 | 20 (15.2%) | 10 (15.2%) | 1.9% | 74.2% | 3.48 | 7.25 | 1 |
| multicell v3 | calibrated | 132 | 66 | 0 (0.0%) | 0 (0.0%) | 1.9% | 89.4% | 3.48 | 7.25 | 1.000 |
| multicell v3 | LOCO | 132 | 66 | 0 (0.0%) | 0 (0.0%) | 1.9% | 89.4% | 3.48 | 7.25 | 1.000 |
| real notebooks (8a) | v3 | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1 |
| real notebooks (8a) | calibrated | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1.000 |
| real notebooks (8a) | LOCO | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1.000 |

## Pre-registered dev criteria

* LOCO <= 2% above high per point and per configuration, pooled and per family with >= 30 configurations: **MET** (pooled 0.00% of points, 0.00% of configurations; read_csv 0.00% / 0.00%; sort_values 0.00% / 0.00%).
* W(a), DECIDING (amendment 1), points both v3 and v4 estimate (524; on the current models every point is shared): median (high_v4 / exp_v4) / (high_v3 / exp_v3) <= 1.30: 1.000 (**MET**).
* W(b), DECIDING only on points v3 does not estimate: 0 such points on the current models -> **INCONCLUSIVE** (it applies once v4 adds coverage).
* W(b) on all points, NOT deciding: median 2.10 (2.0), p90 7.22 (4.0). Known limitation: merge / read_csv width from policy B's Tier 0 high.
* Excluded from the residuals (pre-registered): multicell Tier 0 only 45 cells, multicell uncovered operation (Rule 1) 46 cells.
