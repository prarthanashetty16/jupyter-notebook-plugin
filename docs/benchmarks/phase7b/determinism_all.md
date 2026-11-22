# Tier 1 determinism, v3 working tree (Phase 7b; DEV; all 16 CPUs)

Condition: all. 30 stored dev points (<= 10,000,000 rows; 5 per operation with Tier 1 statistics), 10 repeats each, each a fresh prediction process (the benchmark's worker), mains power (power seen: ['mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Raw rows: `determinism.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| groupby | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| merge | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| pandas.concat | 5 | 3 | 12.93% | 17.44% | 0.00% | 0.00% | 11.96% | 91.56% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 0 fallback differs between repeats: 3 of 28
- concat/realistic_nulls|n=10000000: Tier 1 in 7 of 10 runs
- v3/concat/four_frames_light_nulls|n=3000000: Tier 1 in 9 of 10 runs
- v3/concat/two_strings_long|n=1000000: Tier 1 in 9 of 10 runs
