# Phase 8 pre-registration: freeze v4 (`models-frozen-v4`)

Committed **before any v4 model change and before any v4 held-out data exists**. Dated 2026-11-24. No v4 synthetic
held-out group is generated and no Phase 8b held-out notebook is collected until this file is committed. Changes after
the commit are dated amendments at the end. An amendment can never relax a criterion after any held-out value has been
seen. The Phase 8b protocol is `docs/benchmarks/phase8b-preregistration.md`, updated in the same commit.

**Earlier protected sets:**
* **val-v5 becomes a v4 Linux held-out group** (section 2). It has never been accessed:
  * the Test-split access log in `docs/PROGRESS.md` has only its CREATION entry (2026-11-18, split version 6), and no
    `evaluate --val` access;
  * no other access log mentions it;
  * no result file exists in any `validation/` directory except those of the consumed val-v3 and val-v4. File counts
    only, no file opened.
  * **Digest check (2026-11-24, `benchmarks.split.load_split`):**
    * `benchmarks/split.json` version 6 is unchanged since commit `867ffe2` ("Freeze val-v5 (split v6) ...");
    * group `val-v5` has 47 cases, stored sha256 `a4fc850b12d8a2df26094b83993493c87781a305410622aaa7b7a9f94b353dbd`,
      recomputed identical;
    * file sha256 `ad602b63c767312d78d27095bc188db9f2836076cdadcf989687a30751bac87c`.

  The Phase 7 pre-registration planned val-v5 as the Linux check of v3. It is reassigned to v4 BEFORE any access, so v3
  gets no Linux held-out check. v3 had already FAILED its Windows held-out check.
* **test-v2** stays sealed and is not part of this pre-registration.

**What I knew when writing this:**

* every dev result in `docs/PROGRESS.md`, including the v3 dev evaluation (Phase 7b/7c);
* the v3 Windows held-out verdict, which FAILED: multicell v2 6/28 cells above high, 3/14 configurations; v3 9/61 cells,
  5/31 configurations; the uncovered-operation rule was MET. Its per-template results were read, and both groups are dev
  data since 2026-11-24;
* the static census of `real_notebooks/` (`tools/static_ops.py`; `real_notebooks/MANIFEST.md`): 241 code cells, 75 with a
  detected pandas / NumPy operation, 18 with every operation at least partially modelled in v3. If every operation in
  section 1 (1)-(3) were covered, the name-level count would be at most 62 of 75 (computed on dev, 2026-11-24);
* the design of val-v5 (Phase 4d: 47 single-operation configurations of the v3-era operations, seeds >= 501, sizes up to
  30M rows), but none of its values.

I have seen no val-v5 or test-v2 value, no v4 held-out group (none exists) and no notebook of the Phase 8b held-out batch
(none is collected).

---

## 0. Discipline (applies to every item)

* **Dev data** (read freely, used for derivation, calibration and dev criteria):
  * split v6 `dev` (123 cases);
  * multi-statement group v1 (33 configurations);
  * the consumed Windows groups multicell v2 (all configurations) and v3 (all 96 configurations), dev since 2026-11-24;
  * the Phase 5 suggestion configurations and the Phase 8a Amazon notebooks;
  * the Phase 7a/7b probes;
  * `real_notebooks/` (5 notebooks, digests in its manifest; Phase 8b dev set);
  * every v4 probe.
* **Held-out for v4** (opt-in, logged, each run ONCE on `models-frozen-v4`): see section 2. The synthetic groups and the
  Phase 8b batch are created only after the v4 tag exists (Order, below).
* **Derivation rule (model items).** Unchanged from v3:
  * every model change is DERIVED from pandas / numpy behaviour (source reading, written down before the probe);
  * it is confirmed by an isolated probe (`nexus.measure`, fresh spawned process, inputs from disk, median of 3) at
    >= 200 MiB of input or peak, on mains power, with the raw output committed;
  * **adoption bar: every probe variant within +-15% of the derived peak**;
  * a contradicted derivation is not adopted, and the contradiction is reported. A second derivation is reported as a
    second attempt.
* **The one exception: upper-bound calibration (item C).** It is the only place where a number is fitted to dev
  residuals, and only by the procedure fixed in C. No other constant is fitted to any dev data.
* **Frozen and not changed in v4:**
  * the risk WARN_MARGIN 0.85 and CONFIDENCE_FLOOR 0.30;
  * the risk-v2 C3 policy;
  * the time buckets;
  * the time calibration artifact `calibration-v1.json` (not refitted);
  * the 250 ms analysis ceiling (CLAUDE.md).

  The displayed `high` changes only through item C. Displayed `low` / `expected` keep policy B.
* **Regression rule (every change, on all dev data).** As in Phase 6c / 7b: RAM above_high per operation and tier must not
  rise. Any listed regression needs a written keep or revert decision before the freeze.
* **Order:**
  1. this commit (with the updated Phase 8b protocol);
  2. the Phase 8b collection protocol completed by the owner and committed (its fields only, no notebook);
  3. v4 work on dev: derivations, probes and model changes, then calibration (item C) last, on the final models;
  4. dev criteria evaluated and reported;
  5. **the calibration factors are computed on dev and committed inside the frozen file set, and `models-frozen-v4` is
     tagged** (manifest; guard). This happens before any v4 held-out group is generated or collected;
  6. after the tag: the synthetic split files `ops-v4` and multicell v4 are generated and committed; the Phase 8b batch is
     collected per its protocol and its manifest with SHA-256 digests is committed. The batch gets no census, no static
     analysis and no reading of cells;
  7. held-out runs, each once;
  8. the report, as it comes out.

## 1. Scope of freeze v4 (nothing else)

Each item has a dev success criterion (needed before the freeze) and a failure rule. Held-out criteria are in section 2.

### (1) Must

**(1a) fillna on text columns.**
* *Context.* The v3 probes contradicted the frozen term on pandas 3 `str` columns (measured/derived 1.33, 1.30).
* *Change.* A new derivation from the `str` storage the environment actually uses (python vs pyarrow-backed). It is
  written down before the probe, and it is a second attempt.
* *Dev success:* every probe variant within +-15%. Variants:
  * NA share 0 / 10% / 90%;
  * short and long strings;
  * scalar and dict values;
  * one and several text columns.
* *Failure rule:* not adopted; text fillna stays UNKNOWN (named).

**(1b) copy -> fillna within a cell.**
* *Change.* Column statistics (text included) are carried through `copy`, so a `fillna` on a frame copied earlier in the
  cell gets the same estimate as on the original.
* *Dev success:*
  * cell model within +-15% on probes of `d = df.copy(); d.fillna(...)` (numeric, text, mixed);
  * 0 above_high on the dev multicell cells of this form.
* *Failure rule:* the cell keeps the v3 behaviour.

**(1c) value_counts.**
* *Context.* The v3 derivation was contradicted (1.40, 2.14). This is a second attempt.
* *Change.* A derivation from the hashtable path (`value_counts_internal`, `hashtable.value_count`): unique count from Tier
  1 statistics, object / `str` vs numeric keys, `normalize`, `dropna`, `Series` and `DataFrame` receivers. Tier 0 gives
  a range bounded by unique count = rows.
* *Dev success:* every probe variant within +-15% at low / medium / high cardinality.
* *Failure rule:* stays UNKNOWN (named).

**(1d) copy on receivers v3 cannot size.**
* *Change.* `X.copy()` where X is a column selection (`df[[...]]`, `df['c']`), `.loc` / `.iloc` slice, boolean-mask
  filter, `head` / `tail` / `sample`, or a frame produced earlier in the cell by a modelled operation:
  * the upper bound is the bytes of the selected columns of the base frame (all rows for a mask);
  * `low` is the bytes of the shape that can be derived statically, where one can (column selection, `head(n)`).

  A receiver produced by an UNMODELLED operation stays UNKNOWN (named).
* *Dev success:* each form probed; actual <= high for every variant, and expected within +-15% where the shape can be
  derived.
* *Failure rule:* that receiver form stays UNKNOWN.

### (2) Should

Each operation below follows the derivation rule. A failed operation stays UNKNOWN (named) and is reported; it does not
block the others.

* **`duplicated`**: hashtable on the key columns; output bool array.
* **`dropna`**: mask + take; output bounded by the input (`how`, `subset`, `thresh`).
* **`reset_index`**: insert of the index as columns; `drop=True`; RangeIndex vs materialised index.
* **`Series.map`**: dict / Series mapper (indexer + take) and numpy ufunc. A Python-function mapper is DEFERRED (same as
  apply).
* **`to_numpy`**: zero-copy single-dtype case vs consolidation copy; `dtype=` and `copy=`.
* **`astype` on several columns / a dict**: the per-column sum of the v3 single-column term. Category conversion needs
  Tier 1 unique counts.
* **`read_csv(parse_dates=...)`**: a re-derivation of the serial-path term that measured 1.36 in v3. This is a second
  attempt.

### (3) Easy wins

* **`np.zeros` / `np.empty`**: shape x itemsize. Low and expected for `np.zeros` account for lazy zero pages: the RSS peak
  appears only when the pages are written, and the probe decides which term is displayed.
* **`np.array`**: from a known object (copy semantics, `copy=`, dtype conversion). From a literal or unknown iterable:
  UNKNOWN.
* **`np.linspace`**: num x itemsize.
* **`sample`**: take of n or frac rows; `replace=`.
* **`describe`**: per-column quantile workspace. Numeric and object / `str` columns are derived separately.

*Dev success for (2) and (3):* every probe variant within +-15%, and the regression rule.

### (4) Deferred, with an explicit UNKNOWN message

`apply` / `map` with a Python function, `to_csv`, `join`, `pd.get_dummies`, `corr`.
* *Change.* The UNKNOWN message names the operation and says that it is not modelled in v4 ("no estimate for
  `df.corr()`: not modelled in v4"). The risk class is never OK, as under the uncovered-operation rule.
* **Cell range rule (Rule 1, new in v4):** when a cell contains an operation without an estimate, NEXUS does not display
  a cell range. It shows the estimated operations' ranges labelled "excludes `<op>`" and the class UNKNOWN / WARN /
  HIGH_RISK.
  * Such a cell has no cell estimate, so it is NOT scored for above_high.
  * Instead it is scored by the excludes-label criterion (section 2, decisive) and counts against coverage.
  * The secondary v3-way above_high (section 2, not deciding) is reported for comparability.
  * The number of such cells is reported in every evaluation.
* *Dev success:*
  * the messages are tested;
  * on all dev multicell cells with an operation without an estimate, the class is never OK at any simulated headroom
    where the actual exceeds it.

### (C) Upper-bound calibration from dev residuals

*Why.* On the Windows held-out groups, covered cells and points went above high because of errors in the models
themselves, not only because of uncovered operations. The model `high` is a derivation, not an error bound.

*Procedure (fixed here, run once on the final v4 models, before the freeze):*
* **Residual** = actual RAM / displayed `expected`, on dev valid Tier 1 points (cell model for multi-statement cells).
* **Unit of exchangeability = the CONFIGURATION** (a dev case, a multicell configuration, a real notebook). Each
  configuration contributes its MAXIMUM residual, so the bound targets the per-configuration criterion.
* **Groups:** one per operation family (the registry model; a multi-statement cell's family is its dominant-peak
  operation).
  * A family with >= 30 dev configurations gets its own factor.
  * Smaller families use the pooled factor over all configurations.
* **Factor:** q_f = the ceil((n + 1)(1 - alpha))-th smallest configuration residual, with **alpha = 0.02** (split
  conformal). If that rank exceeds n, q_f = the largest residual x 1.10, and the family is listed as "factor at the
  sample maximum".
* **Calibrated high:** `high_v4 = max(high_model, expected x q_f)`. It only raises the high: `low` and `expected` are
  unchanged.
* **Computed on dev only and frozen inside the `models-frozen-v4` tag** (artifact `calibration/upper-v1.json` in the
  manifest, with the committed script that computes it). This is done **before any v4 held-out group is generated or
  collected** (Order, step 5). The script is not re-run after the freeze.
* *Stated limitation.* The conformal coverage holds only if held-out configurations are exchangeable with dev ones. The
  held-out groups are generated differently (new seeds and shapes; real notebooks), so the bound is a design target, not
  a guarantee. The held-out criteria test it.
* *Dev success:*
  * leave-one-configuration-out estimate (factor recomputed without the configuration, then applied to it) <= 2% above
    high per point and per configuration, pooled and per family with >= 30 configurations;
  * the width criterion W on dev (below).
* *Failure rule:* if LOCO exceeds 2% at alpha = 0.02, alpha is NOT lowered after seeing that and nothing else is retuned.
  Calibration is still adopted, the dev criterion is reported as FAILED, and the held-out bars do not change.

### (T) Tier 0 / Tier 1 selection must not depend on wall-clock time

*Context.* v3 item (3) FAILED: the deterministic gate disagreed with the live deadline on 41% of 2-core inputs and was
reverted, so v3 still selects the tier by live timing.

*Change.*
* The tier is a pure function of (cell source, inspected metadata: shapes, dtypes, sizes, machine profile id). Fixed
  sample sizes and seeds keep the cell-seeded sampler.
* The statistics work is bounded by construction (row and column caps), so the dev worst case on the reference machine
  fits the budget.
* No live timing decides the tier. The hard deadline stays only as the interceptor's fail-safe: when it fires, NEXUS shows
  NOTHING for that cell (silence, per CLAUDE.md), never a Tier 0 fallback. Every firing is recorded.
* **A firing counts as NOT ESTIMATED in every coverage metric:** the dev target, the Phase 8b held-out coverage, and the
  reported shares. The cell stays in the denominator.

*Dev success:* 10 fresh-process repeats on >= 30 dev inputs (all Tier 1 operations, sizes up to 10M rows; mains):
* identical tier and estimate across all repeats of every input where the deadline did not fire;
* deadline firings <= 5% of the repeats on 2 contended cores, and 0% on the idle measurement machine. Each firing is
  listed.

*Failure rule:* the tier stays a pure function regardless (no live-timing fallback is reinstated). Whether the firing bar
was met is reported, and the user-visible silence rate is a reported limitation.

## 2. Held-out sets and criteria (each set run once; reported with n and the 95% bounds)

**Sets** (all created after the v4 tag, except val-v5, which is sealed since 2026-11-18):
* **Synthetic single-operation group `ops-v4`**: every operation in (1)-(3) plus the v3 operations.
  * >= 40 configurations (operation x shape x seed), new seeds and shapes never used in dev, sizes so the peak is
    >= 200 MiB;
  * risk replay with simulated limits as in `benchmarks.risk_eval`.
* **Synthetic multi-statement group multicell v4**: >= 16 templates covering (1)-(4), chains, frames created earlier in
  the cell and rebinding, with new seeds and shapes.
  * Per template, the configurations with the two largest salted hashes are held out: >= 32 configurations / 64 cells.
* **Both synthetic groups run on Windows (reference laptop) AND Linux** (a machine with >= 32 GB RAM, its own full mains
  profile per `heldout_env.py`). Each platform is a separate held-out run and is reported separately; **each platform must
  pass on its own**. Leak protection as for v3:
  * digest-checked split files;
  * held-out console output shows id / status / time only;
  * results in `heldout/` directories;
  * every access logged in `docs/benchmarks/phase8-heldout-access-log.md`.
* **val-v5** (Linux only; 47 single-operation configurations, digest above): run once on `models-frozen-v4` with the
  val-v5 runbook. Results go in `<results>/validation/`, it is read only by `evaluate --val --reason "..."`, and the access
  is logged in the PROGRESS Test-split access log.
  * Its configurations cover only v3-era operations, so it tests the v3-era models plus the v4 calibration and tier rule
    on a second platform. It does not test the new v4 operations.
* **Phase 8b held-out batch** (protocol: `docs/benchmarks/phase8b-preregistration.md`): fresh notebooks, 15-20 targeted
  for collection, run on Windows.
  * **Eligible cell:** a code cell in which the frozen v4 analyser detects >= 1 pandas / NumPy operation and which
    executes without error in the Phase 8a harness.
  * **>= 150 eligible cells are required, counted at run time.** With fewer, every Phase 8b criterion is INCONCLUSIVE. A
    top-up batch is allowed only through an amendment committed before that batch is collected, and it is sealed the same
    way.

| criterion | sets | bar |
|---|---|---|
| RAM above_high per POINT / CELL | ops-v4 and val-v5 (Tier 1, as displayed), multicell v4 held-out (cell model; cells with a displayed cell range), Phase 8b valid points; per platform | <= 3%, one-sided 95% Clopper-Pearson upper bound quoted ("consistent with <= x%") |
| RAM above_high per CONFIGURATION | ops-v4, val-v5, multicell v4 held-out; per platform | <= 3%, bound quoted |
| **excludes-label criterion** (Rule 1) | multicell v4 held-out, Phase 8b; per platform | **0 violations.** A violation: a cell labelled "excludes `<op>`" whose class is OK at a simulated headroom (64 MiB .. 8 GiB) that its actual peak exceeds |
| time within-one bucket, **Tier 1** | ops-v4, val-v5, multicell v4 cells with measured time >= 100 ms, Phase 8b valid time points; per platform | >= 95%, Wilson 95% lower bound quoted. Tier 0 reported, no verdict. The tier is fixed here, unlike v3 |
| range width W | every held-out set; per platform | (a) points estimated by both v3 and v4 (prediction-only re-run of `models-frozen-v3` on the same inputs): median of (high_v4 / expected_v4) / (high_v3 / expected_v3) <= **1.30**; (b) all v4-estimated points: median high_v4 / expected_v4 <= **2.0** and 90th percentile <= **4.0** |
| R1 recall | ops-v4 and val-v5 risk replay; per platform | >= 98% pooled and at every limit with >= 20 positives |
| R2 false alarms | ops-v4, val-v5; per platform | pooled <= 30% and per operation <= 50% (operations with >= 20 non-positive pairs) |
| R3 HIGH_RISK precision | ops-v4, val-v5; per platform | >= 75% (no claim with < 20 HIGH_RISK points) |
| uncovered-operation rule | multicell v4 held-out, Phase 8b | a cell with NO estimated operation (UNKNOWN, no "excludes" label) is never OK at a simulated headroom its actual exceeds; one violation fails |
| coverage (held-out) | Phase 8b | paired run-time share (Phase 8b pre-registration, section 3; deadline firings count as not estimated) of v4 minus that of v3 >= **15** percentage points |
| *secondary, NOT deciding:* above_high scored the v3 way | multicell v4 held-out, Phase 8b; per platform | no bar. Cells labelled "excludes `<op>`" are scored against the range v3 would have displayed (the cell model over the estimated operations only). It is reported next to the deciding rate, for comparability with the v3 results |

**Dev coverage target (needed before the freeze, not a held-out bar):** on `real_notebooks/`, run-time share >= **55%**
of executed cells with >= 1 detected operation have every detected operation estimated. A deadline firing counts as
not estimated. For reference: v3 static is 24% (18/75), and the static ceiling of the v4 scope is 83% (62/75). The
static share is reported alongside, labelled OVERSTATING.

A metric with fewer than **30** valid points (configurations: fewer than 10) is **INCONCLUSIVE**, never a pass.

## 3. Dev / held-out discipline

* Develop and decide on dev only.
* Each held-out set runs ONCE per platform on `models-frozen-v4`. Before each run:
  * the freeze guard (0 problems);
  * `heldout_env.require_profile()`;
  * mains power (no `--allow-battery`).
* Protected values are never printed, plotted or pasted before that set's single evaluate call. Afterwards the set is
  dev, and a v5 check needs new sets.
* No model, threshold, calibration factor or rule changes between the freeze and the last held-out read. A change after
  a read invalidates the remaining runs (new freeze, new sets).
* The v3 prediction-only re-run used for criterion W(a) runs AFTER the v4 actuals are recorded. It reads no actuals until
  the evaluate call.

## 4. What counts as failure

* **Failure of the whole v4** ("`models-frozen-v4` FAILED its held-out check"), on any synthetic set, val-v5 or platform:
  * RAM above_high > 3% per point / cell or per configuration;
  * the excludes-label criterion (any violation);
  * time within-one < 95% on ops-v4 or val-v5;
  * R1 < 98%;
  * the width criterion W;
  * the freeze guard reporting a difference (the run aborts).

  A failed v4 is not repaired on those data.
* **Failure of an item** (claim withdrawn; v4 not failed as a whole):
  * R2 (a third failure, reported as a repeat) or R3;
  * the uncovered-operation rule;
  * held-out coverage;
  * a Phase 8b accuracy criterion;
  * any dev criterion of section 1, reported before the freeze.
* The secondary v3-way above_high never decides anything.
* INCONCLUSIVE is reported as such and never counted as a pass. Every outcome is reported as it comes out, with its 95%
  bounds.
