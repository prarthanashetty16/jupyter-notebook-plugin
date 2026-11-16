# Tier 0 diagnosis from development results

Source: `benchmarks/results/small-recal2` (suite `small`, git `1692579`). Groups used: dev and exposed-v1 only; the sealed test-v2 split is never read. Points by group: {'dev': 87}. Floors: RAM >= 32 MiB, time >= 100 ms, spread <= 30%. read_csv parser not recorded in these rows (run predates Phase 3d); verified separately.

fold = predicted/actual, shown **+x** for over-prediction and **-x** for under-prediction (x times too low). Only valid measurements get a fold.

## 1. Error structure per operation (structural vs data-dependent)

Rule: no dominant error if |bias| and scenario spread are both below x1.5; data-dependent if scenario spread >= max(|bias|, x2); otherwise structural (scaling exponent if the log-ratio size trend is >= 0.1/decade, else a constant factor).

| op | metric | points | scenarios | bias_fold | data_spread_log10 | trend_per_decade | dev_bias_fold | exposed_bias_fold | classification | evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| astype | RAM | 5 | 3 | -1.61 | 0.13 | – | -1.61 | – | structural (constant factor) | median fold -1.61; scenario spread x1.35 |
| astype | TIME | 4 | 3 | -1.30 | 0.41 | – | -1.30 | – | data-dependent | median fold -1.30; scenario spread x2.56 |
| drop_duplicates | RAM | 11 | 4 | 1.55 | 0.18 | 0.09 | 1.55 | – | structural (constant factor) | median fold +1.55; scenario spread x1.53, size trend +0.09/decade |
| drop_duplicates | TIME | 12 | 4 | -1.01 | 0.20 | -0.25 | -1.01 | – | structural (scaling exponent) | median fold -1.01; scenario spread x1.59, size trend -0.25/decade |
| groupby | RAM | 4 | 3 | 2.06 | 0.21 | – | 2.06 | – | structural (constant factor) | median fold +2.06; scenario spread x1.60 |
| groupby | TIME | 3 | 2 | -1.41 | – | – | -1.41 | – | no dominant error | median fold -1.41; n/a (<3 scenarios) |
| merge | RAM | 5 | 5 | 5.16 | 0.11 | – | 5.16 | – | structural (constant factor) | median fold +5.16; scenario spread x1.30 |
| merge | TIME | 2 | 2 | 1.48 | – | – | 1.48 | – | no dominant error | median fold +1.48; n/a (<3 scenarios) |
| operator.matmul | RAM | 2 | 1 | -1.04 | – | – | -1.04 | – | no dominant error | median fold -1.04; n/a (<3 scenarios) |
| operator.matmul | TIME | 1 | 1 | -1.08 | – | – | -1.08 | – | no dominant error | median fold -1.08; n/a (<3 scenarios) |
| pandas.concat | RAM | 4 | 2 | 1.28 | – | – | 1.28 | – | no dominant error | median fold +1.28; n/a (<3 scenarios) |
| pandas.concat | TIME | 1 | 1 | -1.42 | – | – | -1.42 | – | no dominant error | median fold -1.42; n/a (<3 scenarios) |
| pandas.read_csv | RAM | 9 | 3 | -2.67 | 0.11 | 0.03 | -2.67 | – | structural (constant factor) | median fold -2.67; scenario spread x1.30, size trend +0.03/decade |
| pandas.read_csv | TIME | 7 | 3 | -2.73 | 0.44 | -0.09 | -2.73 | – | data-dependent | median fold -2.73; scenario spread x2.76, size trend -0.09/decade |
| sort_values | RAM | 6 | 3 | 2.27 | 0.02 | – | 2.27 | – | structural (constant factor) | median fold +2.27; scenario spread x1.04 |
| sort_values | TIME | 7 | 3 | 1.41 | 0.14 | -0.16 | 1.41 | – | no dominant error | median fold +1.41; scenario spread x1.37, size trend -0.16/decade |

## 2. Scaling: log-log slope of actual time and RAM versus n

Per operation (median over scenarios); linear = 1, matmul n is the matrix side so cubic = 3. `superlinear_time` = actual time slope above 1.15 (x3 for matmul).

| op | scenarios | time_slope_actual | time_slope_pred | ram_slope_actual | ram_slope_pred | superlinear_time |
|---|---|---|---|---|---|---|
| astype | 5 | 0.99 | 1.00 | 0.98 | 1.00 | False |
| drop_duplicates | 5 | 1.25 | 1.00 | 0.90 | 1.00 | True |
| groupby | 3 | 1.02 | 1.00 | 0.96 | 1.00 | False |
| merge | 5 | 1.08 | 1.00 | 1.06 | 1.01 | False |
| numpy.sort | 2 | – | – | 0.98 | 1.00 | False |
| operator.matmul | 1 | 2.34 | 3.00 | 1.64 | 1.43 | False |
| pandas.concat | 2 | 1.21 | 1.01 | 0.99 | 1.00 | True |
| pandas.read_csv | 3 | 1.06 | 1.01 | 0.98 | 1.01 | False |
| sort_values | 3 | 1.26 | 1.05 | 1.02 | 1.00 | True |

Per scenario:

| op | scenario | points | sizes | time_pts | ram_pts | time_slope_actual | time_r2 | time_slope_pred | ram_slope_actual | ram_r2 | ram_slope_pred |
|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | astype/float_to_float32 | 3 | 300,000..3,000,000 | 0 | 3 | – | – | – | 0.97 | 1.00 | 1.00 |
| astype | astype/int_to_float64 | 3 | 300,000..3,000,000 | 0 | 3 | – | – | – | 0.98 | 1.00 | 1.00 |
| astype | astype/int_to_str | 3 | 300,000..3,000,000 | 3 | 3 | 0.99 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| astype | astype/str_to_category_highcard | 3 | 300,000..3,000,000 | 3 | 3 | 1.37 | 1.00 | 1.00 | 0.80 | 0.96 | 1.00 |
| astype | astype/str_to_category_lowcard | 3 | 300,000..3,000,000 | 3 | 3 | 0.97 | 1.00 | 1.00 | 0.98 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/mixed_dup0 | 3 | 300,000..3,000,000 | 3 | 3 | 1.24 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/mixed_dup50 | 3 | 300,000..3,000,000 | 3 | 3 | 1.28 | 0.99 | 1.00 | 0.91 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/numeric_dup50 | 3 | 300,000..3,000,000 | 3 | 3 | 1.18 | 1.00 | 1.00 | 0.90 | 1.00 | 1.00 |
| drop_duplicates | drop_duplicates/strings_dup50 | 3 | 300,000..3,000,000 | 3 | 3 | 1.26 | 1.00 | 1.00 | 0.87 | 0.98 | 1.00 |
| drop_duplicates | drop_duplicates/subset_s0_lowcard | 3 | 300,000..3,000,000 | 1 | 3 | – | – | – | 0.66 | 0.86 | 1.00 |
| groupby | groupby/int_sum_numeric | 3 | 300,000..3,000,000 | 2 | 3 | 1.02 | 1.00 | 1.00 | 0.96 | 1.00 | 1.00 |
| groupby | groupby/str_highcard_sum_f0 | 3 | 300,000..3,000,000 | 3 | 3 | 1.33 | 1.00 | 1.00 | 0.81 | 0.96 | 1.00 |
| groupby | groupby/str_lowcard_sum_f0 | 3 | 300,000..3,000,000 | 2 | 3 | 1.01 | 1.00 | 1.00 | 0.98 | 1.00 | 1.00 |
| merge | merge/inner_1to1 | 2 | 300,000..1,000,000 | 2 | 2 | 1.04 | 1.00 | 1.00 | 1.06 | 1.00 | 1.01 |
| merge | merge/inner_fanout3 | 2 | 300,000..1,000,000 | 2 | 2 | 1.01 | 1.00 | 1.00 | 1.02 | 1.00 | 1.01 |
| merge | merge/inner_manymany | 2 | 300,000..1,000,000 | 2 | 2 | 1.12 | 1.00 | 1.00 | 1.01 | 1.00 | 1.01 |
| merge | merge/inner_overlap10 | 2 | 300,000..1,000,000 | 1 | 2 | – | – | – | 1.08 | 1.00 | 1.01 |
| merge | merge/left_1to1 | 2 | 300,000..1,000,000 | 2 | 2 | 1.12 | 1.00 | 1.00 | 1.06 | 1.00 | 1.01 |
| numpy.sort | np_sort/random | 3 | 300,000..3,000,000 | 1 | 3 | – | – | – | 0.98 | 1.00 | 1.00 |
| numpy.sort | np_sort/sorted | 3 | 300,000..3,000,000 | 1 | 3 | – | – | – | 0.98 | 1.00 | 1.00 |
| operator.matmul | matmul/square_f64 | 3 | 1,000..3,000 | 3 | 3 | 2.34 | 0.99 | 3.00 | 1.64 | 1.00 | 1.43 |
| pandas.concat | concat/mixed | 3 | 300,000..3,000,000 | 3 | 3 | 1.21 | 1.00 | 1.01 | 0.99 | 1.00 | 1.01 |
| pandas.concat | concat/numeric | 3 | 300,000..3,000,000 | 1 | 3 | – | – | – | 1.00 | 1.00 | 1.00 |
| pandas.read_csv | read_csv/mixed | 3 | 300,000..3,000,000 | 3 | 3 | 1.06 | 1.00 | 1.01 | 0.98 | 1.00 | 1.01 |
| pandas.read_csv | read_csv/numeric | 3 | 300,000..3,000,000 | 3 | 3 | 0.91 | 0.99 | 1.02 | 0.96 | 1.00 | 1.02 |
| pandas.read_csv | read_csv/strings | 3 | 300,000..3,000,000 | 3 | 3 | 1.13 | 1.00 | 1.00 | 0.99 | 1.00 | 1.00 |
| sort_values | sort_values/by_int | 3 | 300,000..3,000,000 | 3 | 3 | 1.30 | 1.00 | 1.04 | 1.02 | 1.00 | 1.00 |
| sort_values | sort_values/by_int_float | 3 | 300,000..3,000,000 | 3 | 3 | 1.26 | 1.00 | 1.05 | 1.01 | 1.00 | 1.00 |
| sort_values | sort_values/by_str | 3 | 300,000..3,000,000 | 3 | 3 | 1.23 | 1.00 | 1.07 | 1.02 | 1.00 | 1.00 |

## 3. Largest errors, both directions

### 3a. Under-predictions (actual above predicted), worst 25

| op | scenario | split | size | ram_actual_MB | ram_pred_MB | ram_fold | time_actual_s | time_pred_s | time_fold |
|---|---|---|---|---|---|---|---|---|---|
| astype | astype/str_to_category_highcard | dev | 1000000 | 74.30 | 18.69 | -3.98 | 0.51 | 0.22 | -2.34 |
| pandas.read_csv | read_csv/strings | dev | 3000000 | 1327 | 466 | -2.85 | 2.49 | 0.67 | -3.70 |
| astype | astype/str_to_category_highcard | dev | 3000000 | 127 | 56.08 | -2.26 | 2.27 | 0.65 | -3.49 |
| pandas.read_csv | read_csv/strings | dev | 1000000 | 438 | 154 | -2.84 | 0.75 | 0.22 | -3.36 |
| pandas.read_csv | read_csv/strings | dev | 300000 | 135 | 46.19 | -2.91 | 0.19 | 0.07 | -2.79 |
| pandas.read_csv | read_csv/mixed | dev | 300000 | 143 | 49.97 | -2.86 | 0.18 | 0.07 | -2.44 |
| pandas.read_csv | read_csv/mixed | dev | 3000000 | 1370 | 513 | -2.67 | 2.01 | 0.74 | -2.73 |
| pandas.read_csv | read_csv/mixed | dev | 1000000 | 446 | 168 | -2.66 | 0.65 | 0.24 | -2.68 |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 3000000 | 289 | 286 | -1.01 | 2.03 | 0.80 | -2.52 |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 1000000 | 117 | 95.37 | -1.23 | 0.63 | 0.27 | -2.34 |
| groupby | groupby/str_highcard_sum_f0 | dev | 3000000 | 127 | 219 | 1.73 | 1.77 | 0.84 | -2.10 |
| pandas.read_csv | read_csv/numeric | dev | 300000 | 62.91 | 35.33 | -1.78 | 0.02 | 0.05 | – |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 300000 | 36.68 | 28.61 | -1.28 | 0.13 | 0.08 | -1.66 |
| astype | astype/int_to_str | dev | 1000000 | 91.92 | 57.22 | -1.61 | 0.09 | 0.13 | – |
| astype | astype/int_to_str | dev | 3000000 | 276 | 172 | -1.61 | 0.28 | 0.38 | 1.38 |
| pandas.read_csv | read_csv/numeric | dev | 1000000 | 190 | 119 | -1.59 | 0.06 | 0.17 | – |
| astype | astype/str_to_category_lowcard | dev | 3000000 | 87.17 | 56.08 | -1.55 | 0.19 | 0.65 | 3.43 |
| pandas.read_csv | read_csv/numeric | dev | 3000000 | 571 | 370 | -1.54 | 0.19 | 0.53 | 2.84 |
| pandas.concat | concat/mixed | dev | 3000000 | 251 | 500 | 1.99 | 0.35 | 0.24 | -1.42 |
| groupby | groupby/str_highcard_sum_f0 | dev | 1000000 | 74.41 | 73.05 | -1.02 | 0.40 | 0.28 | -1.41 |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 3000000 | 335 | 548 | 1.63 | 2.86 | 2.16 | -1.33 |
| sort_values | sort_values/by_int_float | dev | 3000000 | 241 | 592 | 2.46 | 1.14 | 0.86 | -1.32 |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 3000000 | 335 | 548 | 1.63 | 2.65 | 2.16 | -1.23 |
| pandas.concat | concat/numeric | dev | 1000000 | 64.96 | 53.41 | -1.22 | 0.02 | 0.03 | – |
| pandas.concat | concat/numeric | dev | 3000000 | 195 | 160 | -1.21 | 0.06 | 0.08 | – |

### 3b. Every valid point, sorted by worst error in either direction (rows with a negative fold are under-predictions)

| op | scenario | split | size | ram_actual_MB | ram_pred_MB | ram_fold | time_actual_s | time_pred_s | time_fold | under |
|---|---|---|---|---|---|---|---|---|---|---|
| groupby | groupby/str_lowcard_sum_f0 | dev | 3000000 | 86.92 | 214 | 2.46 | 0.12 | 0.84 | 6.92 |  |
| merge | merge/inner_overlap10 | dev | 1000000 | 49.33 | 286 | 5.80 | 0.05 | 0.17 | – |  |
| merge | merge/left_1to1 | dev | 1000000 | 54.39 | 286 | 5.26 | 0.08 | 0.17 | – |  |
| merge | merge/inner_1to1 | dev | 1000000 | 55.39 | 286 | 5.16 | 0.08 | 0.17 | – |  |
| merge | merge/inner_fanout3 | dev | 1000000 | 63.89 | 286 | 4.48 | 0.12 | 0.17 | 1.50 |  |
| groupby | groupby/int_sum_numeric | dev | 3000000 | 46.24 | 191 | 4.13 | 0.07 | 0.32 | – |  |
| astype | astype/str_to_category_highcard | dev | 1000000 | 74.30 | 18.69 | -3.98 | 0.51 | 0.22 | -2.34 | UNDER |
| pandas.read_csv | read_csv/strings | dev | 3000000 | 1327 | 466 | -2.85 | 2.49 | 0.67 | -3.70 | UNDER |
| astype | astype/str_to_category_highcard | dev | 3000000 | 127 | 56.08 | -2.26 | 2.27 | 0.65 | -3.49 | UNDER |
| astype | astype/str_to_category_lowcard | dev | 3000000 | 87.17 | 56.08 | -1.55 | 0.19 | 0.65 | 3.43 | UNDER |
| pandas.read_csv | read_csv/strings | dev | 1000000 | 438 | 154 | -2.84 | 0.75 | 0.22 | -3.36 | UNDER |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 3000000 | 211 | 681 | 3.23 | 2.37 | 2.86 | 1.21 |  |
| pandas.read_csv | read_csv/strings | dev | 300000 | 135 | 46.19 | -2.91 | 0.19 | 0.07 | -2.79 | UNDER |
| pandas.read_csv | read_csv/mixed | dev | 300000 | 143 | 49.97 | -2.86 | 0.18 | 0.07 | -2.44 | UNDER |
| pandas.read_csv | read_csv/numeric | dev | 3000000 | 571 | 370 | -1.54 | 0.19 | 0.53 | 2.84 | UNDER |
| merge | merge/inner_manymany | dev | 1000000 | 104 | 286 | 2.76 | 0.12 | 0.17 | 1.46 |  |
| pandas.read_csv | read_csv/mixed | dev | 3000000 | 1370 | 513 | -2.67 | 2.01 | 0.74 | -2.73 | UNDER |
| pandas.read_csv | read_csv/mixed | dev | 1000000 | 446 | 168 | -2.66 | 0.65 | 0.24 | -2.68 | UNDER |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 3000000 | 289 | 286 | -1.01 | 2.03 | 0.80 | -2.52 | UNDER |
| sort_values | sort_values/by_int_float | dev | 3000000 | 241 | 592 | 2.46 | 1.14 | 0.86 | -1.32 | UNDER |
| sort_values | sort_values/by_int_float | dev | 1000000 | 80.44 | 197 | 2.45 | 0.26 | 0.27 | 1.04 |  |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 1000000 | 117 | 95.37 | -1.23 | 0.63 | 0.27 | -2.34 | UNDER |
| sort_values | sort_values/by_str | dev | 3000000 | 241 | 546 | 2.27 | 2.16 | 3.18 | 1.47 |  |
| sort_values | sort_values/by_int | dev | 3000000 | 241 | 546 | 2.27 | 0.59 | 0.55 | -1.08 | UNDER |
| sort_values | sort_values/by_int | dev | 1000000 | 80.72 | 182 | 2.25 | 0.12 | 0.18 | 1.41 |  |
| sort_values | sort_values/by_str | dev | 1000000 | 81.30 | 182 | 2.24 | 0.52 | 0.99 | 1.90 |  |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 300000 | 28.55 | 68.09 | – | 0.13 | 0.29 | 2.21 |  |
| drop_duplicates | drop_duplicates/strings_dup50 | dev | 1000000 | 103 | 227 | 2.20 | 0.65 | 0.95 | 1.47 |  |
| sort_values | sort_values/by_str | dev | 300000 | 23.16 | 54.02 | – | 0.13 | 0.27 | 2.12 |  |
| groupby | groupby/str_highcard_sum_f0 | dev | 3000000 | 127 | 219 | 1.73 | 1.77 | 0.84 | -2.10 | UNDER |
| pandas.concat | concat/mixed | dev | 3000000 | 251 | 500 | 1.99 | 0.35 | 0.24 | -1.42 | UNDER |
| pandas.concat | concat/mixed | dev | 1000000 | 83.62 | 167 | 1.99 | 0.08 | 0.08 | – |  |
| pandas.read_csv | read_csv/numeric | dev | 300000 | 62.91 | 35.33 | -1.78 | 0.02 | 0.05 | – | UNDER |
| drop_duplicates | drop_duplicates/numeric_dup50 | dev | 300000 | 36.68 | 28.61 | -1.28 | 0.13 | 0.08 | -1.66 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 3000000 | 335 | 548 | 1.63 | 2.65 | 2.16 | -1.23 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 3000000 | 335 | 548 | 1.63 | 2.86 | 2.16 | -1.33 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 300000 | 33.56 | 54.47 | 1.62 | 0.15 | 0.22 | 1.41 |  |
| astype | astype/int_to_str | dev | 1000000 | 91.92 | 57.22 | -1.61 | 0.09 | 0.13 | – | UNDER |
| astype | astype/int_to_str | dev | 3000000 | 276 | 172 | -1.61 | 0.28 | 0.38 | 1.38 | UNDER |
| pandas.read_csv | read_csv/numeric | dev | 1000000 | 190 | 119 | -1.59 | 0.06 | 0.17 | – | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup0 | dev | 1000000 | 118 | 183 | 1.55 | 0.62 | 0.72 | 1.15 |  |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 300000 | 41.00 | 54.47 | 1.33 | 0.15 | 0.22 | 1.42 |  |
| groupby | groupby/str_highcard_sum_f0 | dev | 1000000 | 74.41 | 73.05 | -1.02 | 0.40 | 0.28 | -1.41 | UNDER |
| drop_duplicates | drop_duplicates/mixed_dup50 | dev | 1000000 | 133 | 183 | 1.37 | 0.85 | 0.72 | -1.18 | UNDER |
| pandas.concat | concat/numeric | dev | 1000000 | 64.96 | 53.41 | -1.22 | 0.02 | 0.03 | – | UNDER |
| pandas.concat | concat/numeric | dev | 3000000 | 195 | 160 | -1.21 | 0.06 | 0.08 | – | UNDER |
| operator.matmul | matmul/square_f64 | dev | 3000 | 77.91 | 76.66 | -1.02 | 0.30 | 0.28 | -1.08 | UNDER |
| operator.matmul | matmul/square_f64 | dev | 2000 | 40.76 | 38.52 | -1.06 | 0.09 | 0.08 | – | UNDER |

## 4. read_csv parse throughput (plausibility check)

| scenario | rows | file_MB | time_s | MB_per_s |
|---|---|---|---|---|
| read_csv/mixed | 300000 | 34.93 | 0.18 | 199 |
| read_csv/mixed | 1000000 | 117 | 0.65 | 181 |
| read_csv/mixed | 3000000 | 358 | 2.01 | 178 |
| read_csv/numeric | 300000 | 24.70 | 0.02 | 1082 |
| read_csv/numeric | 1000000 | 83.37 | 0.06 | 1391 |
| read_csv/numeric | 3000000 | 259 | 0.19 | 1380 |
| read_csv/strings | 300000 | 32.29 | 0.19 | 174 |
| read_csv/strings | 1000000 | 108 | 0.75 | 144 |
| read_csv/strings | 3000000 | 326 | 2.49 | 131 |
