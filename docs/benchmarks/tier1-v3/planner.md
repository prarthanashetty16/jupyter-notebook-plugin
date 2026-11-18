# Model-based planner on the existing development points (cap 2.50 GiB)

Points with a stored actual and a prediction: 360. Measured fine (status ok): 322; killed by the cap: 1; the old static rule skipped others before measuring (they have no prediction here and are unchanged).

* **Killed by the cap and now skipped before running:** 1 of 1.
* **Measured fine but the planner would now skip (planned footprint above the cap; the price of using an upper bound):** 3 of 322 (1%); of these the measured total RSS was within 2.07 GiB at most.

## Killed by the cap

| point_id | source | baseline_MiB | high_MiB | planned_GiB | measured_total_GiB | would_skip |
|---|---|---|---|---|---|---|
| v3/drop_duplicates/null_heavy_full|n=10000000 | tier1 | 840 | 2116 | 2.89 | – | True |

## Measured fine, would now be skipped

| point_id | source | baseline_MiB | high_MiB | planned_GiB | measured_total_GiB |
|---|---|---|---|---|---|
| drop_duplicates/mixed_dup0|n=10000000 | tier0 | 939 | 2116 | 2.98 | 2.07 |
| drop_duplicates/mixed_dup50|n=10000000 | tier1 | 939 | 1841 | 2.72 | 2.01 |
| read_csv/wide_numeric|n=3000000 | tier1 | 497 | 2275 | 2.71 | 1.58 |

