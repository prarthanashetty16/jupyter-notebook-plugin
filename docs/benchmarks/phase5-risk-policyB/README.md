# Phase 5 risk engine re-evaluated on policy-B ranges (Phase 6b erratum)

**Dev data, not validation; no new measurement; no threshold changed.** The Phase 5 report
(`docs/benchmarks/phase5-risk-dev/`) said it replayed "stored Tier 1 predictions under range policy B", but
`benchmarks/results/tier1-v3` stores each model's OWN Tier 1 range (policy A) for 194 of 323 Tier 1 rows: policy B
(Tier 1 low / expected, Tier 0 high) is applied in the pipeline, which started after that run (commit `c95f674`).
The risk engine's alerts depend on `high`, so the Phase 5 R1-R4 figures were computed on the wrong ranges.

Commands (`--policy-b` applies policy B to the stored rows; the frozen stack's own run already stores policy B):

```bash
python -m benchmarks.risk_eval benchmarks/results/tier1-v3 --policy-b --out docs/benchmarks/phase5-risk-policyB/tier1-v3
python -m benchmarks.risk_eval benchmarks/results/phase6-dev-mains --policy-b --out docs/benchmarks/phase5-risk-policyB/phase6-dev-mains
```

`tier1-v3` = the Phase 5 model state with policy B applied (194 Tier 1 `high` values changed); `phase6-dev-mains` = the
frozen stack `models-frozen-v1` (0 changed: stored as policy B). Both give the same verdicts and the same per-operation
rates to the reported precision.

## Pre-registered criteria (Part A6), as they come out

| criterion | Phase 5 report (policy A, wrong) | policy B (correct) | verdict |
|---|---|---|---|
| R1 recall >= 98% per limit with >= 20 positives and pooled | 100% (1119 / 1119) | 100% (1119 / 1119, Wilson lower 99.7%) | **met** |
| R2a pooled false-alarm rate <= 30% (claim limits) | 14.0% | 25.0% | met |
| R2b no operation with >= 20 non-positive pairs above 50% | none | **merge 58.8% (85 non-positive pairs), read_csv 78.0% (59)** | **FAILED** |
| R3 HIGH_RISK precision >= 75% | 98.6% | 98.6% | **met** |
| R4 no cell without an estimate is OK; UNKNOWN share | 0 UNKNOWN | 0 of 2260 pairs UNKNOWN | **met** |

**R2 FAILED** (per operation: merge, read_csv) under the ranges the risk engine actually uses; the risk engine does not meet all of its pre-registered criteria. Per operation (policy A -> B): merge 12% -> 59%, read_csv
44% -> 78%, astype 8% -> 15%, groupby 7% -> 19%, drop_duplicates 15% -> 20%; others unchanged. Cause: policy B's `high` is
Tier 0's high, which for merge (unknown key uniqueness: the sort-based path) and read_csv (unknown bytes per field: 2..24) is
several times the expected peak, so WARN (`high > 0.85 x headroom`) fires on cells that fit. Per limit the false-alarm rate is
56% at 64 MB, 46%, 55%, 25%, 17%, 20% at 2048 MB.

## Status of the risk engine (2026-11-21)

**R2 FAILED per operation (merge 58.8%, read_csv 78.0% false alarms, bar 50%). The risk engine of `models-frozen-v1`
therefore does NOT meet all of its pre-registered criteria** (R1, R3 and R4 are met; R2's pooled part is met). This stands
for the frozen stack; nothing was changed.

## Candidate risk-v2 fixes (dated 2026-11-21): HYPOTHESES, not adopted

To be evaluated only on a FRESH split created and pre-registered AFTER the held-out runs (val-v5, Phase 8a) have been read,
never on held-out data and not before those runs (changing a frozen file now would invalidate them):

1. **Per-operation policy for read_csv:** use the Tier 1 upper bound (the sniffed bytes per field narrows Tier 0's 2..24 B/field
   span) for WARN on read_csv, keeping Tier 0's high for HIGH_RISK and for cells without statistics.
2. Per-operation policy for merge: when Tier 1 established key uniqueness and the output rows, WARN on the Tier 1 upper bound;
   otherwise Tier 0's high (the sort-based path stays possible).
3. WARN on the Tier 1 upper bound wherever Tier 1 statistics ran, for every operation (policy A for WARN, B for HIGH_RISK);
   the val-v4 failure that led to policy B is the known risk of this one.
4. A separate "possible" alert level that says the upper bound comes from a wide Tier 0 range, without changing the classes.
5. Narrower Tier 0 highs for merge / read_csv by derivation (a RAM-model change, judged by the RAM pre-registration rules).
6. Keep the engine and accept R2 as failed (the stated price of recall over false alarms).

Each needs its own pre-registration with the R1-R4 bars unchanged, a new freeze and a held-out check.
