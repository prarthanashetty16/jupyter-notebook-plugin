# RAM accuracy per operation and tier, all dev points (stored actuals; v2 stored vs v3 final predictions)

DEV only. bias = median expected / actual; err_med = median |expected - actual| / actual; above_high = count.

| op | tier | n_v2 | bias_v2 | err_med_v2 | above_high_v2 | n_v3 | bias_v3 | err_med_v3 | above_high_v3 |
|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 49 | 1.00 | 0.17 | 0 | 49 | 1.00 | 0.17 | 0 |
| astype | 1 | 49 | 1.00 | 0.01 | 0 | 49 | 1.00 | 0.01 | 0 |
| drop_duplicates | 0 | 41 | 0.96 | 0.17 | 0 | 41 | 0.96 | 0.17 | 0 |
| drop_duplicates | 1 | 41 | 1.05 | 0.13 | 0 | 41 | 1.05 | 0.12 | 0 |
| groupby | 0 | 41 | 1.57 | 0.57 | 0 | 41 | 1.57 | 0.57 | 0 |
| groupby | 1 | 41 | 1.01 | 0.01 | 0 | 41 | 1.01 | 0.01 | 0 |
| merge | 0 | 37 | 1.55 | 0.56 | 0 | 37 | 1.55 | 0.56 | 0 |
| merge | 1 | 37 | 1.06 | 0.08 | 0 | 37 | 1.06 | 0.08 | 0 |
| numpy.sort | 0 | 12 | 1.00 | 0.00 | 0 | 12 | 1.00 | 0.00 | 0 |
| numpy.sort | 1 | 12 | 1.00 | 0.00 | 0 | 12 | 1.00 | 0.00 | 0 |
| operator.matmul | 0 | 24 | 0.97 | 0.03 | 0 | 24 | 0.97 | 0.03 | 0 |
| operator.matmul | 1 | 24 | 0.97 | 0.03 | 0 | 24 | 0.97 | 0.03 | 0 |
| pandas.concat | 0 | 27 | 0.92 | 0.08 | 0 | 27 | 0.92 | 0.08 | 0 |
| pandas.concat | 1 | 27 | 1.05 | 0.05 | 0 | 27 | 1.05 | 0.06 | 0 |
| pandas.read_csv | 0 | 24 | 1.20 | 0.39 | 0 | 24 | 1.20 | 0.39 | 0 |
| pandas.read_csv | 1 | 24 | 1.22 | 0.22 | 0 | 24 | 1.09 | 0.13 | 0 |
| sort_values | 0 | 29 | 1.01 | 0.01 | 0 | 29 | 1.01 | 0.01 | 0 |
| sort_values | 1 | 29 | 1.01 | 0.01 | 0 | 29 | 1.01 | 0.01 | 0 |

