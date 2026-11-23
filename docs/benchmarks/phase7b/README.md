# Phase 7b: the v3 scope implemented and evaluated on DEV (not yet frozen)

**Every number here is DEV.** No held-out value was read. test-v2, val-v5 (Mode B) and the v2 multi-statement held-out
part are sealed. **`models-frozen-v3` is NOT tagged**: you asked to read these results first. The freeze steps and the
held-out commands are at the end. Pre-registration: `../phase7-preregistration.md`; diagnosis: `../phase7a/README.md`.

**Power.** The probes, the first dev re-prediction and the first determinism check ran on mains. You accepted battery for
the dev-only steps. Those steps are the final re-prediction rows 124-646, the final multi-statement evaluation and
the final determinism check (its last 39 rows were on mains). They ran with `--allow-battery`, and each row or report
records `battery (user-accepted)` with the raw psutil / WMI readings. **Timing figures from those runs are
battery-throttled and are not usable for calibration or any timing claim.** RAM figures do not depend on the power state.
The Amazon subsample run was on mains.

## Commits (one per item; hunks of shared files staged per item)

| commit | item | files |
|---|---|---|
| `e7578a8` | second-attempt derivations + bar, before probing | probe script |
| `258af6d` | harness: child timeout, faulthandler, crash = harness event | `benchmarks/childproc.py`, multicell runner |
| `e5ed666` | (1) read_csv reader paths + arguments | `models/read_csv.py`, `stats.py` (na_values), CI mechanism test |
| `2874253` | (2) non-load bias: merge output, consolidation check, rebinding release | `models/_output.py`, `models/merge.py`, `state.py`, `cellpeak.py` |
| `949d4cf` | (3) cell-seeded sampler + deterministic gate | `stats.py`, `failsafe.py`, `pipeline.py`, `render.py` |
| `a11a3fc` | (5) names bound earlier in the cell shadow the namespace | `cellframes.py` (new), `pipeline.py` |
| `fc6d3fd` | (5) new models: `apply(np.<ufunc>)`, `set_index` | `models/explode_apply.py`, `models/set_index.py` |
| `0f3d8b5` | (4) risk v2 (C3) + named UNKNOWN | `risk.py`, `pipeline.py`, `benchmarks/risk_eval.py` |
| `f322620` | (3) deterministic gate REVERTED (failure rule) | `stats.py`, `failsafe.py` (= v2 again) |
| `08bf282` | dev-only `--allow-battery` (outside the freeze) | `benchmarks/powerguard.py` + dev tools |

Staging slip: `949d4cf` already passed `dtypes` to `CsvProfile` without the field (added in `a11a3fc`). Between those two
commits, read_csv Tier 1 raised an error and fell back to Tier 0. The commit message records it; history is not rewritten.

## Probe findings (`probes/`; bar: every variant within +-15%, the serial reader must be in range)

| change | result | adopted |
|---|---|---|
| read_csv parallel `F + 2V` (6, 2 workers; 1-CPU affinity, which pandas ignores on Windows; float32 scalar) | 1.002-1.005 | yes |
| read_csv `dtype` dict `F + V + W` | 1.008 | yes |
| read_csv serial range (`usecols`, `nrows`, `max_threads=1`) | in range, 0.98-1.03 (run 2, after the serial Tier 0 low was derived; run 1: Tier 1 rejected by the guard) | yes |
| reader path = the path pandas takes (sizes either side of 5 MiB, 8 argument sets, default / 1 / 2 threads) | 48 / 48 (CI mechanism test) | yes |
| merge output term (elided, 20% unmatched, how=left, duplicated keys, outer, sort=True) | 0.999-1.003 (run 2; sort=True was 4.0 in run 1: never elided now) | yes |
| copy (consolidated + str, fragmented, fragmented + str) | 1.000 | yes |
| rebinding release (rebinding/mixed@4M cell) | 1.002 (v2: 1.12) | yes |
| `apply(np.log)` float32, `apply(np.exp)` int64 | 1.000, 1.001 | yes |
| `set_index` SECOND ATTEMPT (bar fixed in `e7578a8`) | 0.2-0.4 MiB vs derived 0 on 12M rows: pass | yes |
| `value_counts` SECOND ATTEMPT | 0.704, **0.344, 0.549**, 1.067, 1.131 | **no** |
| `Series.explode` | **1.341, 1.274, 1.605**, 1.104 | **no** |
| native child crash (0xC0000005, Phase 7a) | 0 of 50 runs (25 same condition, 25 control) | not reproduced; recorded as a harness event if it recurs |

## Dev results

### Single operations (`ram_accuracy_dev.md`, `regression_dev.md`; 646 rows, stored actuals)

RAM above_high **0 for every operation and tier, v2 and v3**. Changes:
* read_csv Tier 1: bias 1.22 -> **1.09**, median error 22% -> **13%** (the files with text columns keep the v2 formula);
* drop_duplicates / concat Tier 1: median error 13 -> 12% / 5 -> 6%;
* everything else is unchanged to the reported precision.

| regression (pre-registered B) | decision |
|---|---|
| read_csv Tier 1 RAM width 3.04 -> 3.48 | **keep**: the expected moved down to the probed `F + 2V`, while the displayed high is policy B's Tier 0 high (unchanged), so the ratio grows. Risk WARN uses the own Tier 1 high (C3) |
| astype / merge / groupby Tier 1 width (4th decimal), groupby Tier 1 time p90 1.79 -> 1.89 | **keep**: the cell-seeded sampler draws other rows (sampling noise) |

### Multi-statement cells, v1 group, all 66 cells DEV (`multicell_v3_dev.md`)

| | bias | median error | p90 | coverage | above_high cells | configurations above high | width |
|---|---|---|---|---|---|---|---|
| v3 | **1.00** | **1.1%** | 14.6% | **89.4%** | **2 of 66 (3.0%)** | **1 of 33** | 3.30 |
| v2 | 1.15 | 14.6% | 102.1% | 63.6% | 0 | 0 | 2.92 |

Every load template is at 0.99-1.01 (v2: 1.17-3.12). The non-load templates are rebinding 0.99, chain 0.97, copy_fillna 1.05, and
astype_groupby 1.12 (small sizes; exact at 10M rows in probe 1b).

* **Item (2) dev criterion "above_high still 0 of the cells": FAILED.** Both cells are `copy_fillna/mixed` (1M: 88 vs 65
  MiB; 2M: 176 vs 130). Each contains `df.fillna(0)` on pandas-3 `str` columns, which is uncovered. v2's `copy`
  over-prediction (366 vs 214 MiB) happened to cover the uncovered `fillna`; with `copy` now exact, the cell's high covers only
  the estimated operations. The risk engine reports these cells UNKNOWN (never OK). **Your decision: freeze with this
  criterion reported as FAILED, no amendment.**
* On the per-cell 3% and per-configuration 3% bars of the held-out criteria, these dev figures would be 3.03% and 3.03%.
  On dev, that is just over both bars.

### Risk (R1-R4, `risk_v3/`, `risk_v2_stored/`)

| | R1 recall | R2 pooled | merge | read_csv | R3 | R4 UNKNOWN pairs |
|---|---|---|---|---|---|---|
| **v3 (C3)** | 100% (1119 / 1119) | **17.1%** | **9.4%** | **39.0%** | 98.7% | 0 |
| v2 (stored) | 100% | 25.0% | 58.8% | 78.0% | 98.6% | 0 |

R2 PASSES on dev with v3 (it failed with v2). Pre-check (`c3_precheck.out`): the three val-v3/v4 merge points whose actual
exceeded their own Tier 1 high are still flagged HIGH_RISK at every positive limit (worst own high / actual 0.92 against the
0.85 WARN margin). When Tier 1 falls back, C3 keeps Tier 0's high (unit test; no dev fallback point exists).

### Determinism (`determinism_*.md`; 30 dev points up to 10M rows, 10 fresh-process repeats)

* **Item (3) determinism: NOT achieved (pre-registered failure rule applied).** With the deterministic gate (mains run),
  the hard deadline fired after the gate had admitted the statistics on 12 of 29 2-core inputs (41% > 10%). The gate was
  reverted to v2's adaptive one (`f322620`); the cell-seeded sampler stayed.
* **Final code (findings, battery-throttled timing):**
  * 16 CPUs: no Tier 1 / Tier 0 flips (0 of 28). Same-tier differences on 2 points: drop_duplicates strings 10M (844-1049
    MiB, ~22%; the adaptive sample size varies) and groupby 10M (0.05%).
  * 2 contended CPUs: 12 of 28 points flip between Tier 1 and Tier 0, and 1 point has a same-tier spread (groupby 10M, 0.05%).
  * 20 / 20 runs ended `memory_limit` (the prediction process of two 10M-row points above the runner's cap: harness events,
    not scored).

### Amazon notebooks, 22% subsamples (DEV; `realworld_dev_tables.md`, `static_coverage_*.out`)

* The runs stopped on the watchdog earlier than in Phase 6c (cells 11 and 71), because less RAM was free: the cap was 2.18 / 2.48
  GiB vs 3.76 / 3.10 GiB. This is the environment, not a model change.
* RAM, 7 valid points: bias 0.99, median error 18.3%, 0 above high. Time, 8 valid points: within-one 87.5%. Fewer than 30
  points: no verdict.
* Risk: 42 cells with a detected operation: 5 OK, 1 WARN, 36 UNKNOWN. 34 of the UNKNOWN cells say "no estimate for this
  cell"; 2 name the operation.
* **Static coverage** (cells with an operation whose every detected operation has a matching model, same 575 code
  cells): **v3 45.9% vs v2 31.7%**. This is an UPPER bound and it overstates v3: models match by operation name, so the 79
  `apply` cells count as matched although v3 estimates only `apply(np.<ufunc>)`, and the 67 `set_index` cells count although
  only single numeric keys are estimated. The Phase 8b pre-registration should use a run-time measure or a static check that
  includes the arguments.

## What was derived, and what stays uncovered

* **Derived and adopted:**
  * read_csv reader paths (parallel, series wrap, serial range, unknown range) and Tier 1 for usecols / nrows / numeric
    dtype / na_values;
  * the merge output term (elision, sort=True);
  * the copy consolidation check;
  * conservative rebinding release;
  * frames created in the cell (shapes / dtypes, Tier 0 only);
  * `apply(np.<ufunc>)`;
  * `set_index` (one numeric key);
  * risk C3 + named UNKNOWN;
  * the cell-seeded sampler.
* **Not adopted** (probe or rule failed):
  * the deterministic statistics gate;
  * `Series.explode`;
  * `value_counts`.
* **Uncovered:**
  * value_counts, explode (Series and DataFrame), apply with Python functions, set_index with text / multiple keys / append;
  * fillna on text columns, parse_dates, text columns on the parallel read_csv path (v2 term);
  * operations on merge / groupby / drop_duplicates results created in the cell;
  * column statistics carried between statements.

## Freeze (NOT done; after you have read this)

1. Switch the guard to `models-frozen-v3` (`FROZEN_TAG`, `PREVIOUS_TAG = models-frozen-v2`, add `src/nexus/cellframes.py`
   to `FROZEN_PATTERNS`; the new models are under `models/*.py`).
2. Write `docs/benchmarks/frozen-manifest.md` for v3, with v2 moved to `frozen-manifest-v2.md` and v1 kept: changed /
   added / unchanged files with hashes, and what is outside the freeze.
3. Clone the repository with tags into a temporary directory and run `python -m benchmarks.frozen check` there. It must
   show 0 problems.
4. Then tag `models-frozen-v3` on that commit.

The held-out entry points keep their profile, power (no `--allow-battery`) and freeze checks.

## Held-out runs (each ONCE, on the v3 tag; any model change after v3 invalidates their held-out status)

The multi-statement group v2 (15 configurations, 30 cells), on this machine, on mains:

    git checkout models-frozen-v3 && python -m benchmarks.frozen check
    python -m benchmarks.multicell.run run --version 2 --heldout --reason "Phase 7 held-out check of models-frozen-v3"
    python -m benchmarks.multicell.run evaluate --version 2 --heldout --reason "Phase 7 held-out check of models-frozen-v3" --out docs/benchmarks/phase7c

val-v5 (Mode B) on the Linux VM (>= 32 GB, > 1 vCPU; `docs/benchmarks/val-v5-linux-runbook.md`):

    git checkout models-frozen-v3 && python -m benchmarks.frozen check
    pip install -e ".[dev,bench]" && nexus-calibrate-machine --force
    python -m benchmarks plan --suite full --splits val-v5 --mem-limit-gb 24 --max-size 400000000
    nohup python -m benchmarks full --splits val-v5 --tiers 0,1,2 --out benchmarks/results/val-v5 --mem-limit-gb 24 --max-size 400000000 --require-calibrated --no-report > val-v5.log 2>&1 &
    python -m benchmarks evaluate benchmarks/results/val-v5 --val --reason "held-out check of models-frozen-v3"

**Tooling gap to close before that run (outside the freeze):** `evaluate --val` does not yet replay the risk engine. The
pre-registered R1-R3 on val-v5 need the `risk_eval` replay inside `evaluate --val` (logged, values printed only by that call).

The fresh real-notebook run (Phase 8b): first collect the notebooks (`../phase7a/heldout_design.md` (d)), then commit
`docs/benchmarks/phase8b-preregistration.md` before opening any of them, then:

    git checkout models-frozen-v3 && python -m benchmarks.frozen check
    python -m benchmarks.realworld.coverage <folder> --out docs/benchmarks/phase8b/coverage
    python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b/<name> --tier 1
    python -m benchmarks.realworld.evaluate_real benchmarks/results/realworld/phase8b/* --out docs/benchmarks/phase8b/report.md

The held-out above_high results will be reported as "consistent with <= x%" using the one-sided 95% upper bound (decision 6).
For example, 0 of 30 cells is consistent with a true rate up to 9.5%.

**Not done (decision 6, second part): the v2 multi-statement held-out group was NOT enlarged.** `split_v2.json` was
frozen in Phase 7a, before any model change. A larger group created now would be designed after the v3 dev results were
seen. If you want it anyway, it needs a new split version (new salt, new configurations), committed before the tag.

### Known limitations of v3 (as of Phase 7c, before the tag)

* **Determinism is NOT achieved on contended machines.** The deterministic statistics gate failed its pre-registered rule:
  the hard deadline fired after admission on 12 of 29 2-core inputs (41%; the bar is 10%). It was **reverted** to v2's adaptive,
  timed gate; only the cell-seeded sampler stays. On the final code (dev, battery-throttled timing), 2 contended CPUs flip 12 of
  28 inputs between Tier 1 and Tier 0, and 16 CPUs flip 0 of 28. Two inputs still vary within the same tier: drop_duplicates on
  10M rows of strings (844-1049 MiB, ~22%) and groupby on 10M rows (0.05%).
* **Item (2) dev criterion FAILED.** 2 of the 66 v1 multi-statement cells are above the v3 high (copy_fillna/mixed: 88 vs 65 MiB
  and 176 vs 130 MiB), because a `fillna` on text columns has no estimate. That is 3.03% of cells and 1 of 33 configurations.
  The risk engine reports both UNKNOWN, or HIGH_RISK where the actual exceeds the headroom, and never OK
  (`docs/benchmarks/phase7c/uncovered_risk.md`). Frozen with the criterion reported as FAILED (owner's decision).
* **Uncovered operations stay uncovered:**
  * value_counts (second attempt failed), explode (Series and DataFrame), apply with Python functions;
  * set_index with text / several keys / append, fillna on text columns, parse_dates, text columns on the parallel
    read_csv path (v2 term);
  * operations on merge / groupby / drop_duplicates results created in the same cell;
  * no column statistics are carried between statements.

  A cell with any of these is UNKNOWN unless the covered part already warns. Its displayed range covers only the
  estimated operations.
* **The read_csv path depends on the CPUs.** The estimate follows pandas' own reader choice: parallel when the file is >= 5 MiB
  and pandas uses more than one worker (min(cpu_count, 6, affinity / cgroup quota on Linux); Windows and macOS ignore
  affinity), serial otherwise. The same call can therefore get a different estimate on a different machine. A pandas without
  the parallel reader gets a range over both paths.
* **One laptop and synthetic data.** Every probe and dev number comes from one Windows 11 laptop (16 logical CPUs, 16 GiB) and,
  apart from the two Amazon notebooks (dev, 22% subsamples), from synthetic frames. Linux is covered only by the planned val-v5
  VM run.
* **pandas 3.1.1 / numpy 2.5.5 only.** The derivations read pandas 3.1.1 source; other versions are informational in CI (the
  pandas-mechanisms matrix), and no result is claimed for them.
* **The R2 result is a dev selection.** Risk v2 (C3) was chosen on dev by a rule written beforehand. Its dev figures (R2 pooled
  17.1%, merge 9.4%, read_csv 39.0%) are not a validation: the claim stands only if val-v5 confirms it, and a failure there
  is reported as a repeat FAILED.
* **Timing figures of the battery runs** (the final dev re-prediction rows, multi-statement evaluation and determinism check)
  are battery-throttled and not usable for calibration or any timing claim.

### Added in Phase 7c: the enlarged multi-statement group v3 (amendment 1), run ONCE on the v3 tag, on mains

    git checkout models-frozen-v3 && python -m benchmarks.frozen check
    python -m benchmarks.multicell.run run --version 3 --heldout --reason "Phase 7 held-out check of models-frozen-v3 (group v3)"
    python -m benchmarks.multicell.run evaluate --version 3 --heldout --reason "Phase 7 held-out check of models-frozen-v3 (group v3)" --out docs/benchmarks/phase7c

Criteria (pre-registered in amendment 1):
* RAM above_high <= 3% of the 64 cells and <= 3% of the 32 configurations, each reported as "consistent with <= x%" (one-sided
  95% upper bound; for 0 events 4.6% and 8.9%);
* the uncovered-operation rule: no cell with an uncovered operation is OK at a simulated headroom its actual exceeds. The
  report prints MET / FAILED.

Group v2 (15 configurations / 30 cells) is run once as well (commands above). The two groups are reported separately and pooled.
