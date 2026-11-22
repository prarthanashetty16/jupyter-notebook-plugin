# Tier 1 fallback rate under scarce CPU (Phase 6b; information only, no model change)

Tier 1 statistics run inside the 250 ms analysis budget; when it runs out, the estimate falls back to Tier 0 (`tier1.reason = 'time budget'`). Same stored dev points and code as the frozen stack `models-frozen-v1`, prediction only. Conditions: `benchmarks/fallback_rate.py` (affinity to 2 logical CPUs; plus 2 busy loops on the same CPUs for the contended run). The baseline is on mains; see the power notes of each run below.

## Fallback to Tier 0 on the time budget, per operation

| op | points | 16 cores (baseline, phase6-dev-mains) | cores2 | cores2_contended |
|---|---|---|---|---|
| astype | 63 | 0 (0%) | 0 (0%) | 0 (0%) |
| drop_duplicates | 47 | 0 (0%) | 1 (2%) | 9 (19%) |
| groupby | 51 | 0 (0%) | 0 (0%) | 0 (0%) |
| merge | 37 | 0 (0%) | 0 (0%) | 8 (22%) |
| pandas.read_csv | 24 | 0 (0%) | 0 (0%) | 0 (0%) |
| pandas.concat | 27 | 1 (4%) | 1 (4%) | 11 (41%) |
| ALL | 249 | 1 (0%) | 2 (1%) | 28 (11%) |

**`cores2` was measured ON BATTERY** (power at start: battery, at end: battery): battery throttling and the CPU condition are confounded; the 16-core baseline was measured on mains.

`cores2`: `{"condition": "cores2", "affinity": [0, 1], "busy_loops": 0, "power": "battery", "started": "2026-11-21 23:23:07", "finished": "2026-11-21 23:33:34", "power_end": "battery"}`

**`cores2_contended` was measured ON BATTERY** (power at start: battery, at end: mains): battery throttling and the CPU condition are confounded; the 16-core baseline was measured on mains.

`cores2_contended`: `{"condition": "cores2_contended", "affinity": [0, 1], "busy_loops": 2, "power": "battery", "started": "2026-11-21 23:33:34", "finished": "2026-11-22 00:05:47", "power_end": "mains"}`

## What a fallback means for the user (dev, per operation: Tier 0 vs Tier 1)

RAM: median |expected - actual| / actual and mean width (high - low) / expected of the stored policy-B rows; time: the same for the calibrated LOCO predictions of Phase 6 (`docs/benchmarks/phase6/tier*_loco.csv`).

| op | RAM error T1 -> T0 | RAM width T1 -> T0 | time error T1 -> T0 | time width T1 -> T0 |
|---|---|---|---|---|
| astype | 1% -> 17% | 0.93 -> 0.99 | 32% -> 67% | 1.48 -> 4.91 |
| drop_duplicates | 12% -> 17% | 0.78 -> 1.06 | 25% -> 26% | 2.39 -> 2.46 |
| groupby | 2% -> 57% | 2.18 -> 1.47 | 26% -> 86% | 1.55 -> 10.63 |
| merge | 8% -> 55% | 5.23 -> 3.66 | 24% -> 39% | 1.62 -> 2.23 |
| pandas.read_csv | 22% -> 39% | 3.04 -> 2.65 | 12% -> 20% | 0.89 -> 1.27 |
| pandas.concat | 6% -> 8% | 0.85 -> 1.00 | 38% -> 28% | 6.21 -> 4.59 |

## Reading (information only; no model, budget or threshold changed)

* **Two dedicated cores barely matter:** 2 of 249 points fell back (1%), the same order as 16 cores (1 point). The Tier 1
  statistics are single-threaded and sample-bounded, so fewer cores alone do not exhaust the 250 ms budget.
* **Contended CPU (about half of each of the 2 cores) does:** 28 of 249 points (11%) fell back: concat 41%, merge 22%,
  drop_duplicates 19%; astype, groupby and read_csv 0%. By size: 5 points at 1M rows, 14 at 3M, 9 at 10M.
* **Where it hurts:** the merge fallbacks are the fan-out / low-overlap joins (`inner_bigright_fanout8`, `overlap20_fanout10`,
  `overlap55_fanout4p5`, `left_overlap40_fanout9`, the outer zipf joins), exactly the cases where Tier 1's join statistics
  carry the RAM estimate: on dev a merge at Tier 0 has a median RAM error of 55% vs 8% at Tier 1 (policy B keeps the Tier 0
  high, so the alert side stays covered; the central estimate and the time get worse: 24% -> 39%). For concat the fallback
  costs little (RAM 6% -> 8%); for drop_duplicates RAM 12% -> 17%. What a user would see: a wider "most likely" bucket
  and, for merge, a central RAM figure that can be off by about half.
* **Confounds:** the 2-core run was entirely on battery; the contended run started on battery and ended on mains (the
  charger came back during it). The busy loops halve the CPU share only roughly (the OS scheduler decides). The baseline is a
  mains run of the same code. These numbers are therefore an indication of the direction and the affected operations, not
  a rate for a specific machine.
* **Not done:** throttling the CPU clock (would need a system power-plan change); a run on a real 2-vCPU VM.

## Note (2026-11-22, Phase 6d profile audit)

The two runs above used a corrupted machine profile (quick, battery; `docs/benchmarks/phase6d/profile_audit.md`). The fallback counts depend only on the Tier 1 statistics and their time budget, not on the profile, and the error table comes from Phase 6 dev data: **no number in this report changes**. The stored time estimates of these runs were recomputed with the restored profile (`predictions_time_restored_profile.csv` in each results folder).
