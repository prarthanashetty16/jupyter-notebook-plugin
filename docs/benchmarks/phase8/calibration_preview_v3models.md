# v4 item C: upper-bound calibration, DEV preview

Tree `f2e19cc+992d4e1cc143`. Split conformal, alpha = 0.02, own factor for families with >= 30 configurations, pooled otherwise. **Preview on the current models: the frozen artifact is computed once, on the final v4 models (pre-registration, Order 5).**

## Factors

| family | configurations | q | at sample max |
|---|---|---|---|
| (pooled) | 213 | 1.191 | False |
| read_csv | 54 | 1.175 | False |
| sort_values | 37 | 1.197 | True |

Configurations per family: read_csv 54, sort_values 37, merge 25, astype 24, concat 21, groupby 18, drop_duplicates 16, np_sort 8, matmul 6, fillna 3, copy 1

## Dev results (v3 = model high; calibrated in sample; LOCO = factor refitted without the configuration)

| source | high | points | configs | above high (points) | above high (configs) | median error | coverage | high/expected median | p90 | W(a) median high_cal/high_v3 |
|---|---|---|---|---|---|---|---|---|---|---|
| all | v3 | 472 | 213 | 4 (0.8%) | 2 (0.9%) | 2.1% | 93.4% | 2.45 | 7.25 | 1 |
| all | calibrated | 472 | 213 | 0 (0.0%) | 0 (0.0%) | 2.1% | 94.3% | 2.45 | 7.25 | 1.000 |
| all | LOCO | 472 | 213 | 0 (0.0%) | 0 (0.0%) | 2.1% | 94.3% | 2.45 | 7.25 | 1.000 |
| single-op | v3 | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.74 | 5.67 | 1 |
| single-op | calibrated | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.74 | 5.67 | 1.000 |
| single-op | LOCO | 284 | 120 | 0 (0.0%) | 0 (0.0%) | 2.5% | 98.6% | 1.74 | 5.67 | 1.000 |
| multicell v1 | v3 | 58 | 29 | 0 (0.0%) | 0 (0.0%) | 1.1% | 91.4% | 4.34 | 6.72 | 1 |
| multicell v1 | calibrated | 58 | 29 | 0 (0.0%) | 0 (0.0%) | 1.1% | 91.4% | 4.34 | 6.72 | 1.000 |
| multicell v1 | LOCO | 58 | 29 | 0 (0.0%) | 0 (0.0%) | 1.1% | 91.4% | 4.34 | 6.72 | 1.000 |
| multicell v2 | v3 | 34 | 17 | 0 (0.0%) | 0 (0.0%) | 21.0% | 85.3% | 7.05 | 19.26 | 1 |
| multicell v2 | calibrated | 34 | 17 | 0 (0.0%) | 0 (0.0%) | 21.0% | 85.3% | 7.05 | 19.26 | 1.000 |
| multicell v2 | LOCO | 34 | 17 | 0 (0.0%) | 0 (0.0%) | 21.0% | 85.3% | 7.05 | 19.26 | 1.000 |
| multicell v3 | v3 | 92 | 46 | 4 (4.3%) | 2 (4.3%) | 1.3% | 81.5% | 3.99 | 12.05 | 1 |
| multicell v3 | calibrated | 92 | 46 | 0 (0.0%) | 0 (0.0%) | 1.3% | 85.9% | 3.99 | 12.05 | 1.000 |
| multicell v3 | LOCO | 92 | 46 | 0 (0.0%) | 0 (0.0%) | 1.3% | 85.9% | 3.99 | 12.05 | 1.000 |
| real notebooks (8a) | v3 | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1 |
| real notebooks (8a) | calibrated | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1.000 |
| real notebooks (8a) | LOCO | 4 | 1 | 0 (0.0%) | 0 (0.0%) | 13.0% | 100.0% | 3.20 | 3.24 | 1.000 |

## Pre-registered dev criteria

* LOCO <= 2% above high per point and per configuration, pooled and per family with >= 30 configurations: **MET** (pooled 0.00% of points, 0.00% of configurations; read_csv 0.00% / 0.00%; sort_values 0.00% / 0.00%).
* W(a) median high_cal / high_v3 <= 1.30: 1.000 (**MET**).
* W(b) median high / expected <= 2.0: 2.45; p90 <= 4.0: 7.25 (**FAILED**).
