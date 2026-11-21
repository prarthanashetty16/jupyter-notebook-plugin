# Phase 5 pre-registration: risk engine and rule-based suggestions

Written and committed **before any Phase 5 number exists** (no risk classification, no suggestion re-estimate and no
suggestion measurement has been computed). Dated 2026-11-18. Changes after this commit are dated amendments appended at the
end; the text above an amendment is never edited.

**Frozen inputs.** Tier 0, Tier 1, the guard, range policy B, the Tier 2 estimator and the controller are frozen. Phase 5
reads their `Estimate`s and changes none of them. Tier 2 stays experimental and off by default. `test-v2` and `val-v5` stay
sealed and unrun. Nothing in this phase is tuned on held-out data.

**What I already know (disclosure).** Before writing this I know the Phase 4b.3 result of the *existing* simulated-OOM
table on dev: the rule "inspected bytes + `high` > limit" had recall 100% at every limit and precision 75% at 2048 MB on 322
valid points. The thresholds below were chosen from principle (stated per item), not fitted to those tables; where a number
could have been influenced by that memory it says so.

---

## Part A. Risk engine (`nexus/risk.py`)

### A1. Inputs

* `Estimate` per operation of the cell (range policy B: Tier 1 `low` / `expected`, Tier 0 `high`; or Tier 2 when enabled),
  with `confidence`, `tier` and `note` (a non-empty `note` means the guard rejected Tier 1 and Tier 0 was kept).
* `ResourceSnapshot`: `available_ram` (psutil *available*), the container / cgroup limit and usage, so
  `A = effective_available = min(available_ram, cgroup.limit - cgroup.usage)`; free swap `S`; the kernel's RSS `R`.
* `A` is **headroom**: memory the cell may still allocate. The baseline `R` (data already resident, e.g. the inputs) is
  already excluded from `A` on a live machine, so the live rule compares the estimate with `A` directly. The simulated-limit
  evaluation (Part C) reproduces this by `A = limit - baseline`, with `baseline = inspected_bytes` (the same baseline the
  existing OOM table uses).
* Peak figures are the per-cell range of the existing models: one operation per benchmark point.

### A2. Cell range

For a cell with several estimated operations: `low` = max of the lows, `expected` = max of the expected values, `high` = **sum**
of the highs (operations run in sequence and intermediates may stay alive; the sum is an upper bound, the max is not). This
combination rule is not exercised by the dev evaluation (benchmark points are single operations); it is unit-tested only and is
not part of any success criterion.

### A3. Classes (checked in this order)

1. **UNKNOWN**, never OK, when any of:
   * no operation of the cell has an estimate (no model, `NoEstimateError`, analysis timeout, internal error: reported as
     "no estimate" and the reason, never as OK);
   * some operations have an estimate and others do not **and** the class would otherwise be OK (part of the cell is not
     covered);
   * `A` could not be measured;
   * any figure is non-finite or violates `0 <= low <= expected <= high`;
   * the class would otherwise be OK **and** `confidence < 0.30` (the floor already used by Tier 2 and by the no-op model's
     confidence of 0).
2. **HIGH_RISK** when `expected > A` (the central estimate does not fit; `low > A` is the strict special case). Zero or
   negative `A` with `expected > 0` is HIGH_RISK.
3. **WARN** when `high > margin * A` with `margin = 0.85`.
4. **OK** otherwise.

Why these numbers. (i) HIGH_RISK uses `expected`, not `low`: the model's own median says the cell will not fit; `low` is an
optimistic bound and using it would label a probable crash as merely "risky". (ii) `margin = 0.85`: `available` is a snapshot
that other processes, the allocator (fragmentation, page rounding) and the OS reserve eat into during the run; 15% is a
conventional reserve, chosen from that and not from dev tables. (iii) WARN uses `high` (a 95%-style upper bound) because a
missed crash costs lost work, while a false alarm costs one read of a message. (iv) The 0.30 confidence floor is the floor
that Tier 2 already uses.

**Swap.** Swap is never added to headroom: a cell that fits only by swapping will not crash but may be orders of magnitude
slower. If `expected > A` but `expected <= A + S`, the class is still HIGH_RISK and the reason says "may swap instead of
failing". The trade-off is stated: counting swap would hide the case where a notebook becomes unusable.

**Cgroup / container limit.** Included through `effective_available`; the reason names the limit when it is the binding one.

**Time risk (separate, never changes the memory class).** Only the existing order-of-magnitude bucket
(`nexus.timebuckets`) of `time_expected` is used. Flag `long_run` when that bucket is `1-10 min` or `over 10 min`. No seconds
are shown. A time flag never changes UNKNOWN / OK / WARN / HIGH_RISK.

**False alarm vs missed crash.** The asymmetry is deliberate: the margin and the `high`-based WARN favour recall. The cost is
reported (Part C) per operation and per size rather than hidden.

### A4. Fail-safe behaviour

`nexus.risk` never raises into the user's cell and never alters or blocks it; any exception inside classification yields no
output (the session fail-safe) and the report states "no estimate". Quiet by default: nothing is printed for OK cells unless
verbose.

### A5. Report content

`RiskReport`: class, one-line reason naming the dominant cost drivers (taken from `Estimate.drivers` of the operation that sets
`expected` / `high`), the resource snapshot (`A`, swap, cgroup limit, total), the estimate's tier / confidence / fallback
`note`, the time bucket and the `long_run` flag.

### A6. Risk success criteria (dev; evaluated on stored predictions and stored actuals, no new measurements)

Setup. Stored dev Tier 1 predictions (the latest policy-B run) and stored actuals. Simulated limits `64, 128, 256, 512, 1024,
2048, 4096` MB. Positive (a real overrun) = the existing definition of `benchmarks.evaluate.oom_table`: the measured footprint
(`input_bytes` + measured peak RAM) exceeds the limit, or the child was killed at a cap >= the limit. Only points with a valid
actual (not censored / excluded) count. **Alert = WARN or HIGH_RISK. UNKNOWN is not an alert**: a positive point classified
UNKNOWN or OK is a miss.

* **R1. Recall.** Recall of alerts over positives >= 98% (a) for each limit with at least 20 positives, and (b) pooled over
  all (point, limit) pairs. Limits with fewer than 20 positives are reported with their counts and marked "too few positives:
  no claim". Wilson 95% lower bounds are reported next to every recall; the criterion is on the point estimate.
* **R2. False alarms.** False-alarm rate = alerts among non-positives. Pooled over limits with at least 20 positives it must be
  <= 30%; no operation with at least 20 non-positive (point, limit) pairs may exceed 50%. The 30% / 50% figures are set from
  the stated asymmetry (a warning should not be noise most of the time), not from the dev tables.
* **R3. HIGH_RISK precision.** The share of HIGH_RISK points that are real overruns is >= 75%, pooled over limits with at least
  20 HIGH_RISK points. (75% equals the precision I had seen for the older `high` rule at 2048 MB; it is the bar a *more
  selective* class should clear, and was not tuned further.)
* **R4. UNKNOWN is honest.** Report the share of valid points classified UNKNOWN and the share of OK; the criterion is only
  that no cell without an estimate is OK (unit tests, not data).
* Each missed criterion is reported as failed. Every missed crash (positive classified OK / UNKNOWN) is listed individually.
  Dev positives are few at large limits (and at small limits almost every point is positive); the report says where.
  All of this is **dev, not validation**.

---

## Part B. Suggestions (`nexus/suggestions/`)

### B1. Rules (fixed list; one file each; supported operations only)

| rule | applies to | semantics label |
|---|---|---|
| downcast numeric dtypes (`astype` / `pd.to_numeric(downcast=...)`) | a frame / series with int64 / float64 columns | `changes_precision` (float64 -> float32) or `changes_dtype` (int64 -> smaller int); `preserving` only when the stored values are *proved* representable (min / max of the live data within the target range and integer-valued) |
| low-cardinality `object` -> `category` | `object` / `str` columns with distinct share below 50% (live statistics) | `changes_dtype` |
| `read_csv`: `usecols` / `dtype` / `chunksize` | a `read_csv` call | `usecols`: `preserving` only if a conservative liveness check proves the dropped columns unused in the rest of the cell, else refused; `dtype`: `changes_dtype`; `chunksize`: `changes_results` (returns an iterator) |
| drop unused columns before `merge` / `groupby` | `merge`, `groupby` | `preserving` only if the liveness check proves the dropped columns unused in the REST of the cell (and the result's column set is unchanged); otherwise refused |
| avoid `copy` | `.copy()` | only where provably safe (the source is never read again in the rest of the cell AND is not otherwise referenced in the cell); else refused. The kernel's other cells are not visible, so the snippet says so and the label is `changes_results` (aliasing) unless the copy is of a temporary |
| delete unreferenced large variables | large live variables not referenced in the cell | suggest only; the warning says other cells may use them; semantics `changes_results`; never claims cell peak savings, only freed headroom |
| sort / merge key dtype optimisation | `sort_values`, `merge` keys | `changes_dtype` (e.g. `object` key -> `category`, int64 -> int32) |

A rule that cannot prove safety **refuses** (returns nothing). Rules never edit the user's cell; `%nexus apply n` prints the
modified source only.

**Liveness check** (conservative). For a candidate "columns C unused" the check walks the REST of the cell and refuses on:
any whole-frame use of the variable (passed to a call, returned as the cell's value, `.columns`, `.shape` on the frame is
allowed, `.dtypes` / `.info()` / `.describe()` / `print(df)` are not), any subscript or attribute use of a name in C, a
non-literal subscript (variable, f-string, slice, `.loc[:, expr]`), `**kwargs`, `eval` / `exec` / `locals` / `globals` /
`getattr` / `.filter` / `.query` / `.eval`, star-imports, loops or comprehensions that read the frame generically, an alias
assigned from the variable, `del`, `inplace=True` on it, and any parse error. When in doubt: refuse. Unit tests include
>= 25 adversarial snippets that must all be refused (100% required) and >= 15 positive snippets that must be accepted.

### B2. Re-estimation

Every suggestion is passed back through the **frozen** estimators on a *virtual modification*: the modified cell's analysis
features and a virtual state (descriptors with the new dtypes / column sets / sizes), never executing code and never mutating
the namespace. The result is the new range and the predicted saving
`saving = expected_before - expected_after` (RAM) and `saving_frac = saving / expected_before`.

* **Meaningful saving threshold (stated up front):** `saving_frac >= 0.20` **and** `saving >= 64 MiB`. Below it the suggestion
  is discarded (not shown).
* Discard if the re-estimate fell back to Tier 0 with `confidence < 0.30`, or has no estimate.
* **Never show** a suggestion whose re-estimated `high` is above the original `high`.
* Rank by predicted saving (descending), ties by least semantic change (`preserving` < `changes_precision` < `changes_dtype` <
  `changes_results`).
* Time: suggestions make no time claim (the time models are order-of-magnitude only).

Reasons for 20% / 64 MiB: the instrument's repeat spread is 9% median / 30% p90 (`timebuckets`), so savings below ~10%
cannot be told from noise; 20% leaves margin; 64 MiB is above the instrument's RAM floor for the benchmark.

### B3. Evaluation design (fixed before measuring)

* **Cells.** Synthetic data and templates over supported operations, risky by construction: the cell's measured peak without
  the suggestion is at least 200 MiB on the development machine and at most the 2.5 GiB cap. At least 40 configurations
  in total and at least 30 dev cells. A *configuration* = (rule family, cell template, data shape / dtype / cardinality
  setting); each has one or two sizes.
* **Split by configuration.** Held-out assignment is deterministic and made before any measurement: per rule family, sort that
  family's configurations by `sha256("phase5-suggestions-v1:" + configuration key)` and hold out the last
  `ceil(0.40 * n_family)` (at least one). At least 14 held-out configurations in total and every rule family represented in
  both parts. The split is stored in `benchmarks/suggestions/split.json` (version 1) with a digest check; it is never edited
  (a new version would be created instead).
* **Leak protection (same as the validation splits).** The held-out part is opt-in (`--heldout --reason "..."`), results go to
  `<results>/heldout/`, the runner / log / console print only point id, status and elapsed time, no tooling other than the
  final evaluate command reads it, a test scans the other modules for the protected API names, and every use is logged in the
  access log of `docs/PROGRESS.md`. **The held-out part is not run in Phase 5**; the command is given.
* **Measurement (dev).** Real peak RAM with and without each suggestion in fresh child processes (the validated
  `nexus.measure` instrument; inputs loaded from disk; median of 3 repeats), and the real semantic effect: outputs compared
  with `assert_frame_equal` / `np.array_equal` including dtypes for `preserving`; for the other labels the maximum absolute
  (and relative) error and the list of dtype changes.
* Statistics on delete-variable suggestions (they change headroom, not the cell's peak, and returned memory is not reliably
  visible in RSS) are excluded from the measured-saving statistics and reported by semantic / reference checks only.

### B4. Suggestion success criteria (dev)

* **S1. No `preserving` bug.** Zero suggestions labelled `preserving` whose measured output differs from the original. Any
  such case is a bug: it is listed, and the rule is fixed or made to refuse (and the fix is recorded as a dated amendment;
  the measured result with the bug stays in the report).
* **S2. Do no harm.** Zero shown suggestions whose measured peak RAM is more than 10% above the unmodified cell's (10% = the
  repeat-spread median rounded up; any increase at all is also listed).
* **S3. Predicted vs measured saving.** In saving fraction of the unmodified measured peak: median absolute error <= 15
  percentage points and p90 <= 35 points; bias (signed median) is reported without a criterion.
* **S4. Meaningful.** At least 80% of shown suggestions have a measured saving `>= 20%` and `>= 64 MiB`.
* **S5. Refusal.** The adversarial liveness battery: 100% refused; the positive battery: >= 90% accepted.
* **S6. Labels honest.** For `changes_precision` / `changes_dtype` / `changes_results` the report states the measured max error
  and dtype changes; a label weaker than the measured effect (e.g. `changes_dtype` with a numeric value change beyond dtype
  rounding) is a bug.
* Rule-level claims need at least 3 dev cells; fewer is reported "not evaluated". A missed criterion is reported as failed.
* Held-out evaluation (later, once) uses exactly S1-S4 on the held-out configurations; after it is read, it becomes dev.

---

## Part C. Where the numbers come from

Part A (R1-R4) uses only stored dev predictions and actuals (`benchmarks/results/...`, dev split, no protected data) and the
exact `oom_table` positive definition. Part B (S1-S4) measures only the dev part of the suggestion benchmark. No benchmark is
run to tune anything.

## UI contract (not scored)

`%nexus status`, `%nexus explain`, `%nexus suggestions`, `%nexus apply <n>`; text / HTML only; `apply` prints the modified
source and never executes or edits; time only as a bucket; quiet for OK cells unless verbose.

---

## Amendment 1 (2026-11-18, written after the Phase 5 dev run 1 was read; no held-out data exist)

Everything above is unchanged. What changed and why, in the order it happened:

1. **Rule refinements chosen for safety, made while implementing (before any measurement).** `downcast_numeric` is never
   `preserving` (the B4 check compares dtypes, so a narrower dtype is `changes_dtype`; floats `changes_precision`); `read_csv`
   `usecols` and the merge column-selection are `changes_results` when the result is bound to a name (later cells may use the
   dropped columns) and `preserving` only when consumed inside the expression; `read_csv dtype=` is not proposed (the frozen
   model has no dtype feature, so a saving cannot be re-estimated); `copy` and `delete` suggestions have no frozen operation
   model, so their saving is the exact descriptor size (`estimate_source = "descriptor"`), thresholds still apply.
   Re-estimation of both "before" and "after" uses the frozen model at Tier 0 on a virtual state plus the materialised
   temporary (`temp_bytes`); Tier 1 statistics are not re-run on virtual data.
2. **Benchmark design changed three times BEFORE any suggestion was measured** (split files v1 -> v2 -> v3, all kept in
   `benchmarks/suggestions/`). A baseline-only pass on DEV cells showed that most cells were not "risky" (peak < 200 MiB: pandas
   groupby / merge / sort on these frames are cheap), so frame sizes were set by target bytes, groupby / sort templates were
   replaced by more memory-hungry ones, and the split was re-created by the same sha256 rule. Only dev baseline peaks (no suggestion
   outcome, no held-out value) informed this. Final: v3, 40 configurations, 21 dev / 19 held-out, digest in `split_v3.json`.
3. **Run 1 on dev (reported in full in `docs/benchmarks/phase5-suggestions-dev/suggestions_dev_run1.md`): S2, S3 and S4 FAILED.**
   One shown suggestion (`downcast_numeric` on a merge) was modelled at +27% saving and measured -47% (RAM increased). The rule
   was changed to refuse `merge` (this amendment). Run 2 re-ran the same dev configurations; its report is the one in
   `suggestions_dev.md`. **Run 2 is a re-measurement of the same dev data after a fix made from run 1, so its pass is not
   evidence of generalisation; only the held-out part can be.**
4. **Not met as pre-registered:** at least 30 dev cells that are risky. Of 40 dev cells only 19 were risky (peak >= 200 MiB), and
   only 15 candidates were shown and measured. Rule-level claims exist for 3 rule families only (>= 3 shown).

---

## Amendment 2 (2026-11-18, written after the held-out suggestion result was read; the held-out configurations are now dev)

Everything above is unchanged, including every threshold (20% / 64 MiB, S1-S5). The held-out check was run once and read: S1 and S2
PASSED, S3 FAILED (n=9, median 5.5, p90 39.0 against <= 15 / <= 35), S4 FAILED (9 of 12 = 75% against >= 80%). Nothing was re-run.

1. **`select_columns` disabled by default.** Post-hoc, after the failure, on the evidence dev 46% predicted vs 13% measured and held-out 46-59%
   predicted vs 13-19% measured (three suggestions). It can be enabled explicitly (`NEXUS_ENABLE_RULES`, `%nexus rule enable`, `suggest(enable=)`).
   A post-hoc subset without it would meet S3 and S4 numerically but does not count as a pass.
2. **Disclosure about B2 as implemented.** For suggestions whose saving is a descriptor size (`avoid_copy`, `delete_unreferenced`) the engine
   applied only the 64 MiB condition; the 20% condition was not evaluated, because no estimate of the unmodified cell's peak exists for them
   (Amendment 1 said "thresholds still apply", true for bytes only). This is how the held-out and dev runs actually behaved. Thresholds are not changed.
3. **Interface.** Every shown suggestion states what its label changes in plain words, and suggestions without a model re-estimate show
   "no estimate of saving" instead of a saving.

---

## Erratum (2026-11-21, Phase 6b; the text above is unchanged)

The Phase 5 risk evaluation (Part A6, `docs/benchmarks/phase5-risk-dev/`) was reported as computed on "stored Tier 1
predictions under range policy B" but replayed `benchmarks/results/tier1-v3`, whose stored Tier 1 rows hold each model's own
range (policy A) for 194 of 323 points. **The R1-R4 numbers reported in Phase 5 were therefore on the wrong ranges.** Re-run
on policy-B ranges with no new measurement and no threshold change (`docs/benchmarks/phase5-risk-policyB/`): R1 recall 100%
MET; R2 pooled false alarms 25.0% (<= 30% met) but **R2 FAILED** because merge (58.8%) and read_csv (78.0%) exceed the 50%
per-operation bar; R3 HIGH_RISK precision 98.6% MET; R4 0 UNKNOWN MET. Candidate changes are proposals only (a risk-engine or
range change after the freeze `models-frozen-v1` needs a decision, a new freeze and a held-out check).
