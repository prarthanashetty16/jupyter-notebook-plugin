# Before/after: measurement instrument v1 (polling) vs v2 (OS peak + disk setup)

## Pooled Tier 0 accuracy

| metric | run | points | valid | censored | excluded | median_err | p90_err | bias | coverage | width |
|---|---|---|---|---|---|---|---|---|---|---|
| RAM | before | 87 | 53 | n/a | 34 | 92% | 558% | 1.92 | 70% | 243% |
| RAM | after | 82 | 46 | 36 | 0 | 64% | 268% | 1.35 | 78% | 197% |
| TIME | before | 87 | 35 | n/a | 52 | 69% | 472% | 1.65 | 80% | 378% |
| TIME | after | 82 | 37 | 45 | 0 | 64% | 85% | 0.38 | 81% | 378% |


## Per operation: RAM bias (expected/actual) and coverage

| op | ram_bias_v1 | ram_cov_v1 | ram_n_v1 | ram_bias_v2 | ram_cov_v2 | ram_n_v2 | verdict |
|---|---|---|---|---|---|---|---|
| ALL | 1.92 | 70% | 53 | 1.35 | 78% | 46.00 | unchanged (ok) |
| astype | 0.69 | 71% | 7 | 0.62 | 80% | 5.00 | unchanged (ok) |
| drop_duplicates | 1.59 | 100% | 8 | 1.55 | 91% | 11.00 | unchanged (ok) |
| groupby | 4.08 | 100% | 4 | 2.09 | 100% | 4.00 | unchanged (bad) |
| merge | 6.33 | 45% | 11 | 5.16 | 100% | 5.00 | unchanged (bad) |
| numpy.sort | 1.02 | 100% | 1 | – | – | – | no valid v2 points |
| operator.matmul | 3.61 | 100% | 3 | 0.96 | 100% | 2.00 | now ok |
| pandas.concat | 1.32 | 50% | 4 | 1.41 | 50% | 4.00 | unchanged (ok) |
| pandas.read_csv | 0.63 | 100% | 9 | 0.37 | 100% | 9.00 | now bad |
| sort_values | 2.40 | 0% | 6 | 2.27 | 0% | 6.00 | unchanged (bad) |


## Per operation: TIME bias (expected/actual) and coverage

| op | time_bias_v1 | time_cov_v1 | time_n_v1 | time_bias_v2 | time_cov_v2 | time_n_v2 | verdict |
|---|---|---|---|---|---|---|---|
| ALL | 1.65 | 80% | 35 | 0.38 | 81% | 37.00 | now bad |
| astype | 1.26 | 100% | 4 | 0.60 | 50% | 4.00 | unchanged (ok) |
| drop_duplicates | 0.93 | 100% | 8 | 0.35 | 75% | 12.00 | now bad |
| groupby | 0.67 | 67% | 3 | 0.32 | 67% | 3.00 | now bad |
| merge | 1.59 | 86% | 7 | 0.41 | 100% | 2.00 | now bad |
| numpy.sort | – | – | 0 | – | – | – | no valid v2 points |
| operator.matmul | 6.01 | 0% | 1 | 0.81 | 100% | 1.00 | now ok |
| pandas.concat | 1.35 | 100% | 1 | 0.16 | 0% | 1.00 | now bad |
| pandas.read_csv | 2.40 | 67% | 6 | 0.37 | 100% | 7.00 | unchanged (bad) |
| sort_values | 1.95 | 60% | 5 | 0.45 | 100% | 7.00 | now bad |


## Time: effect of calibration alone (same v2 measurements)

| time model | valid | median_err | p90_err | bias | coverage |
|---|---|---|---|---|---|
| default constants | 37 | 66% | 335% | 1.25 | 81% |
| calibrated constants | 37 | 64% | 85% | 0.38 | 81% |


Verdict thresholds: bias within 0.5x-2x counts as ok. v1 numbers came from the unreliable polling instrument; v2 numbers are the provisional-but-trustworthy ones.
