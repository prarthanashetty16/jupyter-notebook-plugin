# Risk engine on DEVELOPMENT data (Phase 5)

Source: `benchmarks\results\tier1-v3` (stored Tier 1 predictions and stored actuals; no new measurement). Ranges: range policy B applied to the stored rows (194 of 323 Tier 1 rows had a different `high` as stored). **Dev data, not validation.** Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part A6. Alert = WARN or HIGH_RISK; UNKNOWN and OK are misses on positive points.

## Verdicts

* **R1 recall >= 98%:** PASS. Pooled over all (point, limit) pairs 100.0% (1119/1119, Wilson 95% lower 99.7%). Limits with >= 20 positives: [64, 128, 256, 512, 1024, 2048]; below target: none.
* **R2 false alarms (pooled <= 30%, no operation > 50%):** FAIL. Pooled over the claim limits 25.0%; operations above the per-op bar: [('merge', 0.5882352941176471), ('pandas.read_csv', 0.7796610169491526)].
* **R3 HIGH_RISK precision >= 75%:** PASS. Pooled over limits [64, 128, 256, 512, 1024, 2048]: 98.6%.
* **R4 UNKNOWN:** 0 of 2260 (point, limit) pairs are UNKNOWN, 922 are OK.

## Per limit

| limit_mb | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 | 323 | 314 | 314 | 0 | 5 | 4 | 100% | 99% | 56% | 98% | 314 | 100% | 0 | 4 |
| 128 | 323 | 297 | 297 | 0 | 12 | 14 | 100% | 99% | 46% | 96% | 296 | 100% | 0 | 14 |
| 256 | 323 | 228 | 228 | 0 | 52 | 43 | 100% | 98% | 55% | 81% | 223 | 98% | 0 | 43 |
| 512 | 323 | 172 | 172 | 0 | 37 | 114 | 100% | 98% | 25% | 82% | 175 | 97% | 0 | 114 |
| 1024 | 323 | 78 | 78 | 0 | 41 | 204 | 100% | 95% | 17% | 66% | 78 | 97% | 0 | 204 |
| 2048 | 323 | 30 | 30 | 0 | 58 | 235 | 100% | 89% | 20% | 34% | 34 | 88% | 0 | 235 |
| 4096 | 322 | 0 | 0 | 0 | 14 | 308 | – | – | 4% | 0% | 0 | – | 0 | 308 |


## Per operation (claim limits only)

| op | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 378 | 235 | 235 | 0 | 22 | 121 | 100% | 98% | 15% | 91% | 231 | 100% | 0 | 121 |
| drop_duplicates | 282 | 178 | 178 | 0 | 21 | 83 | 100% | 98% | 20% | 89% | 177 | 99% | 0 | 83 |
| groupby | 306 | 190 | 190 | 0 | 22 | 94 | 100% | 98% | 19% | 90% | 189 | 99% | 0 | 94 |
| merge | 222 | 137 | 137 | 0 | 50 | 35 | 100% | 97% | 59% | 73% | 136 | 100% | 0 | 35 |
| numpy.sort | 96 | 16 | 16 | 0 | 0 | 80 | 100% | 81% | 0% | 100% | 16 | 100% | 0 | 80 |
| operator.matmul | 174 | 60 | 60 | 0 | 26 | 88 | 100% | 94% | 23% | 70% | 59 | 100% | 0 | 88 |
| pandas.concat | 162 | 103 | 103 | 0 | 9 | 50 | 100% | 96% | 15% | 92% | 99 | 100% | 0 | 50 |
| pandas.read_csv | 144 | 85 | 85 | 0 | 46 | 13 | 100% | 96% | 78% | 65% | 98 | 87% | 0 | 13 |
| sort_values | 174 | 115 | 115 | 0 | 9 | 50 | 100% | 97% | 15% | 93% | 115 | 100% | 0 | 50 |


## Per size (claim limits only)

| size | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2000 | 36 | 2 | 2 | 0 | 8 | 26 | 100% | 34% | 24% | 20% | 2 | 100% | 0 | 26 |
| 3000 | 36 | 7 | 7 | 0 | 7 | 22 | 100% | 65% | 24% | 50% | 7 | 100% | 0 | 22 |
| 4000 | 36 | 13 | 13 | 0 | 4 | 19 | 100% | 77% | 17% | 76% | 12 | 100% | 0 | 19 |
| 6000 | 36 | 19 | 19 | 0 | 4 | 13 | 100% | 83% | 24% | 83% | 19 | 100% | 0 | 13 |
| 8000 | 30 | 19 | 19 | 0 | 3 | 8 | 100% | 83% | 27% | 86% | 19 | 100% | 0 | 8 |
| 1000000 | 654 | 267 | 267 | 0 | 95 | 292 | 100% | 99% | 25% | 74% | 267 | 97% | 0 | 292 |
| 3000000 | 636 | 432 | 432 | 0 | 57 | 147 | 100% | 99% | 28% | 88% | 432 | 99% | 0 | 147 |
| 5000000 | 48 | 4 | 4 | 0 | 0 | 44 | 100% | 51% | 0% | 100% | 4 | 100% | 0 | 44 |
| 10000000 | 426 | 356 | 356 | 0 | 27 | 43 | 100% | 99% | 39% | 93% | 358 | 99% | 0 | 43 |


## Missed crashes (positive, not alerted): 0

none
