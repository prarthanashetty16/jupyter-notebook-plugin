# Risk engine on DEVELOPMENT data (Phase 5)

Source: `benchmarks\results\tier1-v3` (stored Tier 1 predictions under range policy B and stored actuals; no new measurement). **Dev data, not validation.** Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part A6. Alert = WARN or HIGH_RISK; UNKNOWN and OK are misses on positive points.

## Verdicts

* **R1 recall >= 98%:** PASS. Pooled over all (point, limit) pairs 100.0% (1119/1119, Wilson 95% lower 99.7%). Limits with >= 20 positives: [64, 128, 256, 512, 1024, 2048]; below target: none.
* **R2 false alarms (pooled <= 30%, no operation > 50%):** PASS. Pooled over the claim limits 14.0%; operations above the per-op bar: none.
* **R3 HIGH_RISK precision >= 75%:** PASS. Pooled over limits [64, 128, 256, 512, 1024, 2048]: 98.6%.
* **R4 UNKNOWN:** 0 of 2260 (point, limit) pairs are UNKNOWN, 1024 are OK.

## Per limit

| limit_mb | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 64 | 323 | 314 | 314 | 0 | 5 | 4 | 100% | 99% | 56% | 98% | 314 | 100% | 0 | 4 |
| 128 | 323 | 297 | 297 | 0 | 12 | 14 | 100% | 99% | 46% | 96% | 296 | 100% | 0 | 14 |
| 256 | 323 | 228 | 228 | 0 | 39 | 56 | 100% | 98% | 41% | 85% | 223 | 98% | 0 | 56 |
| 512 | 323 | 172 | 172 | 0 | 18 | 133 | 100% | 98% | 12% | 91% | 175 | 97% | 0 | 133 |
| 1024 | 323 | 78 | 78 | 0 | 25 | 220 | 100% | 95% | 10% | 76% | 78 | 97% | 0 | 220 |
| 2048 | 323 | 30 | 30 | 0 | 16 | 277 | 100% | 89% | 5% | 65% | 34 | 88% | 0 | 277 |
| 4096 | 322 | 0 | 0 | 0 | 2 | 320 | – | – | 1% | 0% | 0 | – | 0 | 320 |


## Per operation (claim limits only)

| op | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| astype | 378 | 235 | 235 | 0 | 11 | 132 | 100% | 98% | 8% | 96% | 231 | 100% | 0 | 132 |
| drop_duplicates | 282 | 178 | 178 | 0 | 16 | 88 | 100% | 98% | 15% | 92% | 177 | 99% | 0 | 88 |
| groupby | 306 | 190 | 190 | 0 | 8 | 108 | 100% | 98% | 7% | 96% | 189 | 99% | 0 | 108 |
| merge | 222 | 137 | 137 | 0 | 10 | 75 | 100% | 97% | 12% | 93% | 136 | 100% | 0 | 75 |
| numpy.sort | 96 | 16 | 16 | 0 | 0 | 80 | 100% | 81% | 0% | 100% | 16 | 100% | 0 | 80 |
| operator.matmul | 174 | 60 | 60 | 0 | 26 | 88 | 100% | 94% | 23% | 70% | 59 | 100% | 0 | 88 |
| pandas.concat | 162 | 103 | 103 | 0 | 9 | 50 | 100% | 96% | 15% | 92% | 99 | 100% | 0 | 50 |
| pandas.read_csv | 144 | 85 | 85 | 0 | 26 | 33 | 100% | 96% | 44% | 77% | 98 | 87% | 0 | 33 |
| sort_values | 174 | 115 | 115 | 0 | 9 | 50 | 100% | 97% | 15% | 93% | 115 | 100% | 0 | 50 |


## Per size (claim limits only)

| size | n | positives | tp | fn | fp | tn | recall | recall_wilson_low | false_alarm | precision | high_n | high_precision | unknown | ok |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2000 | 36 | 2 | 2 | 0 | 8 | 26 | 100% | 34% | 24% | 20% | 2 | 100% | 0 | 26 |
| 3000 | 36 | 7 | 7 | 0 | 7 | 22 | 100% | 65% | 24% | 50% | 7 | 100% | 0 | 22 |
| 4000 | 36 | 13 | 13 | 0 | 4 | 19 | 100% | 77% | 17% | 76% | 12 | 100% | 0 | 19 |
| 6000 | 36 | 19 | 19 | 0 | 4 | 13 | 100% | 83% | 24% | 83% | 19 | 100% | 0 | 13 |
| 8000 | 30 | 19 | 19 | 0 | 3 | 8 | 100% | 83% | 27% | 86% | 19 | 100% | 0 | 8 |
| 1000000 | 654 | 267 | 267 | 0 | 48 | 339 | 100% | 99% | 12% | 85% | 267 | 97% | 0 | 339 |
| 3000000 | 636 | 432 | 432 | 0 | 32 | 172 | 100% | 99% | 16% | 93% | 432 | 99% | 0 | 172 |
| 5000000 | 48 | 4 | 4 | 0 | 0 | 44 | 100% | 51% | 0% | 100% | 4 | 100% | 0 | 44 |
| 10000000 | 426 | 356 | 356 | 0 | 9 | 61 | 100% | 99% | 13% | 98% | 358 | 99% | 0 | 61 |


## Missed crashes (positive, not alerted): 0

none
