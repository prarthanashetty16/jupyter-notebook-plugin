# Multi-statement cells (v2, Phase 7): HELD-OUT part (read once)

30 cells run; 28 with a measured peak (others censored / killed: ['v2:text_fillna/mixed@1500000', 'v2:text_fillna/mixed@3000000']).

## All cells

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new (cellpeak) | 28 | 14 | 1.00 | 15.5% | 92.9% | 71.4% | 21.4% | 6 | 3 | 7.1% | 5.15 |
| v1 (combine) | 28 | 14 | 0.87 | 16.0% | 92.9% | 75.0% | 21.4% | 6 | 3 | 3.6% | 8.85 |

* **above_high <= 3% of cells:** 21.4% -> FAILED
* **above_high <= 5% of configurations:** 3 of 14 -> FAILED

## Cells whose every operation has an estimate (descriptive)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| new | 16 | 8 | 1.15 | 15.5% | 48.6% | 93.8% | 0.0% | 0 | 0 | 6.2% | 6.00 |
| v1 | 16 | 8 | 0.94 | 13.3% | 24.6% | 93.8% | 0.0% | 0 | 0 | 6.2% | 10.87 |

## Per template (new model)

| template | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width | v1_bias | uncovered_ops |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| apply_forms | 2 | 1 | 0.07 | 92.9% | 92.9% | 0.0% | 100.0% | 2 | 1 | 0.0% | 0.30 | 0.07 | 2 |
| chain_copy | 2 | 1 | 1.03 | 2.7% | 4.7% | 50.0% | 0.0% | 0 | 0 | 50.0% | 1.10 | 1.00 | 2 |
| concat_reads_groupby | 2 | 1 | 1.00 | 0.4% | 0.4% | 100.0% | 0.0% | 0 | 0 | 0.0% | 5.23 | 0.81 | 4 |
| concat_then_dedup | 2 | 1 | 1.49 | 48.6% | 49.9% | 100.0% | 0.0% | 0 | 0 | 0.0% | 1.44 | 0.95 | 0 |
| copy_astype | 2 | 1 | 1.12 | 12.0% | 14.4% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.37 | 0.75 | 0 |
| explode_groupby | 2 | 1 | 0.22 | 77.8% | 80.8% | 0.0% | 100.0% | 2 | 1 | 0.0% | 1.98 | 0.22 | 2 |
| load_fillna | 2 | 1 | 1.00 | 0.4% | 0.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 6.45 | 1.00 | 0 |
| load_nrows_merge | 2 | 1 | 1.48 | 48.2% | 54.8% | 100.0% | 0.0% | 0 | 0 | 0.0% | 19.31 | 0.89 | 0 |
| loads_tsv_na | 2 | 1 | 1.00 | 0.4% | 0.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 4.52 | 0.79 | 0 |
| loads_usecols_dtype | 2 | 1 | 1.00 | 0.4% | 0.5% | 100.0% | 0.0% | 0 | 0 | 0.0% | 7.57 | 0.94 | 0 |
| merge_del_groupby | 2 | 1 | 1.21 | 21.0% | 25.1% | 50.0% | 0.0% | 0 | 0 | 50.0% | 7.69 | 1.21 | 0 |
| set_index_copy | 2 | 1 | 0.00 | 100.0% | 100.0% | 0.0% | 100.0% | 2 | 1 | 0.0% | - | 0.00 | 2 |
| sort_then_groupby | 2 | 1 | 1.21 | 20.6% | 23.1% | 100.0% | 0.0% | 0 | 0 | 0.0% | 0.65 | 0.87 | 0 |
| text_fillna | 0 | None | None | None | None | None | None | None | None | None | None | - | 4 |
| value_counts_dedup | 2 | 1 | 0.99 | 3.1% | 3.8% | 100.0% | 0.0% | 0 | 0 | 0.0% | 10.40 | 0.99 | 2 |

## Uncovered-operation rule (amendment 1): a cell with an uncovered operation must never be OK

at a simulated headroom its ACTUAL exceeds (UNKNOWN, WARN and HIGH_RISK are acceptable).

Cells with an uncovered operation: 12; violations (OK while actual > headroom): 0 -> MET

## Every cell (MiB)

| cell | actual | new low/exp/high | v1 exp/high | mode | uncovered |
|---|---|---|---|---|---|
| v2:loads_usecols_dtype/wide@1500000 | 521 | 425 / 524 / 4293 | 489 / 8518 | statements | 0 |
| v2:loads_usecols_dtype/wide@3000000 | 1000 | 814 / 1002 / 8587 | 934 / 17035 | statements | 0 |
| v2:load_nrows_merge/num@1500000 | 82 | 65 / 114 / 2275 | 69 / 2549 | statements | 0 |
| v2:load_nrows_merge/num@3000000 | 146 | 130 / 229 / 4549 | 137 / 5098 | statements | 0 |
| v2:load_fillna/wide@1500000 | 591 | 469 / 587 / 4259 | 587 / 4448 | statements | 0 |
| v2:load_fillna/wide@3000000 | 1178 | 938 / 1175 / 8518 | 1175 / 8895 | statements | 0 |
| v2:concat_reads_groupby/wide@1500000 | 728 | 606 / 725 / 4397 | 587 / 8518 | statements | 2 |
| v2:concat_reads_groupby/wide@3000000 | 1454 | 1211 / 1449 / 8793 | 1175 / 17035 | statements | 2 |
| v2:loads_tsv_na/num@1500000 | 444 | 370 / 442 / 2367 | 350 / 4549 | statements | 0 |
| v2:loads_tsv_na/num@3000000 | 886 | 739 / 883 / 4734 | 700 / 9098 | statements | 0 |
| v2:set_index_copy/mixed@1500000 | 69 | 0 / 0 / 11 | 0 / 11 | statements | 1 |
| v2:set_index_copy/mixed@3000000 | 138 | 0 / 0 / 23 | 0 / 23 | statements | 1 |
| v2:value_counts_dedup/num@1500000 | 19 | 14 / 18 / 141 | 18 / 141 | statements | 1 |
| v2:value_counts_dedup/num@3000000 | 19 | 15 / 19 / 282 | 19 / 282 | statements | 1 |
| v2:explode_groupby/lists@1500000 | 134 | 29 / 35 / 80 | 35 / 80 | statements | 1 |
| v2:explode_groupby/lists@3000000 | 257 | 43 / 47 / 160 | 47 / 160 | statements | 1 |
| v2:apply_forms/num@1500000 | 162 | 10 / 11 / 13 | 11 / 13 | statements | 1 |
| v2:apply_forms/num@3000000 | 324 | 19 / 23 / 26 | 23 / 26 | statements | 1 |
| v2:text_fillna/mixed@1500000 | - | 0 / 0 / 0 | 0 / 0 | none | 2 |
| v2:text_fillna/mixed@3000000 | - | 0 / 0 / 0 | 0 / 0 | none | 2 |
| v2:chain_copy/num@1500000 | 115 | 117 / 121 / 244 | 114 / 315 | statements | 1 |
| v2:chain_copy/num@3000000 | 229 | 224 / 229 / 488 | 229 / 631 | statements | 1 |
| v2:copy_astype/mixed@1500000 | 110 | 103 / 120 / 148 | 80 / 148 | statements | 0 |
| v2:copy_astype/mixed@3000000 | 208 | 207 / 240 / 296 | 160 / 296 | statements | 0 |
| v2:merge_del_groupby/mixed@1500000 | 54 | 54 / 69 / 504 | 69 / 618 | statements | 0 |
| v2:merge_del_groupby/mixed@3000000 | 90 | 82 / 105 / 1007 | 105 / 1236 | statements | 0 |
| v2:sort_then_groupby/mixed@1500000 | 122 | 113 / 143 / 206 | 103 / 278 | statements | 0 |
| v2:sort_then_groupby/mixed@3000000 | 231 | 226 / 286 / 412 | 206 / 555 | statements | 0 |
| v2:concat_then_dedup/mixed@1500000 | 206 | 176 / 303 / 609 | 195 / 609 | statements | 0 |
| v2:concat_then_dedup/mixed@3000000 | 404 | 338 / 607 / 1218 | 389 / 1218 | statements | 0 |
