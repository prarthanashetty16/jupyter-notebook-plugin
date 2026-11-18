# Tier 2 vs Tier 1 on development data (ALL numbers are dev; nothing is held out)

322 development points with Tier 1 and Tier 2 predictions.

## Availability of a Tier 2 estimate

| op | points | safe_and_sampled | ram_fit | time_fit |
|---|---|---|---|---|
| astype | 63 | 43 | 32 | 38 |
| drop_duplicates | 46 | 30 | 17 | 25 |
| groupby | 51 | 18 | 11 | 12 |
| merge | 37 | 30 | 12 | 25 |
| numpy.sort | 16 | 0 | 0 | 0 |
| operator.matmul | 29 | 18 | 18 | 6 |
| pandas.concat | 27 | 16 | 16 | 0 |
| pandas.read_csv | 24 | 24 | 24 | 17 |
| sort_values | 29 | 23 | 7 | 22 |
| ALL | 322 | 202 | 137 | 145 |


Reasons RAM got no Tier 2 estimate (numbers masked):

| reason | points |
|---|---|
| RAM: # sampl# siz#s abov# th# # floor (larg#st m#asur#d #): th# larg#st sampl# i | 142 |
| no law pr#dicts th# n#xt sampl# (b#st CV #rror #) | 16 |
|  | 15 |
| no growth with sampl# siz# (fix#d cost or nois#) | 12 |


## RAM: Tier 1 (global range policy) vs Tier 2 vs combinations (valid points where the Tier 2 fit was accepted)

| op | variant | n | err_med | err_p90 | bias | coverage | above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | tier1 | 32 | 0% | 1% | 1 | 100% | 0% | 0% | 101% |
| astype | tier1_native | 32 | 0% | 1% | 1 | 100% | 0% | 0% | 32% |
| astype | tier2 | 32 | 117% | 253% | 2.17 | 66% | 0% | 34% | 1174% |
| astype | hull | 32 | 117% | 253% | 2.17 | 100% | 0% | 0% | 1181% |
| astype | geomean | 32 | 48% | 88% | 1.48 | 100% | 0% | 0% | 1790% |
| drop_duplicates | tier1 | 17 | 7% | 23% | 1.03 | 100% | 0% | 0% | 74% |
| drop_duplicates | tier1_native | 17 | 7% | 23% | 1.03 | 100% | 0% | 0% | 63% |
| drop_duplicates | tier2 | 17 | 18% | 38% | 1.18 | 88% | 0% | 12% | 124% |
| drop_duplicates | hull | 17 | 18% | 38% | 1.18 | 100% | 0% | 0% | 136% |
| drop_duplicates | geomean | 17 | 8% | 28% | 1.06 | 100% | 0% | 0% | 145% |
| groupby | tier1 | 10 | 2% | 15% | 1.01 | 100% | 0% | 0% | 166% |
| groupby | tier1_native | 10 | 2% | 15% | 1.01 | 100% | 0% | 0% | 66% |
| groupby | tier2 | 10 | 28% | 90% | 1.08 | 70% | 0% | 30% | 185% |
| groupby | hull | 10 | 28% | 90% | 1.08 | 100% | 0% | 0% | 192% |
| groupby | geomean | 10 | 10% | 46% | 1.03 | 100% | 0% | 0% | 185% |
| merge | tier1 | 12 | 6% | 19% | 1.04 | 100% | 0% | 0% | 330% |
| merge | tier1_native | 12 | 6% | 19% | 1.04 | 100% | 0% | 0% | 40% |
| merge | tier2 | 12 | 16% | 935% | 1.02 | 83% | 8% | 8% | 138% |
| merge | hull | 12 | 16% | 935% | 1.02 | 100% | 0% | 0% | 145% |
| merge | geomean | 12 | 11% | 221% | 1.04 | 100% | 0% | 0% | 230% |
| operator.matmul | tier1 | 18 | 3% | 6% | 0.967 | 100% | 0% | 0% | 109% |
| operator.matmul | tier1_native | 18 | 3% | 6% | 0.967 | 100% | 0% | 0% | 109% |
| operator.matmul | tier2 | 18 | 46% | 59% | 0.545 | 50% | 50% | 0% | 254% |
| operator.matmul | hull | 18 | 46% | 59% | 0.545 | 100% | 0% | 0% | 393% |
| operator.matmul | geomean | 18 | 28% | 37% | 0.724 | 100% | 0% | 0% | 294% |
| pandas.concat | tier1 | 16 | 5% | 8% | 0.946 | 100% | 0% | 0% | 100% |
| pandas.concat | tier1_native | 16 | 5% | 8% | 0.946 | 100% | 0% | 0% | 100% |
| pandas.concat | tier2 | 16 | 8% | 29% | 0.986 | 100% | 0% | 0% | 1628% |
| pandas.concat | hull | 16 | 8% | 29% | 0.986 | 100% | 0% | 0% | 1640% |
| pandas.concat | geomean | 16 | 6% | 15% | 0.953 | 100% | 0% | 0% | 1804% |
| pandas.read_csv | tier1 | 24 | 22% | 30% | 1.22 | 100% | 0% | 0% | 304% |
| pandas.read_csv | tier1_native | 24 | 22% | 30% | 1.22 | 100% | 0% | 0% | 58% |
| pandas.read_csv | tier2 | 24 | 19% | 48% | 1.17 | 96% | 0% | 4% | 402% |
| pandas.read_csv | hull | 24 | 19% | 48% | 1.17 | 100% | 0% | 0% | 408% |
| pandas.read_csv | geomean | 24 | 20% | 32% | 1.2 | 100% | 0% | 0% | 401% |
| sort_values | tier1 | 7 | 0% | 0% | 0.999 | 100% | 0% | 0% | 38% |
| sort_values | tier1_native | 7 | 0% | 0% | 0.999 | 100% | 0% | 0% | 38% |
| sort_values | tier2 | 7 | 33% | 752% | 1.33 | 86% | 0% | 14% | 134% |
| sort_values | hull | 7 | 33% | 752% | 1.33 | 100% | 0% | 0% | 142% |
| sort_values | geomean | 7 | 16% | 145% | 1.16 | 100% | 0% | 0% | 251% |
| ALL | tier1 | 136 | 3% | 22% | 1 | 100% | 0% | 0% | 156% |
| ALL | tier1_native | 136 | 3% | 22% | 1 | 100% | 0% | 0% | 62% |
| ALL | tier2 | 136 | 25% | 166% | 1.13 | 79% | 7% | 14% | 621% |
| ALL | hull | 136 | 25% | 166% | 1.13 | 100% | 0% | 0% | 646% |
| ALL | geomean | 136 | 16% | 65% | 1.07 | 100% | 0% | 0% | 808% |


## TIME: Tier 1 (global range policy) vs Tier 2 vs combinations (valid points where the Tier 2 fit was accepted)

| op | variant | n | err_med | err_p90 | bias | coverage | above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | tier1 | 35 | 65% | 224% | 1.41 | 97% | 3% | 0% | 375% |
| astype | tier1_native | 35 | 65% | 224% | 1.41 | 97% | 3% | 0% | 375% |
| astype | tier2 | 35 | 26% | 125% | 1.23 | 83% | 3% | 14% | 201% |
| astype | hull | 35 | 26% | 125% | 1.23 | 97% | 3% | 0% | 520% |
| astype | geomean | 35 | 50% | 111% | 1.31 | 97% | 3% | 0% | 442% |
| drop_duplicates | tier1 | 25 | 26% | 72% | 0.902 | 92% | 4% | 4% | 375% |
| drop_duplicates | tier1_native | 25 | 26% | 72% | 0.902 | 92% | 4% | 4% | 375% |
| drop_duplicates | tier2 | 25 | 39% | 57% | 0.618 | 84% | 16% | 0% | 5484% |
| drop_duplicates | hull | 25 | 39% | 57% | 0.618 | 100% | 0% | 0% | 5699% |
| drop_duplicates | geomean | 25 | 29% | 65% | 0.772 | 100% | 0% | 0% | 4051% |
| groupby | tier1 | 12 | 95% | 325% | 1.48 | 75% | 8% | 17% | 375% |
| groupby | tier1_native | 12 | 95% | 325% | 1.48 | 75% | 8% | 17% | 375% |
| groupby | tier2 | 12 | 42% | 68% | 0.718 | 67% | 25% | 8% | 171% |
| groupby | hull | 12 | 42% | 68% | 0.718 | 92% | 8% | 0% | 691% |
| groupby | geomean | 12 | 69% | 147% | 0.996 | 92% | 8% | 0% | 527% |
| merge | tier1 | 21 | 42% | 84% | 1.13 | 100% | 0% | 0% | 375% |
| merge | tier1_native | 21 | 42% | 84% | 1.13 | 100% | 0% | 0% | 375% |
| merge | tier2 | 21 | 15% | 1758% | 0.928 | 95% | 5% | 0% | 5131% |
| merge | hull | 21 | 15% | 1758% | 0.928 | 100% | 0% | 0% | 5350% |
| merge | geomean | 21 | 32% | 414% | 1.18 | 100% | 0% | 0% | 4218% |
| operator.matmul | tier1 | 5 | 3% | 5% | 0.993 | 100% | 0% | 0% | 480% |
| operator.matmul | tier1_native | 5 | 3% | 5% | 0.993 | 100% | 0% | 0% | 480% |
| operator.matmul | tier2 | 5 | 68% | 75% | 0.317 | 40% | 60% | 0% | 120% |
| operator.matmul | hull | 5 | 68% | 75% | 0.317 | 100% | 0% | 0% | 1337% |
| operator.matmul | geomean | 5 | 42% | 50% | 0.581 | 100% | 0% | 0% | 782% |
| pandas.read_csv | tier1 | 13 | 66% | 73% | 0.345 | 100% | 0% | 0% | 375% |
| pandas.read_csv | tier1_native | 13 | 66% | 73% | 0.345 | 100% | 0% | 0% | 375% |
| pandas.read_csv | tier2 | 13 | 20% | 51% | 1.2 | 100% | 0% | 0% | 1181% |
| pandas.read_csv | hull | 13 | 20% | 51% | 1.2 | 100% | 0% | 0% | 1211% |
| pandas.read_csv | geomean | 13 | 36% | 52% | 0.652 | 100% | 0% | 0% | 1243% |
| sort_values | tier1 | 22 | 38% | 175% | 0.888 | 95% | 0% | 5% | 375% |
| sort_values | tier1_native | 22 | 38% | 175% | 0.888 | 95% | 0% | 5% | 375% |
| sort_values | tier2 | 22 | 47% | 706% | 0.629 | 77% | 18% | 5% | 531% |
| sort_values | hull | 22 | 47% | 706% | 0.629 | 100% | 0% | 0% | 820% |
| sort_values | geomean | 22 | 40% | 202% | 0.703 | 100% | 0% | 0% | 769% |
| ALL | tier1 | 133 | 53% | 205% | 0.972 | 95% | 2% | 3% | 379% |
| ALL | tier1_native | 133 | 53% | 205% | 0.972 | 95% | 2% | 3% | 379% |
| ALL | tier2 | 133 | 37% | 118% | 0.928 | 83% | 12% | 5% | 2117% |
| ALL | hull | 133 | 37% | 118% | 0.928 | 98% | 2% | 0% | 2419% |
| ALL | geomean | 133 | 40% | 126% | 0.841 | 98% | 2% | 0% | 1869% |


## Overhead of the dry run

| op | n | overhead_med_s | overhead_max_s | fraction_med | share_overhead_below_run |
|---|---|---|---|---|---|
| astype | 37 | 1.8 | 3.27 | 3.44 | 8% |
| drop_duplicates | 38 | 2.11 | 4.41 | 1.5 | 39% |
| groupby | 31 | 2.04 | 7.31 | 5.96 | 29% |
| merge | 24 | 2.4 | 9.06 | 6.46 | 0% |
| numpy.sort | 3 | 1.77 | 1.78 | 13.7 | 0% |
| operator.matmul | 19 | 1.99 | 2.52 | 3.92 | 5% |
| pandas.concat | 16 | 2.92 | 13.2 | 10.3 | 0% |
| pandas.read_csv | 17 | 1.84 | 1.97 | 2.67 | 18% |
| sort_values | 26 | 2.2 | 3.6 | 1.32 | 27% |
| ALL | 211 | 1.98 | 13.2 | 3.44 | 18% |


## Where it pays off (RAM, by input size)

| bucket | points | t2_closer | median_gain_log | overhead_med_s | run_time_med_s |
|---|---|---|---|---|---|
| <=1M | 55 | 20% | -0.154 | 1.88 | 0.257 |
| 3M | 55 | 29% | -0.0988 | 1.93 | 0.506 |
| 10M+ | 26 | 23% | -0.174 | 1.98 | 0.892 |


## Merge residual points (non-unique right keys, small output)

| point | actual_MiB | t1_fold | t2_ram_ok | t2_fold | t2_in_range | reason |
|---|---|---|---|---|---|---|
| merge/inner_overlap10|n=1000000 | 49.1 | 0.931 | False | nan | None | RAM: 2 sample sizes above the 1.04858e+06 floor (largest measured 1.31 |
| merge/inner_overlap10|n=3000000 | 83.8 | 1.05 | False | nan | None | RAM: 1 sample sizes above the 1.04858e+06 floor (largest measured 6.00 |
| v3/merge/inner_overlap25_fanout6|n=1000000 | 71.8 | 0.869 | False | nan | None | no law predicts the next sample (best CV error 0.89) |
| v3/merge/inner_overlap25_fanout6|n=3000000 | 181 | 0.856 | False | nan | None | RAM: 2 sample sizes above the 1.04858e+06 floor (largest measured 1.00 |
| v4/merge/inner_overlap35_fanout7|n=1000000 | 71.6 | 0.891 | True | 0.449 | True |  |
| v4/merge/inner_overlap35_fanout7|n=3000000 | 180 | 1.85 | False | nan | None | RAM: 2 sample sizes above the 1.04858e+06 floor (largest measured 9.89 |
| v4/merge/inner_overlap20_fanout10|n=1000000 | 69.9 | 0.833 | False | nan | None | RAM: 2 sample sizes above the 1.04858e+06 floor (largest measured 2.49 |
| v4/merge/inner_overlap20_fanout10|n=3000000 | 179 | 0.794 | False | nan | None | RAM: 1 sample sizes above the 1.04858e+06 floor (largest measured 1.00 |


## Worst RAM cases for Tier 2 (log error of Tier 2 minus Tier 1)

| point_id | kind | t1_err | t2_err | worse_by | crosses_cap |
|---|---|---|---|---|---|
| v3/astype/str_to_category_card25|n=10000000 | astype | 0.00475 | 3.62 | 3.62 | False |
| concat/mixed|n=1000000 | concat | 0.0863 | 3.2 | 3.12 | False |
| v3/sort_values/int_datetime_lowcard|n=1000000 | sort_values | 0.00685 | 2.96 | 2.95 | False |
| v3/merge/left_overlap90_fanout1p2|n=1000000 | merge | 0.0725 | 2.74 | 2.67 | False |
| v4/merge/outer_overlap70_zipf1p5|n=1000000 | merge | 0.0291 | 2.43 | 2.4 | False |
| v3/astype/str_to_category_card25|n=3000000 | astype | 0.00892 | 2.4 | 2.4 | False |
| v3/astype/str_to_category_card12000|n=10000000 | astype | 0.0037 | 1.26 | 1.26 | False |
| v4/astype/str_to_category_card6000|n=10000000 | astype | 0.00472 | 1.26 | 1.26 | False |
| astype/str_to_category_lowcard|n=10000000 | astype | 0.00419 | 1.26 | 1.25 | False |
| v4/astype/str_to_category_card40000|n=10000000 | astype | 0.0044 | 1.22 | 1.22 | False |
| astype/str_to_category_zipf|n=10000000 | astype | 0.00249 | 1.2 | 1.2 | False |
| v4/astype/int_to_category_card15000|n=3000000 | astype | 0.0113 | 1.18 | 1.17 | False |


## Worst time cases for Tier 2

| point_id | kind | t1_err | t2_err | worse_by | crosses_cap |
|---|---|---|---|---|---|
| groupby/two_keys_mean_realistic|n=3000000 | groupby_agg | 0.851 | 3.77 | 2.92 | True |
| v3/merge/right_overlap05_text|n=1000000 | merge | 0.471 | 3.28 | 2.81 | False |
| v4/merge/inner_overlap95_fanout1p1|n=1000000 | merge | 0.322 | 3 | 2.68 | False |
| v4/merge/inner_overlap55_fanout4p5|n=1000000 | merge | 0.353 | 2.92 | 2.57 | False |
| sort_values/by_datetime|n=3000000 | sort_values | 0.461 | 2.7 | 2.24 | False |
| v3/merge/outer_overlap65_zipf|n=1000000 | merge | 0.363 | 2.55 | 2.19 | False |
| v4/sort_values/float_int_lowcard|n=1000000 | sort_values | 0.195 | 2.17 | 1.97 | False |
| v3/sort_values/two_str_keys|n=1000000 | sort_values | 1.47 | 3.27 | 1.8 | False |
| v4/drop_duplicates/numeric_wide_nulls12|n=3000000 | drop_duplicates | 1 | 2.62 | 1.61 | True |
| matmul/square_f64|n=6000 | matmul | 0.028 | 1.43 | 1.41 | False |
| matmul/rect_f64|n=4000 | matmul | 0.00726 | 1.29 | 1.28 | False |
| matmul/rect_f64|n=6000 | matmul | 0.0639 | 1.15 | 1.08 | False |

