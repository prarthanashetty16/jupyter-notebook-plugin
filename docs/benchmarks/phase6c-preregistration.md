# Phase 6c pre-registration: a bounded, derived fix round, then `models-frozen-v2`

Written and committed **before any Phase 6c change or measurement**. Dated 2026-11-22. Changes after this commit are dated
amendments appended at the end.

**Status of the data.** The two Amazon notebooks (`amazon_ml_solution`, `amazon_solution_old`) were opened and run in Phase 8a
and the fixes below are motivated by that run: they are **dev data** from now on and can never count as held out. test-v2 and
val-v5 stay sealed and unrun; nothing is tuned on them. Real data, outputs and code stay on this machine and are never committed.

**What stays as it is.** The risk-engine classes and thresholds (WARN margin 0.85, confidence floor 0.30, HIGH_RISK on
`expected > headroom`), range policy B, the Tier 1 guard, the Phase 5 suggestion thresholds, every Phase 6 rule (machine profile
format 3, the calibration artifact `calibration-v1`, the conformal method) and every RAM / time model not named below.
**The Phase 5 R2 failure (merge, read_csv false alarms) is NOT addressed in this phase.**

---

## 1. Scope (exactly four items, nothing else)

1. **Cell-level peak model** replacing `nexus.risk.combine` (max of the expected values, sum of the highs):
   `peak(cell) = max over statements s of [ retained(before s) + temporaries(s) + peak(current operation) ]`, with
   `retained` = outputs of earlier operations whose result is bound to a name in the cell (and not `del`eted later in the
   cell) or still referenced at the end of the cell; `temporaries(s)` = outputs of earlier operations of the same statement
   (chains: they stay alive until the statement ends); `peak(op)` = the operation's own incremental peak (which includes its
   output). Every term from the operation's own low / expected / high, giving the cell's low / expected / high. An operation's
   output size comes from a new `output_bytes` of its model (the bytes of the result object, derived per model); a model
   without it counts its whole peak as retained (conservative). Liveness rules, conservative where unclear:
   * a result bound by assignment is retained until an explicit `del` of that name in the cell; **rebinding a name is NOT a
     release** (the old object may be referenced elsewhere);
   * an expression statement's result is released after the statement, except the last statement of the cell (kept by
     IPython's output history);
   * an operation inside a loop, a comprehension, a function / class body or a `try` / `with` block: the cell is **not
     modelled** by the new rule and falls back to the v1 aggregation, with a flag.
   The baseline is the state resident before the cell (incremental figures, as everywhere in NEXUS).
2. **`read_csv` Tier 1 with `sep` / `delimiter`, `dtype`, `usecols`, `header`, `nrows`**, decided from the pandas source:
   which arguments only change tokenising (passed to the sampler's own parse), which change output bytes or per-field cost
   (derived), and which must keep the refusal (anything that switches to the python engine, e.g. a multi-character or regex
   separator; extension / category dtypes unless derived; callables; any argument not listed).
3. **Models for `copy` (deep) and `fillna` (scalar or dict value, not inplace)**, derived from copy semantics (when pandas copies,
   when it shares under copy-on-write, block consolidation), probed at >= 200 MiB. No other new operation.
4. **Extension defaults:** `%load_ext nexus` runs Tier 1 (statistics; the controller's Tier 2 dry runs stay OFF by default, so
   the controller cannot escalate and the result equals Tier 1; `%nexus tier 2` opts in); `select_columns` stays off. When an
   estimate fell back to Tier 0 the display says so prominently: "reduced-accuracy estimate: statistics unavailable (<reason>)"
   with the reason (time budget / unsupported arguments / no statistics). The wording changes no estimate and no risk class.

## 2. How every change is justified

Each change is DERIVED from pandas / numpy behaviour (source reading) and checked by an isolated probe whose peaks are
**>= 200 MiB** on the OS peak counter (`nexus.measure`, fresh process, inputs from disk). Nothing is fitted to the notebooks or to
any benchmark point; a constant that cannot be derived is not introduced. Probes and their outputs are kept in
`docs/benchmarks/phase6c/probes/`.

## 3. Evaluation

**A. Multi-statement cell benchmark (new).** At least 30 synthetic multi-statement cells over the supported operations
(several loads in one cell, load then merge, chains with temporaries, deletes, copy / fillna, expression statements,
rebinding), each a *configuration* = (template, data shape) with one or two sizes, peaks >= 200 MiB, measured with the validated
instrument (median of 3 fresh processes, inputs from disk). **Split by configuration before any measurement:** per template, the
configuration with the largest `sha256("phase6c-multicell-v1:" + key)` is held out (at least 12 held-out cells in total),
stored in a frozen, digest-checked split file; the held-out part is opt-in (`--heldout --reason`), its runner output shows only
id / status / time, its results go to a separate folder, every access is logged, and it is **not run in this phase**.
On dev, report per cell and per template: bias (median expected / actual), median and p90 |error|, coverage, above_high, below_low,
width, for the new cell model AND for the v1 aggregation on the same cells.
* **Success (dev):** new-model RAM above_high <= 3% of the dev cells and <= 5% of the dev configurations; median |error| reported
  (no bar). The held-out part, run later once, is judged by the same two bars.
* If the dev bars fail, the cell model is not adopted (v1 aggregation kept) and that is reported.

**B. Regression on all existing dev data.** Every pre-registered per-operation metric (RAM above_high, coverage, width; time
median / p90 error, same-bucket, within-one, coverage) must be unchanged or better on the existing dev points (Phases 3-6 dev
split; prediction re-run where a model file changed, stored predictions where it did not, which is shown by file hashes). RAM
above_high must stay 0%. Any regression is listed with a decision (keep / revert).

**C. read_csv / copy / fillna.** Their probes (>= 200 MiB) are reported with predicted vs measured; the new read_csv Tier 1
arguments and the two new models also appear in the multi-statement benchmark.

**D. Real notebooks (dev, information only).** Seeded random-row subsample copies (20-25% of the rows, same format and columns)
of the notebook data under `benchmarks/results/realworld/` (git-ignored), the Phase 8a harness on mains power with the new
stack; accuracy, UNKNOWN reasons and risk classes are reported, every number labelled dev. No verdict.

## 4. What counts as failure

* A change without an isolated derivation / probe: not adopted.
* Multi-statement dev bars (above_high <= 3% per cell, <= 5% per configuration) not met: the cell model FAILS and is not adopted.
* Any per-operation regression in B without a recorded decision; any RAM above_high > 0% on existing dev points: the change
  that caused it is reverted.
* A probe that contradicts a derivation: that change is not adopted.
Failures are reported as they come out; nothing is repaired and re-claimed on the same data.

## 5. Freeze

After the evaluation: tag `models-frozen-v2`, extend `docs/benchmarks/frozen-manifest.md` (v1 stays documented; changed, added
and unchanged frozen files with hashes; what is outside the freeze) and point the guard at v2. Any model change after v2
invalidates the held-out status of the runs that use it (val-v5, the multi-statement held-out cells, a future fresh
real-notebook test).
