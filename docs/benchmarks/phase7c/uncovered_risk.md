# Multi-statement dev cells: v3 risk class where an operation is uncovered (Phase 7c, DEV, information only)

Prediction only on the v1 cells (66, all dev; stored actuals). A **missed overrun** = class OK while the actual exceeds the simulated headroom.

| cell | actual MiB | v3 high MiB | uncovered | 64 | 128 | 256 | 512 | 1024 | 2048 | 4096 | 8192 | ever OK | missed overrun | UNKNOWN names it |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| concat_loads/num@1000000 | 296 | 1578 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\nu...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| concat_loads/num@2000000 | 592 | 3155 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\nu...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| concat_loads/mixed@1000000 | 282 | 1334 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\mi...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| concat_loads/mixed@2000000 | 536 | 2667 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\mi...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| copy_fillna/mixed@1000000 (above high) | 88 | 65 | `df.fillna(0)` | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| copy_fillna/mixed@2000000 (above high) | 176 | 130 | `df.fillna(0)` | HIGH_RISK | HIGH_RISK | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| concat_loads/wide@1000000 | 486 | 2931 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\wi...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | WARN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |
| concat_loads/wide@2000000 | 970 | 5862 | `pd.concat([pd.read_csv('benchmarks\\.cache\\multicell\\wi...` | HIGH_RISK | HIGH_RISK | HIGH_RISK | HIGH_RISK | WARN | UNKNOWN | UNKNOWN | UNKNOWN | False | False | True |

Cells with an uncovered operation: 8; ever OK: 0; missed overruns: 0.
