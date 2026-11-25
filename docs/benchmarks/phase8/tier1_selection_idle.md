# Tier 1 deterministic selection, v4 dev, idle machine

Condition: all. 28 stored dev points (<= 10,000,000 rows), 3 repeats each, each a fresh prediction process with a 250 ms hard deadline, mains power (power seen: ['mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Every hard-deadline firing is NOT ESTIMATED. Raw rows: `tier1_selection_idle.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| groupby | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| merge | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| pandas.concat | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 1/Tier 0 selection differs between non-firing repeats: 0 of 28
Points with non-identical estimate signatures among non-firing repeats: 0 of 19 comparable points
Successful non-firing analyses: 56/84; each is an estimate or a deterministic model-level no-estimate.
Hard-deadline firings: 28/84 = 33.33%; pre-registered bar <= 0%: **FAILED**.
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
- drop_duplicates/strings_dup50|n=10000000, repeat 0
- drop_duplicates/strings_dup50|n=10000000, repeat 1
- drop_duplicates/strings_dup50|n=10000000, repeat 2
- v3/merge/left_overlap90_fanout1p2|n=3000000, repeat 1
- merge/left_1to1|n=10000000, repeat 0
- merge/left_1to1|n=10000000, repeat 1
- merge/left_1to1|n=10000000, repeat 2
- v3/concat/two_strings_long|n=1000000, repeat 0
- v3/concat/two_strings_long|n=1000000, repeat 1
- v3/concat/two_strings_long|n=1000000, repeat 2
- v3/concat/four_frames_light_nulls|n=3000000, repeat 0
- v3/concat/four_frames_light_nulls|n=3000000, repeat 1
- v3/concat/four_frames_light_nulls|n=3000000, repeat 2
- concat/realistic_nulls|n=10000000, repeat 0
- concat/realistic_nulls|n=10000000, repeat 1
- concat/realistic_nulls|n=10000000, repeat 2
- v4/concat/two_category_heavy|n=10000000, repeat 0
- v4/concat/two_category_heavy|n=10000000, repeat 1
- v4/concat/two_category_heavy|n=10000000, repeat 2
Non-deadline worker failures (also unestimated): 0.
