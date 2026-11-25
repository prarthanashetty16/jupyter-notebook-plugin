# Tier 1 selection recheck (v4, contended run 3)

Condition: cores2_contended. 28 stored dev points (<= 10,000,000 rows), 3 repeats each, each a fresh prediction process with a 250 ms hard deadline, mains power (power seen: ['mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Every hard-deadline firing is NOT ESTIMATED. Raw rows: `tier1_selection_recheck_cores2_3.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 0 | - | - | - | - | - | - | - |
| groupby | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| merge | 4 | 0 | - | - | - | - | - | - | - |
| pandas.concat | 5 | 0 | - | - | - | - | - | - | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 1/Tier 0 selection differs between non-firing repeats: 0 of 28
Points with non-identical estimate signatures among non-firing repeats: 0 of 10 comparable points 
Successful non-firing analyses: 30/84; each is an estimate or a deterministic model-level no-estimate.
Hard-deadline firings: 30/84 = 35.71%; pre-registered bar <= 5%: **FAILED**.
Firing inputs:
- drop_duplicates/mixed_dup0|n=1000000, repeat 0
- drop_duplicates/mixed_dup0|n=1000000, repeat 1
- drop_duplicates/mixed_dup0|n=1000000, repeat 2
- v4/drop_duplicates/null_heavy_full|n=1000000, repeat 0
- v4/drop_duplicates/null_heavy_full|n=1000000, repeat 1
- v4/drop_duplicates/null_heavy_full|n=1000000, repeat 2
- v3/drop_duplicates/null_heavy_full|n=3000000, repeat 0
- v3/drop_duplicates/null_heavy_full|n=3000000, repeat 1
- v3/drop_duplicates/null_heavy_full|n=3000000, repeat 2
- v4/groupby/str_card0p9_mean|n=1000000, repeat 0
- v4/groupby/str_card0p9_mean|n=1000000, repeat 1
- v4/groupby/str_card0p9_mean|n=1000000, repeat 2
- merge/inner_1to1|n=1000000, repeat 0
- merge/inner_1to1|n=1000000, repeat 1
- merge/inner_1to1|n=1000000, repeat 2
- v4/merge/inner_overlap55_fanout4p5|n=1000000, repeat 0
- v4/merge/inner_overlap55_fanout4p5|n=1000000, repeat 1
- v4/merge/inner_overlap55_fanout4p5|n=1000000, repeat 2
- v3/merge/left_overlap90_fanout1p2|n=3000000, repeat 0
- v3/merge/left_overlap90_fanout1p2|n=3000000, repeat 1
- v3/merge/left_overlap90_fanout1p2|n=3000000, repeat 2
- concat/mixed|n=1000000, repeat 0
- concat/mixed|n=1000000, repeat 1
- concat/mixed|n=1000000, repeat 2
- v3/concat/two_strings_long|n=1000000, repeat 0
- v3/concat/two_strings_long|n=1000000, repeat 1
- v3/concat/two_strings_long|n=1000000, repeat 2
- v3/concat/four_frames_light_nulls|n=3000000, repeat 0
- v3/concat/four_frames_light_nulls|n=3000000, repeat 1
- v3/concat/four_frames_light_nulls|n=3000000, repeat 2
Non-deadline worker failures (also unestimated): 24.
- v4/astype/str_to_category_card6000|n=10000000, repeat 0: memory_limit
- v4/astype/str_to_category_card6000|n=10000000, repeat 1: memory_limit
- v4/astype/str_to_category_card6000|n=10000000, repeat 2: memory_limit
- drop_duplicates/strings_dup50|n=10000000, repeat 0: memory_limit
- drop_duplicates/strings_dup50|n=10000000, repeat 1: memory_limit
- drop_duplicates/strings_dup50|n=10000000, repeat 2: memory_limit
- v4/drop_duplicates/numeric_wide_nulls12|n=10000000, repeat 0: memory_limit
- v4/drop_duplicates/numeric_wide_nulls12|n=10000000, repeat 1: memory_limit
- v4/drop_duplicates/numeric_wide_nulls12|n=10000000, repeat 2: memory_limit
- groupby/two_keys_mean_realistic|n=10000000, repeat 0: memory_limit
- groupby/two_keys_mean_realistic|n=10000000, repeat 1: memory_limit
- groupby/two_keys_mean_realistic|n=10000000, repeat 2: memory_limit
- v4/groupby/zipf_int_card0p006|n=10000000, repeat 0: memory_limit
- v4/groupby/zipf_int_card0p006|n=10000000, repeat 1: memory_limit
- v4/groupby/zipf_int_card0p006|n=10000000, repeat 2: memory_limit
- merge/left_1to1|n=10000000, repeat 0: memory_limit
- merge/left_1to1|n=10000000, repeat 1: memory_limit
- merge/left_1to1|n=10000000, repeat 2: memory_limit
- concat/realistic_nulls|n=10000000, repeat 0: memory_limit
- concat/realistic_nulls|n=10000000, repeat 1: memory_limit
- concat/realistic_nulls|n=10000000, repeat 2: memory_limit
- v4/concat/two_category_heavy|n=10000000, repeat 0: memory_limit
- v4/concat/two_category_heavy|n=10000000, repeat 1: memory_limit
- v4/concat/two_category_heavy|n=10000000, repeat 2: memory_limit
