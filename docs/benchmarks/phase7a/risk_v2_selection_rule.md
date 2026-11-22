# Phase 7a item 1f: risk-v2 candidate selection rule (written and committed BEFORE any candidate is computed)

Design only. Evaluated on STORED dev data, with no new measurement and no frozen file changed. This file is
committed before the evaluation script exists, and its rule is applied as written.

## Data

* Ranges: `benchmarks/results/phase6c-dev` holds the frozen-v2 predictions of all dev points (Tier 0 and Tier 1,
  policy B as stored). The actuals are the stored ones (`load_joined`).
* A model's OWN Tier 1 `high` (before policy B replaces it with Tier 0's) is stored only in
  `benchmarks/results/tier1-v3` (Phase 5 model state). It is used for a point only if that point's Tier 1
  `expected` in tier1-v3 equals the frozen-v2 Tier 1 `expected` within 1%, i.e. the model gives the same answer
  on that point. Points that fail this are listed and evaluated with policy B under every candidate (no change).
* Limits, positives, headroom and the classes: exactly `benchmarks.risk_eval` (Phase 5 Part A6; limits
  64 MB .. 2048 MB; claim limits = those with >= 20 positives). R1-R3 bars unchanged: recall >= 98% (pooled and
  per claim limit), R2 pooled <= 30% and per operation (>= 20 non-positive pairs) <= 50%, R3 HIGH_RISK precision >= 75%.

## Candidates

The classes depend on `high` only through WARN (`high > 0.85 x headroom`). HIGH_RISK (`expected > headroom`) is
the same under every candidate.

* **C0** keeps risk as is: WARN on the policy-B `high` (Tier 0's high).
* **C1** (read_csv): for `pandas.read_csv` points whose Tier 1 statistics ran, WARN on the model's own Tier 1
  `high`. Every other point keeps C0.
* **C2** (merge): for `merge` points whose Tier 1 join statistics ran, WARN on the model's own Tier 1 `high`.
  Every other point keeps C0.
* **C3**: C1 and C2 together.

## Rule (applied in this order)

1. **Eligible:** R1 is met (pooled and at every claim limit) AND the candidate adds **zero** misses relative to
   C0. No positive (point, limit) pair that C0 alerts may become a non-alert, and R3 must stay >= 75%.
2. Among the eligible candidates, keep those that meet R2 in full (pooled <= 30%, and every operation with >= 20
   non-positive pairs <= 50%). If more than one does, select the one that changes the FEWEST operations
   (C1 or C2 before C3). A remaining tie goes to the lower pooled false-alarm rate.
3. If no eligible candidate meets R2 in full, select the eligible candidate with the lowest maximum per-operation
   false-alarm rate, but only if it lowers that maximum by >= 10 percentage points against C0. Otherwise select
   **C0**. In both cases R2 is reported as **FAILED on dev** for the selected candidate.
4. The selection is a dev decision. It becomes a v3 claim only through the held-out check pre-registered in
   `docs/benchmarks/phase7-preregistration.md`. A selected candidate that then fails there is reported as FAILED,
   not re-selected.
