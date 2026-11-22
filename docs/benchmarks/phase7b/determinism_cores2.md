# Tier 1 determinism, v3 working tree (Phase 7b; DEV; 2 CPUs + 2 busy loops)

Condition: cores2_contended. 30 stored dev points (<= 10,000,000 rows; 5 per operation with Tier 1 statistics), 10 repeats each, each a fresh prediction process (the benchmark's worker), mains power (power seen: ['mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Raw rows: `determinism.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 5 | 1 | 0.00% | 13.36% | 0.00% | 0.00% | 0.00% | 84.10% | 0.00% |
| drop_duplicates | 5 | 1 | 0.00% | 25.38% | 0.00% | 0.00% | 0.00% | 39.71% | 0.00% |
| groupby | 5 | 1 | 0.00% | 34.27% | 0.00% | 0.00% | 0.00% | 0.51% | 0.00% |
| merge | 4 | 1 | 0.00% | 57.67% | 0.00% | 0.00% | 0.00% | 39.82% | 0.00% |
| pandas.concat | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 0 fallback differs between repeats: 4 of 29
- astype/str_to_category_highcard|n=10000000: Tier 1 in 9 of 10 runs
- v4/drop_duplicates/numeric_wide_nulls12|n=10000000: Tier 1 in 5 of 10 runs
- groupby/two_keys_mean_realistic|n=10000000: Tier 1 in 9 of 10 runs
- merge/left_1to1|n=10000000: Tier 1 in 1 of 10 runs
