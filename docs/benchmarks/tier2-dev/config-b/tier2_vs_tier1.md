# Tier 2 vs Tier 1 on development data (ALL numbers are dev; nothing is held out)

322 development points with Tier 1 and Tier 2 predictions.

## Availability of a Tier 2 estimate

| op | points | safe_and_sampled | ram_fit | time_fit |
|---|---|---|---|---|
| astype | 63 | 54 | 52 | 47 |
| drop_duplicates | 46 | 37 | 28 | 33 |
| groupby | 51 | 25 | 18 | 16 |
| merge | 37 | 37 | 34 | 25 |
| numpy.sort | 16 | 12 | 12 | 3 |
| operator.matmul | 29 | 18 | 18 | 6 |
| pandas.concat | 27 | 27 | 27 | 5 |
| pandas.read_csv | 24 | 23 | 23 | 18 |
| sort_values | 29 | 26 | 24 | 20 |
| ALL | 322 | 259 | 236 | 173 |


Reasons RAM got no Tier 2 estimate (numbers masked):

| reason | points |
|---|---|
| RAM: # sampl# siz#s abov# th# # floor (larg#st m#asur#d #): th# larg#st sampl# i | 53 |
|  | 15 |
| no law pr#dicts th# n#xt sampl# (b#st CV #rror #) | 12 |
| no growth with sampl# siz# (fix#d cost or nois#) | 6 |


## RAM: Tier 1 (global range policy) vs Tier 2 vs combinations (valid points where the Tier 2 fit was accepted)

| op | variant | n | err_med | err_p90 | bias | coverage | above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | tier1 | 48 | 1% | 1% | 1 | 100% | 0% | 0% | 90% |
| astype | tier1_native | 48 | 1% | 1% | 1 | 100% | 0% | 0% | 46% |
| astype | tier2 | 48 | 15% | 156% | 1.05 | 60% | 2% | 38% | 284% |
| astype | hull | 48 | 15% | 156% | 1.05 | 100% | 0% | 0% | 311% |
| astype | geomean | 48 | 8% | 60% | 1.03 | 100% | 0% | 0% | 365% |
| drop_duplicates | tier1 | 27 | 11% | 17% | 1.03 | 100% | 0% | 0% | 75% |
| drop_duplicates | tier1_native | 27 | 11% | 17% | 1.03 | 100% | 0% | 0% | 66% |
| drop_duplicates | tier2 | 27 | 13% | 29% | 1.11 | 89% | 0% | 11% | 238% |
| drop_duplicates | hull | 27 | 13% | 29% | 1.11 | 100% | 0% | 0% | 254% |
| drop_duplicates | geomean | 27 | 7% | 18% | 1.06 | 100% | 0% | 0% | 256% |
| groupby | tier1 | 17 | 1% | 16% | 1.01 | 100% | 0% | 0% | 222% |
| groupby | tier1_native | 17 | 1% | 16% | 1.01 | 100% | 0% | 0% | 64% |
| groupby | tier2 | 17 | 14% | 88% | 1.14 | 76% | 0% | 24% | 212% |
| groupby | hull | 17 | 14% | 88% | 1.14 | 100% | 0% | 0% | 228% |
| groupby | geomean | 17 | 11% | 36% | 1.11 | 100% | 0% | 0% | 249% |
| merge | tier1 | 34 | 8% | 19% | 1.08 | 97% | 0% | 3% | 503% |
| merge | tier1_native | 34 | 8% | 19% | 1.08 | 91% | 6% | 3% | 58% |
| merge | tier2 | 34 | 13% | 376% | 1.11 | 79% | 3% | 18% | 449% |
| merge | hull | 34 | 13% | 376% | 1.11 | 97% | 0% | 3% | 480% |
| merge | geomean | 34 | 11% | 120% | 1.09 | 97% | 0% | 3% | 529% |
| numpy.sort | tier1 | 12 | 0% | 0% | 0.997 | 100% | 0% | 0% | 40% |
| numpy.sort | tier1_native | 12 | 0% | 0% | 0.997 | 100% | 0% | 0% | 40% |
| numpy.sort | tier2 | 12 | 0% | 0% | 1 | 100% | 0% | 0% | 39% |
| numpy.sort | hull | 12 | 0% | 0% | 1 | 100% | 0% | 0% | 42% |
| numpy.sort | geomean | 12 | 0% | 0% | 0.999 | 100% | 0% | 0% | 42% |
| operator.matmul | tier1 | 18 | 3% | 6% | 0.967 | 100% | 0% | 0% | 109% |
| operator.matmul | tier1_native | 18 | 3% | 6% | 0.967 | 100% | 0% | 0% | 109% |
| operator.matmul | tier2 | 18 | 45% | 59% | 0.545 | 44% | 50% | 6% | 250% |
| operator.matmul | hull | 18 | 45% | 59% | 0.545 | 100% | 0% | 0% | 391% |
| operator.matmul | geomean | 18 | 28% | 37% | 0.724 | 100% | 0% | 0% | 292% |
| pandas.concat | tier1 | 27 | 8% | 16% | 0.923 | 100% | 0% | 0% | 100% |
| pandas.concat | tier1_native | 27 | 8% | 16% | 0.923 | 100% | 0% | 0% | 100% |
| pandas.concat | tier2 | 27 | 9% | 18% | 0.933 | 100% | 0% | 0% | 186% |
| pandas.concat | hull | 27 | 9% | 18% | 0.933 | 100% | 0% | 0% | 219% |
| pandas.concat | geomean | 27 | 9% | 15% | 0.915 | 100% | 0% | 0% | 229% |
| pandas.read_csv | tier1 | 23 | 22% | 30% | 1.22 | 100% | 0% | 0% | 312% |
| pandas.read_csv | tier1_native | 23 | 22% | 30% | 1.22 | 100% | 0% | 0% | 59% |
| pandas.read_csv | tier2 | 23 | 15% | 29% | 1.14 | 74% | 0% | 26% | 128% |
| pandas.read_csv | hull | 23 | 15% | 29% | 1.14 | 100% | 0% | 0% | 143% |
| pandas.read_csv | geomean | 23 | 19% | 26% | 1.19 | 100% | 0% | 0% | 138% |
| sort_values | tier1 | 24 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| sort_values | tier1_native | 24 | 1% | 1% | 1.01 | 100% | 0% | 0% | 45% |
| sort_values | tier2 | 24 | 3% | 21% | 1.02 | 96% | 0% | 4% | 235% |
| sort_values | hull | 24 | 3% | 21% | 1.02 | 100% | 0% | 0% | 240% |
| sort_values | geomean | 24 | 2% | 10% | 1.01 | 100% | 0% | 0% | 262% |
| ALL | tier1 | 230 | 3% | 20% | 1 | 100% | 0% | 0% | 177% |
| ALL | tier1_native | 230 | 3% | 20% | 1 | 99% | 1% | 0% | 64% |
| ALL | tier2 | 230 | 13% | 75% | 1.04 | 78% | 5% | 17% | 250% |
| ALL | hull | 230 | 13% | 75% | 1.04 | 100% | 0% | 0% | 280% |
| ALL | geomean | 230 | 10% | 38% | 1.03 | 100% | 0% | 0% | 296% |


## TIME: Tier 1 (global range policy) vs Tier 2 vs combinations (valid points where the Tier 2 fit was accepted)

| op | variant | n | err_med | err_p90 | bias | coverage | above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| astype | tier1 | 36 | 67% | 224% | 1.41 | 97% | 3% | 0% | 375% |
| astype | tier1_native | 36 | 67% | 224% | 1.41 | 97% | 3% | 0% | 375% |
| astype | tier2 | 36 | 21% | 72% | 1.21 | 78% | 0% | 22% | 133% |
| astype | hull | 36 | 21% | 72% | 1.21 | 100% | 0% | 0% | 541% |
| astype | geomean | 36 | 51% | 98% | 1.46 | 100% | 0% | 0% | 478% |
| drop_duplicates | tier1 | 29 | 28% | 63% | 0.941 | 97% | 3% | 0% | 375% |
| drop_duplicates | tier1_native | 29 | 28% | 63% | 0.941 | 97% | 3% | 0% | 375% |
| drop_duplicates | tier2 | 29 | 32% | 46% | 0.702 | 79% | 14% | 7% | 957% |
| drop_duplicates | hull | 29 | 32% | 46% | 0.702 | 100% | 0% | 0% | 1213% |
| drop_duplicates | geomean | 29 | 25% | 66% | 0.775 | 100% | 0% | 0% | 1292% |
| groupby | tier1 | 14 | 95% | 302% | 1.61 | 79% | 7% | 14% | 375% |
| groupby | tier1_native | 14 | 95% | 302% | 1.61 | 79% | 7% | 14% | 375% |
| groupby | tier2 | 14 | 33% | 55% | 0.667 | 50% | 43% | 7% | 133% |
| groupby | hull | 14 | 33% | 55% | 0.667 | 93% | 7% | 0% | 840% |
| groupby | geomean | 14 | 66% | 88% | 1.04 | 93% | 7% | 0% | 525% |
| merge | tier1 | 20 | 38% | 76% | 1.1 | 100% | 0% | 0% | 375% |
| merge | tier1_native | 20 | 38% | 76% | 1.1 | 100% | 0% | 0% | 375% |
| merge | tier2 | 20 | 16% | 32% | 0.87 | 90% | 5% | 5% | 7759% |
| merge | hull | 20 | 16% | 32% | 0.87 | 100% | 0% | 0% | 8098% |
| merge | geomean | 20 | 25% | 43% | 1.05 | 100% | 0% | 0% | 10253% |
| numpy.sort | tier1 | 3 | 21% | 22% | 1.21 | 100% | 0% | 0% | 390% |
| numpy.sort | tier1_native | 3 | 21% | 22% | 1.21 | 100% | 0% | 0% | 390% |
| numpy.sort | tier2 | 3 | 25% | 412% | 0.834 | 100% | 0% | 0% | 114% |
| numpy.sort | hull | 3 | 25% | 412% | 0.834 | 100% | 0% | 0% | 470% |
| numpy.sort | geomean | 3 | 5% | 135% | 1.01 | 100% | 0% | 0% | 483% |
| operator.matmul | tier1 | 6 | 6% | 187% | 1.02 | 100% | 0% | 0% | 480% |
| operator.matmul | tier1_native | 6 | 6% | 187% | 1.02 | 100% | 0% | 0% | 480% |
| operator.matmul | tier2 | 6 | 50% | 73% | 0.619 | 50% | 50% | 0% | 185% |
| operator.matmul | hull | 6 | 50% | 73% | 0.619 | 100% | 0% | 0% | 1371% |
| operator.matmul | geomean | 6 | 38% | 81% | 0.815 | 100% | 0% | 0% | 788% |
| pandas.concat | tier1 | 5 | 44% | 102% | 1.44 | 100% | 0% | 0% | 375% |
| pandas.concat | tier1_native | 5 | 44% | 102% | 1.44 | 100% | 0% | 0% | 375% |
| pandas.concat | tier2 | 5 | 32% | 60% | 1.32 | 80% | 0% | 20% | 2741% |
| pandas.concat | hull | 5 | 32% | 60% | 1.32 | 100% | 0% | 0% | 2974% |
| pandas.concat | geomean | 5 | 23% | 51% | 1.23 | 100% | 0% | 0% | 2609% |
| pandas.read_csv | tier1 | 15 | 66% | 134% | 0.363 | 100% | 0% | 0% | 375% |
| pandas.read_csv | tier1_native | 15 | 66% | 134% | 0.363 | 100% | 0% | 0% | 375% |
| pandas.read_csv | tier2 | 15 | 4% | 21% | 1.02 | 100% | 0% | 0% | 728% |
| pandas.read_csv | hull | 15 | 4% | 21% | 1.02 | 100% | 0% | 0% | 772% |
| pandas.read_csv | geomean | 15 | 43% | 62% | 0.603 | 100% | 0% | 0% | 918% |
| sort_values | tier1 | 20 | 38% | 194% | 0.857 | 95% | 0% | 5% | 375% |
| sort_values | tier1_native | 20 | 38% | 194% | 0.857 | 95% | 0% | 5% | 375% |
| sort_values | tier2 | 20 | 31% | 100% | 0.767 | 85% | 15% | 0% | 1209% |
| sort_values | hull | 20 | 31% | 100% | 0.767 | 100% | 0% | 0% | 1432% |
| sort_values | geomean | 20 | 35% | 141% | 0.773 | 100% | 0% | 0% | 1368% |
| ALL | tier1 | 148 | 53% | 200% | 0.994 | 96% | 2% | 2% | 380% |
| ALL | tier1_native | 148 | 53% | 200% | 0.994 | 96% | 2% | 2% | 380% |
| ALL | tier2 | 148 | 25% | 61% | 0.929 | 80% | 11% | 9% | 1621% |
| ALL | hull | 148 | 25% | 61% | 0.929 | 99% | 1% | 0% | 1980% |
| ALL | geomean | 148 | 39% | 93% | 0.898 | 99% | 1% | 0% | 2212% |


## Overhead of the dry run

| op | n | overhead_med_s | overhead_max_s | fraction_med | share_overhead_below_run |
|---|---|---|---|---|---|
| astype | 37 | 1.9 | 2.6 | 3.41 | 5% |
| drop_duplicates | 38 | 2.3 | 6.6 | 1.63 | 24% |
| groupby | 31 | 2.15 | 7.91 | 6.28 | 29% |
| merge | 24 | 2.67 | 3.36 | 6.58 | 0% |
| numpy.sort | 3 | 1.85 | 1.86 | 14.4 | 0% |
| operator.matmul | 19 | 1.95 | 2.3 | 4.07 | 11% |
| pandas.concat | 16 | 3 | 13.7 | 10.7 | 0% |
| pandas.read_csv | 17 | 1.91 | 2.27 | 2.87 | 0% |
| sort_values | 26 | 2.64 | 6.13 | 1.75 | 23% |
| ALL | 211 | 2.15 | 13.7 | 3.8 | 13% |


## Where it pays off (RAM, by input size)

| bucket | points | t2_closer | median_gain_log | overhead_med_s | run_time_med_s |
|---|---|---|---|---|---|
| <=1M | 93 | 32% | -0.0812 | 1.93 | 0.176 |
| 3M | 87 | 39% | -0.0365 | 2.25 | 0.506 |
| 10M+ | 50 | 42% | -0.00341 | 2.54 | 0.892 |


## Merge residual points (non-unique right keys, small output)

| point | actual_MiB | t1_fold | t2_ram_ok | t2_fold | t2_in_range | reason |
|---|---|---|---|---|---|---|
| merge/inner_overlap10|n=1000000 | 49.1 | 0.931 | False | nan | None | no law predicts the next sample (best CV error 0.54) |
| merge/inner_overlap10|n=3000000 | 83.8 | 1.05 | True | 1.86 | False |  |
| v3/merge/inner_overlap25_fanout6|n=1000000 | 71.8 | 0.869 | True | 1.03 | True |  |
| v3/merge/inner_overlap25_fanout6|n=3000000 | 181 | 0.856 | True | 1.24 | True |  |
| v4/merge/inner_overlap35_fanout7|n=1000000 | 71.6 | 0.891 | True | 1.04 | True |  |
| v4/merge/inner_overlap35_fanout7|n=3000000 | 180 | 1.85 | True | 1.05 | True |  |
| v4/merge/inner_overlap20_fanout10|n=1000000 | 69.9 | 0.833 | True | 11.2 | False |  |
| v4/merge/inner_overlap20_fanout10|n=3000000 | 179 | 0.794 | False | nan | None | RAM: 2 sample sizes above the 1.04858e+06 floor (largest measured 2.08 |


## Worst RAM cases for Tier 2 (log error of Tier 2 minus Tier 1)

| point_id | kind | t1_err | t2_err | worse_by | crosses_cap |
|---|---|---|---|---|---|
| v4/merge/inner_overlap20_fanout10|n=1000000 | merge | 0.182 | 2.42 | 2.23 | False |
| astype/str_to_category_zipf|n=1000000 | astype | 0.00179 | 2.05 | 2.05 | False |
| v4/astype/str_to_category_card150000|n=1000000 | astype | 0.01 | 2.01 | 2 | False |
| v3/merge/right_overlap05_text|n=1000000 | merge | 0.127 | 2.13 | 2 | False |
| v4/astype/str_to_category_card6000|n=1000000 | astype | 0.00947 | 1.88 | 1.88 | False |
| v4/merge/outer_overlap70_zipf1p5|n=1000000 | merge | 0.0291 | 1.79 | 1.76 | False |
| merge/inner_fanout3|n=1000000 | merge | 0.108 | 1.81 | 1.7 | False |
| v4/astype/str_to_category_card150000|n=10000000 | astype | 0.00441 | 0.956 | 0.951 | False |
| astype/str_to_category_zipf|n=10000000 | astype | 0.00249 | 0.94 | 0.937 | False |
| v4/astype/str_to_category_card40000|n=10000000 | astype | 0.0044 | 0.939 | 0.935 | False |
| matmul/rect_f64|n=6000 | matmul | 0.022 | 0.936 | 0.914 | False |
| matmul/square_f64|n=6000 | matmul | 0.0219 | 0.935 | 0.913 | False |


## Worst time cases for Tier 2

| point_id | kind | t1_err | t2_err | worse_by | crosses_cap |
|---|---|---|---|---|---|
| astype/str_to_category_highcard|n=1000000 | astype | 0.659 | 2.75 | 2.09 | False |
| v3/drop_duplicates/high_survivor_subset_i0_d0|n=1000000 | drop_duplicates | 0.412 | 2.2 | 1.79 | False |
| np_sort/sorted|n=10000000 | np_sort | 0.164 | 1.81 | 1.64 | False |
| drop_duplicates/mixed_dup50|n=1000000 | drop_duplicates | 0.0967 | 1.67 | 1.57 | False |
| v4/matmul/three_quarter_rect|n=4000 | matmul | 0.0189 | 1.38 | 1.37 | False |
| matmul/rect_f64|n=8000 | matmul | 0.0508 | 1.24 | 1.19 | False |
| sort_values/by_str_desc_nulls|n=1000000 | sort_values | 0.769 | 1.93 | 1.16 | False |
| v3/sort_values/two_str_keys|n=1000000 | sort_values | 1.47 | 2.39 | 0.92 | False |
| v3/drop_duplicates/null_subset_f0_s0|n=3000000 | drop_duplicates | 0.0199 | 0.682 | 0.662 | True |
| v4/astype/str_to_category_card0p12|n=1000000 | astype | 0.108 | 0.611 | 0.504 | False |
| v4/astype/str_to_category_card150000|n=1000000 | astype | 0.0594 | 0.554 | 0.494 | False |
| matmul/rect_f64|n=4000 | matmul | 0.00726 | 0.446 | 0.439 | False |

