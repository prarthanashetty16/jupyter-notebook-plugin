# Multi-statement cells (Phase 8c): HELD-OUT part (read once)

64 cells run; 54 with a measured peak (others censored / killed: ['v4:set_index_ops/textwide@1500000', 'v4:set_index_ops/textwide@3000000', 'v4:set_index_ops/indexheavy@1500000', 'v4:set_index_ops/indexheavy@3000000', 'v4:apply_ufunc/textwide@1500000', 'v4:apply_ufunc/textwide@3000000', 'v4:deletes_v4/balanced@1500000', 'v4:deletes_v4/balanced@3000000', 'v4:deletes_v4/skewed@1500000', 'v4:deletes_v4/skewed@3000000']).

## Fully covered cells (above-high criteria; partial cells excluded)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new (cellpeak) | 22 | 11 | 1.16 | 15.5% | 40.6% | 81.8% | 0.0% | 0 | 0 | 18.2% | 4.25 |
| v1 (combine) | 22 | 11 | 0.99 | 17.1% | 47.7% | 100.0% | 0.0% | 0 | 0 | 0.0% | 10.42 |

* **above_high <= 3% of cells:** 0.0% -> MET
* **above_high <= 3% of configurations:** 0 of 11 (0.0%) -> MET

## Cells whose every operation has an estimate (descriptive)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new | 22 | 11 | 1.16 | 15.5% | 40.6% | 81.8% | 0.0% | 0 | 0 | 18.2% | 4.25 |
| v1 | 22 | 11 | 0.99 | 17.1% | 47.7% | 100.0% | 0.0% | 0 | 0 | 0.0% | 10.42 |

## Per template (new model)

| template | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width | v1_bias | uncovered_ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| apply_ufunc | 2 | 1 | 0.99 | 1.0% | 1.3% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.30 | 0.66 | 0 |
| astype_on_created | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| chain_v4 | 4 | 2 | 1.55 | 54.8% | 85.9% | 0.0% | 0.0% | 0 | 0 | 100.0% | 3.12 | 1.00 | 0 |
| concat_then_sort | 4 | 2 | 1.00 | 0.2% | 0.3% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.87 | 0.52 | 0 |
| copy_then_fillna | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| deletes_v4 | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| groupby_on_created | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| load_fillna_text | 4 | 2 | 1.17 | 16.5% | 16.8% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.46 | 1.17 | 0 |
| load_then_merge_left | 4 | 2 | 1.16 | 16.4% | 17.2% | 100.0% | 0.0% | 0 | 0 | 0.0% | 3.52 | 1.16 | 0 |
| loads_args | 4 | 2 | 0.90 | 10.1% | 13.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 12.28 | 0.60 | 0 |
| partial_get_dummies | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| partial_map | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| rebinding_alias | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| rebinding_v4 | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| set_index_ops | 0 | None | None | None | None | None | None | None | None | None | None | - | 0 |
| text_fillna_cols | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |

## Partial-cell scoring (Phase 8 preregistration Amendment 7)

Cells: 28 fully covered, 36 partial, 0 wholly uncovered.
Partial cells scored with measured actuals and a covered estimate: 32.
Partial lower-bound violations (displayed low > actual): 0 -> MET
Partial risk violations (OK while actual > simulated headroom): 0 -> MET
Wholly uncovered cells with actuals and risk classes: 0; violations: 0 -> MET

## Every cell (MiB)

| cell | actual | new low/exp/high | v1 exp/high | mode | uncovered |
|---|---|---|---|---|---|
| v4:loads_args/textwide@1500000 | 173 | 124 / 152 / 1823 | 117 / 3577 | statements | 0 |
| v4:loads_args/textwide@3000000 | 343 | 247 / 296 / 3646 | 227 / 7154 | statements | 0 |
| v4:loads_args/skewed@1500000 | 91 | 72 / 83 / 1143 | 49 / 2217 | statements | 0 |
| v4:loads_args/skewed@3000000 | 165 | 144 / 157 / 2287 | 89 / 4433 | statements | 0 |
| v4:load_fillna_text/balanced@1500000 | 235 | 215 / 273 / 1178 | 273 / 1224 | statements | 0 |
| v4:load_fillna_text/balanced@3000000 | 468 | 430 / 547 / 2357 | 547 / 2448 | statements | 0 |
| v4:load_fillna_text/skewed@1500000 | 230 | 208 / 265 / 1108 | 265 / 1154 | statements | 0 |
| v4:load_fillna_text/skewed@3000000 | 454 | 417 / 530 / 2217 | 530 / 2308 | statements | 0 |
| v4:text_fillna_cols/indexheavy@1500000 | 78 | at least 23 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:text_fillna_cols/indexheavy@3000000 | 155 | at least 46 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:text_fillna_cols/skewed@1500000 | 78 | at least 23 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:text_fillna_cols/skewed@3000000 | 155 | at least 46 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:load_then_merge_left/balanced@1500000 | 236 | 215 / 273 / 1178 | 273 / 1636 | statements | 0 |
| v4:load_then_merge_left/balanced@3000000 | 468 | 430 / 547 / 2357 | 547 / 3272 | statements | 0 |
| v4:load_then_merge_left/nullable@1500000 | 235 | 214 / 272 / 1170 | 272 / 1628 | statements | 0 |
| v4:load_then_merge_left/nullable@3000000 | 464 | 428 / 545 / 2339 | 545 / 3255 | statements | 0 |
| v4:concat_then_sort/textwide@1500000 | 499 | 458 / 498 / 827 | 255 / 827 | statements | 0 |
| v4:concat_then_sort/textwide@3000000 | 996 | 917 / 996 / 1654 | 509 / 1654 | statements | 0 |
| v4:concat_then_sort/narrow@1500000 | 235 | 198 / 235 / 432 | 123 / 432 | statements | 0 |
| v4:concat_then_sort/narrow@3000000 | 470 | 396 / 469 / 864 | 246 / 864 | statements | 0 |
| v4:copy_then_fillna/nullable@1500000 | 130 | at least 62 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:copy_then_fillna/nullable@3000000 | 261 | at least 123 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:copy_then_fillna/narrow@1500000 | 76 | at least 39 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:copy_then_fillna/narrow@3000000 | 152 | at least 77 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:set_index_ops/textwide@1500000 | - | 0 / 0 / 11 | 0 / 23 | statements | 0 |
| v4:set_index_ops/textwide@3000000 | - | 0 / 0 / 23 | 0 / 46 | statements | 0 |
| v4:set_index_ops/indexheavy@1500000 | - | 0 / 0 / 11 | 0 / 23 | statements | 0 |
| v4:set_index_ops/indexheavy@3000000 | - | 0 / 0 / 23 | 0 / 46 | statements | 0 |
| v4:apply_ufunc/textwide@1500000 | - | 19 / 23 / 26 | 11 / 26 | statements | 0 |
| v4:apply_ufunc/textwide@3000000 | - | 39 / 46 / 53 | 23 / 53 | statements | 0 |
| v4:apply_ufunc/narrow@1500000 | 17 | 15 / 17 / 20 | 11 / 20 | statements | 0 |
| v4:apply_ufunc/narrow@3000000 | 35 | 29 / 34 / 39 | 23 / 39 | statements | 0 |
| v4:deletes_v4/balanced@1500000 | - | at least 80 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:deletes_v4/balanced@3000000 | - | at least 160 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:deletes_v4/skewed@1500000 | - | at least 80 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:deletes_v4/skewed@3000000 | - | at least 160 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:rebinding_v4/balanced@1500000 | 231 | at least 187 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_v4/balanced@3000000 | 453 | at least 375 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_v4/indexheavy@1500000 | 220 | at least 187 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_v4/indexheavy@3000000 | 430 | at least 375 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_alias/nullable@1500000 | 179 | at least 149 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_alias/nullable@3000000 | 336 | at least 284 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_alias/indexheavy@1500000 | 173 | at least 143 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:rebinding_alias/indexheavy@3000000 | 325 | at least 273 (covers 4 of 5) | not scored (partial) | statements | 1 |
| v4:chain_v4/nullable@1500000 | 85 | 112 / 121 / 507 | 84 / 678 | statements | 0 |
| v4:chain_v4/nullable@3000000 | 170 | 195 / 207 / 1013 | 169 / 1357 | statements | 0 |
| v4:chain_v4/narrow@1500000 | 62 | 106 / 120 / 391 | 69 / 536 | statements | 0 |
| v4:chain_v4/narrow@3000000 | 124 | 184 / 206 / 781 | 123 / 1073 | statements | 0 |
| v4:groupby_on_created/nullable@1500000 | 103 | at least 94 (covers 2 of 3) | not scored (partial) | statements | 1 |
| v4:groupby_on_created/nullable@3000000 | 194 | at least 189 (covers 2 of 3) | not scored (partial) | statements | 1 |
| v4:groupby_on_created/textwide@1500000 | 146 | at least 137 (covers 2 of 3) | not scored (partial) | statements | 1 |
| v4:groupby_on_created/textwide@3000000 | 280 | at least 275 (covers 2 of 3) | not scored (partial) | statements | 1 |
| v4:astype_on_created/balanced@1500000 | 219 | at least 87 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:astype_on_created/balanced@3000000 | 433 | at least 160 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:astype_on_created/nullable@1500000 | 222 | at least 96 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:astype_on_created/nullable@3000000 | 439 | at least 169 (covers 3 of 4) | not scored (partial) | statements | 1 |
| v4:partial_map/narrow@1500000 | 151 | at least 29 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_map/narrow@3000000 | 301 | at least 43 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_map/indexheavy@1500000 | 151 | at least 29 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_map/indexheavy@3000000 | 301 | at least 43 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_get_dummies/nullable@1500000 | 91 | at least 6 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_get_dummies/nullable@3000000 | 180 | at least 11 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_get_dummies/narrow@1500000 | 19 | at least 6 (covers 1 of 2) | not scored (partial) | statements | 1 |
| v4:partial_get_dummies/narrow@3000000 | 38 | at least 11 (covers 1 of 2) | not scored (partial) | statements | 1 |
