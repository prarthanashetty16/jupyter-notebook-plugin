# Phase 4b.3: why val-v4 failed, and what was changed (development data)

val-v4 failed the pre-registered criterion (Tier 1 above_high 5.4% per point, limit 3%): 3 astype
`float_to_str_nulls` points (Tier 1 expected ~0) and 2 merge `inner_overlap20_fanout10` points. val-v4 is
**dev** from split version 5 (access log updated); there is no held-out group now and none was created or
run. test-v2 is sealed and unrun. Everything below is development evidence.

## 1. astype float -> str with nulls: root cause and audit

**Root cause.** In pandas 3 `astype(str)` keeps a null as a null (no `"nan"` string object). The Tier 1
sampler computed string lengths with `.str.len()`, which is NaN for the null rows; the mean was NaN; every
figure derived from it was NaN; and `models._util.build` did `max(0.0, x)`, and `max(0.0, nan)` is `0.0`:
a silent zero estimate (`ram_low = ram_expected = ram_high = 0`). Reproduced on a float column and on a
datetime column with 4% nulls (a 60k-row frame is enough); int columns cannot hold nulls and were never
affected. Three layers failed: the statistic ignored nulls, `build` converted NaN to 0, and nothing checked
the result.

**Fix** (`models/astype.py`): lengths are taken over the non-null sample only, the null share is a feature
(`null_fraction`), and the per-row cost is `8 B pointer + (1 - null_fraction) x str object` (a null costs no
object; checks out: 66.6 MiB measured at 1M rows = 69.8 B/row vs 8 + 0.96 x 64 = 69.4). A column with no
non-null value stays at Tier 0. `build` now raises on NaN / infinity instead of clamping them to zero.
After the fix the 10M-row point predicts 649 / 662 / 675 MiB against 665 measured.

**Audit of every Tier 1 path** (`tests/test_tier1_audit.py`, 40 cells): float / datetime / text with nulls, an
all-null column, a constant column, empty strings, mixed lengths, bool, category, int, for astype (str,
category, int32), groupby (one key, two keys, null keys, category keys), drop_duplicates (full, subsets) and
sort_values. Every estimate is finite, positive and ordered; the all-null float / datetime -> str cases fall
back to Tier 0 with a reason. On the stored predictions of all 360 development points after the re-run:
0 non-finite and 0 non-positive RAM or time figures (before: 3, all of them this bug).

## 2. Sanity guard (`nexus/guard.py`, applied in the pipeline)

A Tier 1 estimate is rejected, Tier 0 kept and the reason written to `Estimate.note` and to
`features["tier1"]` when: computing it failed or any figure is NaN / infinite; its expected RAM or time is not
positive; or its expected RAM is more than 2x outside Tier 0's [low, high].

**Counted on all development data before adopting the range condition** (360 points: dev, exposed-v1,
val-v3, val-v4; 211 Tier 1 estimates that used statistics; old predictions): the non-positive condition
fires on 3 (the three zero estimates). The *strict* condition "expected outside Tier 0's [low, high]" also
fires on exactly those 3 and on **0 of the other 208**, i.e. on no correct point in the data. But dev
contains few float / datetime sources with nulls, and Tier 0 does not know about nulls: a datetime column
with 4% nulls to `str` is 69.5 B/row (correct) against a Tier 0 low of 70.5 B/row, and the strict condition
rejects that correct estimate (reproduced, now a regression test). So the range check is widened to 2x
(it still catches 0 / 100x garbage). This is a deliberate departure from "adopt the strict condition because
dev shows no false trigger": absence of triggers on dev is weak evidence when a constructed counterexample
exists. The range check is evaluated for RAM only (the Tier 1 / Tier 0 time centres were not compared).
After the re-run the guard rejected nothing on dev (0 of 360).

## 3. merge: inner joins in dev

`docs/benchmarks/tier1-v3/merge_inner_table.md` lists all 20 inner-join points with a valid RAM actual
(overlap, fan-out, true vs estimated output rows, Tier 1 fold, M / n_left). Findings:

* **The output-row statistic is right on every point** (estimate / true 0.96-1.03), including both failing
  configurations (0.96-0.99). The error is in the RAM formula.
* **Under-prediction (fold < 0.9) occurs in exactly the points with non-unique right keys and a small
  output: M / n_left <= 0.14, all 6 of them** (overlap 0.20-0.35, fan-out 6-10; val-v3 `overlap25_fanout6`,
  val-v4 `overlap20_fanout10`, `overlap35_fanout7`): fold 0.79-0.89. Fold falls monotonically with M / n_left
  (0.79-0.83 at 0.03, 0.86-0.87 at 0.09, 0.88-0.89 at 0.14, ~1 from 0.5). Points with non-unique right keys and
  a large output (bigright, manymany, fanout3, overlap55) are 0.98-1.16; unique-right points at the same low
  overlap (overlap10, M / n_left 0.05) are 0.93-1.05. So the cause is not low overlap, not fan-out and not
  output size alone: it is the sort-based path when few rows match.
* **Did 4b.2 patch a symptom?** Partly. The union-table mechanism is real and now confirmed from the pandas 3.1
  source (`_factorize_keys` factorizes the right keys first and, when they are not unique, the left keys into
  the same table; then `libjoin.inner_join` group-sorts both label arrays). It removed the gross error
  (3M: fold 0.50 -> 0.86) but its coefficients were fitted to a 27-probe grid whose own scatter (0.83-1.17) is
  the same residual that now shows up as val-v4's 0.79-0.83. The 4b.2 term captured the dominant part, not
  the cause of the residual.
* **Residual mechanism: not found.** Probes (`pf1`-`pf4`): at n = 1M, n_right = 100k the peak of
  `get_join_indexers` is **65 / 49 / 59 MiB for fan-out 2 / 6 / 10** (reproducible to < 1 MiB over six runs,
  so it is not noise) while `_factorize_keys` alone is flat at ~70 MiB for all of them, `libjoin.inner_join`
  alone never exceeds the setup peak (censored), and the khash int64 replica says the union table touches the
  same 16 MiB in every configuration. Neither the table, the join step nor the output size explains a
  non-monotone 16 MiB swing at fixed n_left, n_right and M. No constant was fitted. **Known limitation,
  documented:** for non-unique right keys with M / n_left <= ~0.15 the model is up to ~20% low at Tier 1
  (expected), and the range policy (section 4) is what keeps the actual inside the range.

## 4. Range policy: fallback adopted globally

The pre-registered fallback "Tier 1 expected value with Tier 0's high as the upper end" (candidate C in
`benchmarks/range_policy.py`, named B in the request) is adopted globally (`nexus.ranges`:
`[Tier 1 low, Tier 1 expected, Tier 0 high]`; the guard runs first). Re-scored with the pre-registered
criterion on all 284 development points with a valid RAM actual and Tier 1 predictions of the fixed models
(`docs/benchmarks/tier1-v3/range_policy.md`); A = the models' own range, C = adopted:

| group | points | A: above_high / coverage / width | C: above_high / coverage / width |
|---|---|---|---|
| all dev | 284 (120 configs) | 1.1% (1.7% of configs) / 97.5% / 0.64 | **0.0% (0.0%)** / 98.6% / 1.78 |
| original dev incl. exposed-v1 | 109 | 0.0% / 99.1% / 0.67 | 0.0% / 99.1% / 1.87 |
| former val-v3 | 82 | 1.2% / 97.6% / 0.64 | 0.0% / 98.8% / 1.80 |
| former val-v4 (after the astype fix) | 93 | **2.2%** / 95.7% / 0.61 | 0.0% / 97.8% / 1.65 |

On the pre-registered rule alone the winner on dev is still **A** (admissible, narrower); C is adopted by
decision after the val-v4 failure, because it is the only candidate with zero points above `high`. val-v4 was
5.4% (5 points) with the astype bug; with the fix it is 2.2% (the 2 merge points), under the 3% limit.

Per operation (above_high per point A -> C; width A -> C; width cost): astype 0 -> 0, 0.45 -> 0.93 (x2.1);
drop_duplicates 0 -> 0, 0.66 -> 0.78 (x1.2); groupby 0 -> 0, 0.56 -> 2.18 (x3.9); **merge 8.1% -> 0.0%** (10.5%
-> 0.0% of configurations), 0.56 -> 5.13 (**x9.1**); numpy.sort, matmul, concat, sort_values unchanged (Tier 1
not used or already equal); read_csv 0 -> 0, 0.58 -> 3.04 (x5.2); all operations x2.9 (0.64 -> 1.78). The
policy is the same for every operation; nothing was changed per operation.

**Hypotheses that need a fresh split (not adopted):** (1) apply C only to merge (the only operation with
above_high on dev), keeping the models' own ranges elsewhere: width cost x9 for merge, ~x1 elsewhere; (2) a
merge-specific high derived from M / n_left on the non-unique path; (3) keep A everywhere and treat merge as a
known limitation. Each is a per-operation choice made after seeing dev data, so it cannot be validated on dev.

## 5. The OOM false negative at 2048 MB

On val-v4 under the `high` rule at 2048 MB (7 positives, recall 86%): the miss was
`v4/astype/float_to_str_nulls|n=10000000` (actual peak 665 MiB, input 1,689 MiB, total 2,354 MiB > 2,048): Tier 1
predicted `high` = 0 (the zero bug), so inspected bytes + 0 < 2,048 and no warning (Tier 0 had `high` = 839 MiB and
would have warned). **The planner would not have caught it either**: `benchmarks/planner` uses baseline (939 MiB)
+ Tier 1 `high` (0) = 939 MiB, well under any cap. After the fix Tier 1 predicts 649 / 662 / 675 MiB, NEXUS's
rule (1,689 + 675 = 2,364) warns, and the dev OOM table at 2048 MB under `high` has 0 false negatives
(`oom_misses_2048.md`: none; 30 positives, 100% recall, precision 75%); at every simulated limit 64-4096 MB the
`high` rule has recall 100% on all 322 valid development points. (The planner's baseline uses the estimated, not the
deep-measured, input size; for object-heavy frames it can under-state the resident input: a planner caveat, not
changed here.)

## 6. Large sizes

Only 8 of 283 valid RAM points exceed 1 GiB (drop_duplicates 2, read_csv 6; none for astype, groupby, merge,
sort, matmul, concat; the maximum is 1.51 GiB), and 37 of the 360 development points were skipped by the 2.5 GiB cap
(merge 20, drop_duplicates 7, astype 3, groupby 3, read_csv 2, ...). The multi-GiB regime, where an OOM warning
matters, is extrapolated. The exact commands for a >= 32 GB Linux machine are in
`docs/benchmarks/large-size-linux.md` (not run).

## 7. What was not changed

Time models (concat time under-predicted 0.19x on val-v4, groupby over-predicted 3.3x, astype 1.4x, read_csv 0.31x)
and concat with category-heavy frames (RAM 23% low at 10M rows: 595 MiB expected, 785 measured) are Phase 6 inputs.
