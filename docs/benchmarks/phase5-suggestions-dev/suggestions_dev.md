# Suggestion benchmark: DEV configurations

Source: `benchmarks\results\suggestions-r2\dev\results.jsonl`. Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part B4. RAM = peak above baseline of the cell in fresh spawned processes (median of 3), inputs loaded from disk. Saving fractions are relative to the unmodified cell's measured peak. A modified run whose peak the OS counter cannot resolve (censored) gives only a LOWER BOUND on the saving and is excluded from S3.

## Verdicts

* cells run: 40; risky (original peak >= 200 MiB): 19; candidates measured: 15; shown by the filters: 15.
* **S1 no `preserving` bug:** PASS (0 cases).
* **S2 do no harm (shown, >10% more RAM):** PASS (0 of 15 shown; any measured increase among ALL candidates, shown or not: 0).
* **S3 predicted vs measured saving (pp of the original peak):** PASS - n=11, signed bias 7.2%, median |error| 10.0%, p90 |error| 33.2% (targets <= 15% and <= 35%).
* **S4 shown suggestions with a measured saving >= 20% and >= 64 MiB:** PASS (12 of 15 = 80.0%; target >= 80%).

## Per rule (shown suggestions)

| rule family | candidates | shown | measured saving, shown (median) | predicted, shown (median) | harm | bugs |
|---|---|---|---|---|---|---|
| avoid_copy | 4 | 4 | 58.3% | n/a | 0 | 0 |
| downcast_numeric | 3 | 3 | 34.3% | 27.1% | 0 | 0 |
| key_dtype | 1 | 1 (fewer than 3 shown: no rule-level claim) | 16.8% | 46.1% | 0 | 0 |
| read_csv_options | 6 | 6 | 93.4% | 83.1% | 0 | 0 |
| select_columns | 1 | 1 (fewer than 3 shown: no rule-level claim) | 12.7% | 45.8% | 0 | 0 |

## Every measured candidate

| cell | rule | label | shown (why not) | predicted saving | measured saving | measured vs original MiB | outputs identical | dtype changes | max abs err |
|---|---|---|---|---|---|---|---|---|---|
| avoid_copy/C_D/num8@2000000 | avoid_copy | preserving | yes | n/a | 71.3% | 214 -> 62 | True | 0 | 0.0 |
| avoid_copy/C_D/num8@4000000 | avoid_copy | preserving | yes | n/a | 71.4% | 428 -> 123 | True | 0 | 0.0 |
| avoid_copy/C_S/num8@2000000 | avoid_copy | preserving | yes | n/a | 45.4% | 336 -> 184 | True | 0 | 0.0 |
| avoid_copy/C_S/num8@4000000 | avoid_copy | preserving | yes | n/a | 45.4% | 672 -> 367 | True | 0 | 0.0 |
| downcast_numeric/M1/int8@7900000 | select_columns | preserving | yes | 56.2% | 18.6% | 242 -> 197 | True | 0 | 0.0 |
| downcast_numeric/S1/int8@3900000 | downcast_numeric | changes_precision | yes | 27.1% | 34.3% | 358 -> 235 | False | 9 | 2.4908210938257014e-08 |
| downcast_numeric/S1/int8@7900000 | downcast_numeric | changes_precision | yes | 27.1% | 34.3% | 724 -> 475 | False | 9 | 2.7701777316480047e-08 |
| key_dtype/M1/k_int@11200000 | select_columns | preserving | yes | 46.1% | 16.8% | 343 -> 286 | True | 0 | 0.0 |
| read_csv_options/R_B/csv8@1500000 | read_csv_options | changes_results | yes | 83.1% | 93.1% | 351 -> 24 | True | 0 | 0.0 |
| read_csv_options/R_B/csv8@3000000 | read_csv_options | changes_results | yes | 83.1% | 93.3% | 699 -> 46 | True | 0 | 0.0 |
| read_csv_options/R_C/csv16@1500000 | read_csv_options | preserving | yes | 91.0% | 96.5% | 679 -> 23 | True | 0 | 0.0 |
| read_csv_options/R_C/csv16@3000000 | read_csv_options | preserving | yes | 91.0% | 96.6% | 1354 -> 46 | True | 0 | 0.0 |
| read_csv_options/R_C/csv8@1500000 | read_csv_options | preserving | yes | 83.1% | 93.1% | 351 -> 24 | True | 0 | 0.0 |
| read_csv_options/R_C/csv8@3000000 | read_csv_options | preserving | yes | 83.1% | 93.4% | 699 -> 46 | True | 0 | 0.0 |
| select_columns/M1/w6@11200000 | select_columns | preserving | yes | 45.8% | 12.7% | 343 -> 300 | True | 0 | 0.0 |

## `preserving` suggestions whose output differed (0)

none

## Candidates that INCREASED measured RAM (0)

none

## delete_unreferenced (not measured for peak: it frees headroom)

* delete_unreferenced/X/junk_t@2000000: no suggestion
