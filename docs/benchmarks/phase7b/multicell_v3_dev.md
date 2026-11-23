# Multi-statement cells v1 (all 66, DEV): v3 working tree vs stored v2 predictions

**Battery run (user-accepted):** these results were made on battery power. Timing figures (analysis time, Tier 1 fallbacks on the time budget, wall times) are battery-throttled and are NOT usable for calibration or for any timing claim; RAM figures do not depend on the power state.

Power: `{"power": "battery (user-accepted)", "battery_psutil": "sbattery(percent=75, secsleft=4294967295, power_plugged=False)", "battery_wmi": {"PowerOnline": false, "Charging": false, "Discharging": true, "RemainingCapacity": 30656, "Voltage": 11895}}`

Prediction only (fresh processes), stored actuals; power battery (user-accepted). Harness events: none.

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3 (cellpeak, v3 models) | 66 | 33 | 1.00 | 1.1% | 14.6% | 89.4% | 3.0% | 2 | 1 | 7.6% | 3.30 |
| v2 (stored) | 66 | 33 | 1.15 | 14.6% | 102.1% | 63.6% | 0.0% | 0 | 0 | 36.4% | 2.92 |

## dev

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3 | 44 | 22 | 1.00 | 1.6% | 14.6% | 88.6% | 0.0% | 0 | 0 | 11.4% | 3.10 |
| v2 | 44 | 22 | 1.13 | 12.6% | 77.4% | 63.6% | 0.0% | 0 | 0 | 36.4% | 2.87 |

## former held-out (dev)

| model | n | configs | bias | err_med | err_p90 | coverage | above_high | above_high_n | configs_above_high | below_low | width |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v3 | 22 | 11 | 1.00 | 0.8% | 12.0% | 90.9% | 9.1% | 2 | 1 | 0.0% | 3.70 |
| v2 | 22 | 11 | 1.17 | 17.2% | 102.3% | 63.6% | 0.0% | 0 | 0 | 36.4% | 3.04 |

## Per template (v3 vs v2 bias; v3 uncovered operations)

| template | n | v3_bias | v2_bias | v3_err_med | v3_above_high | v3_coverage | v3_uncovered_ops |
|---|---|---|---|---|---|---|---|
| astype_groupby | 6 | 1.12 | 1.12 | 12.2% | 0.0% | 100.0% | 0 |
| chain | 6 | 0.97 | 1.11 | 3.3% | 0.0% | 100.0% | 0 |
| concat_loads | 6 | 1.00 | 1.17 | 0.6% | 0.0% | 100.0% | 6 |
| copy_fillna | 6 | 1.05 | 1.10 | 9.5% | 33.3% | 0.0% | 2 |
| deletes | 6 | 0.99 | 0.99 | 0.8% | 0.0% | 100.0% | 0 |
| expressions | 6 | 0.99 | 1.00 | 0.8% | 0.0% | 100.0% | 0 |
| load_dtype_nrows | 6 | 1.01 | 3.12 | 1.3% | 0.0% | 83.3% | 0 |
| load_then_merge | 6 | 0.99 | 1.23 | 1.0% | 0.0% | 100.0% | 0 |
| loads2 | 6 | 1.00 | 1.17 | 0.7% | 0.0% | 100.0% | 0 |
| loads3_tsv | 6 | 1.00 | 1.77 | 0.7% | 0.0% | 100.0% | 0 |
| rebinding | 6 | 0.99 | 1.10 | 0.5% | 0.0% | 100.0% | 0 |

Cells above the v3 high: [('copy_fillna/mixed@1000000', 88, 65), ('copy_fillna/mixed@2000000', 176, 130)]
