# Phase 6c regression check on all existing dev data (pre-registration B)

Before: `benchmarks\results\phase6c-dev` (models-frozen-v1); after: `benchmarks\results\phase7b-dev-final` (Phase 6c). 646 (point, tier) rows in both; only in before: 0, only in after: 0.

* rows whose RAM low / expected / high changed: **100** (astype, drop_duplicates, groupby, merge, pandas.concat, pandas.read_csv)
* rows whose calibrated expected time changed: **126** (astype, drop_duplicates, groupby, merge, pandas.concat)

| op | tier | above_high before | above_high after | ram_cov before | ram_cov after | ram_width before | ram_width after | t_err_med before | t_err_med after | same_n before | same_n after | within_one_n before | within_one_n after | t_cov before | t_cov after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 0 | 0 | 0 | 0.918 | 0.918 | 0.995 | 0.995 | 0.635 | 0.635 | 26 | 26 | 37 | 37 | 0.973 | 0.973 |
| astype | 1 | 0 | 0 | 1 | 1 | 0.926 | 0.927 | 0.262 | 0.262 | 33 | 33 | 37 | 37 | 1 | 1 |
| drop_duplicates | 0 | 0 | 0 | 1 | 1 | 1.06 | 1.06 | 0.243 | 0.243 | 31 | 31 | 38 | 38 | 1 | 1 |
| drop_duplicates | 1 | 0 | 0 | 0.951 | 0.951 | 0.788 | 0.775 | 0.212 | 0.21 | 36 | 36 | 38 | 38 | 0.947 | 0.947 |
| groupby | 0 | 0 | 0 | 0.976 | 0.976 | 1.47 | 1.47 | 0.784 | 0.784 | 17 | 17 | 31 | 31 | 1 | 1 |
| groupby | 1 | 0 | 0 | 0.976 | 0.976 | 2.18 | 2.18 | 0.239 | 0.239 | 25 | 25 | 31 | 31 | 0.968 | 0.968 |
| merge | 0 | 0 | 0 | 0.946 | 0.946 | 3.66 | 3.66 | 0.316 | 0.316 | 20 | 20 | 24 | 24 | 1 | 1 |
| merge | 1 | 0 | 0 | 0.973 | 0.973 | 5.23 | 5.24 | 0.236 | 0.236 | 21 | 21 | 24 | 24 | 1 | 1 |
| numpy.sort | 0 | 0 | 0 | 1 | 1 | 0.4 | 0.4 | 0.0088 | 0.0088 | 3 | 3 | 3 | 3 | 1 | 1 |
| numpy.sort | 1 | 0 | 0 | 1 | 1 | 0.4 | 0.4 | 0.0088 | 0.0088 | 3 | 3 | 3 | 3 | 1 | 1 |
| operator.matmul | 0 | 0 | 0 | 1 | 1 | 1.25 | 1.25 | 0.0894 | 0.0894 | 18 | 18 | 19 | 19 | 1 | 1 |
| operator.matmul | 1 | 0 | 0 | 1 | 1 | 1.25 | 1.25 | 0.0894 | 0.0894 | 18 | 18 | 19 | 19 | 1 | 1 |
| pandas.concat | 0 | 0 | 0 | 1 | 1 | 1 | 1 | 0.229 | 0.229 | 12 | 12 | 16 | 16 | 0.875 | 0.875 |
| pandas.concat | 1 | 0 | 0 | 1 | 1 | 0.869 | 0.854 | 0.272 | 0.289 | 11 | 11 | 16 | 16 | 0.875 | 0.875 |
| pandas.read_csv | 0 | 0 | 0 | 0.958 | 0.958 | 2.65 | 2.65 | 0.167 | 0.167 | 13 | 13 | 17 | 17 | 1 | 1 |
| pandas.read_csv | 1 | 0 | 0 | 1 | 1 | 3.04 | 3.48 | 0.116 | 0.116 | 17 | 17 | 17 | 17 | 1 | 1 |
| sort_values | 0 | 0 | 0 | 1 | 1 | 0.45 | 0.45 | 0.419 | 0.419 | 18 | 18 | 26 | 26 | 0.885 | 0.885 |
| sort_values | 1 | 0 | 0 | 1 | 1 | 0.45 | 0.45 | 0.419 | 0.419 | 18 | 18 | 26 | 26 | 0.885 | 0.885 |

## Regressions (pre-registered B)

- astype tier 1: ram_width 0.9265 -> 0.9266
- groupby tier 1: ram_width 2.177 -> 2.18
- groupby tier 1: t_err_p90 1.787 -> 1.89
- merge tier 1: ram_width 5.235 -> 5.235
- pandas.read_csv tier 1: ram_width 3.042 -> 3.484

## Rows whose RAM changed

- drop_duplicates/mixed_dup50|n=10000000 tier 1: 1305 -> 1208 MiB expected, high 2115 -> 2115
- drop_duplicates/numeric_dup50|n=10000000 tier 1: 957 -> 1152 MiB expected, high 1658 -> 1658
- drop_duplicates/subset_s0_lowcard|n=10000000 tier 1: 27 -> 27 MiB expected, high 985 -> 985
- groupby/str_lowcard_sum_f0|n=3000000 tier 1: 87 -> 87 MiB expected, high 251 -> 251
- groupby/str_lowcard_sum_f0|n=10000000 tier 1: 267 -> 267 MiB expected, high 839 -> 839
- groupby/str_highcard_sum_f0|n=1000000 tier 1: 75 -> 75 MiB expected, high 83 -> 83
- groupby/str_highcard_sum_f0|n=3000000 tier 1: 128 -> 128 MiB expected, high 251 -> 251
- read_csv/numeric|n=1000000 tier 1: 223 -> 186 MiB expected, high 1082 -> 1082
- read_csv/numeric|n=3000000 tier 1: 682 -> 567 MiB expected, high 3363 -> 3363
- astype/str_to_category_lowcard|n=3000000 tier 1: 87 -> 87 MiB expected, high 188 -> 188
- astype/str_to_category_lowcard|n=10000000 tier 1: 267 -> 267 MiB expected, high 694 -> 694
- astype/str_to_category_highcard|n=1000000 tier 1: 75 -> 75 MiB expected, high 79 -> 79
- astype/str_to_category_highcard|n=3000000 tier 1: 128 -> 128 MiB expected, high 188 -> 188
- astype/int_to_str|n=1000000 tier 1: 91 -> 91 MiB expected, high 106 -> 106
- astype/int_to_str|n=3000000 tier 1: 274 -> 274 MiB expected, high 320 -> 320
- astype/int_to_str|n=10000000 tier 1: 915 -> 915 MiB expected, high 1068 -> 1068
- drop_duplicates/subset_i0_s0_lowcard|n=1000000 tier 1: 79 -> 79 MiB expected, high 96 -> 96
- drop_duplicates/subset_i0_s0_lowcard|n=3000000 tier 1: 240 -> 240 MiB expected, high 288 -> 288
- drop_duplicates/subset_i0_s0_lowcard|n=10000000 tier 1: 801 -> 801 MiB expected, high 961 -> 961
- groupby/two_keys_mean_realistic|n=1000000 tier 1: 104 -> 104 MiB expected, high 150 -> 150
- groupby/two_keys_mean_realistic|n=3000000 tier 1: 215 -> 215 MiB expected, high 370 -> 370
- groupby/two_keys_mean_realistic|n=10000000 tier 1: 586 -> 586 MiB expected, high 1341 -> 1341
- read_csv/wide_numeric|n=1000000 tier 1: 625 -> 509 MiB expected, high 3412 -> 3412
- read_csv/wide_numeric|n=3000000 tier 1: 1893 -> 1540 MiB expected, high 10380 -> 10380
- astype/str_to_category_zipf|n=1000000 tier 1: 60 -> 60 MiB expected, high 79 -> 79
- astype/str_to_category_zipf|n=3000000 tier 1: 114 -> 115 MiB expected, high 188 -> 188
- astype/str_to_category_zipf|n=10000000 tier 1: 278 -> 278 MiB expected, high 694 -> 694
- v3/drop_duplicates/null_heavy_full|n=10000000 tier 1: 1339 -> 1686 MiB expected, high 2115 -> 2115
- v3/drop_duplicates/high_survivor_subset_i0_d0|n=1000000 tier 1: 80 -> 80 MiB expected, high 96 -> 96
- v3/drop_duplicates/high_survivor_subset_i0_d0|n=3000000 tier 1: 240 -> 240 MiB expected, high 288 -> 288
- v3/drop_duplicates/high_survivor_subset_i0_d0|n=10000000 tier 1: 801 -> 801 MiB expected, high 961 -> 961
- v3/merge/inner_overlap25_fanout6|n=1000000 tier 1: 62 -> 62 MiB expected, high 445 -> 445
- v3/merge/inner_overlap25_fanout6|n=3000000 tier 1: 154 -> 154 MiB expected, high 1336 -> 1336
- v3/merge/outer_overlap65_zipf|n=1000000 tier 1: 213 -> 212 MiB expected, high 537 -> 537
- v3/merge/outer_overlap65_zipf|n=3000000 tier 1: 644 -> 644 MiB expected, high 1611 -> 1611
- v3/merge/inner_bigright_fanout8|n=1000000 tier 1: 100 -> 100 MiB expected, high 891 -> 891
- v3/groupby/int_card20000_mean|n=1000000 tier 1: 28 -> 28 MiB expected, high 76 -> 76
- v3/groupby/str_card0p04_two_values|n=1000000 tier 1: 71 -> 71 MiB expected, high 83 -> 83
- v3/groupby/str_card0p04_two_values|n=3000000 tier 1: 118 -> 118 MiB expected, high 251 -> 251
- v3/groupby/str_card0p04_two_values|n=10000000 tier 1: 281 -> 281 MiB expected, high 839 -> 839
- v3/groupby/two_keys_card800|n=1000000 tier 1: 91 -> 91 MiB expected, high 150 -> 150
- v3/groupby/two_keys_card800|n=3000000 tier 1: 184 -> 184 MiB expected, high 370 -> 370
- v3/groupby/str_card0p75_sum|n=1000000 tier 1: 77 -> 77 MiB expected, high 83 -> 83
- v3/groupby/str_card0p75_sum|n=3000000 tier 1: 183 -> 182 MiB expected, high 251 -> 251
- v3/astype/str_to_category_card12000|n=1000000 tier 1: 63 -> 63 MiB expected, high 79 -> 79
- v3/astype/str_to_category_card12000|n=3000000 tier 1: 109 -> 109 MiB expected, high 188 -> 188
- v3/astype/str_to_category_card0p75|n=1000000 tier 1: 77 -> 77 MiB expected, high 79 -> 79
- v3/astype/str_to_category_card0p75|n=3000000 tier 1: 182 -> 182 MiB expected, high 188 -> 188
- v3/astype/int_to_category_card0p04|n=1000000 tier 1: 30 -> 30 MiB expected, high 56 -> 56
- v3/astype/int_to_category_card0p04|n=3000000 tier 1: 51 -> 51 MiB expected, high 135 -> 135
- v3/concat/four_frames_light_nulls|n=10000000 tier 1: 770 -> 885 MiB expected, high 1426 -> 1426
- v3/concat/two_strings_long|n=10000000 tier 1: 541 -> 656 MiB expected, high 968 -> 968
- v3/read_csv/float_heavy|n=1000000 tier 1: 497 -> 400 MiB expected, high 2758 -> 2758
- v3/read_csv/float_heavy|n=3000000 tier 1: 1501 -> 1209 MiB expected, high 8361 -> 8361
- v3/read_csv/short_ints|n=1000000 tier 1: 224 -> 230 MiB expected, high 440 -> 440
- v3/read_csv/short_ints|n=3000000 tier 1: 677 -> 694 MiB expected, high 1349 -> 1349
- v3/read_csv/two_columns|n=1000000 tier 1: 94 -> 77 MiB expected, high 429 -> 429
- v3/read_csv/two_columns|n=3000000 tier 1: 291 -> 236 MiB expected, high 1345 -> 1345
- v4/astype/str_to_category_card6000|n=10000000 tier 1: 259 -> 259 MiB expected, high 694 -> 694
- v4/astype/str_to_category_card40000|n=1000000 tier 1: 71 -> 71 MiB expected, high 79 -> 79
- v4/astype/str_to_category_card40000|n=3000000 tier 1: 117 -> 117 MiB expected, high 188 -> 188
- v4/astype/str_to_category_card40000|n=10000000 tier 1: 278 -> 278 MiB expected, high 694 -> 694
- v4/astype/str_to_category_card150000|n=1000000 tier 1: 72 -> 72 MiB expected, high 79 -> 79
- v4/astype/str_to_category_card150000|n=3000000 tier 1: 118 -> 118 MiB expected, high 188 -> 188
- v4/astype/str_to_category_card150000|n=10000000 tier 1: 279 -> 279 MiB expected, high 694 -> 694
- v4/astype/str_to_category_card0p12|n=1000000 tier 1: 72 -> 72 MiB expected, high 79 -> 79
- v4/astype/str_to_category_card0p12|n=3000000 tier 1: 120 -> 120 MiB expected, high 188 -> 188
- v4/astype/int_to_category_card15000|n=1000000 tier 1: 27 -> 27 MiB expected, high 56 -> 56
- v4/astype/float_to_str_nulls|n=1000000 tier 1: 66 -> 66 MiB expected, high 83 -> 83
- v4/astype/float_to_str_nulls|n=3000000 tier 1: 198 -> 198 MiB expected, high 251 -> 251
- v4/astype/float_to_str_nulls|n=10000000 tier 1: 662 -> 661 MiB expected, high 839 -> 839
- v4/astype/int_to_str_card1500|n=1000000 tier 1: 86 -> 86 MiB expected, high 106 -> 106
- v4/astype/int_to_str_card1500|n=3000000 tier 1: 258 -> 259 MiB expected, high 320 -> 320
- v4/astype/int_to_str_card1500|n=10000000 tier 1: 863 -> 863 MiB expected, high 1068 -> 1068
- v4/groupby/str_card0p003_two_values|n=1000000 tier 1: 41 -> 41 MiB expected, high 83 -> 83
- v4/groupby/str_card0p003_two_values|n=10000000 tier 1: 277 -> 277 MiB expected, high 839 -> 839
- v4/groupby/two_keys_card60|n=1000000 tier 1: 61 -> 61 MiB expected, high 150 -> 150
- v4/groupby/two_keys_card6000|n=1000000 tier 1: 108 -> 108 MiB expected, high 150 -> 150
- v4/groupby/two_keys_card6000|n=3000000 tier 1: 264 -> 264 MiB expected, high 370 -> 370
- v4/groupby/two_keys_card6000|n=10000000 tier 1: 892 -> 892 MiB expected, high 1341 -> 1341
- v4/groupby/int_card40000_mean|n=1000000 tier 1: 30 -> 30 MiB expected, high 76 -> 76
- v4/groupby/zipf_int_card0p006|n=1000000 tier 1: 30 -> 31 MiB expected, high 76 -> 76
- v4/groupby/zipf_int_card0p006|n=3000000 tier 1: 52 -> 52 MiB expected, high 228 -> 228
- v4/groupby/str_card0p9_mean|n=1000000 tier 1: 78 -> 78 MiB expected, high 83 -> 83
- v4/groupby/str_card0p9_mean|n=3000000 tier 1: 186 -> 186 MiB expected, high 251 -> 251
- v4/merge/inner_overlap35_fanout7|n=1000000 tier 1: 63 -> 63 MiB expected, high 445 -> 445
- v4/merge/inner_overlap35_fanout7|n=3000000 tier 1: 159 -> 159 MiB expected, high 1336 -> 1336
- v4/merge/inner_overlap20_fanout10|n=1000000 tier 1: 58 -> 58 MiB expected, high 445 -> 445
- v4/merge/inner_overlap20_fanout10|n=3000000 tier 1: 142 -> 142 MiB expected, high 1336 -> 1336
- v4/merge/inner_overlap55_fanout4p5|n=1000000 tier 1: 78 -> 78 MiB expected, high 445 -> 445
- v4/merge/left_overlap40_fanout9|n=1000000 tier 1: 128 -> 128 MiB expected, high 445 -> 445
- v4/merge/left_overlap40_fanout9|n=3000000 tier 1: 387 -> 387 MiB expected, high 1336 -> 1336
- v4/merge/outer_overlap70_zipf1p5|n=1000000 tier 1: 292 -> 290 MiB expected, high 644 -> 644
- v4/merge/outer_overlap70_zipf1p5|n=3000000 tier 1: 863 -> 863 MiB expected, high 1933 -> 1933
- v4/drop_duplicates/null_subset_floats|n=1000000 tier 1: 83 -> 83 MiB expected, high 103 -> 103
- v4/drop_duplicates/null_subset_floats|n=3000000 tier 1: 247 -> 246 MiB expected, high 311 -> 311
- v4/drop_duplicates/null_subset_cat_date|n=1000000 tier 1: 74 -> 73 MiB expected, high 96 -> 96
- v4/drop_duplicates/null_subset_cat_date|n=3000000 tier 1: 209 -> 209 MiB expected, high 288 -> 288
- v4/drop_duplicates/null_subset_cat_date|n=10000000 tier 1: 691 -> 684 MiB expected, high 961 -> 961
- v4/read_csv/wide_floats|n=1000000 tier 1: 644 -> 514 MiB expected, high 3683 -> 3683
