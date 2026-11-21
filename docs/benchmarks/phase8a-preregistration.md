# Phase 8a pre-registration: accuracy of the frozen stack on real notebooks

Written and committed **before any real notebook is opened or executed** in Phase 8a. Dated 2026-11-22. Changes after this
commit are dated amendments at the end. What I knew when writing it: the Phase 4e static coverage study of the same three
notebooks (aggregate counts only: 605 analysable code cells, 190 with a detected operation, 0 accepted by the Tier 2 safety
analyzer) and every dev result in `docs/PROGRESS.md`; I have not seen any cell code, data or output of the notebooks.

**Frozen stack.** `models-frozen-v1` (40 hash-checked files, `docs/benchmarks/frozen-manifest.md`). The harness calls the
freeze guard at start and aborts on any difference. **Evaluation only:** nothing is tuned on these results; any model change
motivated by them needs a fresh split and a new freeze. test-v2 and val-v5 are not touched.

**Sample (stated up front).** Three notebooks from ONE author (`amazon_ml_solution`, `amazon_solution_old`, `multiseed_exp`),
ML-heavy and built around one dataset. This is a small, unrepresentative sample: a pass says only that the criteria held on
these cells on this machine.

---

## 1. What is run and what is predicted

* Each notebook runs as a copy, cell by cell, in a fresh spawned Python process hosting an IPython `InteractiveShell`
  (ipykernel is not installed; the shell is what a kernel wraps), working directory under `benchmarks/results/realworld/`,
  `MPLBACKEND=Agg`, the machine profile calibrated on mains. Shell / package cells (`!...`, `%pip`, `%conda`, `%%bash`,
  `%%sh`, `%system`, `%%script`) are NOT executed (recorded as skipped).
* Before each cell, outside the measured window, NEXUS analyses it on the live namespace:
  * **primary:** `Pipeline(tier=2)` with the pre-registered controller (Tier 1 statistics under the default 250 ms budget,
    policy B, Tier 2 only if the controller triggers AND the safety analyzer accepts), the calibration artifact, default
    suggestion rules (`select_columns` off);
  * **secondary:** `Pipeline()` at its default Tier 0, which is what `%load_ext nexus` uses today (reported, no verdict).
* **Cell estimate** = the risk engine's combination of the cell's operation estimates (`nexus.risk.combine`: max of lows and
  of expected values, sum of highs; times summed). A cell has a **validated-model operation** if at least one estimate comes
  from a registered model (astype, concat, drop_duplicates, groupby, matmul, merge, np_sort, read_csv, sort_values).

## 2. Actuals and valid points

* **Time:** wall clock of the cell's execution alone (NEXUS analysis excluded), one run.
* **RAM:** the kernel's incremental peak above its RSS at the cell's start. A parent-side sampler polls the kernel's RSS every
  ~2 ms; the OS peak counter (Windows peak working set) is read before and after. The OS counter is exact but monotonic and
  cannot be reset on Windows, so the RAM actual is **valid only when the cell raised the historical OS peak**: actual =
  `peak_after - rss_start` (the sampler is the cross-check). A cell that did not raise the historical peak, or whose actual is
  below the floor, is **CENSORED** (the sampler value is kept for information, never used as an actual; never zero).
* **Floors:** RAM 32 MiB, time 100 ms (the benchmark floors). One run, so no repeat-spread check (stated as a limit).
* **Watchdog kill** (kernel RSS above the cap): the cell's RAM actual is a LOWER BOUND = the observed peak above the start;
  it counts as a valid RAM point and as above `high` only if the bound itself exceeds `high`. Its time is not an actual.
* **Valid RAM point:** a cell with a validated-model estimate (primary pipeline), executed without error (or killed by the
  watchdog), with a valid RAM actual as above. **Valid time point:** same, executed without error, wall time >= 100 ms.
* Cells are also grouped: validated-model with a valid actual / detection-only (an operation detected but no model estimate)
  / cheap (below the floors) / censored / failed (error type only) / skipped.

## 3. Metrics and success criteria

* **RAM:** bias = median(expected / actual), median and p90 of |expected - actual| / actual, coverage (low <= actual <= high),
  above_high, below_low, width. **Criterion: above_high <= 3% of the valid RAM points**; coverage reported.
* **Time:** expected-bucket within-one and same-bucket rates (`nexus.timebuckets`), median / p90 relative error, bias,
  coverage of the calibrated range. **Criterion: within-one >= 95% of the valid time points.**
* **Minimum evidence:** fewer than **30** valid points for a metric makes that verdict **INCONCLUSIVE** (not passed).
* Verdicts MET / FAILED / INCONCLUSIVE, for the primary pipeline only. The secondary (Tier 0) figures are reported next to it.
* Also reported (no criterion): the fully-covered subset (every detected operation of the cell has an estimate), per
  operation of the dominant estimate, worst predictions (operation and shapes only).

## 4. Risk engine

* Class counts (OK / WARN / HIGH_RISK / UNKNOWN) over all analysed cells with a detected operation, as the engine saw them
  (live free RAM); UNKNOWN rate and reasons.
* On valid RAM points, three simulated limits, each giving headroom to `nexus.risk.classify` (thresholds unchanged):
  (a) **free RAM at the cell's start** (positive if the incremental peak exceeds it); (b) a process limit of **2048 MiB** and
  (c) **1024 MiB** (positive if `rss_start + peak > L`; headroom `L - rss_start`). Alert = WARN or HIGH_RISK; a positive
  classified OK or UNKNOWN is a missed overrun. Reported as in Phase 5: R1 recall >= 98% (limits with >= 20 positives, and
  pooled), R2 false-alarm rate pooled <= 30% and per operation <= 50% (operations with >= 20 non-positive pairs), R3 HIGH_RISK
  precision >= 75%, with "too few positives: no claim" where it applies. Every missed overrun is listed (operation, shape).

## 5. Suggestions

Per analysed cell with an estimate: how often at least one suggestion is shown, the rule names and semantics labels only.
Suggestions are **never executed** and their savings are not measured here.

## 6. What counts as failure

* The harness fails its validation on synthetic notebooks: the real notebooks are not run.
* RAM above_high > 3% with >= 30 valid points: **FAILED**. Time within-one < 95% with >= 30 valid points: **FAILED**.
* The freeze guard reports a difference: the run aborts and no result is reported.
* Any failure is reported as it comes out and is not repaired on these data.
