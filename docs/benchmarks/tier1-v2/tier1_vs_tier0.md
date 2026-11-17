# Tier 0 vs Tier 1 (dev)

Group: **dev**. Tier 0 = first-tier models of Phase 4a; Tier 1 = the same models with data statistics where the sample is large enough, else Tier 0 (counted as not used). bias = median expected/actual (>1 over-predicts). `above_high` = actuals beyond the range's upper end (**under-prediction**, dangerous); `below_low` = beyond the lower end (over-prediction). `under_fold`/`over_fold` = median factor by which `expected` is too low / too high on the points where it is.

## RAM: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 28 | 1.00 | 12% | 59% | 93% | 1.01 | 57% | 1.12 | 43% | 1.46 | 0% | 7% |
| astype | 1 | 28 | 1.00 | 0% | 2% | 100% | 0.53 | 50% | 1.00 | 50% | 1.01 | 0% | 0% |
| drop_duplicates | 0 | 27 | 1.03 | 17% | 41% | 100% | 1.04 | 48% | 1.35 | 52% | 1.14 | 0% | 0% |
| drop_duplicates | 1 | 27 | 1.03 | 11% | 20% | 96% | 0.69 | 37% | 1.09 | 63% | 1.11 | 0% | 4% |
| groupby | 0 | 24 | 1.55 | 55% | 125% | 100% | 1.50 | 17% | 1.64 | 83% | 1.73 | 0% | 0% |
| groupby | 1 | 24 | 1.01 | 1% | 21% | 100% | 0.55 | 0% | – | 100% | 1.01 | 0% | 0% |
| merge | 0 | 24 | 1.59 | 59% | 135% | 92% | 3.65 | 25% | 1.33 | 75% | 1.84 | 0% | 8% |
| merge | 1 | 24 | 1.06 | 8% | 15% | 92% | 0.51 | 17% | 1.11 | 83% | 1.08 | 4% | 4% |
| numpy.sort | 0 | 9 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| numpy.sort | 1 | 9 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| operator.matmul | 0 | 16 | 0.97 | 3% | 6% | 100% | 1.26 | 94% | 1.03 | 6% | 1.00 | 0% | 0% |
| operator.matmul | 1 | 16 | 0.97 | 3% | 6% | 100% | 1.26 | 94% | 1.03 | 6% | 1.00 | 0% | 0% |
| pandas.concat | 0 | 21 | 0.94 | 6% | 10% | 100% | 1.00 | 100% | 1.06 | 0% | – | 0% | 0% |
| pandas.concat | 1 | 21 | 0.94 | 6% | 10% | 100% | 1.00 | 100% | 1.06 | 0% | – | 0% | 0% |
| pandas.read_csv | 0 | 19 | 1.55 | 55% | 118% | 100% | 2.65 | 11% | 1.63 | 89% | 1.55 | 0% | 0% |
| pandas.read_csv | 1 | 19 | 1.22 | 22% | 32% | 100% | 0.56 | 11% | 1.04 | 89% | 1.22 | 0% | 0% |
| sort_values | 0 | 23 | 1.01 | 1% | 1% | 100% | 0.47 | 13% | 1.00 | 87% | 1.01 | 0% | 0% |
| sort_values | 1 | 23 | 1.01 | 1% | 1% | 100% | 0.47 | 13% | 1.00 | 87% | 1.01 | 0% | 0% |
| ALL | 0 | 191 | 1.01 | 11% | 92% | 98% | 1.50 | 47% | 1.06 | 53% | 1.32 | 0% | 2% |
| ALL | 1 | 191 | 1.01 | 3% | 20% | 98% | 0.65 | 41% | 1.03 | 59% | 1.03 | 1% | 1% |


## RAM: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 28 | 89% | 86% | 4% | 1.01 | 0.53 |
| drop_duplicates | 27 | 100% | 100% | 0% | 1.04 | 0.69 |
| groupby | 24 | 100% | 100% | 0% | 1.50 | 0.55 |
| merge | 24 | 100% | 100% | 0% | 3.65 | 0.51 |
| numpy.sort | 9 | 0% | 0% | 0% | 0.40 | 0.40 |
| operator.matmul | 16 | 0% | 0% | 0% | 1.26 | 1.26 |
| pandas.concat | 21 | 0% | 0% | 0% | 1.00 | 1.00 |
| pandas.read_csv | 19 | 100% | 100% | 0% | 2.65 | 0.56 |
| sort_values | 23 | 0% | 0% | 0% | 0.47 | 0.47 |
| ALL | 191 | 62% | 62% | 1% | 1.50 | 0.65 |


## RAM: cases where Tier 1 did worse (11 points)

| op | case | size | t1_used | actual | fold_t0 | fold_t1 | lost_coverage | dangerous |
|---|---|---|---|---|---|---|---|---|
| drop_duplicates | drop_duplicates/numeric_dup50 | 10000000 | True | 1043468288 | 1.08 | 1.16 | False | False |
| drop_duplicates | v3/drop_duplicates/null_subset_f0_s0 | 1000000 | True | 52932608 | 1.17 | 1.25 | True | False |
| drop_duplicates | v3/drop_duplicates/null_subset_f0_s0 | 3000000 | True | 144248832 | 1.03 | 1.14 | False | False |
| groupby | groupby/two_keys_mean_realistic | 1000000 | True | 82481152 | 1.06 | 1.33 | False | False |
| groupby | v3/groupby/two_keys_card800 | 1000000 | True | 85082112 | 1.03 | 1.10 | False | False |
| merge | v3/merge/inner_overlap25_fanout6 | 3000000 | True | 189419520 | 1.85 | 0.86 | True | True |
| pandas.read_csv | read_csv/mixed | 1000000 | True | 467279872 | 1.11 | 1.21 | False | False |
| pandas.read_csv | read_csv/mixed | 3000000 | True | 1436184576 | 1.10 | 1.20 | False | False |
| pandas.read_csv | read_csv/strings | 3000000 | True | 1392066560 | 1.03 | 1.22 | False | False |
| pandas.read_csv | v3/read_csv/mixed_nulls_dates | 1000000 | True | 406224896 | 1.18 | 1.40 | False | False |
| pandas.read_csv | v3/read_csv/mixed_nulls_dates | 3000000 | True | 1234055168 | 1.19 | 1.39 | False | False |


## Time: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 20 | 1.43 | 73% | 228% | 95% | 3.75 | 45% | 2.63 | 55% | 2.86 | 5% | 0% |
| astype | 1 | 20 | 1.43 | 73% | 228% | 95% | 3.75 | 45% | 2.63 | 55% | 2.86 | 5% | 0% |
| drop_duplicates | 0 | 26 | 0.89 | 31% | 69% | 92% | 3.75 | 54% | 1.52 | 46% | 1.11 | 4% | 4% |
| drop_duplicates | 1 | 26 | 0.94 | 34% | 76% | 92% | 3.75 | 54% | 1.50 | 46% | 1.28 | 4% | 4% |
| groupby | 0 | 19 | 2.55 | 155% | 498% | 68% | 3.75 | 21% | 2.66 | 79% | 3.04 | 0% | 32% |
| groupby | 1 | 19 | 2.34 | 134% | 380% | 84% | 3.75 | 21% | 3.03 | 79% | 3.02 | 0% | 16% |
| merge | 0 | 15 | 1.10 | 53% | 88% | 100% | 3.75 | 33% | 1.44 | 67% | 1.62 | 0% | 0% |
| merge | 1 | 15 | 1.10 | 53% | 88% | 100% | 3.75 | 33% | 1.44 | 67% | 1.62 | 0% | 0% |
| numpy.sort | 0 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| numpy.sort | 1 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| operator.matmul | 0 | 14 | 1.04 | 10% | 186% | 100% | 4.80 | 43% | 1.09 | 57% | 1.65 | 0% | 0% |
| operator.matmul | 1 | 14 | 1.04 | 10% | 186% | 100% | 4.80 | 43% | 1.09 | 57% | 1.65 | 0% | 0% |
| pandas.concat | 0 | 11 | 1.07 | 26% | 88% | 100% | 3.75 | 36% | 1.29 | 64% | 1.26 | 0% | 0% |
| pandas.concat | 1 | 11 | 1.07 | 26% | 88% | 100% | 3.75 | 36% | 1.29 | 64% | 1.26 | 0% | 0% |
| pandas.read_csv | 0 | 12 | 0.37 | 66% | 198% | 100% | 3.75 | 75% | 2.75 | 25% | 3.01 | 0% | 0% |
| pandas.read_csv | 1 | 12 | 0.37 | 66% | 198% | 100% | 3.75 | 75% | 2.75 | 25% | 3.01 | 0% | 0% |
| sort_values | 0 | 20 | 0.86 | 45% | 194% | 95% | 3.75 | 60% | 1.53 | 40% | 1.98 | 0% | 5% |
| sort_values | 1 | 20 | 0.86 | 45% | 194% | 95% | 3.75 | 60% | 1.53 | 40% | 1.98 | 0% | 5% |
| ALL | 0 | 140 | 1.06 | 53% | 217% | 93% | 3.86 | 45% | 1.66 | 55% | 1.89 | 1% | 6% |
| ALL | 1 | 140 | 1.07 | 53% | 213% | 95% | 3.86 | 45% | 1.64 | 55% | 1.88 | 1% | 4% |


## Time: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 20 | 100% | 0% | 0% | 3.75 | 3.75 |
| drop_duplicates | 26 | 100% | 0% | 0% | 3.75 | 3.75 |
| groupby | 19 | 100% | 0% | 0% | 3.75 | 3.75 |
| merge | 15 | 100% | 0% | 0% | 3.75 | 3.75 |
| numpy.sort | 3 | 0% | 0% | 0% | 3.90 | 3.90 |
| operator.matmul | 14 | 0% | 0% | 0% | 4.80 | 4.80 |
| pandas.concat | 11 | 0% | 0% | 0% | 3.75 | 3.75 |
| pandas.read_csv | 12 | 100% | 0% | 0% | 3.75 | 3.75 |
| sort_values | 20 | 0% | 0% | 0% | 3.75 | 3.75 |
| ALL | 140 | 66% | 0% | 0% | 3.86 | 3.86 |


## Time: cases where Tier 1 did worse (1 points)

| op | case | size | t1_used | actual | fold_t0 | fold_t1 | lost_coverage | dangerous |
|---|---|---|---|---|---|---|---|---|
| drop_duplicates | v3/drop_duplicates/high_survivor_subset_i0_d0 | 1000000 | True | 0.10 | 1.12 | 1.51 | False | False |


## Analysis overhead (warm, per cell)

| op | tier | warm_med_ms | warm_p90_ms | warm_max_ms | cold_med_ms | over_250ms |
|---|---|---|---|---|---|---|
| astype | 0 | 4.33 | 7.01 | 14.26 | 5.40 | 0% |
| astype | 1 | 28.59 | 63.27 | 131 | 33.01 | 0% |
| drop_duplicates | 0 | 4.07 | 7.03 | 10.27 | 4.83 | 0% |
| drop_duplicates | 1 | 116 | 184 | 200 | 106 | 0% |
| groupby | 0 | 3.26 | 4.64 | 6.80 | 4.15 | 0% |
| groupby | 1 | 31.30 | 100 | 127 | 36.77 | 0% |
| merge | 0 | 7.37 | 13.28 | 15.32 | 8.08 | 0% |
| merge | 1 | 123 | 161 | 196 | 135 | 0% |
| numpy.sort | 0 | 0.21 | 0.39 | 0.59 | 0.57 | 0% |
| numpy.sort | 1 | 0.21 | 0.28 | 0.31 | 0.52 | 0% |
| operator.matmul | 0 | 0.22 | 0.46 | 0.59 | 0.53 | 0% |
| operator.matmul | 1 | 0.23 | 0.35 | 0.77 | 0.55 | 0% |
| pandas.concat | 0 | 7.72 | 12.76 | 32.71 | 9.32 | 0% |
| pandas.concat | 1 | 7.83 | 17.83 | 31.49 | 7.47 | 0% |
| pandas.read_csv | 0 | 0.15 | 0.22 | 0.35 | 0.43 | 0% |
| pandas.read_csv | 1 | 23.11 | 31.64 | 33.31 | 88.51 | 0% |
| sort_values | 0 | 4.39 | 5.98 | 6.26 | 5.41 | 0% |
| sort_values | 1 | 4.29 | 6.56 | 8.93 | 4.96 | 0% |
| ALL | 0 | 3.57 | 8.23 | 32.71 | 4.60 | 0% |
| ALL | 1 | 24.90 | 131 | 200 | 31.59 | 0% |

