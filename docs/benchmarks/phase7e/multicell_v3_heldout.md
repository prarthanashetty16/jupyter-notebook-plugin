# Multi-statement cells (v3, Phase 7): HELD-OUT part (read once)

64 cells run; 61 with a measured peak (others censored / killed: ['v3:set_index_ops/narrow@2500000', 'v3:value_counts_mix/textwide@1250000', 'v3:value_counts_mix/textwide@2500000']).

## All cells

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new (cellpeak) | 61 | 31 | 1.00 | 7.6% | 69.4% | 72.1% | 14.8% | 9 | 5 | 13.1% | 2.62 |
| v1 (combine) | 61 | 31 | 0.73 | 32.1% | 50.3% | 82.0% | 14.8% | 9 | 5 | 3.3% | 6.20 |

* **above_high <= 3% of cells:** 14.8% -> FAILED
* **above_high <= 5% of configurations:** 5 of 31 -> FAILED

## Cells whose every operation has an estimate (descriptive)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new | 53 | 27 | 1.00 | 2.9% | 60.0% | 75.5% | 9.4% | 5 | 3 | 15.1% | 2.81 |
| v1 | 53 | 27 | 0.73 | 32.1% | 49.1% | 86.8% | 9.4% | 5 | 3 | 3.8% | 6.96 |

## Per template (new model)

| template | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width | v1_bias | uncovered_ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| apply_ufunc | 4 | 2 | 0.99 | 1.0% | 1.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.30 | 0.58 | 0 |
| astype_on_created | 4 | 2 | 1.27 | 26.6% | 32.3% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.80 | 0.74 | 0 |
| chain_v3 | 4 | 2 | 1.73 | 72.9% | 107.1% | 0.0% | 0.0% | 0 | 0 | 100.0% | 2.66 | 1.05 | 0 |
| concat_then_sort | 4 | 2 | 1.00 | 0.1% | 0.1% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.74 | 0.51 | 0 |
| copy_then_fillna | 4 | 2 | 0.75 | 24.5% | 49.0% | 0.0% | 100.0% | 4 | 2 | 0.0% | 0.29 | 0.54 | 2 |
| deletes_v3 | 4 | 2 | 0.99 | 1.0% | 1.9% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.81 | 0.99 | 0 |
| groupby_on_created | 4 | 2 | 1.26 | 26.3% | 35.6% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.70 | 0.88 | 0 |
| load_fillna_text | 4 | 2 | 1.00 | 1.1% | 10.4% | 100.0% | 0.0% | 0 | 0 | 0.0% | 4.31 | 1.00 | 2 |
| load_then_merge_left | 4 | 2 | 1.11 | 12.3% | 24.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 4.99 | 1.11 | 0 |
| loads_args | 4 | 2 | 0.90 | 9.6% | 11.9% | 100.0% | 0.0% | 0 | 0 | 0.0% | 13.38 | 0.60 | 0 |
| loads_tsv_dtype | 4 | 2 | 0.99 | 1.8% | 5.8% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.45 | 0.80 | 0 |
| rebinding_alias | 4 | 2 | 1.25 | 24.7% | 26.6% | 0.0% | 0.0% | 0 | 0 | 100.0% | 0.50 | 0.57 | 0 |
| rebinding_v3 | 4 | 2 | 1.00 | 0.1% | 0.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.68 | 0.68 | 0 |
| set_index_ops | 3 | 2 | 0.00 | 100.0% | 100.0% | 66.7% | 33.3% | 1 | 1 | 0.0% | - | 0.00 | 0 |
| text_fillna_cols | 4 | 2 | 0.65 | 35.0% | 69.4% | 0.0% | 100.0% | 4 | 2 | 0.0% | 0.00 | 0.55 | 2 |
| value_counts_mix | 2 | 1 | 1.09 | 9.4% | 13.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 2.84 | 1.09 | 4 |

## Uncovered-operation rule (amendment 1): a cell with an uncovered operation must never be OK

at a simulated headroom its ACTUAL exceeds (UNKNOWN, WARN and HIGH_RISK are acceptable).

Cells with an uncovered operation: 8; violations (OK while actual > headroom): 0 -> MET

## Every cell (MiB)

| cell | actual | new low/exp/high | v1 exp/high | mode | uncovered |
|---|---|---|---|---|---|
| v3:loads_args/text@1250000 | 88 | 65 / 80 / 1216 | 51 / 2373 | statements | 0 |
| v3:loads_args/text@2500000 | 161 | 130 / 148 / 2431 | 91 / 4746 | statements | 0 |
| v3:loads_args/textwide@1250000 | 120 | 80 / 109 / 1323 | 80 / 2588 | statements | 0 |
| v3:loads_args/textwide@2500000 | 236 | 159 / 206 / 2646 | 148 / 5177 | statements | 0 |
| v3:load_fillna_text/num@1250000 | 295 | 232 / 292 / 1895 | 292 / 1967 | statements | 0 |
| v3:load_fillna_text/num@2500000 | 587 | 465 / 584 / 3791 | 584 / 3934 | statements | 0 |
| v3:load_fillna_text/narrow@1250000 | 183 | 143 / 186 / 685 | 186 / 685 | statements | 1 |
| v3:load_fillna_text/narrow@2500000 | 324 | 286 / 371 / 1369 | 371 / 1369 | statements | 1 |
| v3:text_fillna_cols/num@1250000 | 91 | 91 / 91 / 91 | 72 / 91 | statements | 0 |
| v3:text_fillna_cols/num@2500000 | 182 | 181 / 181 / 181 | 143 / 181 | statements | 0 |
| v3:text_fillna_cols/mixed@1250000 | 62 | 19 / 19 / 19 | 19 / 19 | statements | 1 |
| v3:text_fillna_cols/mixed@2500000 | 124 | 38 / 38 / 38 | 38 / 38 | statements | 1 |
| v3:load_then_merge_left/num@1250000 | 295 | 232 / 292 / 1895 | 292 / 2353 | statements | 0 |
| v3:load_then_merge_left/num@2500000 | 587 | 465 / 584 / 3791 | 584 / 4707 | statements | 0 |
| v3:load_then_merge_left/mixed@1250000 | 252 | 248 / 311 / 1580 | 311 / 2000 | statements | 0 |
| v3:load_then_merge_left/mixed@2500000 | 500 | 496 / 622 / 3160 | 622 / 3999 | statements | 0 |
| v3:concat_then_sort/wide@1250000 | 525 | 491 / 525 / 854 | 267 / 854 | statements | 0 |
| v3:concat_then_sort/wide@2500000 | 1050 | 981 / 1049 / 1707 | 534 / 1707 | statements | 0 |
| v3:concat_then_sort/textwide@1250000 | 334 | 302 / 334 / 567 | 172 / 567 | statements | 0 |
| v3:concat_then_sort/textwide@2500000 | 668 | 603 / 668 / 1135 | 343 / 1135 | statements | 0 |
| v3:copy_then_fillna/wide@1250000 | 272 | 114 / 272 / 272 | 157 / 272 | statements | 0 |
| v3:copy_then_fillna/wide@2500000 | 544 | 229 / 544 / 544 | 315 / 544 | statements | 0 |
| v3:copy_then_fillna/text@1250000 | 112 | 57 / 57 / 57 | 57 / 57 | statements | 1 |
| v3:copy_then_fillna/text@2500000 | 224 | 114 / 114 / 114 | 114 / 114 | statements | 1 |
| v3:set_index_ops/wide@1250000 | 0 | 0 / 0 / 10 | 0 / 19 | statements | 0 |
| v3:set_index_ops/wide@2500000 | 0 | 0 / 0 / 19 | 0 / 38 | statements | 0 |
| v3:set_index_ops/narrow@1250000 | 10 | 0 / 0 / 5 | 0 / 10 | statements | 0 |
| v3:set_index_ops/narrow@2500000 | - | 0 / 0 / 10 | 0 / 19 | statements | 0 |
| v3:apply_ufunc/text@1250000 | 19 | 16 / 19 / 22 | 10 / 22 | statements | 0 |
| v3:apply_ufunc/text@2500000 | 38 | 32 / 38 / 44 | 19 / 44 | statements | 0 |
| v3:apply_ufunc/narrow@1250000 | 15 | 12 / 14 / 16 | 10 / 16 | statements | 0 |
| v3:apply_ufunc/narrow@2500000 | 29 | 24 / 29 / 33 | 19 / 33 | statements | 0 |
| v3:deletes_v3/wide@1250000 | 135 | 131 / 134 / 610 | 134 / 957 | statements | 0 |
| v3:deletes_v3/wide@2500000 | 269 | 262 / 267 / 1221 | 267 / 1914 | statements | 0 |
| v3:deletes_v3/text@1250000 | 78 | 75 / 76 / 381 | 76 / 602 | statements | 0 |
| v3:deletes_v3/text@2500000 | 154 | 150 / 153 / 763 | 153 / 1204 | statements | 0 |
| v3:rebinding_v3/wide@1250000 | 382 | 353 / 381 / 610 | 257 / 968 | statements | 0 |
| v3:rebinding_v3/wide@2500000 | 763 | 706 / 763 / 1221 | 515 / 1936 | statements | 0 |
| v3:rebinding_v3/textwide@1250000 | 239 | 210 / 238 / 372 | 162 / 634 | statements | 0 |
| v3:rebinding_v3/textwide@2500000 | 477 | 420 / 477 / 744 | 324 / 1268 | statements | 0 |
| v3:rebinding_alias/num@1250000 | 173 | 176 / 212 / 279 | 95 / 339 | statements | 0 |
| v3:rebinding_alias/num@2500000 | 336 | 339 / 424 / 559 | 191 / 678 | statements | 0 |
| v3:rebinding_alias/text@1250000 | 134 | 138 / 165 / 218 | 76 / 278 | statements | 0 |
| v3:rebinding_alias/text@2500000 | 260 | 263 / 329 / 437 | 153 / 556 | statements | 0 |
| v3:chain_v3/narrow@1250000 | 46 | 86 / 100 / 308 | 63 / 410 | statements | 0 |
| v3:chain_v3/narrow@2500000 | 91 | 146 / 166 / 591 | 100 / 820 | statements | 0 |
| v3:chain_v3/textwide@1250000 | 87 | 129 / 142 / 502 | 86 / 661 | statements | 0 |
| v3:chain_v3/textwide@2500000 | 172 | 229 / 248 / 1001 | 172 / 1323 | statements | 0 |
| v3:groupby_on_created/narrow@1250000 | 57 | 54 / 77 / 122 | 50 / 181 | statements | 0 |
| v3:groupby_on_created/narrow@2500000 | 112 | 107 / 153 / 243 | 100 / 362 | statements | 0 |
| v3:groupby_on_created/textwide@1250000 | 104 | 94 / 115 / 153 | 86 / 212 | statements | 0 |
| v3:groupby_on_created/textwide@2500000 | 193 | 188 / 230 / 305 | 172 / 424 | statements | 0 |
| v3:astype_on_created/num@1250000 | 104 | 96 / 129 / 198 | 76 / 255 | statements | 0 |
| v3:astype_on_created/num@2500000 | 193 | 191 / 257 / 397 | 153 / 511 | statements | 0 |
| v3:astype_on_created/text@1250000 | 85 | 77 / 100 / 156 | 57 / 214 | statements | 0 |
| v3:astype_on_created/text@2500000 | 154 | 153 / 200 / 313 | 114 / 427 | statements | 0 |
| v3:loads_tsv_dtype/num@1250000 | 366 | 303 / 363 / 1968 | 292 / 3791 | statements | 0 |
| v3:loads_tsv_dtype/num@2500000 | 730 | 606 / 727 / 3935 | 583 / 7582 | statements | 0 |
| v3:loads_tsv_dtype/narrow@1250000 | 253 | 198 / 246 / 765 | 186 / 1369 | statements | 0 |
| v3:loads_tsv_dtype/narrow@2500000 | 459 | 395 / 492 / 1531 | 371 / 2739 | statements | 0 |
| v3:value_counts_mix/mixed@1250000 | 29 | 27 / 33 / 95 | 33 / 95 | statements | 1 |
| v3:value_counts_mix/mixed@2500000 | 41 | 36 / 43 / 191 | 43 / 191 | statements | 1 |
| v3:value_counts_mix/textwide@1250000 | - | 27 / 33 / 76 | 33 / 76 | statements | 1 |
| v3:value_counts_mix/textwide@2500000 | - | 36 / 43 / 153 | 43 / 153 | statements | 1 |
