# Tier 1 determinism, v3 final (Phase 7b; DEV; all 16 CPUs; battery)

**Battery run (user-accepted):** these results were made on battery power. Timing figures (analysis time, Tier 1 fallbacks on the time budget, wall times) are battery-throttled and are NOT usable for calibration or for any timing claim; RAM figures do not depend on the power state.

Power at the start: `{"power": "battery (user-accepted)", "battery_psutil": "sbattery(percent=74, secsleft=4294967295, power_plugged=False)", "battery_wmi": {"PowerOnline": false, "Charging": false, "Discharging": true, "RemainingCapacity": 30195, "Voltage": 11550}}`

Condition: all. 30 stored dev points (<= 10,000,000 rows; 5 per operation with Tier 1 statistics), 10 repeats each, each a fresh prediction process (the benchmark's worker), mains power (power seen: ['battery (user-accepted)']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Raw rows: `determinism.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 0 | 0.00% | 21.73% | 0.00% | 0.00% | 0.00% | 5.23% | 52.52% |
| groupby | 5 | 0 | 0.00% | 0.05% | 0.00% | 0.00% | 0.00% | 2.40% | 0.00% |
| merge | 4 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| pandas.concat | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.11% | 5.30% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 0 fallback differs between repeats: 0 of 28
