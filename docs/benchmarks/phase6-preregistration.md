# Phase 6 pre-registration: calibration (time models, time ranges, RAM gaps), then freeze

Written and committed **before any Phase 6 number exists** (no new prediction, probe, residual, coverage or fit has been
computed in Phase 6). Dated 2026-11-18. Changes after this commit are dated amendments appended at the end; the text above an
amendment is never edited.

**What is protected.** `test-v2` and `val-v5` stay sealed and unrun. Real-notebook results (Phase 8a) do not exist and stay
held out: no real notebook and no real-notebook data is used for anything in this phase. Everything is developed and evaluated
on the **dev** split only (split v6 `dev`: the Phase 3-3b cases and the former exposed-v1, val-v3 and val-v4; the Phase 5
suggestion held-out configurations are dev as well). The result of the phase is a **frozen** model stack (tag
`models-frozen-v1`) that val-v5 (another machine, Linux) and the real-data test evaluate later.

**What I already know (disclosure).** The dev figures already reported in `docs/PROGRESS.md`: Tier 1 time median error 53%,
coverage 96%, expected-bucket within-one 100% (Phase 4c / 4d replay); the 4b.3 "Phase 6 inputs" time biases (concat 0.19x on
val-v4 and 1.25x on val-v3, groupby 3.34x / 2.24x, astype 1.41x / 2.20x, read_csv 0.31x / 0.36x, float32 matmul 2.84x); Tier 2
time: median error 25%, coverage 80%, median width ~16x of expected; the merge-peak probe of Phase 5b (20-88 MiB, N:1 joins). The
thresholds below are set from principle (stated per item); where one could have been influenced by those figures it says so.

---

## 1. Data, units and definitions

* **Data.** `benchmarks/results/tier2-dev-b` read through `benchmarks.evaluate.load_joined` (dev rows only; the loader refuses
  protected cases): 360 measured points in 123 configurations, Tier 0 / Tier 1 / Tier 2 predictions of the frozen 4b.3 / 4c models
  with their stored `features`. Time actuals: `time_value` of points classified `valid` (repeat spread <= 30%, actual >= 100 ms;
  the existing `Floors`). No benchmark point is re-measured for calibration; predictions are recomputed from the stored features
  with the candidate models. If a candidate needs a feature that is not stored, the predictions are re-run on the dev points
  (prediction only, no measurement) and that is reported.
* **Configuration** = a benchmark case (all of its sizes). Every fitted parameter is fitted with **leave-one-configuration-out
  (LOCO)**: the prediction for a point of configuration c uses parameters fitted on all dev configurations except c. The parameters
  shipped in the calibration artifact are fitted once on all dev configurations; the evaluation reports the LOCO figures only.
* **Errors (time).** `rel_err = |expected - actual| / actual` (median and p90 per operation, as in every earlier report);
  `log_err = |ln(expected / actual)|`; `bias = median(expected / actual)`; **bucket**: `nexus.timebuckets` (same bucket, within one
  bucket); **coverage** = share of valid points with `low <= actual <= high`; **width** = mean `(high - low) / expected` (the
  current Tier 0 / 1 band 0.25x .. 4x has width 3.75).
* **Size buckets** for coverage: input bytes < 64 MiB, 64-256 MiB, >= 256 MiB (matmul and numpy.sort by input bytes as well).

## 2. Targets on dev (LOCO)

**(a) Time estimates (Tier 0 and Tier 1, each).**
* expected-bucket within-one >= **95%** overall (it stays at or above 95%);
* the same-bucket rate overall does **not drop** below the frozen models' rate on the same points;
* median and p90 `rel_err`, and bias, are reported per operation, before and after (no numeric target per operation: they enter
  (d)).

**(b) Time ranges (Tier 0 / 1 and Tier 2).**
* per-operation coverage in **[88%, 95%]** under LOCO, for every operation that is calibrated per operation (section 4);
* mean width reported against the current one (3.75 for Tier 0 / 1; Tier 2's own, ~16x);
* coverage also reported per configuration and per size bucket (no target, descriptive; a configuration whose points are all outside
  its range is listed).

**(c) RAM.** Policy B (Tier 1 low / expected, Tier 0 high) is unchanged. A RAM expected-value change is allowed only with a
derivation from pandas source or from isolated probes whose peaks are **>= 200 MiB**; it must not raise RAM above_high on dev (per
point or per configuration, compared with the frozen models on the same points), and it is evaluated with LOCO (a derived change
with no fitted parameter is LOCO trivially; any fitted constant in it is LOCO-fitted). Coverage and width are reported and must be
unchanged or better.

**(d) No silent regressions.** For every operation and every metric above (time: median rel_err, p90 rel_err, same-bucket,
within-one, coverage; RAM: above_high, coverage, width), a change for the worse is listed as a **regression with a decision**
(keep / revert, and why). "Worse" means: median rel_err up by more than 2 percentage points, p90 rel_err up by more than 5 pp,
same-bucket or within-one down by at least one point, coverage outside [88%, 95%] where it was inside, RAM above_high up by any
point, RAM width up. The thresholds are noise allowances fixed from the instrument's repeat spread (median 9%, p90 30%), not from
any Phase 6 figure.

## 3. Time models (expected value)

Order of work, per operation:
1. **Machine profile v3** (`nexus-calibrate-machine`): throughput as a function of **working-set size** (cache-resident to
   RAM-resident), first-touch allocation cost, page-fault cost, memory bandwidth, hash (factorize) throughput by table size, sort
   throughput by n, BLAS float64 / float32 throughput and thread scaling. Measured **only on dedicated primitives**, never on
   benchmark points or benchmark data. The profile carries provenance (machine, library versions, date, format version). It is a
   required input for time estimation; without it a documented conservative generic profile is used and every time estimate is
   flagged **"uncalibrated machine"** (section 6).
2. **Derive** each correction from the algorithm and the primitives (n log n where the algorithm sorts and that is justified from
   pandas source, working-set-dependent throughput, per-call overheads). For each known bias a **probe** checks the mechanism
   before any model is changed: concat under-prediction (why a copy-like operation was ~5x under on category-heavy frames),
   groupby and astype over-prediction, read_csv under-prediction by dtype mix and engine, float32 matmul over-prediction (BLAS
   threads and dtype). A mechanism that a probe does not confirm is not put into a model.
3. Only the part that cannot be derived is **fitted**: one multiplicative residual per operation, `m_op = exp(median ln(actual /
   expected_derived))` over the training configurations (LOCO). No constant is fitted to an individual benchmark point; no
   per-configuration or per-size constant.

**Candidates and selection (criterion fixed now).**
* `F` = frozen models (current profile), `D` = derived models with the v3 profile, `D+m` = D with the per-operation residual.
* Selection between D and D+m (and F as the fall-back): the candidate with the lowest **pooled LOCO median log_err** over all
  valid Tier 1 time points, **subject to** target (a) (within-one >= 95%, same-bucket not below F). If neither D nor D+m satisfies (a),
  F is kept and the phase reports the time-model calibration as FAILED.
* The fitted residual of each operation is reported: its size is the measure of what the derivation did not explain.

## 4. Time ranges (calibration method)

**Tier 0 / 1: LOCO split-conformal on normalised log residuals, per operation.** For a point of configuration c of operation o:
residuals `r = ln(actual / expected)` of the selected candidate's (LOCO) expected value, from all valid points of operation o in
configurations other than c; `low = expected * exp(q_lo)`, `high = expected * exp(q_hi)` with `q_lo` / `q_hi` the empirical
quantiles at levels `alpha/2` and `1 - alpha/2` after the finite-sample correction (`ceil((n + 1)(1 - alpha/2)) / n`), **nominal
coverage 90% (alpha = 0.10)**. `low <= expected <= high` is enforced (the range is widened to contain the point estimate, never
narrowed). The shipped quantiles are those of all dev configurations.

**Too few configurations.** An operation with **fewer than 8 dev configurations** is not calibrated per operation (with fewer than
8, a held-out configuration's quantiles rest on at most 6 others, too few to describe between-configuration variation): it gets the
**generic band**, the pooled conformal quantiles over all operations at **nominal 95%**, and its estimates carry the flag
**"generic time range"**. On dev this applies to matmul (6 configurations); this count was known before writing the rule.

**Tier 2: LOCO conformal on Tier 2's own normalised scores.** Tier 2's range already scales with its extrapolation distance, so the
score is normalised by it: `s = ln(actual / expected) / ln(high / expected)` above and `ln(expected / actual) / ln(expected / low)`
below; `q` = the finite-sample-corrected 90% quantile of the scores of the other configurations of the operation (accepted Tier 2
time fits only); new range `[expected * (low / expected)^q, expected * (high / expected)^q]`. Operations with fewer than 8
configurations with accepted Tier 2 time fits use the pooled score quantile at 95% and the flag. The controller's groupby x1.5 rule
(R2 of Phase 4d) is left as it is; it applies on top.

**Uncalibrated machine / unvalidated pandas.** No calibrated machine profile: the generic profile, and the time range widened by a
factor **3** on each side (low / 3, high x 3) with the flag "uncalibrated machine" (principle: throughputs differ by up to ~3x between
a laptop and a server CPU generation; not fitted). Installed pandas outside the validated range of the calibration artifact
(validated = the pandas minor version(s) the artifact was fitted on): warn once per session, widen every time range by **2** on each
side, flag "unvalidated pandas version". The RAM range is not changed by these flags (RAM models are derived from pandas internals
whose guards are the pandas-matrix tests of section 6), but the flag is shown.

## 5. Optional learned residual model

A scikit-learn model (optional extra `learn`; gradient-boosted trees on operation, log rows, log bytes, text share, key-distinct
share and the derived expected time, predicting the remaining log residual) is included **only if** under LOCO on dev it lowers
the pooled median log_err of the selected candidate by **at least 10% (relative)**, does not raise the pooled p90 log_err, and does
not lower within-one or same-bucket rates. Otherwise it is left out and the negative result is documented. It is never required at
run time.

## 6. Calibration artifact, freeze

* Versioned JSON shipped with the package (`src/nexus/calibration/`), with provenance: data hash of the results used, git
  commit, machine-profile id, python / pandas / numpy versions, date, the list of fitted parameters and what each was fitted on.
  The loader validates the format version; absent or outdated artifact: the uncalibrated behaviour of section 4 with a flag (never
  an exception); pandas outside the validated range: warn once, widen, flag. `nexus-calibrate <results dir>` regenerates the
  artifact; a user-local artifact is opt-in and stays local (never shipped, never overwrites the packaged one).
* The pandas-internals terms the models depend on (hash-table page residency, factorize cost growth, copy / copy-on-write
  semantics, concat of categoricals) are guarded by probe tests that run in a CI matrix over pandas versions. Results are claimed
  only for versions that were actually run.
* **Freeze.** After the dev evaluation the commit is tagged `models-frozen-v1` and `docs/benchmarks/frozen-manifest.md` records
  hashes of the model files, the calibration artifact and the machine-profile format, the versions and the policy and thresholds
  in force. Held-out runs (val-v5, Phase 8a) record the commit and abort when the working tree differs from the tag. Any model
  change after the freeze invalidates the held-out status of those runs.

## 7. What counts as failure

* (a) not met for the selected candidate: the time-model calibration FAILS on dev, F is kept, and the failure is reported.
* (b) not met for an operation calibrated per operation: that operation's range calibration FAILS on dev and is reported (the
  calibrated range is still shipped only if its coverage is closer to [88%, 95%] than the current band's; otherwise the current band
  stays for that operation, with a decision recorded).
* (c) violated by a RAM change: the change is reverted.
* Every regression under (d) without a recorded decision is a process failure.
* A pass on dev is not validation: all of this is fitted and evaluated on dev configurations from one machine.

## 8. Machine-transfer risk

Every time actual and every primitive throughput in this phase come from **one Windows machine** (16 logical CPUs, 16 GiB). val-v5
runs on another machine (Linux, >= 32 GB) after running `nexus-calibrate-machine` there. What transfers is the **form** of the
models and the per-operation residuals and conformal quantiles, which are ratios to throughputs measured on the target machine. If
the residuals are partly machine-specific (cache sizes, memory bandwidth, BLAS library, thread count, OS page-fault cost), val-v5
coverage will be lower than dev coverage; that risk is untested until val-v5 and is stated in every report of this phase. The
working-set-dependent profile is meant to move the machine-specific part into measured primitives; whether it does is exactly what
val-v5 checks.

---

## Amendment 1 (2026-11-18, written after the first dev comparison was read; nothing above is changed)

**What I had seen when writing this.** The candidate table on the stored predictions: D and D+m lower the Tier 1 pooled
median log error (0.58 -> 0.33 / 0.25) but neither meets target (a) at Tier 0 (same bucket 159 points for F, 158 for D,
154 for D+m), so under section 3 F would be kept; a learned residual on top of the stored F passed the section-5 margin
at Tier 1 (0.58 -> 0.27). I had not computed anything with F recomputed on a mains profile.

**Power state (the reason for this amendment).** The development laptop was on battery during part of the session. A first
prediction re-run made on battery showed 13 Tier 1 fallbacks for "time budget" and one timeout that the earlier run did not
have, and the first Phase 6 machine profile has no recorded power state. The calibration tool now records the power state
and refuses to measure on battery. The stored F predictions (`tier2-dev-b`) were made with the v2 profile of 2026-11-16
23:40, whose power state is unknown. A residual, a conformal quantile or a learned model fitted on predictions made with
one profile does not apply to estimates made with another, so a calibration fitted on the stored F could not be shipped for
this machine whatever the comparison says.

**Change.** Every prediction used for fitting or for the comparison is made with a profile measured on mains power:
* D: `benchmarks/results/phase6-dev-mains` (v3 profile of 2026-11-18 22:14, mains recorded at start and end; the battery
  run `phase6-dev` is discarded);
* F: recomputed from the stored features of `tier2-dev-b` with the frozen pre-Phase-6 code (commit `a34747a`) and a v2
  profile measured now on mains with that commit's `nexus-calibrate-machine`. The stored-F comparison is reported next to
  it, and both are in the report; the decision uses the mains F.

**Clarifications (no change of rule).** (i) The minimum of 8 configurations counts configurations with valid time points
for the metric (numpy.sort has 8 configurations but 3 with valid time points; matmul 6). (ii) The stored F rows hold each
model's own Tier 1 RAM range (policy A; policy B has been applied in the pipeline since commit `c95f674`, after that run);
the RAM comparison applies policy B to them. (iii) Target (a) applies to each tier and one candidate is selected for the
stack, as written in sections 2-3. (iv) The learned residual model (section 5) must meet its conditions at Tier 0 and at
Tier 1 (consistent with (a) applying to each tier); this reading is written after seeing its Tier 1 result on the stored F
and before any Tier 0 or mains-F result. (v) Tier 2 time ranges are used at run time only for the controller's R2
operations (read_csv, astype, merge, groupby); the others are reported but not used.
