# Tier 0 diagnosis from development results

Source: `benchmarks/results/full` (suite `full`, git `cc45596`). Groups used: dev and exposed-v1 only; the sealed test-v2 split is never read. Points by group: {'dev': 84, 'exposed-v1': 52}. Floors: RAM >= 32 MiB, time >= 100 ms, spread <= 30%. read_csv parser not recorded in these rows (run predates Phase 3d); verified separately.

fold = predicted/actual, shown **+x** for over-prediction and **-x** for under-prediction (x times too low). Only valid measurements get a fold.

## 1. Error structure per operation (structural vs data-dependent)

Rule: no dominant error if |bias| and scenario spread are both below x1.5; data-dependent if scenario spread >= max(|bias|, x2); otherwise structural (scaling exponent if the log-ratio size trend is >= 0.1/decade, else a constant factor).

| op | metric | points | scenarios | bias_fold | data_spread_log10 | trend_per_decade | dev_bias_fold | exposed_bias_fold | classification | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| astype | RAM | 16 | 8 | -1.52 | 0.16 | 0.00 | -1.61 | -1.21 | structural (constant factor) | median fold -1.52; scenario spread x1.45, size trend +0.00/decade |
| astype | TIME | 11 | 5 | 1.42 | 0.35 | -0.02 | 1.43 | -1.37 | data-dependent | median fold +1.42; scenario spread x2.23, size trend -0.02/decade |
| drop_duplicates | RAM | 17 | 6 | 1.55 | 0.17 | 0.06 | 1.57 | 1.54 | structural (constant factor) | median fold +1.55; scenario spread x1.48, size trend +0.06/decade |
| drop_duplicates | TIME | 17 | 7 | -1.13 | 0.45 | -0.39 | -1.27 | 1.28 | data-dependent | median fold -1.13; scenario spread x2.83, size trend -0.39/decade |
| groupby | RAM | 10 | 5 | 2.06 | 0.28 | 0.18 | 2.57 | 1.53 | structural (scaling exponent) | median fold +2.06; scenario spread x1.91, size trend +0.18/decade |
| groupby | TIME | 8 | 5 | 3.72 | 0.44 | – | 4.78 | 2.90 | structural (constant factor) | median fold +3.72; scenario spread x2.77 |
| merge | RAM | 14 | 7 | 5.22 | 0.23 | – | 5.22 | 3.50 | structural (constant factor) | median fold +5.22; scenario spread x1.68 |
| merge | TIME | 7 | 7 | 1.63 | 0.26 | – | 1.65 | -1.52 | structural (constant factor) | median fold +1.63; scenario spread x1.81 |
| numpy.sort | RAM | 7 | 4 | -1.00 | 0.00 | – | -1.00 | -1.00 | no dominant error | median fold -1.00; scenario spread x1.00 |
| numpy.sort | TIME | 3 | 3 | 1.21 | 0.01 | – | 1.19 | 1.22 | no dominant error | median fold +1.21; scenario spread x1.01 |
| operator.matmul | RAM | 9 | 2 | -1.02 | – | 0.02 | -1.03 | -1.02 | no dominant error | median fold -1.02; n/a (<3 scenarios), size trend +0.02/decade |
| operator.matmul | TIME | 7 | 2 | -1.03 | – | 0.12 | -1.08 | 1.02 | no dominant error | median fold -1.03; n/a (<3 scenarios), size trend +0.12/decade |
| pandas.concat | RAM | 12 | 4 | 2.01 | 0.17 | 0.00 | 1.28 | 2.10 | structural (constant factor) | median fold +2.01; scenario spread x1.49, size trend +0.00/decade |
| pandas.concat | TIME | 6 | 4 | 1.07 | 0.16 | – | 1.06 | 1.07 | no dominant error | median fold +1.07; scenario spread x1.46 |
| pandas.read_csv | RAM | 10 | 5 | -1.87 | 0.13 | – | -2.67 | -1.59 | structural (constant factor) | median fold -1.87; scenario spread x1.34 |
| pandas.read_csv | TIME | 8 | 4 | -2.39 | 0.38 | – | -2.92 | 1.24 | data-dependent | median fold -2.39; scenario spread x2.42 |
| sort_values | RAM | 14 | 5 | 2.27 | 0.02 | 0.00 | 2.28 | 2.27 | structural (constant factor) | median fold +2.27; scenario spread x1.04, size trend +0.00/decade |
| sort_values | TIME | 11 | 5 | -1.20 | 0.21 | -0.31 | -1.20 | -1.01 | structural (scaling exponent) | median fold -1.20; scenario spread x1.62, size trend -0.31/decade |

## 2. Scaling: log-log slope of actual time and RAM versus n

Per operation (median over scenarios); linear = 1, matmul n is the matrix side so cubic = 3. `superlinear_time` = actual time slope above 1.15 (x3 for matmul).

| op | scenarios | time_slope_actual | time_slope_pred | ram_slope_actual | ram_slope_pred | superlinear_time |
|---|---|---|---|---|---|---|
| astype | 8 | 1.02 | 1.00 | 0.99 | 1.00 | False |
| drop_duplicates | 7 | 1.38 | 1.00 | 0.94 | 1.00 | True |
| groupby | 5 | 1.07 | 1.00 | 0.95 | 1.00 | False |
| merge | 7 | 1.34 | 1.00 | 0.97 | 1.00 | True |
| numpy.sort | 4 | 1.15 | 1.06 | 1.00 | 1.00 | True |
| operator.matmul | 2 | 2.73 | 3.00 | 1.81 | 1.83 | False |
| pandas.concat | 4 | 1.29 | 1.00 | 1.00 | 1.00 | True |
| pandas.read_csv | 5 | 1.01 | 1.01 | 1.00 | 1.01 | False |
| sort_values | 5 | 1.36 | 1.05 | 1.00 | 1.00 | True |

Per scenario:

| op | scenario | points | sizes | time_pts | ram_pts | time_slope_actual | time_r2 | time_slope_pred | ram_slope_actual | ram_r2 | ram_slope_pred |
|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | astype/datetime_to_str | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.02 | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 |
| astype | astype/float_to_float32 | 3 | 1,000,000..10,000,000 | 0 | 3 | – | – | – | 0.99 | 1.00 | 1.00 |
| astype | astype/int_to_float64 | 3 | 1,000,000..10,000,000 | 1 | 3 | – | – | – | 0.99 | 1.00 | 1.00 |
| astype | astype/int_to_int32 | 3 | 1,000,000..10,000,000 | 0 | 3 | – | – | – | 0.99 | 1.00 | 1.00 |
| astype | astype/int_to_str | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| astype | astype/str_to_category_highcard | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.48 | 1.00 | 1.00 | 0.49 | 1.00 | 1.00 |
| astype | astype/str_to_category_lowcard | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.02 | 1.00 | 1.00 | 0.96 | 1.00 | 1.00 |
| astype | astype/str_to_category_zipf | 3 | 1,000,000..10,000,000 | 3 | 3 | 0.98 | 1.00 | 1.00 | 0.66 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/mixed_dup0 | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.38 | 1.00 | 1.00 | 1.01 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/mixed_dup50 | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.45 | 0.99 | 1.00 | 0.94 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/numeric_dup50 | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.39 | 0.99 | 1.00 | 0.93 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/realistic_nulls_dup30 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.25 | 1.00 | 1.00 | 0.97 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/strings_dup50 | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.40 | 1.00 | 1.00 | 0.85 | 0.98 | 1.00 |
| drop_duplicates | drop_duplicates/subset_i0_s0_lowcard | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.24 | 1.00 | 1.00 | 1.05 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/subset_s0_lowcard | 3 | 1,000,000..10,000,000 | 2 | 2 | 1.05 | 1.00 | 1.00 | 0.17 | 1.00 | 1.00 |
| groupby | groupby/cat_key_zipf_sum | 3 | 1,000,000..10,000,000 | 2 | 3 | 0.83 | 1.00 | 1.00 | 0.99 | 1.00 | 1.00 |
| groupby | groupby/int_sum_numeric | 3 | 1,000,000..10,000,000 | 3 | 3 | 0.96 | 0.99 | 1.00 | 0.98 | 1.00 | 1.00 |
| groupby | groupby/str_highcard_sum_f0 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.52 | 1.00 | 1.00 | 0.49 | 1.00 | 1.00 |
| groupby | groupby/str_lowcard_sum_f0 | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.07 | 1.00 | 1.00 | 0.95 | 1.00 | 1.00 |
| groupby | groupby/two_keys_mean_realistic | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.07 | 1.00 | 1.00 | 0.82 | 0.99 | 1.00 |
| merge | merge/inner_1to1 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.31 | 1.00 | 1.00 | 0.94 | 1.00 | 1.00 |
| merge | merge/inner_fanout3 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.40 | 1.00 | 1.00 | 0.97 | 1.00 | 1.00 |
| merge | merge/inner_manymany | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.50 | 1.00 | 1.00 | 0.99 | 1.00 | 1.00 |
| merge | merge/inner_overlap10 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.23 | 1.00 | 1.00 | 0.49 | 1.00 | 1.00 |
| merge | merge/left_1to1 | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.27 | 1.00 | 1.00 | 0.56 | 1.00 | 1.00 |
| merge | merge/outer_overlap50_realistic | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.34 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| merge | merge/right_fanout4_strings | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.46 | 1.00 | 1.00 | 0.99 | 1.00 | 1.00 |
| numpy.sort | np_sort/float32_random | 2 | 5,000,000..10,000,000 | 2 | 2 | 1.12 | 1.00 | 1.06 | 1.00 | 1.00 | 1.00 |
| numpy.sort | np_sort/random | 2 | 5,000,000..10,000,000 | 2 | 2 | 1.19 | 1.00 | 1.06 | 1.00 | 1.00 | 1.00 |
| numpy.sort | np_sort/reverse | 2 | 5,000,000..10,000,000 | 2 | 2 | 1.09 | 1.00 | 1.06 | 1.00 | 1.00 | 1.00 |
| numpy.sort | np_sort/sorted | 2 | 5,000,000..10,000,000 | 2 | 2 | 1.19 | 1.00 | 1.06 | 1.00 | 1.00 | 1.00 |
| operator.matmul | matmul/rect_f64 | 5 | 2,000..8,000 | 5 | 5 | 2.77 | 1.00 | 3.00 | 1.83 | 1.00 | 1.85 |
| operator.matmul | matmul/square_f64 | 4 | 2,000..6,000 | 4 | 4 | 2.68 | 0.99 | 3.00 | 1.79 | 1.00 | 1.82 |
| pandas.concat | concat/mixed | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.41 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 |
| pandas.concat | concat/numeric | 3 | 1,000,000..10,000,000 | 2 | 3 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| pandas.concat | concat/realistic_nulls | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.16 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 |
| pandas.concat | concat/three_frames | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.42 | 1.00 | 1.00 | 0.99 | 1.00 | 1.00 |
| pandas.read_csv | read_csv/mixed | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.01 | 1.00 | 1.02 | 1.02 | 1.00 | 1.02 |
| pandas.read_csv | read_csv/numeric | 2 | 1,000,000..3,000,000 | 2 | 2 | 0.97 | 1.00 | 1.03 | 1.00 | 1.00 | 1.03 |
| pandas.read_csv | read_csv/realistic_nulls | 2 | 1,000,000..3,000,000 | 2 | 2 | 0.87 | 1.00 | 1.01 | 0.98 | 1.00 | 1.01 |
| pandas.read_csv | read_csv/strings | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.06 | 1.00 | 1.01 | 1.01 | 1.00 | 1.01 |
| pandas.read_csv | read_csv/wide_numeric | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.09 | 1.00 | 1.01 | 1.00 | 1.00 | 1.01 |
| sort_values | sort_values/by_datetime | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.40 | 1.00 | 1.04 | 1.00 | 1.00 | 1.00 |
| sort_values | sort_values/by_int | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.36 | 1.00 | 1.04 | 1.00 | 1.00 | 1.00 |
| sort_values | sort_values/by_int_float | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.35 | 1.00 | 1.05 | 1.00 | 1.00 | 1.00 |
| sort_values | sort_values/by_str | 3 | 1,000,000..10,000,000 | 3 | 3 | 1.37 | 1.00 | 1.06 | 1.00 | 1.00 | 1.00 |
| sort_values | sort_values/by_str_desc_nulls | 2 | 1,000,000..3,000,000 | 2 | 2 | 1.36 | 1.00 | 1.06 | 1.01 | 1.00 | 1.00 |

## 3. Largest errors, both directions

### 3a. Under-predictions (actual above predicted), worst 25

| op | scenario | split | size | ram_actual_MB | ram_pred_MB | ram_fold | time_actual_s | time_pred_s | time_fold |
|---|---|---|---|---|---|---|---|---|---|
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 10000000 | 995 | 954 | -1.04 | 11.88 | 2.68 | -4.43 |
| astype | astype/str_to_category_highcard | dev | 1000000 | 74.38 | 18.69 | -3.98 | 0.42 | 0.22 | -1.93 |
| pandas.read_csv | read_csv/strings | dev | 3000000 | 1328 | 466 | -2.85 | 2.20 | 0.67 | -3.28 |
| astype | astype/str_to_category_highcard | dev | 3000000 | 127 | 56.08 | -2.26 | 2.12 | 0.65 | -3.27 |
| astype | astype/str_to_category_zipf | exposed-v1 | 1000000 | 60.25 | 18.69 | -3.22 | 0.08 | 0.22 | – |
| pandas.read_csv | read_csv/strings | dev | 1000000 | 438 | 154 | -2.84 | 0.69 | 0.22 | -3.10 |
| pandas.read_csv | read_csv/mixed | dev | 1000000 | 446 | 168 | -2.66 | 0.67 | 0.24 | -2.75 |
| pandas.read_csv | read_csv/mixed | dev | 3000000 | 1370 | 513 | -2.67 | 2.02 | 0.74 | -2.73 |
| groupby | groupby/str_highcard_sum_f0 | dev | 3000000 | 127 | 219 | 1.73 | 2.21 | 0.84 | -2.62 |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 10000000 | 1148 | 1825 | 1.59 | 18.51 | 7.19 | -2.57 |
| merge | merge/outer_overlap50_realistic | exposed-v1 | 3000000 | 536 | 912 | 1.70 | 1.35 | 0.55 | -2.45 |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 10000000 | 1201 | 1825 | 1.52 | 15.83 | 7.19 | -2.20 |
| pandas.concat | concat/mixed | dev | 10000000 | 835 | 1667 | 2.00 | 1.77 | 0.81 | -2.19 |
| sort_values | sort_values/by_datetime | exposed-v1 | 10000000 | 801 | 1820 | 2.27 | 4.11 | 1.92 | -2.14 |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 3000000 | 289 | 286 | -1.01 | 1.71 | 0.80 | -2.13 |
| pandas.read_csv | read_csv/realistic_nulls | exposed-v1 | 1000000 | 306 | 161 | -1.90 | 0.48 | 0.23 | -2.09 |
| astype | astype/str_to_category_zipf | exposed-v1 | 3000000 | 116 | 56.08 | -2.07 | 0.22 | 0.65 | 2.99 |
| sort_values | sort_values/by_int_float | dev | 10000000 | 801 | 1972 | 2.46 | 5.88 | 3.03 | -1.94 |
| pandas.read_csv | read_csv/realistic_nulls | exposed-v1 | 3000000 | 898 | 487 | -1.85 | 1.26 | 0.70 | -1.79 |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 1000000 | 117 | 95.37 | -1.23 | 0.49 | 0.27 | -1.84 |
| sort_values | sort_values/by_int | dev | 10000000 | 801 | 1820 | 2.27 | 3.16 | 1.92 | -1.64 |
| astype | astype/int_to_str | dev | 1000000 | 91.95 | 57.22 | -1.61 | 0.09 | 0.13 | – |
| astype | astype/int_to_str | dev | 3000000 | 276 | 172 | -1.61 | 0.27 | 0.38 | 1.44 |
| astype | astype/int_to_str | dev | 10000000 | 919 | 572 | -1.61 | 0.90 | 1.28 | 1.42 |
| pandas.read_csv | read_csv/numeric | dev | 1000000 | 189 | 119 | -1.59 | 0.07 | 0.17 | – |

### 3b. Every valid point, sorted by worst error in either direction (rows with a negative fold are under-predictions)

| op | scenario | split | size | ram_actual_MB | ram_pred_MB | ram_fold | time_actual_s | time_pred_s | time_fold | under |
|---|---|---|---|---|---|---|---|---|---|---|
| drop_duplicates | drop_duplicates/subset_s0_lowcard | dev | 10000000 | – | 1135 | – | 0.17 | 2.52 | 14.57 |  |
| merge | merge/inner_overlap10 | dev | 3000000 | 83.78 | 858 | 10.24 | 0.17 | 0.52 | 3.16 |  |
| groupby | groupby/cat_key_zipf_sum | exposed-v1 | 10000000 | 86.11 | 634 | 7.36 | 0.11 | 1.05 | 9.29 |  |
| merge | merge/left_1to1 | dev | 3000000 | 101 | 858 | 8.49 | 0.27 | 0.52 | 1.96 |  |
| merge | merge/right_fanout4_strings | exposed-v1 | 3000000 | 173 | 1250 | 7.24 | 0.67 | 0.72 | 1.06 |  |
| merge | merge/right_fanout4_strings | exposed-v1 | 1000000 | 57.90 | 417 | 7.20 | 0.14 | 0.24 | – |  |
| groupby | groupby/str_lowcard_sum_f0 | dev | 3000000 | 86.92 | 214 | 2.46 | 0.13 | 0.84 | 6.54 |  |
| groupby | groupby/str_lowcard_sum_f0 | dev | 10000000 | 266 | 713 | 2.68 | 0.46 | 2.81 | 6.04 |  |
| merge | merge/inner_overlap10 | dev | 1000000 | 49.07 | 286 | 5.83 | 0.04 | 0.17 | – |  |
| merge | merge/inner_1to1 | dev | 3000000 | 155 | 858 | 5.53 | 0.32 | 0.52 | 1.63 |  |
| merge | merge/left_1to1 | dev | 1000000 | 54.39 | 286 | 5.26 | 0.07 | 0.17 | – |  |
| merge | merge/inner_1to1 | dev | 1000000 | 55.14 | 286 | 5.18 | 0.08 | 0.17 | – |  |
| groupby | groupby/int_sum_numeric | dev | 10000000 | 153 | 637 | 4.16 | 0.22 | 1.05 | 4.78 |  |
| merge | merge/inner_fanout3 | dev | 3000000 | 183 | 858 | 4.67 | 0.48 | 0.52 | 1.10 |  |
| merge | merge/inner_fanout3 | dev | 1000000 | 63.39 | 286 | 4.51 | 0.10 | 0.17 | – |  |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 10000000 | 995 | 954 | -1.04 | 11.88 | 2.68 | -4.43 | UNDER |
| groupby | groupby/int_sum_numeric | dev | 3000000 | 46.24 | 191 | 4.13 | 0.08 | 0.32 | – |  |
| astype | astype/str_to_category_highcard | dev | 1000000 | 74.38 | 18.69 | -3.98 | 0.42 | 0.22 | -1.93 | UNDER |
| pandas.read_csv | read_csv/strings | dev | 3000000 | 1328 | 466 | -2.85 | 2.20 | 0.67 | -3.28 | UNDER |
| astype | astype/str_to_category_highcard | dev | 3000000 | 127 | 56.08 | -2.26 | 2.12 | 0.65 | -3.27 | UNDER |
| astype | astype/str_to_category_lowcard | dev | 3000000 | 86.92 | 56.08 | -1.55 | 0.20 | 0.65 | 3.24 | UNDER |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 3000000 | 211 | 681 | 3.23 | 2.79 | 2.86 | 1.03 |  |
| astype | astype/str_to_category_zipf | exposed-v1 | 1000000 | 60.25 | 18.69 | -3.22 | 0.08 | 0.22 | – | UNDER |
| astype | astype/str_to_category_lowcard | dev | 10000000 | 266 | 187 | -1.43 | 0.69 | 2.16 | 3.13 | UNDER |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 10000000 | 727 | 2270 | 3.12 | 15.01 | 9.53 | -1.57 | UNDER |
| pandas.read_csv | read_csv/strings | dev | 1000000 | 438 | 154 | -2.84 | 0.69 | 0.22 | -3.10 | UNDER |
| pandas.read_csv | read_csv/wide_numeric | exposed-v1 | 1000000 | 513 | 376 | -1.37 | 0.18 | 0.54 | 3.01 | UNDER |
| astype | astype/str_to_category_zipf | exposed-v1 | 3000000 | 116 | 56.08 | -2.07 | 0.22 | 0.65 | 2.99 | UNDER |
| groupby | groupby/two_keys_mean_realistic | exposed-v1 | 3000000 | 170 | 247 | 1.45 | 0.33 | 0.95 | 2.90 |  |
| astype | astype/str_to_category_zipf | exposed-v1 | 10000000 | 278 | 187 | -1.49 | 0.76 | 2.16 | 2.86 | UNDER |
| merge | merge/inner_manymany | dev | 3000000 | 310 | 858 | 2.77 | 0.55 | 0.52 | – |  |
| pandas.read_csv | read_csv/mixed | dev | 1000000 | 446 | 168 | -2.66 | 0.67 | 0.24 | -2.75 | UNDER |
| pandas.read_csv | read_csv/wide_numeric | exposed-v1 | 3000000 | 1545 | 1143 | -1.35 | 0.60 | 1.65 | 2.75 | UNDER |
| merge | merge/inner_manymany | dev | 1000000 | 104 | 286 | 2.75 | 0.11 | 0.17 | 1.65 |  |
| pandas.read_csv | read_csv/mixed | dev | 3000000 | 1370 | 513 | -2.67 | 2.02 | 0.74 | -2.73 | UNDER |
| groupby | groupby/str_highcard_sum_f0 | dev | 3000000 | 127 | 219 | 1.73 | 2.21 | 0.84 | -2.62 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 10000000 | 1148 | 1825 | 1.59 | 18.51 | 7.19 | -2.57 | UNDER |
| sort_values | sort_values/by_int_float | dev | 10000000 | 801 | 1972 | 2.46 | 5.88 | 3.03 | -1.94 | UNDER |
| sort_values | sort_values/by_int_float | dev | 3000000 | 241 | 592 | 2.46 | 1.26 | 0.86 | -1.47 | UNDER |
| sort_values | sort_values/by_int_float | dev | 1000000 | 80.41 | 197 | 2.45 | 0.26 | 0.27 | – |  |
| sort_values | sort_values/by_str_desc_nulls | exposed-v1 | 1000000 | 79.75 | 195 | 2.45 | 0.46 | 0.99 | 2.16 |  |
| merge | merge/outer_overlap50_realistic | exposed-v1 | 3000000 | 536 | 912 | 1.70 | 1.35 | 0.55 | -2.45 | UNDER |
| sort_values | sort_values/by_str_desc_nulls | exposed-v1 | 3000000 | 241 | 586 | 2.44 | 2.05 | 3.20 | 1.56 |  |
| groupby | groupby/two_keys_mean_realistic | exposed-v1 | 10000000 | 516 | 828 | 1.60 | 1.34 | 3.17 | 2.37 |  |
| sort_values | sort_values/by_int | dev | 1000000 | 79.88 | 182 | 2.28 | 0.14 | 0.18 | – |  |
| sort_values | sort_values/by_str | dev | 1000000 | 79.92 | 182 | 2.28 | 0.55 | 0.99 | 1.81 |  |
| sort_values | sort_values/by_str | dev | 10000000 | 801 | 1820 | 2.27 | 12.71 | 11.40 | -1.12 | UNDER |
| sort_values | sort_values/by_datetime | exposed-v1 | 10000000 | 801 | 1820 | 2.27 | 4.11 | 1.92 | -2.14 | UNDER |
| sort_values | sort_values/by_int | dev | 10000000 | 801 | 1820 | 2.27 | 3.16 | 1.92 | -1.64 | UNDER |
| sort_values | sort_values/by_datetime | exposed-v1 | 3000000 | 241 | 546 | 2.27 | 0.87 | 0.55 | -1.59 | UNDER |
| sort_values | sort_values/by_str | dev | 3000000 | 241 | 546 | 2.27 | 2.33 | 3.18 | 1.37 |  |
| sort_values | sort_values/by_int | dev | 3000000 | 241 | 546 | 2.27 | 0.66 | 0.55 | -1.20 | UNDER |
| drop_duplicates | drop_duplicates/subset_i0_s0_lowcard | exposed-v1 | 3000000 | 229 | 361 | 1.57 | 0.38 | 0.86 | 2.26 |  |
| sort_values | sort_values/by_datetime | exposed-v1 | 1000000 | 80.66 | 182 | 2.26 | 0.16 | 0.18 | – |  |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 1000000 | 103 | 227 | 2.21 | 0.60 | 0.95 | 1.59 |  |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 10000000 | 1201 | 1825 | 1.52 | 15.83 | 7.19 | -2.20 | UNDER |
| pandas.concat | concat/mixed | dev | 10000000 | 835 | 1667 | 2.00 | 1.77 | 0.81 | -2.19 | UNDER |
| pandas.concat | concat/realistic_nulls | exposed-v1 | 1000000 | 82.80 | 178 | 2.14 | 0.09 | 0.09 | – |  |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 3000000 | 289 | 286 | -1.01 | 1.71 | 0.80 | -2.13 | UNDER |
| pandas.concat | concat/realistic_nulls | exposed-v1 | 10000000 | 836 | 1778 | 2.13 | 1.23 | 0.86 | -1.43 | UNDER |
| pandas.concat | concat/realistic_nulls | exposed-v1 | 3000000 | 251 | 533 | 2.12 | 0.24 | 0.26 | 1.07 |  |
| pandas.read_csv | read_csv/realistic_nulls | exposed-v1 | 1000000 | 306 | 161 | -1.90 | 0.48 | 0.23 | -2.09 | UNDER |
| pandas.concat | concat/three_frames | exposed-v1 | 10000000 | 804 | 1667 | 2.07 | 1.22 | 0.81 | – |  |
| pandas.concat | concat/three_frames | exposed-v1 | 3000000 | 243 | 500 | 2.06 | 0.19 | 0.24 | 1.26 |  |
| pandas.concat | concat/three_frames | exposed-v1 | 1000000 | 82.06 | 167 | 2.03 | 0.05 | 0.08 | – |  |
| pandas.concat | concat/mixed | dev | 3000000 | 251 | 500 | 1.99 | 0.23 | 0.24 | 1.06 |  |
| pandas.concat | concat/mixed | dev | 1000000 | 84.00 | 167 | 1.98 | 0.07 | 0.08 | – |  |
| pandas.concat | concat/numeric | dev | 10000000 | 649 | 534 | -1.21 | 0.14 | 0.26 | 1.88 | UNDER |
| pandas.read_csv | read_csv/realistic_nulls | exposed-v1 | 3000000 | 898 | 487 | -1.85 | 1.26 | 0.70 | -1.79 | UNDER |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 1000000 | 117 | 95.37 | -1.23 | 0.49 | 0.27 | -1.84 | UNDER |
| drop_duplicates | drop_duplicates/subset_i0_s0_lowcard | exposed-v1 | 1000000 | 70.31 | 120 | 1.71 | 0.11 | 0.29 | – |  |
| merge | merge/outer_overlap50_realistic | exposed-v1 | 1000000 | 179 | 304 | 1.70 | 0.31 | 0.18 | – |  |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 3000000 | 335 | 548 | 1.64 | 2.74 | 2.16 | -1.27 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 3000000 | 335 | 548 | 1.63 | 2.44 | 2.16 | -1.13 | UNDER |
| astype | astype/int_to_str | dev | 1000000 | 91.95 | 57.22 | -1.61 | 0.09 | 0.13 | – | UNDER |
| astype | astype/int_to_str | dev | 3000000 | 276 | 172 | -1.61 | 0.27 | 0.38 | 1.44 | UNDER |
| astype | astype/int_to_str | dev | 10000000 | 919 | 572 | -1.61 | 0.90 | 1.28 | 1.42 | UNDER |
| pandas.read_csv | read_csv/numeric | dev | 1000000 | 189 | 119 | -1.59 | 0.07 | 0.17 | – | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 1000000 | 118 | 183 | 1.55 | 0.65 | 0.72 | 1.10 |  |
| drop_duplicates | drop_duplicates/subset_i0_s0_lowcard | exposed-v1 | 10000000 | 782 | 1202 | 1.54 | 1.87 | 2.88 | 1.54 |  |
| pandas.read_csv | read_csv/numeric | dev | 3000000 | 571 | 370 | -1.54 | 0.21 | 0.53 | – | UNDER |
| groupby | groupby/str_highcard_sum_f0 | dev | 1000000 | 74.38 | 73.05 | -1.02 | 0.42 | 0.28 | -1.48 | UNDER |
| astype | astype/datetime_to_str | exposed-v1 | 10000000 | 689 | 572 | -1.20 | 1.84 | 1.28 | -1.43 | UNDER |
| astype | astype/datetime_to_str | exposed-v1 | 3000000 | 207 | 172 | -1.21 | 0.54 | 0.38 | -1.40 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 1000000 | 133 | 183 | 1.37 | 0.66 | 0.72 | 1.08 |  |
| astype | astype/datetime_to_str | exposed-v1 | 1000000 | 67.60 | 57.22 | -1.18 | 0.18 | 0.13 | -1.37 | UNDER |
| drop_duplicates | drop_duplicates/realistic_nulls_dup30 | exposed-v1 | 3000000 | 556 | 565 | 1.02 | 2.69 | 2.17 | -1.24 | UNDER |
| numpy.sort | np_sort/reverse | exposed-v1 | 10000000 | 76.41 | 76.29 | -1.00 | 0.13 | 0.15 | 1.22 | UNDER |
| pandas.concat | concat/numeric | dev | 1000000 | 64.95 | 53.41 | -1.22 | 0.01 | 0.03 | – | UNDER |
| pandas.concat | concat/numeric | dev | 3000000 | 195 | 160 | -1.21 | 0.04 | 0.08 | – | UNDER |
| numpy.sort | np_sort/random | dev | 10000000 | 76.41 | 76.29 | -1.00 | 0.13 | 0.15 | 1.21 | UNDER |
| numpy.sort | np_sort/sorted | dev | 10000000 | 76.41 | 76.29 | -1.00 | 0.13 | 0.15 | 1.18 | UNDER |
| operator.matmul | matmul/square_f64 | dev | 4000 | 134 | 130 | -1.03 | 0.74 | 0.66 | -1.12 | UNDER |
| operator.matmul | matmul/rect_f64 | exposed-v1 | 3000 | 77.91 | 76.66 | -1.02 | 0.15 | 0.14 | -1.10 | UNDER |
| operator.matmul | matmul/square_f64 | dev | 3000 | 77.91 | 76.66 | -1.02 | 0.30 | 0.28 | -1.08 | UNDER |
| operator.matmul | matmul/rect_f64 | exposed-v1 | 6000 | 289 | 283 | -1.02 | 1.05 | 1.11 | 1.07 | UNDER |
| operator.matmul | matmul/rect_f64 | exposed-v1 | 2000 | 40.77 | 38.52 | -1.06 | 0.05 | 0.04 | – | UNDER |
| operator.matmul | matmul/square_f64 | dev | 2000 | 40.76 | 38.52 | -1.06 | 0.12 | 0.08 | – | UNDER |
| drop_duplicates | drop_duplicates/realistic_nulls_dup30 | exposed-v1 | 1000000 | 192 | 188 | -1.02 | 0.68 | 0.72 | 1.06 | UNDER |
| operator.matmul | matmul/rect_f64 | exposed-v1 | 8000 | 505 | 496 | -1.02 | 2.51 | 2.64 | 1.05 | UNDER |
| groupby | groupby/two_keys_mean_realistic | exposed-v1 | 1000000 | 78.66 | 82.26 | 1.05 | 0.11 | 0.32 | – |  |
| operator.matmul | matmul/rect_f64 | exposed-v1 | 4000 | 134 | 130 | -1.03 | 0.33 | 0.33 | -1.01 | UNDER |
| operator.matmul | matmul/square_f64 | dev | 6000 | 289 | 283 | -1.02 | 2.29 | 2.23 | -1.03 | UNDER |
| numpy.sort | np_sort/float32_random | exposed-v1 | 10000000 | 38.28 | 38.15 | -1.00 | 0.06 | 0.15 | – | UNDER |
| numpy.sort | np_sort/sorted | dev | 5000000 | 38.26 | 38.15 | -1.00 | 0.06 | 0.07 | – | UNDER |
| numpy.sort | np_sort/random | dev | 5000000 | 38.26 | 38.15 | -1.00 | 0.06 | 0.07 | – | UNDER |
| numpy.sort | np_sort/reverse | exposed-v1 | 5000000 | 38.26 | 38.15 | -1.00 | 0.06 | 0.07 | – | UNDER |
| astype | astype/float_to_float32 | dev | 10000000 | 38.25 | 38.15 | -1.00 | 0.01 | 0.03 | – | UNDER |
| astype | astype/int_to_int32 | exposed-v1 | 10000000 | 38.25 | 38.15 | -1.00 | 0.01 | 0.03 | – | UNDER |
| astype | astype/int_to_float64 | dev | 10000000 | 76.40 | 76.29 | -1.00 | 0.02 | 0.05 | – | UNDER |

## 4. read_csv parse throughput (plausibility check)

| scenario | rows | file_MB | time_s | MB_per_s |
|---|---|---|---|---|
| read_csv/mixed | 1000000 | 117 | 0.67 | 176 |
| read_csv/mixed | 3000000 | 358 | 2.02 | 178 |
| read_csv/numeric | 1000000 | 83.37 | 0.07 | 1146 |
| read_csv/numeric | 3000000 | 259 | 0.21 | 1224 |
| read_csv/strings | 1000000 | 108 | 0.69 | 157 |
| read_csv/strings | 3000000 | 326 | 2.20 | 148 |
| read_csv/realistic_nulls | 1000000 | 112 | 0.48 | 233 |
| read_csv/realistic_nulls | 3000000 | 340 | 1.26 | 271 |
| read_csv/wide_numeric | 1000000 | 263 | 0.18 | 1460 |
| read_csv/wide_numeric | 3000000 | 799 | 0.60 | 1335 |
