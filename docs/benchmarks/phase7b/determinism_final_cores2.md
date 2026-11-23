# Tier 1 determinism, v3 final (Phase 7b; DEV; 2 CPUs + 2 busy loops; battery)

**Battery run (user-accepted):** these results were made on battery power. Timing figures (analysis time, Tier 1 fallbacks on the time budget, wall times) are battery-throttled and are NOT usable for calibration or for any timing claim; RAM figures do not depend on the power state.

Power at the start: `{"power": "battery (user-accepted)", "battery_psutil": "sbattery(percent=62, secsleft=4294967295, power_plugged=False)", "battery_wmi": {"PowerOnline": false, "Charging": false, "Discharging": true, "RemainingCapacity": 25560, "Voltage": 11138}}`

Condition: cores2_contended. 30 stored dev points (<= 10,000,000 rows; 5 per operation with Tier 1 statistics), 10 repeats each, each a fresh prediction process (the benchmark's worker), mains power (power seen: ['battery (user-accepted)', 'mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Raw rows: `determinism.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 4 | 15.58% | 24.11% | 0.00% | 0.00% | 3.67% | 40.05% | 89.12% |
| groupby | 5 | 2 | 0.00% | 43.28% | 0.00% | 0.00% | 0.00% | 89.35% | 0.00% |
| merge | 4 | 2 | 5.89% | 42.67% | 0.00% | 0.00% | 9.44% | 22.57% | 0.00% |
| pandas.concat | 5 | 4 | 12.93% | 17.44% | 0.00% | 0.00% | 21.80% | 91.51% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 0 fallback differs between repeats: 12 of 28
- drop_duplicates/mixed_dup0|n=1000000: Tier 1 in 3 of 10 runs
- v3/drop_duplicates/null_heavy_full|n=3000000: Tier 1 in 4 of 10 runs
- v4/drop_duplicates/null_heavy_full|n=1000000: Tier 1 in 7 of 10 runs
- v4/drop_duplicates/numeric_wide_nulls12|n=10000000: Tier 1 in 8 of 10 runs
- groupby/two_keys_mean_realistic|n=10000000: Tier 1 in 7 of 10 runs
- v4/groupby/str_card0p9_mean|n=1000000: Tier 1 in 9 of 10 runs
- v3/merge/left_overlap90_fanout1p2|n=3000000: Tier 1 in 6 of 10 runs
- v4/merge/inner_overlap55_fanout4p5|n=1000000: Tier 1 in 9 of 10 runs
- concat/mixed|n=1000000: Tier 1 in 6 of 10 runs
- concat/realistic_nulls|n=10000000: Tier 1 in 7 of 10 runs
- v3/concat/four_frames_light_nulls|n=3000000: Tier 1 in 7 of 10 runs
- v3/concat/two_strings_long|n=1000000: Tier 1 in 9 of 10 runs
