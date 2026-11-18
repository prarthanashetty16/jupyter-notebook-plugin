# Tier 0 vs Tier 1 (dev)

Group: **dev**. Tier 0 = first-tier models of Phase 4a; Tier 1 = the same models with data statistics where the sample is large enough, else Tier 0 (counted as not used). bias = median expected/actual (>1 over-predicts). `above_high` = actuals beyond the range's upper end (**under-prediction**, dangerous); `below_low` = beyond the lower end (over-prediction). `under_fold`/`over_fold` = median factor by which `expected` is too low / too high on the points where it is.

## RAM: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 49 | 1.00 | 17% | 65% | 92% | 0.99 | 53% | 1.09 | 47% | 1.44 | 0% | 8% |
| astype | 1 | 49 | 1.00 | 1% | 1% | 100% | 0.45 | 41% | 1.00 | 59% | 1.01 | 0% | 0% |
| drop_duplicates | 0 | 41 | 0.97 | 17% | 32% | 100% | 1.06 | 51% | 1.31 | 49% | 1.13 | 0% | 0% |
| drop_duplicates | 1 | 41 | 1.05 | 12% | 32% | 95% | 0.66 | 37% | 1.10 | 63% | 1.12 | 0% | 5% |
| groupby | 0 | 41 | 1.57 | 57% | 124% | 98% | 1.47 | 22% | 1.35 | 78% | 1.86 | 0% | 2% |
| groupby | 1 | 41 | 1.01 | 2% | 21% | 98% | 0.56 | 7% | 1.02 | 93% | 1.01 | 0% | 2% |
| merge | 0 | 37 | 1.55 | 55% | 129% | 95% | 3.66 | 27% | 1.33 | 73% | 1.69 | 0% | 5% |
| merge | 1 | 37 | 1.07 | 8% | 20% | 89% | 0.56 | 19% | 1.15 | 81% | 1.08 | 8% | 3% |
| numpy.sort | 0 | 12 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| numpy.sort | 1 | 12 | 1.00 | 0% | 0% | 100% | 0.40 | 100% | 1.00 | 0% | – | 0% | 0% |
| operator.matmul | 0 | 24 | 0.97 | 3% | 6% | 100% | 1.25 | 96% | 1.03 | 4% | 1.00 | 0% | 0% |
| operator.matmul | 1 | 24 | 0.97 | 3% | 6% | 100% | 1.25 | 96% | 1.03 | 4% | 1.00 | 0% | 0% |
| pandas.concat | 0 | 27 | 0.92 | 8% | 16% | 100% | 1.00 | 100% | 1.08 | 0% | – | 0% | 0% |
| pandas.concat | 1 | 27 | 0.92 | 8% | 16% | 100% | 1.00 | 100% | 1.08 | 0% | – | 0% | 0% |
| pandas.read_csv | 0 | 24 | 1.20 | 39% | 120% | 96% | 2.65 | 17% | 1.34 | 83% | 1.55 | 0% | 4% |
| pandas.read_csv | 1 | 24 | 1.22 | 22% | 30% | 100% | 0.58 | 8% | 1.04 | 92% | 1.22 | 0% | 0% |
| sort_values | 0 | 29 | 1.01 | 1% | 1% | 100% | 0.45 | 21% | 1.00 | 79% | 1.01 | 0% | 0% |
| sort_values | 1 | 29 | 1.01 | 1% | 1% | 100% | 0.45 | 21% | 1.00 | 79% | 1.01 | 0% | 0% |
| ALL | 0 | 284 | 1.00 | 12% | 91% | 97% | 1.50 | 49% | 1.07 | 51% | 1.37 | 0% | 3% |
| ALL | 1 | 284 | 1.01 | 3% | 22% | 98% | 0.64 | 40% | 1.03 | 60% | 1.03 | 1% | 1% |


## RAM: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 49 | 94% | 92% | 2% | 0.99 | 0.45 |
| drop_duplicates | 41 | 98% | 95% | 0% | 1.06 | 0.66 |
| groupby | 41 | 100% | 98% | 2% | 1.47 | 0.56 |
| merge | 37 | 97% | 97% | 0% | 3.66 | 0.56 |
| numpy.sort | 12 | 0% | 0% | 0% | 0.40 | 0.40 |
| operator.matmul | 24 | 0% | 0% | 0% | 1.25 | 1.25 |
| pandas.concat | 27 | 0% | 0% | 0% | 1.00 | 1.00 |
| pandas.read_csv | 24 | 100% | 100% | 0% | 2.65 | 0.58 |
| sort_values | 29 | 0% | 0% | 0% | 0.45 | 0.45 |
| ALL | 284 | 66% | 65% | 1% | 1.50 | 0.64 |


## RAM: cases where Tier 1 did worse (23 points)

| op | case | size | t1_used | actual | fold_t0 | fold_t1 | lost_coverage | dangerous |
|---|---|---|---|---|---|---|---|---|
| drop_duplicates | v3/drop_duplicates/null_subset_f0_s0 | 1000000 | True | 52932608 | 1.17 | 1.25 | True | False |
| drop_duplicates | v3/drop_duplicates/null_subset_f0_s0 | 3000000 | True | 144248832 | 1.03 | 1.14 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_cat_date | 1000000 | True | 66519040 | 0.93 | 1.17 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_cat_date | 3000000 | True | 165588992 | 0.90 | 1.32 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_cat_date | 10000000 | True | 548749312 | 0.94 | 1.31 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_floats | 1000000 | True | 54185984 | 1.15 | 1.61 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_floats | 3000000 | True | 154279936 | 0.97 | 1.68 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_texts | 1000000 | True | 48340992 | 1.28 | 1.37 | True | False |
| drop_duplicates | v4/drop_duplicates/null_subset_texts | 3000000 | True | 144379904 | 1.03 | 1.14 | False | False |
| groupby | groupby/two_keys_mean_realistic | 1000000 | True | 82481152 | 1.06 | 1.33 | False | False |
| groupby | v3/groupby/two_keys_card800 | 1000000 | True | 85082112 | 1.03 | 1.13 | False | False |
| merge | v3/merge/inner_overlap25_fanout6 | 3000000 | True | 189419520 | 1.85 | 0.86 | True | True |
| merge | v4/merge/inner_overlap20_fanout10 | 1000000 | True | 73252864 | 1.59 | 0.83 | True | True |
| merge | v4/merge/inner_overlap20_fanout10 | 3000000 | True | 187654144 | 1.87 | 0.79 | True | True |
| pandas.read_csv | read_csv/mixed | 1000000 | True | 467279872 | 1.11 | 1.21 | False | False |
| pandas.read_csv | read_csv/mixed | 3000000 | True | 1436184576 | 1.10 | 1.20 | False | False |
| pandas.read_csv | read_csv/strings | 3000000 | True | 1392066560 | 1.03 | 1.22 | False | False |
| pandas.read_csv | v3/read_csv/mixed_nulls_dates | 1000000 | True | 406224896 | 1.18 | 1.40 | False | False |
| pandas.read_csv | v3/read_csv/mixed_nulls_dates | 3000000 | True | 1234055168 | 1.19 | 1.39 | False | False |
| pandas.read_csv | v4/read_csv/dates_ints | 1000000 | True | 405553152 | 1.00 | 1.12 | False | False |
| pandas.read_csv | v4/read_csv/dates_ints | 3000000 | True | 1178517504 | 1.07 | 1.17 | False | False |
| pandas.read_csv | v4/read_csv/text_nulls | 1000000 | True | 323379200 | 0.94 | 1.20 | False | False |
| pandas.read_csv | v4/read_csv/text_nulls | 3000000 | True | 908660736 | 1.02 | 1.29 | False | False |


## Time: accuracy by tier

| op | tier | valid | bias | err_med | err_p90 | coverage | width | under_share | under_fold | over_share | over_fold | above_high | below_low |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 37 | 1.42 | 65% | 223% | 97% | 3.75 | 38% | 2.67 | 62% | 2.72 | 3% | 0% |
| astype | 1 | 37 | 1.42 | 65% | 223% | 97% | 3.75 | 38% | 2.67 | 62% | 2.72 | 3% | 0% |
| drop_duplicates | 0 | 38 | 0.84 | 34% | 92% | 89% | 3.75 | 61% | 1.57 | 39% | 1.27 | 3% | 8% |
| drop_duplicates | 1 | 38 | 0.94 | 34% | 101% | 89% | 3.75 | 58% | 1.50 | 42% | 1.36 | 3% | 8% |
| groupby | 0 | 31 | 2.80 | 180% | 555% | 58% | 3.75 | 26% | 2.33 | 74% | 4.55 | 0% | 42% |
| groupby | 1 | 31 | 2.57 | 157% | 411% | 74% | 3.75 | 26% | 2.65 | 74% | 3.16 | 3% | 23% |
| merge | 0 | 24 | 1.10 | 38% | 82% | 100% | 3.75 | 33% | 1.43 | 67% | 1.41 | 0% | 0% |
| merge | 1 | 24 | 1.10 | 38% | 82% | 100% | 3.75 | 33% | 1.43 | 67% | 1.41 | 0% | 0% |
| numpy.sort | 0 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| numpy.sort | 1 | 3 | 1.21 | 21% | 22% | 100% | 3.90 | 0% | – | 100% | 1.21 | 0% | 0% |
| operator.matmul | 0 | 19 | 1.03 | 9% | 185% | 100% | 4.80 | 37% | 1.08 | 63% | 1.65 | 0% | 0% |
| operator.matmul | 1 | 19 | 1.03 | 9% | 185% | 100% | 4.80 | 37% | 1.08 | 63% | 1.65 | 0% | 0% |
| pandas.concat | 0 | 16 | 0.99 | 31% | 90% | 81% | 3.75 | 50% | 1.81 | 50% | 1.29 | 19% | 0% |
| pandas.concat | 1 | 16 | 0.99 | 31% | 90% | 81% | 3.75 | 50% | 1.81 | 50% | 1.29 | 19% | 0% |
| pandas.read_csv | 0 | 17 | 0.37 | 68% | 216% | 100% | 3.75 | 76% | 2.90 | 24% | 3.20 | 0% | 0% |
| pandas.read_csv | 1 | 17 | 0.37 | 68% | 216% | 100% | 3.75 | 76% | 2.90 | 24% | 3.20 | 0% | 0% |
| sort_values | 0 | 26 | 0.93 | 40% | 151% | 96% | 3.75 | 54% | 1.45 | 46% | 1.68 | 0% | 4% |
| sort_values | 1 | 26 | 0.93 | 40% | 151% | 96% | 3.75 | 54% | 1.45 | 46% | 1.68 | 0% | 4% |
| ALL | 0 | 211 | 1.07 | 53% | 239% | 90% | 3.85 | 45% | 1.71 | 55% | 1.89 | 2% | 8% |
| ALL | 1 | 211 | 1.07 | 53% | 224% | 92% | 3.85 | 45% | 1.72 | 55% | 1.84 | 3% | 5% |


## Time: how often Tier 1 narrowed the range

| op | points | tier1_used | narrowed | widened | width_t0 | width_t1 |
|---|---|---|---|---|---|---|
| astype | 37 | 100% | 0% | 0% | 3.75 | 3.75 |
| drop_duplicates | 38 | 97% | 0% | 0% | 3.75 | 3.75 |
| groupby | 31 | 100% | 0% | 0% | 3.75 | 3.75 |
| merge | 24 | 96% | 0% | 0% | 3.75 | 3.75 |
| numpy.sort | 3 | 0% | 0% | 0% | 3.90 | 3.90 |
| operator.matmul | 19 | 0% | 0% | 0% | 4.80 | 4.80 |
| pandas.concat | 16 | 0% | 0% | 0% | 3.75 | 3.75 |
| pandas.read_csv | 17 | 100% | 0% | 0% | 3.75 | 3.75 |
| sort_values | 26 | 0% | 0% | 0% | 3.75 | 3.75 |
| ALL | 211 | 69% | 0% | 0% | 3.85 | 3.85 |


## Time: cases where Tier 1 did worse (4 points)

| op | case | size | t1_used | actual | fold_t0 | fold_t1 | lost_coverage | dangerous |
|---|---|---|---|---|---|---|---|---|
| drop_duplicates | v3/drop_duplicates/high_survivor_subset_i0_d0 | 1000000 | True | 0.10 | 1.12 | 1.51 | False | False |
| drop_duplicates | v4/drop_duplicates/null_subset_cat_date | 10000000 | True | 1.89 | 0.58 | 0.47 | False | False |
| groupby | v4/groupby/str_card0p9_mean | 3000000 | True | 2.73 | 0.27 | 0.24 | True | True |
| groupby | v4/groupby/two_keys_card6000 | 3000000 | True | 0.95 | 0.88 | 0.81 | False | False |


## Analysis overhead (warm, per cell)

| op | tier | warm_med_ms | warm_p90_ms | warm_max_ms | cold_med_ms | over_250ms |
|---|---|---|---|---|---|---|
| astype | 0 | 4.29 | 5.89 | 11.08 | 4.86 | 0% |
| astype | 1 | 32.53 | 62.91 | 127 | 35.74 | 0% |
| drop_duplicates | 0 | 3.55 | 7.13 | 13.70 | 4.69 | 0% |
| drop_duplicates | 1 | 97.81 | 159 | 201 | 102 | 0% |
| groupby | 0 | 3.53 | 5.49 | 8.58 | 3.98 | 0% |
| groupby | 1 | 30.67 | 81.15 | 135 | 54.57 | 0% |
| merge | 0 | 6.92 | 10.54 | 13.22 | 8.35 | 0% |
| merge | 1 | 113 | 186 | 237 | 137 | 0% |
| numpy.sort | 0 | 0.26 | 0.41 | 0.46 | 0.66 | 0% |
| numpy.sort | 1 | 0.15 | 0.23 | 0.26 | 0.44 | 0% |
| operator.matmul | 0 | 0.19 | 0.31 | 0.58 | 0.53 | 0% |
| operator.matmul | 1 | 0.19 | 0.41 | 0.54 | 0.56 | 0% |
| pandas.concat | 0 | 8.69 | 15.09 | 18.99 | 10.47 | 0% |
| pandas.concat | 1 | 7.45 | 14.71 | 17.85 | 8.08 | 0% |
| pandas.read_csv | 0 | 0.17 | 0.25 | 0.66 | 0.48 | 0% |
| pandas.read_csv | 1 | 22.79 | 33.41 | 50.32 | 72.88 | 0% |
| sort_values | 0 | 4.68 | 6.32 | 7.99 | 5.29 | 0% |
| sort_values | 1 | 4.26 | 5.47 | 8.60 | 5.54 | 0% |
| ALL | 0 | 3.67 | 8.07 | 18.99 | 4.24 | 0% |
| ALL | 1 | 26.07 | 120 | 237 | 34.60 | 0% |

