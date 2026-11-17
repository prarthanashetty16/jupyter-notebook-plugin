# Tier 0 vs Tier 1 (dev)

Group: **dev**. Tier 0 = first-tier models of Phase 4a; Tier 1 = the same models with data statistics where the sample is large enough, else Tier 0 (counted as not used). bias = median expected/actual (>1 over-predicts). `above_high` = actuals beyond the range's upper end (**under-prediction**, dangerous); `below_low` = beyond the lower end (over-prediction). `under_fold`/`over_fold` = median factor by which `expected` is too low / too high on the points where it is.

## RAM: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 16 | 1.00 | 12% | 50% | 100% | 1.10 | 50% | 1.14 | 50% | 1.11 | 0% | 0% |
| astype | 1 | 16 | 1.00 | 1% | 34% | 94% | 0.79 | 88% | 1.00 | 12% | 1.11 | 6% | 0% |
| drop_duplicates | 0 | 17 | 1.08 | 17% | 35% | 100% | 1.01 | 29% | 1.42 | 71% | 1.14 | 0% | 0% |
| drop_duplicates | 1 | 17 | 1.09 | 11% | 19% | 100% | 0.73 | 29% | 1.10 | 71% | 1.12 | 0% | 0% |
| groupby | 0 | 10 | 1.49 | 49% | 135% | 100% | 1.71 | 20% | 1.37 | 80% | 1.58 | 0% | 0% |
| groupby | 1 | 10 | 0.89 | 14% | 32% | 90% | 0.84 | 60% | 1.22 | 40% | 1.05 | 10% | 0% |
| merge | 0 | 14 | 1.79 | 79% | 200% | 93% | 3.67 | 14% | 1.33 | 86% | 1.92 | 0% | 7% |
| merge | 1 | 14 | 1.04 | 6% | 10% | 93% | 0.56 | 21% | 1.07 | 79% | 1.05 | 0% | 7% |
| numpy.sort | 0 | 7 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| numpy.sort | 1 | 7 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| operator.matmul | 0 | 9 | 0.98 | 2% | 6% | 100% | 1.18 | 100% | 1.02 | 0% | – | 0% | 0% |
| operator.matmul | 1 | 9 | 0.98 | 2% | 6% | 100% | 1.18 | 100% | 1.02 | 0% | – | 0% | 0% |
| pandas.concat | 0 | 12 | 0.93 | 7% | 8% | 100% | 1.00 | 100% | 1.07 | 0% | – | 0% | 0% |
| pandas.concat | 1 | 12 | 0.93 | 7% | 8% | 100% | 1.00 | 100% | 1.07 | 0% | – | 0% | 0% |
| pandas.read_csv | 0 | 10 | 1.57 | 57% | 116% | 100% | 2.65 | 0% | – | 100% | 1.57 | 0% | 0% |
| pandas.read_csv | 1 | 10 | 1.22 | 22% | 26% | 100% | 0.59 | 0% | – | 100% | 1.22 | 0% | 0% |
| sort_values | 0 | 14 | 1.01 | 1% | 1% | 100% | 0.45 | 0% | – | 100% | 1.01 | 0% | 0% |
| sort_values | 1 | 14 | 1.01 | 1% | 1% | 100% | 0.45 | 0% | – | 100% | 1.01 | 0% | 0% |
| ALL | 0 | 109 | 1.01 | 8% | 93% | 99% | 1.48 | 41% | 1.05 | 59% | 1.14 | 0% | 1% |
| ALL | 1 | 109 | 1.00 | 6% | 22% | 97% | 0.72 | 51% | 1.06 | 49% | 1.07 | 2% | 1% |


## RAM: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 16 | 81% | 75% | 6% | 1.10 | 0.79 |
| drop_duplicates | 17 | 100% | 94% | 0% | 1.01 | 0.73 |
| groupby | 10 | 100% | 100% | 0% | 1.71 | 0.84 |
| merge | 14 | 100% | 100% | 0% | 3.67 | 0.56 |
| numpy.sort | 7 | 0% | 0% | 0% | 0.40 | 0.40 |
| operator.matmul | 9 | 0% | 0% | 0% | 1.18 | 1.18 |
| pandas.concat | 12 | 0% | 0% | 0% | 1.00 | 1.00 |
| pandas.read_csv | 10 | 100% | 100% | 0% | 2.65 | 0.59 |
| sort_values | 14 | 0% | 0% | 0% | 0.45 | 0.45 |
| ALL | 109 | 59% | 57% | 1% | 1.48 | 0.72 |


## RAM: cases where Tier 1 did worse (9 points)

| op | case | size | t1_used | actual | fold_t0 | fold_t1 | lost_coverage | dangerous |
|---|---|---|---|---|---|---|---|---|
| astype | astype/str_to_category_highcard | 3000000 | True | 132915200 | 1.01 | 1.21 | False | False |
| astype | astype/str_to_category_zipf | 1000000 | True | 63172608 | 0.71 | 0.41 | True | True |
| astype | astype/str_to_category_zipf | 3000000 | True | 121806848 | 1.10 | 0.63 | False | False |
| drop_duplicates | drop_duplicates/numeric_dup50 | 10000000 | True | 1043468288 | 1.08 | 1.16 | False | False |
| groupby | groupby/str_highcard_sum_f0 | 3000000 | True | 132907008 | 1.04 | 1.21 | False | False |
| groupby | groupby/two_keys_mean_realistic | 1000000 | True | 82481152 | 0.96 | 0.61 | True | True |
| pandas.read_csv | read_csv/mixed | 1000000 | True | 467279872 | 1.11 | 1.21 | False | False |
| pandas.read_csv | read_csv/mixed | 3000000 | True | 1436184576 | 1.10 | 1.20 | False | False |
| pandas.read_csv | read_csv/strings | 3000000 | True | 1392066560 | 1.03 | 1.22 | False | False |


## Time: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 11 | 1.42 | 48% | 213% | 100% | 3.75 | 45% | 1.43 | 55% | 2.92 | 0% | 0% |
| astype | 1 | 11 | 1.42 | 48% | 213% | 100% | 3.75 | 45% | 1.43 | 55% | 2.92 | 0% | 0% |
| drop_duplicates | 0 | 17 | 0.88 | 46% | 97% | 88% | 3.75 | 53% | 1.84 | 47% | 1.32 | 6% | 6% |
| drop_duplicates | 1 | 17 | 0.90 | 45% | 109% | 88% | 3.75 | 53% | 1.81 | 47% | 1.39 | 6% | 6% |
| groupby | 0 | 8 | 2.80 | 180% | 505% | 62% | 3.75 | 25% | 2.30 | 75% | 4.21 | 0% | 38% |
| groupby | 1 | 8 | 2.69 | 169% | 384% | 75% | 3.75 | 25% | 2.63 | 75% | 3.47 | 0% | 25% |
| merge | 0 | 7 | 1.63 | 63% | 144% | 100% | 3.75 | 14% | 2.45 | 86% | 1.64 | 0% | 0% |
| merge | 1 | 7 | 1.63 | 63% | 144% | 100% | 3.75 | 14% | 2.45 | 86% | 1.64 | 0% | 0% |
| numpy.sort | 0 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| numpy.sort | 1 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| operator.matmul | 0 | 7 | 0.97 | 7% | 9% | 100% | 4.80 | 71% | 1.08 | 29% | 1.06 | 0% | 0% |
| operator.matmul | 1 | 7 | 0.97 | 7% | 9% | 100% | 4.80 | 71% | 1.08 | 29% | 1.06 | 0% | 0% |
| pandas.concat | 0 | 6 | 1.07 | 28% | 71% | 100% | 3.75 | 33% | 1.81 | 67% | 1.16 | 0% | 0% |
| pandas.concat | 1 | 6 | 1.07 | 28% | 71% | 100% | 3.75 | 33% | 1.81 | 67% | 1.16 | 0% | 0% |
| pandas.read_csv | 0 | 8 | 0.42 | 66% | 183% | 100% | 3.75 | 75% | 2.74 | 25% | 2.88 | 0% | 0% |
| pandas.read_csv | 1 | 8 | 0.42 | 66% | 183% | 100% | 3.75 | 75% | 2.74 | 25% | 2.88 | 0% | 0% |
| sort_values | 0 | 11 | 0.83 | 39% | 81% | 100% | 3.75 | 64% | 1.59 | 36% | 1.68 | 0% | 0% |
| sort_values | 1 | 11 | 0.83 | 39% | 81% | 100% | 3.75 | 64% | 1.59 | 36% | 1.68 | 0% | 0% |
| ALL | 0 | 78 | 1.05 | 48% | 202% | 94% | 3.85 | 47% | 1.66 | 53% | 1.63 | 1% | 5% |
| ALL | 1 | 78 | 1.06 | 48% | 202% | 95% | 3.85 | 47% | 1.79 | 53% | 1.65 | 1% | 4% |


## Time: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 11 | 100% | 0% | 0% | 3.75 | 3.75 |
| drop_duplicates | 17 | 100% | 0% | 0% | 3.75 | 3.75 |
| groupby | 8 | 100% | 0% | 0% | 3.75 | 3.75 |
| merge | 7 | 100% | 0% | 0% | 3.75 | 3.75 |
| numpy.sort | 3 | 0% | 0% | 0% | 3.90 | 3.90 |
| operator.matmul | 7 | 0% | 0% | 0% | 4.80 | 4.80 |
| pandas.concat | 6 | 0% | 0% | 0% | 3.75 | 3.75 |
| pandas.read_csv | 8 | 100% | 0% | 0% | 3.75 | 3.75 |
| sort_values | 11 | 0% | 0% | 0% | 3.75 | 3.75 |
| ALL | 78 | 65% | 0% | 0% | 3.85 | 3.85 |


## Time: cases where Tier 1 did worse (0 points)

none

## Analysis overhead (warm, per cell)

| op | tier | warm_med_ms | warm_p90_ms | warm_max_ms | cold_med_ms | over_250ms |
|---|---|---|---|---|---|---|
| astype | 0 | 4.30 | 6.59 | 16.89 | 5.29 | 0% |
| astype | 1 | 23.64 | 45.76 | 64.28 | 24.47 | 0% |
| drop_duplicates | 0 | 3.93 | 8.29 | 13.82 | 4.32 | 0% |
| drop_duplicates | 1 | 109 | 178 | 201 | 97.59 | 0% |
| groupby | 0 | 3.22 | 5.79 | 6.87 | 4.31 | 0% |
| groupby | 1 | 31.33 | 68.04 | 83.30 | 28.00 | 0% |
| merge | 0 | 7.44 | 11.75 | 17.34 | 7.72 | 0% |
| merge | 1 | 97.89 | 129 | 137 | 109 | 0% |
| numpy.sort | 0 | 0.15 | 0.18 | 0.18 | 0.41 | 0% |
| numpy.sort | 1 | 0.13 | 0.15 | 0.16 | 0.40 | 0% |
| operator.matmul | 0 | 0.15 | 0.17 | 0.17 | 0.43 | 0% |
| operator.matmul | 1 | 0.17 | 0.24 | 0.27 | 0.43 | 0% |
| pandas.concat | 0 | 5.91 | 9.16 | 13.37 | 7.06 | 0% |
| pandas.concat | 1 | 5.42 | 11.23 | 16.43 | 6.81 | 0% |
| pandas.read_csv | 0 | 0.16 | 0.25 | 0.27 | 0.41 | 0% |
| pandas.read_csv | 1 | 22.19 | 26.63 | 29.67 | 31.43 | 0% |
| sort_values | 0 | 4.27 | 6.60 | 6.94 | 5.14 | 0% |
| sort_values | 1 | 4.29 | 6.59 | 6.87 | 5.58 | 0% |
| ALL | 0 | 3.98 | 8.10 | 17.34 | 4.65 | 0% |
| ALL | 1 | 21.79 | 109 | 201 | 23.15 | 0% |

