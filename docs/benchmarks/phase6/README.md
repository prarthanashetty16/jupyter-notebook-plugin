# Phase 6: calibration on dev (results)

**Dev only, leave-one-configuration-out (LOCO), one Windows laptop on mains power. Machine transfer is
untested until val-v5 (Linux).** Pre-registration: `../phase6-preregistration.md` (commit `a34747a`) and its
Amendment 1 (commit `b385fe1`, power state). Full tables: `phase6_dev.md` (written by
`python -m benchmarks.phase6_eval --frozen benchmarks/results/tier2-dev-b --derived benchmarks/results/phase6-dev-mains
--frozen-mains docs/benchmarks/phase6/f_mains.csv --out docs/benchmarks/phase6`); per-point LOCO CSVs next to it; probes in
`probes/` (README there).

## Inputs

* D: the derived time models with the v3 machine profile of 2026-11-18 22:14 (mains at start and end, profile id
  `987c455be3cc`, shipped as `src/nexus/calibration/reference_machine.json`; a second measurement agreed within a median
  ratio of 1.00, worst curve point 0.77 / 1.25), predictions re-run on the 323 measured dev points
  (`benchmarks/results/phase6-dev-mains`, 646 / 646 ok). A first re-run made partly on battery (`phase6-dev`) is discarded:
  13 Tier 1 statistics fell back on "time budget" and one point timed out.
* F: the frozen models (pre-Phase-6 code, commit `a34747a`) recomputed from the stored features with a v2 profile measured
  on mains with that commit's calibration (`frozen_v2_profile_mains.json`, `f_mains.csv`). The stored F (`tier2-dev-b`,
  v2 profile of 2026-11-16, power unknown) is reported next to it: its v2 primitives were 30-40% slower than on mains.
* 211 valid time points in 109 configurations per tier; Tier 2: 148 accepted time fits in 89 configurations.

## Outcome of the pre-registered selection

| tier | candidate | median log error | median rel. error | p90 rel. error | same bucket | within one |
|---|---|---|---|---|---|---|
| 0 | F stored (old profile) | 0.59 | 53% | 239% | 159 | 211 |
| 0 | F (mains) | 0.65 | 53% | 164% | 151 | 211 |
| 0 | D | 0.73 | 55% | 308% | 158 | 211 |
| 0 | **D+m** | 0.36 | 33% | 194% | 154 | 211 |
| 1 | F stored (old profile) | 0.58 | 53% | 224% | 158 | 211 |
| 1 | F (mains) | 0.64 | 52% | 146% | 153 | 211 |
| 1 | D | 0.33 | 32% | 76% | 182 | 211 |
| 1 | **D+m** | 0.25 | 25% | 89% | 181 | 211 |

D and D+m meet target (a) at both tiers against the mains F; **D+m is selected** (lowest Tier 1 median log error).
**Against the stored F neither would have met (a) at Tier 0** (159 vs 158 / 154 same-bucket points) and F would have been
kept: the decision rests on Amendment 1 (F recomputed on a mains profile), which was written after that comparison was
read. The learned residual model was NOT included: it lowered the Tier 1 median log error by 7.2% (needs >= 10%), although
it met the conditions at Tier 0 (15.6%).

## Ranges (target (b): coverage in [88%, 95%] per operation calibrated per operation)

Tier 1, LOCO, after: astype 95%, drop_duplicates 95%, merge 92%: met; groupby 87%, read_csv 82%, sort_values 77%, concat
75%: NOT met. Tier 0: astype 95%, drop_duplicates 95%, groupby 94%, merge 92%: met; read_csv 82%, sort_values 77%, concat
75%: NOT met. matmul (6 configurations) and numpy.sort (3 with valid time) get the generic band (95% nominal): 100%.
Pre-registered fallback (decided by `nexus.calfit.range_decisions` from LOCO coverage): concat and sort_values (both tiers) and
read_csv Tier 1 keep the uncalibrated 0.25x .. 4x band around the calibrated expected value (band coverage 81-88%, 88%, 100%,
closer to the target), flag "time range not calibrated"; groupby Tier 1 (87%) and read_csv Tier 0 (82%) keep the conformal
range (closer than the band). Mean width (high - low) / expected: Tier 1 3.85 -> 2.10, Tier 0 3.85 -> 4.57.

Tier 2 (accepted fits only; used at run time only for read_csv, astype, merge, groupby): coverage 80% -> 93% overall; per
operation astype 78 -> 92%, groupby 50 -> 93%, merge 90 -> 95%, read_csv 100 -> 93%. **Width cost**: astype 1.3x -> 11x,
groupby 1.3x -> 36x, merge 78x -> 97x, read_csv 7.3x -> 1.9x. For drop_duplicates, sort_values and concat the normalised score
explodes because Tier 2's own range is very narrow (widths of 2,500x and more): those ranges are not used at run time.

## RAM (target (c))

Policy B unchanged. The only RAM model change is the derived concat Tier 1 for categoricals with differing categories
(probe at 362-831 MiB, OS peak). On dev (policy B applied to the stored F): above_high 0% at both tiers before and after, per
point and per configuration; coverage unchanged (97% / 99%); width unchanged except concat Tier 1 1.00 -> 0.85 (better) and
merge Tier 1 5.13 -> 5.23 (one borderline point whose Tier 1 statistics now finished inside the budget; not a model change).
concat Tier 1 expected: median error 7.7% -> 5.8%, p90 15.7% -> 10.7%, bias 0.92 -> 1.06. The 10M-row category-heavy point
stays at Tier 0 (the category comparison over 2 x 500k categories x 3 columns exceeds the 250 ms statistics budget).
