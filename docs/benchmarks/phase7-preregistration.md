# Phase 7 pre-registration: freeze v3 (`models-frozen-v3`)

Written in Phase 7a and committed **before any v3 model change and before any v3 held-out data is created** (the v2
multi-statement split file is written after this commit). Dated 2026-11-22. Changes after this commit are dated amendments
at the end; an amendment can never relax a criterion after any held-out value has been seen.

**Mode B.** val-v5 has not been run; it stays sealed and unread and is the held-out Linux run for v3. test-v2 stays sealed
and is not part of the v3 check.

**What I knew when writing this:**

* every dev result in `docs/PROGRESS.md`;
* the Phase 7a diagnosis (`docs/benchmarks/phase7a/README.md`, probes in `docs/benchmarks/phase7a/probes/`, all on dev
  inputs or synthetic data);
* the risk-v2 dev selection (rule committed first, `f8e4eba`; result `probes/p1f_risk_v2.out`).

I have seen no val-v5, test-v2 or v2-held-out value, and no notebook of the future Phase 8b set.

---

## 0. Discipline (applies to every item)

* **Dev data** (read freely): split v6 `dev` (123 cases, incl. the former exposed-v1, val-v3, val-v4); the Phase 6c
  multi-statement group v1, all 33 configurations (its 22 former held-out cells are dev since 2026-11-22); the Phase 5 held-out
  suggestion configurations; the Phase 8a Amazon notebooks; the Phase 7a probes; the **dev** part of the multi-statement group
  v2 (28 configurations).
* **Held-out for v3** (opt-in, logged, run once on `models-frozen-v3`): val-v5 (Linux VM); the v2 multi-statement held-out
  part (15 configurations, 30 cells); the Phase 8b fresh real-notebook set (its own pre-registration first). Designs:
  `docs/benchmarks/phase7a/heldout_design.md`.
* **Derivation rule.** Every model change is DERIVED from pandas / numpy behaviour (source reading, written down before the
  probe). It is then confirmed by an isolated probe (`nexus.measure`: fresh spawned process, inputs from disk, incremental OS
  peak, median of 3) at >= 200 MiB of input or peak, on mains power, with the raw output committed. **Adoption bar: every probe
  variant of the change within +-15% of the derived peak** (or the item's own band stated below). A derivation a probe
  contradicts is NOT adopted. The old behaviour stays and the contradiction is reported. A second derivation may be tried, but
  it is reported as a second attempt.
* **Not allowed:** fitting any constant to the Amazon notebooks; fitting to the 22 Phase 6c cells beyond what a derivation
  predicts; changing a frozen threshold to make a criterion pass. The frozen thresholds are the risk WARN_MARGIN 0.85 and
  CONFIDENCE_FLOOR 0.30, range policy B for the DISPLAYED range, the Tier 1 sanity guard, the time buckets and the calibration
  artifact `calibration-v1.json`, which is not refitted in v3.
* **Order.** (1) This commit. (2) `split_v2.json` written and committed. (3) Phase 7b: derivations, probes and model
  changes on dev, each with its regression check on all dev data (the Phase 6c regression rule: RAM above_high 0% per
  operation and tier must not rise; listed regressions need a written keep / revert decision). (4) Freeze `models-frozen-v3`
  (tag + manifest; the guard checks against it). (5) The held-out runs, each once. (6) The report, as it comes out.

## 1. Scope of freeze v3 (nothing else)

Each item has a success criterion on dev (needed before the freeze) and a failure rule. Held-out criteria are in section 4.

### (1) read_csv model structure and its arguments

*Diagnosis (1a).* pandas 3.1.1 reads local, uncompressed files >= 5 MiB with a THREADED PARALLEL reader
(`readers._read_csv_parallel`, eligible per `_can_parallelize_csv`, `min(cpu_count, 6, available CPUs) > 1` workers). Its
peak is **file bytes (mmapped, resident) + 2 x parsed values**, which matches 13 numeric variants at 1.003-1.018 (rows,
columns, int / float, float32, `sep`, `header`, NA, `na_values`). A `dtype` dict takes a branch that closes the mmap first:
**F + V + worker buffers** (1.008). `usecols`, `nrows`, `parse_dates` (and 1 CPU, files < 5 MiB) use the SERIAL reader:
values + one tokenizer chunk. The derived chunk term over-estimates (0.71-0.92), and `parse_dates` measured 1.36. Text columns
on the parallel path are under-predicted by 5-26% (not derived). The frozen Tier 1 formula measures 0.78-0.80 on numeric files,
which is the 1.22-1.25x over-prediction of the Phase 6c held-out cells.

*Change.* Path selection from the call's arguments, file size and the CPUs available to the process. Parallel numeric
term `F + 2V`. Series-wrap term `F + V + W`. Serial path as the RANGE `[V + S, V + S + T]`, since the point term was
contradicted. Tier 1 statistics for `usecols` / `dtype` / `nrows` / `na_values` / one-character `sep` / `header` 0 or None
(`stats.csv_profile` with the call's own arguments; `nrows` caps the row estimate). `parse_dates` and text columns keep the
frozen terms unless a Phase 7b re-derivation passes its probe.

*Dev success:* every 1a numeric variant and every new Phase 7b probe variant within +-15%. RAM above_high on the dev
read_csv points 0% (unchanged).
*Failure rule:* a path or argument whose probe falls outside the band keeps the frozen (Tier 0 for the unsupported arguments)
behaviour, and this is reported.

### (2) The 10-17% over-prediction on multi-statement templates without loads

*Diagnosis (1b).* Per statement (tracemalloc and the OS peaks of the cell's prefixes agree within 1%), the bias comes
from three terms. The operations' own peaks are right:
(a) the `_output` merge term counts the left columns as copied, although pandas 3 does not copy them when every left row
matches once in left order (30.5 measured vs 91.8 MiB retained, chain / rebinding);
(b) the cell model never releases a rebound name (`m = ...` twice: the first result is freed);
(c) `copy` Tier 0 expected counts string objects for `str` columns, while only the pointer arrays are copied (213.6
measured = its `low`, vs 366 expected).
astype_groupby is exact at 10M rows (1.00); its 1.11 at 1-2M rows is a small-size effect and is not addressed.

*Change.*
(a) Derive pandas 3's left-elision condition from `_MergeOperation` and use it in the output term. Tier 1's join
statistics decide it; Tier 0 keeps the copy (conservative).
(b) Release on rebinding only for a name bound in this cell to a result made in this cell, with no other binding of it in
the cell: no alias assignment, subscript / attribute store, container literal, or call argument other than a modelled
operation's receiver. Anything else keeps the conservative rule.
(c) Copy of `str` columns = pointer arrays.

*Dev success:*
* each change's probe within +-15%. Variants: unmatched keys, `sort=True`, `how='left'` and duplicate right keys for (a);
  the alias forms for (b), all of which must keep the conservative rule;
* on the v1 multi-statement group (all 33 configurations, dev), the median bias of the four non-load templates within
  0.95-1.05 at the sizes where the cell peak is >= 200 MiB, with above_high still 0 cells.

*Failure rule:* a change whose probe fails is not adopted. A rebinding rule that lets any dev cell go above_high is reverted.

### (3) Deterministic Tier 1 and the statistics budget

*Diagnosis (1e).* Wherever statistics ran, repeated fresh-process estimates were identical (the seeds are constants). The
non-determinism is the 0.2 s Tier 1 gate:
* merge at 10M rows falls back in every condition (a deterministic coverage loss);
* on 2 contended cores, merge at 3M flips between Tier 1 and Tier 0 across repeats;
* a fixed-sample prototype flipped once on 2 cores.

*Change.* A fixed sample size per call (`min(rows, 200_000)`) and a seed mixed with a hash of the cell source. The gate is
decided by a deterministic prediction of the statistics cost (per-row cost from the machine profile x sample rows), not by
live timing. The hard deadline stays as the safety net. Every fallback is shown ("statistics skipped: <reason>") and
recorded. **The 250 ms analysis ceiling is not raised (CLAUDE.md).**

*Dev success:* 10 fresh-process repeats on >= 30 dev inputs (all Tier 1 operations, sizes up to 10M rows, 16 cores and 2
contended cores, mains). The tier decision must be identical across the repeats of every input unless the hard deadline
fired (each such case listed), the estimate must be identical whenever the tier is, and 100% of fallbacks must be visible.
*Failure rule:* if the deterministic gate disagrees with the deadline on more than 10% of the 2-core inputs, the gate is
not adopted (the frozen adaptive gate stays), and determinism is reported as NOT achieved.

### (4) Risk v2 for the R2 failure, and a named-operation UNKNOWN message

*Selection (1f, rule committed first in `f8e4eba`).* The rule selects **C3**: WARN uses the model's own Tier 1 `high`
for `read_csv` and `merge` when their Tier 1 statistics ran; all other points, HIGH_RISK, and the DISPLAYED range keep policy
B. On dev it gives R1 100% (1119/1119, 0 misses added), R2 pooled 17.7%, merge 11.8%, read_csv 44.1% (C0: 25.0%, 58.8%,
78.0%), R3 98.6%. With the v3 read_csv model, read_csv's own Tier 1 `high` changes. **The C3 rule is frozen as a POLICY
("read_csv and merge WARN on their own Tier 1 high"), not as numbers**, and it is re-checked on dev with the v3 models before
the freeze. If R1 drops below 98% there, or a miss is added against C0, C3 is dropped (C0 kept) and this is reported.
*Message:* an UNKNOWN cell names its uncovered operation(s) ("no estimate for `df.fillna(0)`: ..."). Wording only, no class
change; tested.
*Held-out criterion:* section 4 (R1-R3 on val-v5). **R2 already FAILED once (Phase 5 / 6b: merge 58.8%, read_csv 78.0%). If
R2 fails again on val-v5, it is reported as FAILED (a repeat failure), and risk v2 is not re-tuned on those data.**

### (5) Coverage expansion

*Diagnosis (1d).* The adoption bar was fixed in the probe before it ran (every variant within +-15%).
* **Passed:** `Series.apply` with a numpy ufunc (1.000) and `Series.explode` (1.136).
* **Contradicted:** `set_index` (0.003; pandas 3 does not copy the key), `value_counts` (1.40, 2.14), `DataFrame.explode`
  (1.33), `apply` with a Python function element-wise (2.19) and row-wise (1.25), and `fillna` on pandas-3 `str` columns (1.33,
  1.30).

*Diagnosis (1c).* For an operation on a frame made earlier in the cell, propagated shapes / dtypes are enough for concat (1.00),
copy and sort, and they bound fillna. Merge, groupby, drop_duplicates and astype(category) need column statistics. With
shapes only, merge's expected is 3.68x / 0.53x and groupby's 2.65x; with statistics, 1.22x / 1.06x and 1.15x.

*In scope.*
* `Series.explode` (Tier 1: list-length sample) and `Series.apply(<numpy ufunc>)`.
* A virtual frame per statement result: shapes / dtypes / bytes from the producing model's output term.
* Column statistics carried exactly through value-preserving operations (copy, sort_values, fillna of other columns,
  concat as a union of its inputs' statistics), and from the read_csv sample for frames read in the cell. They are bounded as
  `stats` bounds them, so ranges widen.
* `set_index`: one second, zero-copy derivation may be tried in 7b. It is adopted only if it passes the same bar, and it is
  reported as a second attempt.

*Out of scope (documented as uncovered):* value_counts, DataFrame.explode, apply with Python functions, fillna on text columns,
parse_dates, and text columns on the parallel read_csv path (frozen term).

*Held-out criterion (Phase 8b, fresh notebooks):* the share of analysable code cells with >= 1 detected operation whose EVERY
detected operation has an estimate, computed statically for v3 and for `models-frozen-v2` on the same cells. **v3 must exceed
v2 by >= 10 percentage points.** The RAM / time criteria of section 2 also apply to its valid points (< 30 valid points:
INCONCLUSIVE).

## 2. Held-out criteria (every held-out set; reported with n and the 95% bounds)

| criterion | sets | bar |
|---|---|---|
| RAM above_high per POINT | val-v5 (Tier 1, policy B as displayed), multicell v2 held-out (cell model), Phase 8b valid points | <= 3%, with the one-sided 95% Clopper-Pearson upper bound quoted (0 of 30 -> 9.5%; 0 of 100 -> 3.0%) |
| RAM above_high per CONFIGURATION | val-v5 configurations, multicell v2 held-out configurations | <= 3% of configurations with any point above high, with the 95% upper bound quoted (0 of 15 -> 18.1%) |
| time within-one (bucket) | val-v5 time points; multicell v2 held-out cells with a measured time >= 100 ms; Phase 8b valid time points | >= 95%, with the Wilson 95% lower bound quoted |
| R1 recall | val-v5 (risk replay with simulated limits, `benchmarks.risk_eval` definitions) | >= 98% pooled and at every limit with >= 20 positives |
| R2 false alarms | val-v5 | pooled <= 30% AND **per operation <= 50%** (operations with >= 20 non-positive pairs). **A repeat failure is reported as FAILED** |
| R3 HIGH_RISK precision | val-v5 | >= 75% (no claim with < 20 HIGH_RISK points) |
| coverage | Phase 8b | v3 - v2 >= 10 points (section 1 (5)) |

A metric with fewer than **30** valid points (configurations: fewer than 10) is **INCONCLUSIVE**, not passed.

## 3. Dev / held-out discipline

* Develop and decide on dev only. Each held-out set runs ONCE on `models-frozen-v3`. Before it: the freeze guard (0 problems),
  the held-out environment check (`benchmarks/heldout_env.py`), mains power. Every access is logged: val-v5 in the PROGRESS
  "Test-split access log", multicell v2 in `docs/benchmarks/phase7-heldout-access-log.md`, Phase 8b in its own log.
* Protected values are never printed, plotted or pasted before the one evaluate call. After it, the set is dev, and a future
  held-out check needs a new group.
* No model, threshold or rule changes between the freeze and the last held-out read. A change after a read invalidates the
  remaining held-out runs (new freeze, new groups).

## 4. What counts as failure

* **Failure of the whole v3** (reported as "`models-frozen-v3` FAILED its held-out check"):
  * RAM above_high > 3% per point or per configuration on val-v5 or on the multicell v2 held-out part;
  * time within-one < 95% on val-v5;
  * R1 < 98% on val-v5;
  * the freeze guard reporting a difference before a run (the run aborts).

  A failed v3 is not repaired on those data. v2 is not re-declared validated either (it never passed a full held-out check).
* **Failure of an item** (the item's claim is withdrawn; v3 is not failed as a whole): R2 or R3 on val-v5 (R2 as a repeat
  failure); the coverage criterion; the determinism dev criterion; a criterion of Phase 8b.
* INCONCLUSIVE results are reported as such and never counted as passes.
* Every outcome is reported as it comes out, with the 95% bounds.

---

## Amendment 1 (2026-11-23, Phase 7c): an enlarged multi-statement held-out group (v3) and the uncovered-operation rule

Written before `models-frozen-v3` is tagged and before `benchmarks/multicell/split_v3.json` exists. No held-out value of
any group has been seen. This amendment adds a held-out set and a rule. It relaxes nothing.

* **Group v3** (`benchmarks/multicell/cases_v3.py`, split `split_v3.json`, salt `phase7c-multicell-v3:`):
  * 16 templates x 6 shapes = 96 configurations. Per template, the TWO configurations with the largest salted hash are held
    out: **32 configurations, 64 cells** (sizes 1.25M / 2.5M). The other 64 configurations are dev.
  * New seeds (21-23) and two new shapes (`narrow`, `textwide`).
  * The templates cover fillna on text columns, frames created earlier in the cell, set_index, apply(np.<ufunc>),
    del / rebinding (with an alias), chains, read_csv arguments and an uncovered value_counts.
  * It is designed from the scope and the rules above, not from measured values. Leak protection as v2: digest-checked
    split, held-out console id / status / time only, results in `benchmarks/results/multicell_v3/heldout/`, every access
    logged in `docs/benchmarks/phase7-heldout-access-log.md`, freeze guard and the held-out environment check (mains only,
    no `--allow-battery`). Run ONCE on `models-frozen-v3`.
  * Group v2 (15 configurations, 30 cells, pre-registered in 7a) stays sealed and is run once as well; each group is
    reported separately and pooled.
* **Criteria on group v3 (and v2):**
  * RAM above_high <= 3% of cells AND <= 3% of configurations. Each is quoted with its one-sided 95% Clopper-Pearson upper
    bound and reported as "consistent with a true rate <= x%". For 0 events: 64 cells -> 4.6%, 32 configurations -> 8.9%;
    v2 and v3 pooled, 94 cells -> 3.1%, 47 configurations -> 6.2%.
  * **Uncovered-operation rule:** in every cell with an operation that has no estimate, at every simulated headroom
    (64 MiB .. 8 GiB) where the measured peak exceeds the headroom, the v3 risk class must NOT be OK. UNKNOWN, WARN and
    HIGH_RISK are acceptable. One violation FAILS the rule.
* **Failure:** the above_high bars are part of section 4's "failure of the whole v3" (as for v2). The uncovered-operation
  rule is an item criterion (item 4); its failure withdraws the claim that uncovered operations are handled
  conservatively.

---

## Amendment 2 (2026-11-24): val-v5 reassigned to v4; no Linux held-out check of v3

Append-only; the text above is unchanged. **val-v5 was never run or read for v3.** The Phase 8 pre-registration
(`docs/benchmarks/phase8-preregistration.md`, commit `f2e19cc`) reassigns it, sealed, as a **v4 Linux held-out group**
(digest re-checked there). **v3's Linux held-out check is therefore NOT performed.** The v3 verdict stays the Windows
held-out result recorded in `docs/PROGRESS.md` ("v3 Windows held-out verdict: FAILED"). The val-v5 rows of section 2
(RAM, time, R1-R3 on val-v5) are never evaluated for v3 and are reported as NOT PERFORMED, never as passed.
