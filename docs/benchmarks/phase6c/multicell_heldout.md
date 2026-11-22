# Multi-statement cells: HELD-OUT part (read once)

22 cells run; 22 with a measured peak (others censored / killed: []).

## All cells

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new (cellpeak) | 22 | 11 | 1.17 | 17.2% | 102.3% | 63.6% | 0.0% | 0 | 0 | 36.4% | 3.04 |
| v1 (combine) | 22 | 11 | 1.00 | 6.0% | 84.0% | 86.4% | 0.0% | 0 | 0 | 13.6% | 6.05 |

* **above_high <= 3% of cells:** 0.0% -> MET
* **above_high <= 5% of configurations:** 0 of 11 -> MET

## Cells whose every operation has an estimate (descriptive)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new | 16 | 8 | 1.12 | 12.1% | 174.7% | 62.5% | 0.0% | 0 | 0 | 37.5% | 2.99 |
| v1 | 16 | 8 | 0.98 | 13.4% | 129.6% | 87.5% | 0.0% | 0 | 0 | 12.5% | 6.30 |

## Per template (new model)

| template | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width | v1_bias | uncovered_ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype_groupby | 2 | 1 | 1.11 | 11.4% | 12.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 2.85 | 0.96 | 0 |
| chain | 2 | 1 | 1.14 | 14.4% | 18.0% | 0.0% | 0.0% | 0 | 0 | 100.0% | 2.49 | 0.81 | 0 |
| concat_loads | 2 | 1 | 1.21 | 20.5% | 20.6% | 50.0% | 0.0% | 0 | 0 | 50.0% | 4.18 | 1.02 | 2 |
| copy_fillna | 2 | 1 | 1.17 | 17.2% | 17.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.37 | 1.04 | 2 |
| deletes | 2 | 1 | 0.99 | 1.1% | 1.7% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.55 | 0.99 | 0 |
| expressions | 2 | 1 | 0.99 | 1.1% | 1.7% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.82 | 0.99 | 0 |
| load_dtype_nrows | 2 | 1 | 3.59 | 259.4% | 269.2% | 0.0% | 0.0% | 0 | 0 | 100.0% | 4.48 | 2.85 | 0 |
| load_then_merge | 2 | 1 | 1.25 | 25.4% | 25.6% | 50.0% | 0.0% | 0 | 0 | 50.0% | 4.95 | 1.25 | 2 |
| loads2 | 2 | 1 | 1.17 | 17.4% | 17.6% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.70 | 0.97 | 0 |
| loads3_tsv | 2 | 1 | 2.02 | 102.1% | 102.3% | 0.0% | 0.0% | 0 | 0 | 100.0% | 5.15 | 1.84 | 0 |
| rebinding | 2 | 1 | 1.11 | 11.3% | 11.6% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.87 | 0.68 | 0 |

## Every cell (MiB)

| cell | actual | new low/exp/high | v1 exp/high | mode | uncovered |
|---|---|---|---|---|---|
| loads2/num@1000000 | 297 | 289 / 348 / 1578 | 287 / 3032 | statements | 0 |
| loads2/num@2000000 | 592 | 578 / 696 / 3155 | 574 / 6064 | statements | 0 |
| loads3_tsv/wide@1000000 | 501 | 555 / 1012 / 5770 | 920 / 8517 | statements | 0 |
| loads3_tsv/wide@2000000 | 1000 | 1110 / 2023 / 11540 | 1840 / 17034 | statements | 0 |
| load_dtype_nrows/wide@1000000 | 334 | 472 / 1161 / 5678 | 920 / 5678 | statements | 0 |
| load_dtype_nrows/wide@2000000 | 625 | 944 / 2322 / 11356 | 1840 / 11356 | statements | 0 |
| load_then_merge/wide@1000000 | 394 | 394 / 494 / 2839 | 494 / 2839 | statements | 1 |
| load_then_merge/wide@2000000 | 786 | 789 / 987 / 5678 | 987 / 5678 | statements | 1 |
| chain/mixed@1000000 | 85 | 97 / 101 / 336 | 69 / 529 | statements | 0 |
| chain/mixed@2000000 | 170 | 181 / 186 / 671 | 137 / 1058 | statements | 0 |
| deletes/num@1000000 | 78 | 75 / 76 / 116 | 76 / 309 | statements | 0 |
| deletes/num@2000000 | 153 | 150 / 153 / 233 | 153 / 619 | statements | 0 |
| copy_fillna/mixed@1000000 | 88 | 65 / 103 / 103 | 92 / 103 | statements | 1 |
| copy_fillna/mixed@2000000 | 176 | 130 / 206 / 206 | 183 / 206 | statements | 1 |
| expressions/num@1000000 | 78 | 75 / 76 / 366 | 76 / 544 | statements | 0 |
| expressions/num@2000000 | 153 | 150 / 153 / 732 | 153 / 1087 | statements | 0 |
| rebinding/mixed@1000000 | 193 | 190 / 214 / 376 | 130 / 681 | statements | 0 |
| rebinding/mixed@2000000 | 383 | 380 / 427 / 753 | 259 / 1362 | statements | 0 |
| concat_loads/wide@1000000 | 486 | 486 / 585 / 2931 | 494 / 5678 | statements | 1 |
| concat_loads/wide@2000000 | 970 | 971 / 1171 / 5862 | 987 / 11356 | statements | 1 |
| astype_groupby/num@1000000 | 31 | 29 / 35 / 103 | 31 / 155 | statements | 0 |
| astype_groupby/num@2000000 | 42 | 40 / 47 / 206 | 39 / 310 | statements | 0 |
