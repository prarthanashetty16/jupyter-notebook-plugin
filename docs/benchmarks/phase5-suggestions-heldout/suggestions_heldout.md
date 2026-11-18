# Suggestion benchmark: HELD-OUT configurations

Source: `C:\dev\NEXUS\benchmarks\results\suggestions\heldout\results.jsonl`. Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part B4. RAM = peak above baseline of the cell in fresh spawned processes (median of 3), inputs loaded from disk. Saving fractions are relative to the unmodified cell's measured peak. A modified run whose peak the OS counter cannot resolve (censored) gives only a LOWER BOUND on the saving and is excluded from S3.

## Verdicts

* cells run: 36; risky (original peak >= 200 MiB): 15; candidates measured: 12; shown by the filters: 12.
* **S1 no `preserving` bug:** PASS (0 cases).
* **S2 do no harm (shown, >10% more RAM):** PASS (0 of 12 shown; any measured increase among ALL candidates, shown or not: 0).
* **S3 predicted vs measured saving (pp of the original peak):** FAIL - n=9, signed bias 2.2%, median |error| 5.5%, p90 |error| 39.0% (targets <= 15% and <= 35%).
* **S4 shown suggestions with a measured saving >= 20% and >= 64 MiB:** FAIL (9 of 12 = 75.0%; target >= 80%).

## Per rule (shown suggestions)

| rule family | candidates | shown | measured saving, shown (median) | predicted, shown (median) | harm | bugs |
|---|---|---|---|---|---|---|
| avoid_copy | 3 | 3 | 71.3% | n/a | 0 | 0 |
| downcast_numeric | 1 | 1 (fewer than 3 shown: no rule-level claim) | 18.6% | 56.2% | 0 | 0 |
| key_dtype | 1 | 1 (fewer than 3 shown: no rule-level claim) | 14.6% | 58.8% | 0 | 0 |
| read_csv_options | 6 | 6 | 92.9% | 90.0% | 0 | 0 |
| select_columns | 1 | 1 (fewer than 3 shown: no rule-level claim) | 12.6% | 45.8% | 0 | 0 |

## Every measured candidate

| cell | rule | label | shown (why not) | predicted saving | measured saving | measured vs original MiB | outputs identical | dtype changes | max abs err |
|---|---|---|---|---|---|---|---|---|---|
| avoid_copy/C_G/num8@4000000 | avoid_copy | preserving | yes | n/a | 83.2% | 367 -> 62 | True | 0 | 0.0 |
| avoid_copy/C_M/num8@2000000 | avoid_copy | preserving | yes | n/a | 71.1% | 215 -> 62 | True | 0 | 0.0 |
| avoid_copy/C_M/num8@4000000 | avoid_copy | preserving | yes | n/a | 71.3% | 428 -> 123 | True | 0 | 0.0 |
| downcast_numeric/M1/num8@7900000 | select_columns | preserving | yes | 56.2% | 18.6% | 242 -> 197 | True | 0 | 0.0 |
| key_dtype/M1/k_wide@7100000 | select_columns | preserving | yes | 58.8% | 14.6% | 218 -> 186 | True | 0 | 0.0 |
| read_csv_options/R_B/csv16@1500000 | read_csv_options | changes_results | yes | 91.0% | 96.6% | 679 -> 23 | True | 0 | 0.0 |
| read_csv_options/R_B/csv16@3000000 | read_csv_options | changes_results | yes | 91.0% | 96.6% | 1354 -> 46 | True | 0 | 0.0 |
| read_csv_options/R_K/csv16@1500000 | read_csv_options | changes_results | yes | 90.0% | 92.2% | 679 -> 53 | False | 0 | None |
| read_csv_options/R_K/csv16@3000000 | read_csv_options | changes_results | yes | 90.0% | 93.4% | 1354 -> 90 | False | 0 | None |
| read_csv_options/R_K/csv8@1500000 | read_csv_options | changes_results | yes | 90.0% | 90.2% | 351 -> 35 | False | 0 | None |
| read_csv_options/R_K/csv8@3000000 | read_csv_options | changes_results | yes | 90.0% | 92.4% | 699 -> 53 | False | 0 | None |
| select_columns/M2/w6@11200000 | select_columns | changes_results | yes | 45.8% | 12.6% | 343 -> 300 | True | 0 | 0.0 |

## `preserving` suggestions whose output differed (0)

none

## Candidates that INCREASED measured RAM (0)

none

## delete_unreferenced (not measured for peak: it frees headroom)

* delete_unreferenced/X/junk@2000000: no suggestion
