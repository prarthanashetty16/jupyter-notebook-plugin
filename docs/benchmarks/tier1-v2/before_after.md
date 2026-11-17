# Tier 1 before / after the 4b.2 fixes (development data only)

Identical measured actuals; `before` = predictions of the 4b models, `after` = the 4b.2 models. RAM, valid points, memory-limit lower bounds excluded. `val-v3` = the former held-out group: the fixes were informed by its failures, so its numbers are NOT evidence of generalisation (val-v4 is).


## Tier 1: dev (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 16 | 1% | 34% | 1.00 | 94% | 6% | 0% | 79% | 16 | 0% | 1% | 1.00 | 100% | 0% | 0% | 59% |
| drop_duplicates | 17 | 11% | 19% | 1.09 | 100% | 0% | 0% | 73% | 17 | 11% | 23% | 1.09 | 100% | 0% | 0% | 72% |
| groupby | 10 | 14% | 32% | 0.89 | 90% | 10% | 0% | 84% | 10 | 2% | 28% | 1.02 | 100% | 0% | 0% | 47% |
| merge | 14 | 6% | 10% | 1.04 | 93% | 0% | 7% | 56% | 14 | 7% | 19% | 1.06 | 93% | 0% | 7% | 62% |
| numpy.sort | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% |
| pandas.concat | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 10 | 22% | 26% | 1.22 | 100% | 0% | 0% | 59% | 10 | 22% | 26% | 1.22 | 100% | 0% | 0% | 59% |
| sort_values | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| ALL | 109 | 6% | 22% | 1.00 | 97% | 2% | 1% | 72% | 109 | 3% | 22% | 1.01 | 99% | 0% | 1% | 67% |


### Tier 1: dev (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 8 | 12% | 0% | 8 | 0% | 0% |
| drop_duplicates | 6 | 0% | 0% | 6 | 0% | 0% |
| groupby | 5 | 20% | 0% | 5 | 0% | 0% |
| merge | 7 | 0% | 14% | 7 | 0% | 14% |
| numpy.sort | 4 | 0% | 0% | 4 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 4 | 0% | 0% | 4 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 5 | 0% | 0% | 5 | 0% | 0% |
| ALL | 46 | 4% | 2% | 46 | 0% | 2% |


## Tier 1: val-v3 (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 12 | 1% | 33% | 1.00 | 83% | 17% | 0% | 72% | 12 | 1% | 3% | 1.00 | 100% | 0% | 0% | 45% |
| drop_duplicates | 9 | 3% | 18% | 1.03 | 89% | 0% | 11% | 62% | 9 | 3% | 18% | 1.03 | 89% | 0% | 11% | 63% |
| groupby | 14 | 6% | 37% | 1.01 | 86% | 14% | 0% | 84% | 14 | 1% | 12% | 1.01 | 100% | 0% | 0% | 60% |
| merge | 10 | 7% | 30% | 1.04 | 80% | 20% | 0% | 37% | 10 | 8% | 15% | 1.06 | 90% | 10% | 0% | 36% |
| numpy.sort | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% |
| pandas.concat | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 9 | 22% | 40% | 1.22 | 100% | 0% | 0% | 52% | 9 | 22% | 40% | 1.22 | 100% | 0% | 0% | 52% |
| sort_values | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% |
| ALL | 81 | 4% | 25% | 1.00 | 91% | 7% | 1% | 72% | 81 | 3% | 16% | 1.00 | 98% | 1% | 1% | 64% |


### Tier 1: val-v3 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 5 | 20% | 0% | 5 | 0% | 0% |
| drop_duplicates | 4 | 0% | 25% | 4 | 0% | 25% |
| groupby | 6 | 33% | 0% | 6 | 0% | 0% |
| merge | 5 | 20% | 0% | 5 | 20% | 0% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 3 | 0% | 0% | 3 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 3 | 0% | 0% | 3 | 0% | 0% |
| ALL | 35 | 11% | 3% | 35 | 3% | 3% |


## Tier 0: dev (per point)

| op | ram_n_before | ram_err_med_before | ram_err_p90_before | ram_bias_before | ram_cov_before | ram_above_high_before | ram_below_low_before | ram_width_before | ram_n_after | ram_err_med_after | ram_err_p90_after | ram_bias_after | ram_cov_after | ram_above_high_after | ram_below_low_after | ram_width_after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 16 | 12% | 50% | 1.00 | 100% | 0% | 0% | 110% | 16 | 12% | 43% | 1.00 | 100% | 0% | 0% | 103% |
| drop_duplicates | 17 | 17% | 35% | 1.08 | 100% | 0% | 0% | 101% | 17 | 17% | 35% | 1.08 | 100% | 0% | 0% | 101% |
| groupby | 10 | 49% | 135% | 1.49 | 100% | 0% | 0% | 171% | 10 | 52% | 135% | 1.52 | 100% | 0% | 0% | 155% |
| merge | 14 | 79% | 200% | 1.79 | 93% | 0% | 7% | 367% | 14 | 79% | 200% | 1.79 | 93% | 0% | 7% | 367% |
| numpy.sort | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 7 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% | 9 | 2% | 6% | 0.98 | 100% | 0% | 0% | 118% |
| pandas.concat | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% | 12 | 7% | 8% | 0.93 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 10 | 57% | 116% | 1.57 | 100% | 0% | 0% | 265% | 10 | 57% | 116% | 1.57 | 100% | 0% | 0% | 265% |
| sort_values | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% | 14 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| ALL | 109 | 8% | 93% | 1.01 | 99% | 0% | 1% | 148% | 109 | 8% | 93% | 1.01 | 99% | 0% | 1% | 146% |


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
| astype | 12 | 38% | 84% | 1.07 | 100% | 0% | 0% | 112% | 12 | 39% | 66% | 1.01 | 83% | 0% | 17% | 98% |
| drop_duplicates | 9 | 24% | 41% | 0.76 | 100% | 0% | 0% | 109% | 9 | 24% | 41% | 0.76 | 100% | 0% | 0% | 109% |
| groupby | 14 | 65% | 125% | 1.65 | 100% | 0% | 0% | 161% | 14 | 68% | 125% | 1.68 | 100% | 0% | 0% | 147% |
| merge | 10 | 51% | 131% | 1.51 | 90% | 0% | 10% | 363% | 10 | 51% | 131% | 1.51 | 90% | 0% | 10% | 363% |
| numpy.sort | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% | 2 | 0% | 0% | 1.00 | 100% | 0% | 0% | 40% |
| operator.matmul | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% | 7 | 3% | 5% | 0.97 | 100% | 0% | 0% | 136% |
| pandas.concat | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% | 9 | 4% | 11% | 0.96 | 100% | 0% | 0% | 100% |
| pandas.read_csv | 9 | 40% | 122% | 1.21 | 100% | 0% | 0% | 265% | 9 | 40% | 122% | 1.21 | 100% | 0% | 0% | 265% |
| sort_values | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% | 9 | 0% | 1% | 1.00 | 100% | 0% | 0% | 51% |
| ALL | 81 | 19% | 92% | 1.00 | 99% | 0% | 1% | 160% | 81 | 19% | 92% | 1.00 | 96% | 0% | 4% | 156% |


### Tier 0: val-v3 (per configuration: share with any point above high / below low)

| op | configs_before | cfg_above_high_before | cfg_below_low_before | configs_after | cfg_above_high_after | cfg_below_low_after |
|---|---|---|---|---|---|---|
| astype | 5 | 0% | 0% | 5 | 0% | 20% |
| drop_duplicates | 4 | 0% | 0% | 4 | 0% | 0% |
| groupby | 6 | 0% | 0% | 6 | 0% | 0% |
| merge | 5 | 0% | 20% | 5 | 0% | 20% |
| numpy.sort | 2 | 0% | 0% | 2 | 0% | 0% |
| operator.matmul | 2 | 0% | 0% | 2 | 0% | 0% |
| pandas.concat | 3 | 0% | 0% | 3 | 0% | 0% |
| pandas.read_csv | 5 | 0% | 0% | 5 | 0% | 0% |
| sort_values | 3 | 0% | 0% | 3 | 0% | 0% |
| ALL | 35 | 0% | 3% | 35 | 0% | 6% |

