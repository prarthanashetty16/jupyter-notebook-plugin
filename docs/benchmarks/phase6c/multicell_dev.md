# Multi-statement cells: DEV part (Phase 6c; not validation)

44 cells run; 44 with a measured peak (others censored / killed: []).

## All cells

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new (cellpeak) | 44 | 22 | 1.13 | 12.6% | 77.4% | 63.6% | 0.0% | 0 | 0 | 36.4% | 2.87 |
| v1 (combine) | 44 | 22 | 0.99 | 17.8% | 57.8% | 93.2% | 0.0% | 0 | 0 | 6.8% | 5.84 |

* **above_high <= 3% of cells:** 0.0% -> MET
* **above_high <= 5% of configurations:** 0 of 22 -> MET

## Cells whose every operation has an estimate (descriptive)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new | 36 | 18 | 1.11 | 11.3% | 114.0% | 55.6% | 0.0% | 0 | 0 | 44.4% | 2.62 |
| v1 | 36 | 18 | 0.99 | 24.7% | 78.2% | 91.7% | 0.0% | 0 | 0 | 8.3% | 5.59 |

## Per template (new model)

| template | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width | v1_bias | uncovered_ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype_groupby | 4 | 2 | 1.12 | 12.4% | 12.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 2.99 | 97.1% | 0 |
| chain | 4 | 2 | 1.11 | 10.9% | 15.6% | 0.0% | 0.0% | 0 | 0 | 100.0% | 2.58 | 84.4% | 0 |
| concat_loads | 4 | 2 | 1.16 | 16.0% | 17.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.61 | 94.9% | 4 |
| copy_fillna | 4 | 2 | 1.07 | 7.4% | 9.6% | 0.0% | 0.0% | 0 | 0 | 100.0% | 0.00 | 54.7% | 0 |
| deletes | 4 | 2 | 0.99 | 0.8% | 1.8% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.50 | 99.2% | 0 |
| expressions | 4 | 2 | 1.15 | 16.2% | 32.3% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.26 | 115.5% | 0 |
| load_dtype_nrows | 4 | 2 | 2.91 | 191.5% | 219.9% | 0.0% | 0.0% | 0 | 0 | 100.0% | 4.48 | 231.0% | 0 |
| load_then_merge | 4 | 2 | 1.22 | 21.7% | 23.7% | 100.0% | 0.0% | 0 | 0 | 0.0% | 4.38 | 121.7% | 4 |
| loads2 | 4 | 2 | 1.17 | 17.5% | 20.6% | 75.0% | 0.0% | 0 | 0 | 25.0% | 3.84 | 97.2% | 0 |
| loads3_tsv | 4 | 2 | 1.71 | 71.0% | 77.4% | 25.0% | 0.0% | 0 | 0 | 75.0% | 4.98 | 151.0% | 0 |
| rebinding | 4 | 2 | 1.08 | 8.5% | 10.1% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.90 | 67.3% | 0 |

## Every cell (MiB)

| cell | actual | new low/exp/high | v1 exp/high | mode | uncovered |
|---|---|---|---|---|---|
| loads2/mixed@1000000 | 28203.9% | 256 / 307 / 1334 | 249 / 2528 | statements | 0 |
| loads2/mixed@2000000 | 53585.5% | 511 / 614 / 2667 | 498 / 5055 | statements | 0 |
| loads2/wide@1000000 | 48627.0% | 486 / 585 / 2931 | 494 / 5678 | statements | 0 |
| loads2/wide@2000000 | 96974.6% | 971 / 1171 / 5862 | 987 / 11356 | statements | 0 |
| loads3_tsv/num@1000000 | 31203.5% | 326 / 552 / 3094 | 491 / 4548 | statements | 0 |
| loads3_tsv/num@2000000 | 62208.2% | 653 / 1105 / 6188 | 983 / 9097 | statements | 0 |
| loads3_tsv/mixed@1000000 | 29773.4% | 287 / 468 / 2597 | 410 / 3791 | statements | 0 |
| loads3_tsv/mixed@2000000 | 56677.3% | 573 / 935 / 5194 | 819 / 7583 | statements | 0 |
| load_dtype_nrows/num@1000000 | 21313.7% | 252 / 620 / 3032 | 491 / 3032 | statements | 0 |
| load_dtype_nrows/num@2000000 | 37363.7% | 504 / 1240 / 6064 | 983 / 6064 | statements | 0 |
| load_dtype_nrows/mixed@1000000 | 20638.3% | 210 / 517 / 2528 | 410 / 2528 | statements | 0 |
| load_dtype_nrows/mixed@2000000 | 35387.9% | 420 / 1034 / 5055 | 819 / 5055 | statements | 0 |
| load_then_merge/num@1000000 | 23654.7% | 229 / 287 / 1516 | 287 / 1516 | statements | 1 |
| load_then_merge/num@2000000 | 46989.8% | 457 / 574 / 3032 | 574 / 3032 | statements | 1 |
| load_then_merge/mixed@1000000 | 21488.7% | 198 / 249 / 1264 | 249 / 1264 | statements | 1 |
| load_then_merge/mixed@2000000 | 40005.9% | 396 / 498 / 2527 | 498 / 2527 | statements | 1 |
| chain/num@1000000 | 9331.6% | 105 / 109 / 366 | 76 / 576 | statements | 0 |
| chain/num@2000000 | 18485.5% | 196 / 202 / 732 | 153 / 1153 | statements | 0 |
| chain/wide@1000000 | 12383.2% | 136 / 140 / 488 | 107 / 766 | statements | 0 |
| chain/wide@2000000 | 24589.1% | 257 / 263 / 977 | 214 / 1531 | statements | 0 |
| deletes/mixed@1000000 | 7010.2% | 67 / 69 / 109 | 69 / 270 | statements | 0 |
| deletes/mixed@2000000 | 13780.9% | 135 / 137 / 217 | 137 / 539 | statements | 0 |
| deletes/wide@1000000 | 10822.3% | 105 / 107 / 147 | 107 / 407 | statements | 0 |
| deletes/wide@2000000 | 21407.8% | 209 / 214 / 294 | 214 / 814 | statements | 0 |
| copy_fillna/num@1000000 | 11843.8% | 130 / 130 / 130 | 61 / 130 | statements | 0 |
| copy_fillna/num@2000000 | 23669.9% | 259 / 259 / 259 | 122 / 259 | statements | 0 |
| copy_fillna/wide@1000000 | 21762.5% | 229 / 229 / 229 | 126 / 229 | statements | 0 |
| copy_fillna/wide@2000000 | 43502.0% | 458 / 458 / 458 | 252 / 458 | statements | 0 |
| expressions/mixed@1000000 | 6982.0% | 67 / 92 / 336 | 92 / 536 | statements | 0 |
| expressions/mixed@2000000 | 13780.9% | 135 / 183 / 671 | 183 / 1072 | statements | 0 |
| expressions/wide@1000000 | 10822.7% | 105 / 107 / 488 | 107 / 727 | statements | 0 |
| expressions/wide@2000000 | 21408.2% | 209 / 214 / 977 | 214 / 1453 | statements | 0 |
| rebinding/num@1000000 | 21542.6% | 213 / 237 / 422 | 145 / 750 | statements | 0 |
| rebinding/num@2000000 | 42903.5% | 426 / 473 / 845 | 290 / 1499 | statements | 0 |
| rebinding/wide@1000000 | 30697.7% | 305 / 328 / 606 | 206 / 1024 | statements | 0 |
| rebinding/wide@2000000 | 61213.7% | 609 / 656 / 1214 | 412 / 2048 | statements | 0 |
| concat_loads/num@1000000 | 29635.9% | 289 / 348 / 1578 | 287 / 3032 | statements | 1 |
| concat_loads/num@2000000 | 59163.7% | 578 / 696 / 3155 | 574 / 6064 | statements | 1 |
| concat_loads/mixed@1000000 | 28243.4% | 256 / 307 / 1334 | 249 / 2528 | statements | 1 |
| concat_loads/mixed@2000000 | 53574.2% | 511 / 614 / 2667 | 498 / 5055 | statements | 1 |
| astype_groupby/mixed@1000000 | 3079.7% | 29 / 35 / 80 | 31 / 132 | statements | 0 |
| astype_groupby/mixed@2000000 | 4147.3% | 40 / 47 / 160 | 39 / 265 | statements | 0 |
| astype_groupby/wide@1000000 | 3082.8% | 29 / 35 / 134 | 31 / 186 | statements | 0 |
| astype_groupby/wide@2000000 | 4228.1% | 40 / 47 / 267 | 39 / 371 | statements | 0 |

## Note (2026-11-22, Phase 6d profile audit)

The predictions of these cells were made with a corrupted machine profile. This report evaluates RAM only, which does not depend on the profile; a prediction re-run with the restored profile reproduced every RAM figure exactly (`results_restored_profile.jsonl`). No number here changes.
