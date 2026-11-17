# Tier 0 before/after (Phase 4a)

Before: `full` predictions (first-draft models). After: `tier0-v2` predictions (Phase 4a models). **Both are scored against the same measurements**, so every difference is the model change. `dev` is where the changes were derived; `exposed-v1` is the held-out validation (development and diagnosis only, never a final claim). test-v2 is sealed and was not read.

bias = median(expected/actual) (>1 over-predicts); coverage = share of valid points with actual in [low, high]; width = mean (high-low)/expected; err = |expected-actual|/actual. Only `valid` points enter the metrics; censored/excluded counts shown.

Time predictions unchanged by this phase: **True**.

## RAM, dev

| op | points_before | ram_valid_before | ram_censored_before | ram_excluded_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | points_after | ram_valid_after | ram_censored_after | ram_excluded_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 14 | 9 | 5 | 0 | 38% | 60% | 0.62 | 89% | 11% | 0% | 2.00 | 14 | 9 | 5 | 0 | 12% | 49% | 1.00 | 100% | 0% | 0% | 1.23 |
| drop_duplicates | 15 | 12 | 3 | 0 | 57% | 203% | 1.57 | 100% | 0% | 0% | 1.06 | 15 | 12 | 3 | 0 | 14% | 31% | 1.14 | 100% | 0% | 0% | 0.95 |
| groupby | 8 | 6 | 2 | 0 | 157% | 314% | 2.57 | 100% | 0% | 0% | 3.53 | 8 | 6 | 2 | 0 | 157% | 314% | 2.57 | 100% | 0% | 0% | 3.53 |
| merge | 10 | 10 | 0 | 0 | 422% | 767% | 5.22 | 70% | 0% | 30% | 3.59 | 10 | 10 | 0 | 0 | 103% | 238% | 2.03 | 90% | 0% | 10% | 3.71 |
| numpy.sort | 4 | 4 | 0 | 0 | 0% | 0% | 1.00 | 100% | 0% | 0% | 0.40 | 4 | 4 | 0 | 0 | 0% | 0% | 1.00 | 100% | 0% | 0% | 0.40 |
| operator.matmul | 4 | 4 | 0 | 0 | 3% | 5% | 0.97 | 100% | 0% | 0% | 1.25 | 4 | 4 | 0 | 0 | 3% | 5% | 0.97 | 100% | 0% | 0% | 1.25 |
| pandas.concat | 6 | 6 | 0 | 0 | 58% | 99% | 1.40 | 50% | 0% | 50% | 0.70 | 6 | 6 | 0 | 0 | 4% | 8% | 0.96 | 100% | 0% | 0% | 1.00 |
| pandas.read_csv | 6 | 6 | 0 | 0 | 62% | 65% | 0.38 | 100% | 0% | 0% | 3.00 | 6 | 6 | 0 | 0 | 10% | 88% | 1.10 | 100% | 0% | 0% | 2.65 |
| sort_values | 9 | 9 | 0 | 0 | 128% | 146% | 2.28 | 0% | 0% | 100% | 0.67 | 9 | 9 | 0 | 0 | 1% | 1% | 1.01 | 100% | 0% | 0% | 0.41 |
| ALL | 76 | 66 | 10 | 0 | 64% | 359% | 1.57 | 76% | 2% | 23% | 1.86 | 76 | 66 | 10 | 0 | 8% | 121% | 1.04 | 98% | 0% | 2% | 1.71 |


## RAM, exposed-v1

| op | points_before | ram_valid_before | ram_censored_before | ram_excluded_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | points_after | ram_valid_after | ram_censored_after | ram_excluded_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 9 | 7 | 2 | 0 | 17% | 59% | 0.83 | 86% | 14% | 0% | 2.00 | 9 | 7 | 2 | 0 | 10% | 39% | 1.10 | 100% | 0% | 0% | 0.95 |
| drop_duplicates | 5 | 5 | 0 | 0 | 54% | 65% | 1.54 | 100% | 0% | 0% | 1.34 | 5 | 5 | 0 | 0 | 30% | 42% | 0.70 | 100% | 0% | 0% | 1.14 |
| groupby | 6 | 4 | 2 | 0 | 53% | 464% | 1.53 | 100% | 0% | 0% | 3.27 | 6 | 4 | 2 | 0 | 53% | 464% | 1.53 | 100% | 0% | 0% | 3.27 |
| merge | 4 | 4 | 0 | 0 | 345% | 623% | 4.45 | 50% | 0% | 50% | 3.65 | 4 | 4 | 0 | 0 | 41% | 46% | 1.04 | 100% | 0% | 0% | 3.60 |
| numpy.sort | 4 | 3 | 1 | 0 | 0% | 0% | 1.00 | 100% | 0% | 0% | 0.40 | 4 | 3 | 1 | 0 | 0% | 0% | 1.00 | 100% | 0% | 0% | 0.40 |
| operator.matmul | 5 | 5 | 0 | 0 | 2% | 5% | 0.98 | 100% | 0% | 0% | 1.13 | 5 | 5 | 0 | 0 | 2% | 5% | 0.98 | 100% | 0% | 0% | 1.13 |
| pandas.concat | 6 | 6 | 0 | 0 | 110% | 114% | 2.10 | 0% | 0% | 100% | 0.70 | 6 | 6 | 0 | 0 | 7% | 8% | 0.93 | 100% | 0% | 0% | 1.00 |
| pandas.read_csv | 4 | 4 | 0 | 0 | 36% | 47% | 0.64 | 100% | 0% | 0% | 3.00 | 4 | 4 | 0 | 0 | 87% | 117% | 1.87 | 100% | 0% | 0% | 2.65 |
| sort_values | 5 | 5 | 0 | 0 | 127% | 144% | 2.27 | 0% | 0% | 100% | 0.62 | 5 | 5 | 0 | 0 | 1% | 1% | 1.01 | 100% | 0% | 0% | 0.52 |
| ALL | 48 | 43 | 5 | 0 | 52% | 140% | 1.05 | 67% | 2% | 30% | 1.73 | 48 | 43 | 5 | 0 | 10% | 59% | 1.00 | 100% | 0% | 0% | 1.53 |


## Time, dev

| op | points_before | time_valid_before | time_censored_before | time_excluded_before | time_err_med_before | time_err_p90_before | time_bias_before | time_cov_before | time_above_high_before | time_below_low_before | time_width_before | points_after | time_valid_after | time_censored_after | time_excluded_after | time_err_med_after | time_err_p90_after | time_bias_after | time_cov_after | time_above_high_after | time_below_low_after | time_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 14 | 6 | 8 | 0 | 59% | 218% | 1.43 | 100% | 0% | 0% | 3.75 | 14 | 6 | 8 | 0 | 59% | 218% | 1.43 | 100% | 0% | 0% | 3.75 |
| drop_duplicates | 15 | 13 | 2 | 0 | 46% | 74% | 0.79 | 85% | 8% | 8% | 3.75 | 15 | 13 | 2 | 0 | 46% | 74% | 0.79 | 85% | 8% | 8% | 3.75 |
| groupby | 8 | 5 | 3 | 0 | 378% | 534% | 4.78 | 40% | 0% | 60% | 3.75 | 8 | 5 | 3 | 0 | 378% | 534% | 4.78 | 40% | 0% | 60% | 3.75 |
| merge | 10 | 5 | 3 | 2 | 65% | 168% | 1.65 | 100% | 0% | 0% | 3.75 | 10 | 5 | 3 | 2 | 65% | 168% | 1.65 | 100% | 0% | 0% | 3.75 |
| numpy.sort | 4 | 2 | 2 | 0 | 19% | 21% | 1.19 | 100% | 0% | 0% | 3.90 | 4 | 2 | 2 | 0 | 19% | 21% | 1.19 | 100% | 0% | 0% | 3.90 |
| operator.matmul | 4 | 3 | 0 | 1 | 8% | 10% | 0.92 | 100% | 0% | 0% | 4.80 | 4 | 3 | 0 | 1 | 8% | 10% | 0.92 | 100% | 0% | 0% | 4.80 |
| pandas.concat | 6 | 3 | 3 | 0 | 54% | 82% | 1.06 | 100% | 0% | 0% | 3.75 | 6 | 3 | 3 | 0 | 54% | 82% | 1.06 | 100% | 0% | 0% | 3.75 |
| pandas.read_csv | 6 | 4 | 1 | 1 | 66% | 69% | 0.34 | 100% | 0% | 0% | 3.75 | 6 | 4 | 1 | 1 | 66% | 69% | 0.34 | 100% | 0% | 0% | 3.75 |
| sort_values | 9 | 7 | 0 | 2 | 37% | 61% | 0.83 | 100% | 0% | 0% | 3.75 | 9 | 7 | 0 | 2 | 37% | 61% | 0.83 | 100% | 0% | 0% | 3.75 |
| ALL | 76 | 48 | 22 | 6 | 51% | 219% | 0.95 | 90% | 2% | 8% | 3.82 | 76 | 48 | 22 | 6 | 51% | 219% | 0.95 | 90% | 2% | 8% | 3.82 |


## Time, exposed-v1

| op | points_before | time_valid_before | time_censored_before | time_excluded_before | time_err_med_before | time_err_p90_before | time_bias_before | time_cov_before | time_above_high_before | time_below_low_before | time_width_before | points_after | time_valid_after | time_censored_after | time_excluded_after | time_err_med_after | time_err_p90_after | time_bias_after | time_cov_after | time_above_high_after | time_below_low_after | time_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 9 | 5 | 4 | 0 | 30% | 194% | 0.73 | 100% | 0% | 0% | 3.75 | 9 | 5 | 4 | 0 | 30% | 194% | 0.73 | 100% | 0% | 0% | 3.75 |
| drop_duplicates | 5 | 4 | 0 | 1 | 37% | 105% | 1.30 | 100% | 0% | 0% | 3.75 | 5 | 4 | 0 | 1 | 37% | 105% | 1.30 | 100% | 0% | 0% | 3.75 |
| groupby | 6 | 3 | 2 | 1 | 190% | 701% | 2.90 | 67% | 0% | 33% | 3.75 | 6 | 3 | 2 | 1 | 190% | 701% | 2.90 | 67% | 0% | 33% | 3.75 |
| merge | 4 | 2 | 0 | 2 | 33% | 54% | 0.73 | 100% | 0% | 0% | 3.75 | 4 | 2 | 0 | 2 | 33% | 54% | 0.73 | 100% | 0% | 0% | 3.75 |
| numpy.sort | 4 | 1 | 3 | 0 | 22% | 22% | 1.22 | 100% | 0% | 0% | 3.90 | 4 | 1 | 3 | 0 | 22% | 22% | 1.22 | 100% | 0% | 0% | 3.90 |
| operator.matmul | 5 | 4 | 1 | 0 | 6% | 8% | 1.02 | 100% | 0% | 0% | 4.80 | 5 | 4 | 1 | 0 | 6% | 8% | 1.02 | 100% | 0% | 0% | 4.80 |
| pandas.concat | 6 | 3 | 2 | 1 | 26% | 29% | 1.07 | 100% | 0% | 0% | 3.75 | 6 | 3 | 2 | 1 | 26% | 29% | 1.07 | 100% | 0% | 0% | 3.75 |
| pandas.read_csv | 4 | 4 | 0 | 0 | 114% | 193% | 1.65 | 100% | 0% | 0% | 3.75 | 4 | 4 | 0 | 0 | 114% | 193% | 1.65 | 100% | 0% | 0% | 3.75 |
| sort_values | 5 | 4 | 0 | 1 | 55% | 98% | 1.10 | 100% | 0% | 0% | 3.75 | 5 | 4 | 0 | 1 | 55% | 98% | 1.10 | 100% | 0% | 0% | 3.75 |
| ALL | 48 | 30 | 12 | 6 | 41% | 191% | 1.06 | 97% | 0% | 3% | 3.90 | 48 | 30 | 12 | 6 | 41% | 191% | 1.06 | 97% | 0% | 3% | 3.90 |

