# Phase 4d evaluation on DEVELOPMENT data (every number is dev)

* `controller_vs_tier1.md` - the pre-registered controller replayed on the 322 dev points that have Tier 0 / 1 / 2
  predictions, under declared free-RAM scenarios (2.5 / 8 / 32 GiB), per operation: RAM and time accuracy, coverage,
  above_high, width, escalation rate, Tier 2 usage, fail-closed rate, overhead; plus a labelled WHAT-IF (always escalate).
  `controller_points_*.csv` hold the per-point decisions. Regenerate: `python -m benchmarks.controller_eval benchmarks/results/tier2-dev-b --out docs/benchmarks/phase4d-dev`.
* `multistatement.md` - the Tier 2 safety analyzer on 51 realistic multi-statement cells (6 accepted) and the
  relaxation PROPOSALS (nothing implemented). Regenerate: `python -m benchmarks.multistatement_report --out ...`.

The pre-registration is `docs/benchmarks/phase4d-preregistration.md`; the interpretation is in `docs/PROGRESS.md`
(Phase 4d). The replay feeds the stored dry runs to the real `Controller` class; it is not a new measurement.
