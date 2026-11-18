# Tier 1 before / after the 4b.2 fixes (development data only)

Identical measured actuals; `before` = predictions of the 4b models, `after` = the 4b.2 models. RAM, valid points, memory-limit lower bounds excluded. `val-v3` = the former held-out group: the fixes were informed by its failures, so its numbers are NOT evidence of generalisation (val-v4 is).


## Tier 1: dev (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 16 | 0% | 1% | 1.00 | 100% | 0% | 0% | 59% | 16 | 0% | 1% | 1.00 | 100% | 0% | 0% | 59% |
| drop_duplicates | 17 | 11% | 23% | 1.09 | 100% | 0% | 0% | 72% | 17 | 11% | 19% | 1.05 | 100% | 0% | 0% | 75% |
| groupby | 10 | 2% | 28% | 1.02 | 100% | 0% | 0% | 47% | 10 | 2% | 28% | 1.02 | 100% | 0% | 0% | 47% |
| merge | 14 | 7% | 19% | 1.06 | 93% | 0% | 7% | 62% | 14 | 7% | 19% | 1.06 | 93% | 0% | 7% | 62% |
| numpy.sort | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% |
| pandas.concat | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 10 | 22% | 26% | 1.22 | 100% | 0% | 0% | 59% | 10 | 22% | 26% | 1.22 | 100% | 0% | 0% | 59% |
| sort_values | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| ALL | 109 | 3% | 22% | 1.01 | 99% | 0% | 1% | 67% | 109 | 3% | 22% | 1.01 | 99% | 0% | 1% | 67% |


### Tier 1: dev (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 8 | 0% | 0% | 8 | 0% | 0% |
| drop_duplicates | 6 | 0% | 0% | 6 | 0% | 0% |
| groupby | 5 | 0% | 0% | 5 | 0% | 0% |
| merge | 7 | 0% | 14% | 7 | 0% | 14% |
| numpy.sort | 4 | 0% | 0% | 4 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 4 | 0% | 0% | 4 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 5 | 0% | 0% | 5 | 0% | 0% |
| ALL | 46 | 0% | 2% | 46 | 0% | 2% |


## Tier 1: val-v3 (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 12 | 1% | 3% | 1.00 | 100% | 0% | 0% | 45% | 12 | 1% | 3% | 1.00 | 100% | 0% | 0% | 45% |
| drop_duplicates | 9 | 3% | 18% | 1.03 | 89% | 0% | 11% | 63% | 9 | 3% | 18% | 1.03 | 89% | 0% | 11% | 62% |
| groupby | 14 | 1% | 12% | 1.01 | 100% | 0% | 0% | 60% | 14 | 1% | 13% | 1.01 | 100% | 0% | 0% | 59% |
| merge | 10 | 8% | 15% | 1.06 | 90% | 10% | 0% | 36% | 10 | 8% | 15% | 1.06 | 90% | 10% | 0% | 36% |
| numpy.sort | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% |
| pandas.concat | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 9 | 22% | 40% | 1.22 | 100% | 0% | 0% | 52% | 9 | 22% | 40% | 1.22 | 100% | 0% | 0% | 52% |
| sort_values | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% |
| ALL | 81 | 3% | 16% | 1.00 | 98% | 1% | 1% | 64% | 81 | 3% | 16% | 1.00 | 98% | 1% | 1% | 64% |


### Tier 1: val-v3 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 5 | 0% | 0% | 5 | 0% | 0% |
| drop_duplicates | 4 | 0% | 25% | 4 | 0% | 25% |
| groupby | 6 | 0% | 0% | 6 | 0% | 0% |
| merge | 5 | 20% | 0% | 5 | 20% | 0% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 3 | 0% | 0% | 3 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 3 | 0% | 0% | 3 | 0% | 0% |
| ALL | 35 | 3% | 3% | 35 | 3% | 3% |


## Tier 1: val-v4 (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 21 | 1% | 100% | 1.00 | 86% | 14% | 0% | 35% | 21 | 1% | 1% | 1.00 | 100% | 0% | 0% | 35% |
| drop_duplicates | 14 | 15% | 54% | 1.13 | 93% | 0% | 7% | 56% | 14 | 15% | 54% | 1.13 | 93% | 0% | 7% | 56% |
| groupby | 17 | 2% | 17% | 1.01 | 94% | 0% | 6% | 60% | 17 | 2% | 17% | 1.01 | 94% | 0% | 6% | 60% |
| merge | 13 | 9% | 19% | 1.05 | 85% | 15% | 0% | 39% | 13 | 9% | 20% | 1.08 | 85% | 15% | 0% | 66% |
| numpy.sort | 3 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 3 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 8 | 4% | 6% | 0.96 | 100% | 0% | 0% | 123% | 8 | 4% | 6% | 0.96 | 100% | 0% | 0% | 123% |
| pandas.concat | 6 | 17% | 24% | 0.83 | 100% | 0% | 0% | 100% | 6 | 17% | 24% | 0.83 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 5 | 20% | 27% | 1.20 | 100% | 0% | 0% | 66% | 5 | 20% | 27% | 1.20 | 100% | 0% | 0% | 66% |
| sort_values | 6 | 0% | 1% | 1.00 | 100% | 0% | 0% | 37% | 6 | 0% | 1% | 1.00 | 100% | 0% | 0% | 37% |
| ALL | 93 | 4% | 28% | 1.00 | 92% | 5% | 2% | 58% | 93 | 3% | 24% | 1.01 | 96% | 2% | 2% | 61% |


### Tier 1: val-v4 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 8 | 12% | 0% | 8 | 0% | 0% |
| drop_duplicates | 6 | 0% | 17% | 6 | 0% | 17% |
| groupby | 7 | 0% | 14% | 7 | 0% | 14% |
| merge | 7 | 14% | 0% | 7 | 14% | 0% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.read_csv | 3 | 0% | 0% | 3 | 0% | 0% |
| sort_values | 2 | 0% | 0% | 2 | 0% | 0% |
| ALL | 39 | 5% | 5% | 39 | 3% | 5% |


## Tier 0: dev (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 16 | 12% | 43% | 1.00 | 100% | 0% | 0% | 103% | 16 | 12% | 43% | 1.00 | 100% | 0% | 0% | 103% |
| drop_duplicates | 17 | 17% | 35% | 1.08 | 100% | 0% | 0% | 101% | 17 | 17% | 35% | 1.08 | 100% | 0% | 0% | 101% |
| groupby | 10 | 52% | 135% | 1.52 | 100% | 0% | 0% | 155% | 10 | 52% | 135% | 1.52 | 100% | 0% | 0% | 155% |
| merge | 14 | 79% | 200% | 1.79 | 93% | 0% | 7% | 367% | 14 | 79% | 200% | 1.79 | 93% | 0% | 7% | 367% |
| numpy.sort | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% |
| pandas.concat | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 10 | 57% | 116% | 1.57 | 100% | 0% | 0% | 265% | 10 | 57% | 116% | 1.57 | 100% | 0% | 0% | 265% |
| sort_values | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| ALL | 109 | 8% | 93% | 1.01 | 99% | 0% | 1% | 146% | 109 | 8% | 93% | 1.01 | 99% | 0% | 1% | 146% |


### Tier 0: dev (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 8 | 0% | 0% | 8 | 0% | 0% |
| drop_duplicates | 6 | 0% | 0% | 6 | 0% | 0% |
| groupby | 5 | 0% | 0% | 5 | 0% | 0% |
| merge | 7 | 0% | 14% | 7 | 0% | 14% |
| numpy.sort | 4 | 0% | 0% | 4 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 4 | 0% | 0% | 4 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 5 | 0% | 0% | 5 | 0% | 0% |
| ALL | 46 | 0% | 2% | 46 | 0% | 2% |


## Tier 0: val-v3 (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 12 | 39% | 66% | 1.01 | 83% | 0% | 17% | 98% | 12 | 39% | 66% | 1.01 | 83% | 0% | 17% | 98% |
| drop_duplicates | 9 | 24% | 41% | 0.76 | 100% | 0% | 0% | 109% | 9 | 24% | 41% | 0.76 | 100% | 0% | 0% | 109% |
| groupby | 14 | 68% | 125% | 1.68 | 100% | 0% | 0% | 147% | 14 | 68% | 125% | 1.68 | 100% | 0% | 0% | 147% |
| merge | 10 | 51% | 131% | 1.51 | 90% | 0% | 10% | 363% | 10 | 51% | 131% | 1.51 | 90% | 0% | 10% | 363% |
| numpy.sort | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% |
| pandas.concat | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 9 | 40% | 122% | 1.21 | 100% | 0% | 0% | 265% | 9 | 40% | 122% | 1.21 | 100% | 0% | 0% | 265% |
| sort_values | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% |
| ALL | 81 | 19% | 92% | 1.00 | 96% | 0% | 4% | 156% | 81 | 19% | 92% | 1.00 | 96% | 0% | 4% | 156% |


### Tier 0: val-v3 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 5 | 0% | 20% | 5 | 0% | 20% |
| drop_duplicates | 4 | 0% | 0% | 4 | 0% | 0% |
| groupby | 6 | 0% | 0% | 6 | 0% | 0% |
| merge | 5 | 0% | 20% | 5 | 0% | 20% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 3 | 0% | 0% | 3 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 3 | 0% | 0% | 3 | 0% | 0% |
| ALL | 35 | 0% | 6% | 35 | 0% | 6% |


## Tier 0: val-v4 (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 21 | 18% | 72% | 1.01 | 90% | 0% | 10% | 98% | 21 | 18% | 72% | 1.01 | 90% | 0% | 10% | 98% |
| drop_duplicates | 14 | 13% | 27% | 0.95 | 100% | 0% | 0% | 110% | 14 | 13% | 27% | 0.95 | 100% | 0% | 0% | 110% |
| groupby | 17 | 59% | 124% | 1.59 | 94% | 0% | 6% | 142% | 17 | 59% | 124% | 1.59 | 94% | 0% | 6% | 142% |
| merge | 13 | 55% | 82% | 1.55 | 100% | 0% | 0% | 367% | 13 | 55% | 82% | 1.55 | 100% | 0% | 0% | 367% |
| numpy.sort | 3 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 3 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 8 | 4% | 6% | 0.96 | 100% | 0% | 0% | 123% | 8 | 4% | 6% | 0.96 | 100% | 0% | 0% | 123% |
| pandas.concat | 6 | 17% | 24% | 0.83 | 100% | 0% | 0% | 100% | 6 | 17% | 24% | 0.83 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 5 | 6% | 81% | 1.02 | 80% | 0% | 20% | 265% | 5 | 6% | 81% | 1.02 | 80% | 0% | 20% | 265% |
| sort_values | 6 | 0% | 1% | 1.00 | 100% | 0% | 0% | 37% | 6 | 0% | 1% | 1.00 | 100% | 0% | 0% | 37% |
| ALL | 93 | 17% | 84% | 1.00 | 96% | 0% | 4% | 151% | 93 | 17% | 84% | 1.00 | 96% | 0% | 4% | 151% |


### Tier 0: val-v4 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 8 | 0% | 12% | 8 | 0% | 12% |
| drop_duplicates | 6 | 0% | 0% | 6 | 0% | 0% |
| groupby | 7 | 0% | 14% | 7 | 0% | 14% |
| merge | 7 | 0% | 0% | 7 | 0% | 0% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.read_csv | 3 | 0% | 33% | 3 | 0% | 33% |
| sort_values | 2 | 0% | 0% | 2 | 0% | 0% |
| ALL | 39 | 0% | 8% | 39 | 0% | 8% |

