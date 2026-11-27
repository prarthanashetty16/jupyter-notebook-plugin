# Evaluation and evidence

This document reports measured outcomes, not a product guarantee. Every result is labeled **DEV**, **HELD-OUT**, or
**INCONCLUSIVE**. A pass on a small or development-only set is not described as general validation.

## Methodology

### Measurement instrument

Peak RAM is the incremental OS-tracked resident-memory peak in a spawned child, after setup and before teardown.
`nexus.measure` uses Windows' peak working set and Linux's `VmHWM`; `psutil` polling is a watchdog and cross-check, not
the reported peak. macOS measurement is unsupported. Known allocations in the frozen instrument validation are within
10% of target. On Windows, the OS peak counter cannot be reset, so a cell that does not exceed the setup peak is
censored instead of being assigned a zero delta.

Synthetic notebook harness checks exercised valid peaks, censoring, failures, timeouts, memory caps, and omission of
cell text from result records. These are harness checks, not model-accuracy results.

Sources: [frozen manifest](benchmarks/frozen-manifest.md), [Phase 8a harness validation](benchmarks/phase8a/harness_validation.md),
and [Phase 8a report](benchmarks/phase8a/report.md).

### Splits, preregistration, and freeze

- **DEV** data can support derivation, model selection, and debugging. It does not become held-out evidence by being
  scored after the fact.
- **HELD-OUT** groups are run once against the tagged model stack. The evaluator checks the freeze manifest and logs
  protected-split access. The v4 model tag is `models-frozen-v4`.
- Phase 6 time calibration used leave-one-configuration-out (LOCO) predictions on development data. LOCO is an
  internal calibration check, not an independent held-out set.
- The Phase 8b protocol requires paired v3/v4 runs on identical notebooks, separate checkouts and result roots. It is
  pending owner collection fields; no fresh Phase 8b notebook was opened or run for this documentation.
- `val-v5` and `test-v2` remain sealed and unread. No claim in this document uses their values.

Sources: [frozen manifest](benchmarks/frozen-manifest.md), [Phase 6 results](benchmarks/phase6/phase6_dev.md),
[Phase 8 preregistration](benchmarks/phase8-preregistration.md), and
[Phase 8b preregistration](benchmarks/phase8b-preregistration.md).

## Phase 1-4: foundation and single-operation models

The early phases established the AST analyzer, registry, OS-peak benchmark harness, and Tier 0/Tier 1 operation models.
The benchmark suite is primarily synthetic; those results should not be read as broad real-notebook validation. Phase 6
later selected and calibrated the time terms on DEV configurations.

### Phase 6 time model selection — DEV, LOCO

`D+m` was selected over the frozen baseline by the preregistered median-log-error rule. At Tier 1, all 211 valid time
points were within one order-of-magnitude bucket, but only 181/211 were in the same bucket. The calibrated central
estimate still had 25% median relative error and 89% p90 relative error.

| Candidate, Tier 1 | Valid points | Median relative error | P90 relative error | Same bucket | Within one bucket |
|---|---:|---:|---:|---:|---:|
| Frozen F, mains profile | 211 | 52% | 146% | 153/211 (73%) | 211/211 (100%) |
| Selected D+m, LOCO | 211 | 25% | 89% | 181/211 (86%) | 211/211 (100%) |

Source: [Phase 6 dev evaluation](benchmarks/phase6/phase6_dev.md).

### Phase 6 time ranges — DEV, LOCO

The per-operation target was 88-95% range coverage. Some operations met it; others did not. The documented fallback
keeps uncalibrated ranges for the operations below target. The percentages are development results, not held-out
coverage.

| Operation, Tier 1 | Coverage | Status in report |
|---|---:|---|
| `astype` | 95% | Met |
| `drop_duplicates` | 95% | Met |
| `groupby` | 87% | Not met |
| `merge` | 92% | Met |
| `pandas.concat` | 75% | Not met |
| `pandas.read_csv` | 82% | Not met |
| `sort_values` | 77% | Not met |
| Overall | 89% | Aggregate only |

Source: [Phase 6 results](benchmarks/phase6/README.md) and its full
[dev evaluation](benchmarks/phase6/phase6_dev.md).

### User-facing time buckets

NEXUS presents order-of-magnitude time buckets because point estimates are much less reliable than repeatability. The
selected Phase 6 Tier 1 candidate was within one bucket on every scored DEV point, but only 86% landed in the exact
bucket. The one Phase 8a real-notebook time point is not evidence of accuracy: after correcting the profile, it was
within one bucket, but its result remains **INCONCLUSIVE** because the sample is below 30.

Source: [Phase 6 results](benchmarks/phase6/phase6_dev.md) and
[Phase 8a report](benchmarks/phase8a/report.md).

### Phase 5 risk engine and suggestions

The initial policy-B risk replay had a pooled R2 false-alarm rate within its bar, but failed the per-operation bar for
merge and read_csv. The later C3 risk-v2 selection passed R1-R3 on DEV; it has not been confirmed on the unopened
val-v5 set.

| Risk check | Initial policy B, DEV | C3 selected policy, DEV |
|---|---:|---:|
| R1 recall | 100% (1119/1119), met | 100% (1119/1119), met |
| R2 pooled false alarms | 25.0%, met | 17.1%, met |
| R2 operation false alarms | **FAILED:** merge 58.8%, read_csv 78.0% | merge 9.4%, read_csv 39.0%, met |
| R3 HIGH_RISK precision | 98.6%, met | 98.7%, met |

Source: [policy-B risk re-evaluation](benchmarks/phase5-risk-policyB/README.md) and
[C3 risk-v2 development evaluation](benchmarks/phase7b/README.md).

Suggestion results below are **HELD-OUT** configurations for the Phase 5 suggestion rules. The labels “preserving” and
“changes results” describe semantics; suggestions are never executed by NEXUS.

| Registered suggestion check | Outcome | Evidence |
|---|---|---|
| S1: no `preserving` suggestion changed output | PASS | 0 counterexamples |
| S2: no shown suggestion increased measured RAM by more than 10% | PASS | 0/12 shown |
| S3: predicted vs. measured saving error | **FAILED** | n=9; p90 absolute error 39.0 percentage points; bar <=35 |
| S4: shown suggestions met the minimum measured saving | **FAILED** | 9/12 (75.0%); bar >=80% |

Source: [held-out suggestion report](benchmarks/phase5-suggestions-heldout/suggestions_heldout.md).
The `select_columns` suggestion rule is off by default because its measured savings were over-predicted in the
development work; it remains available only by explicit opt-in.

## Phase 6c: cell-level peak model

The statement-aware cell model accounts for retained outputs and temporaries. On the Phase 6c multi-statement
HELD-OUT group, it had zero above-high cases, but its coverage was 63.6% and the older aggregation covered more actuals.
The small group does not justify a general safety guarantee.

| Model, HELD-OUT | Cells | Configurations | Coverage | Above-high | Median error |
|---|---:|---:|---:|---:|---:|
| Statement-aware cell model | 22 | 11 | 63.6% | 0/22 (0%) | 17.2% |
| Older v1 aggregation | 22 | 11 | 86.4% | 0/22 (0%) | 6.0% |

Source: [Phase 6c multi-statement HELD-OUT report](benchmarks/phase6c/multicell_heldout.md).

The Phase 6c real-notebook subsample check was **DEV / information-only**: 8 valid RAM points had 1 above-high case,
and 9 time points were within one bucket 8/9 times. It was below the minimum evidence threshold and had no verdict.

Source: [Phase 6c results](benchmarks/phase6c/README.md) and
[real-notebook DEV table](benchmarks/phase6c/realworld_dev.md).

## Phase 7: v3 changes and held-out multi-statement failures

The v3 multi-statement held-out groups both failed the preregistered above-high bars. The uncovered-operation safety
rule passed for the v3 group where it was scored. A later risk C3 selection passed its DEV R1-R3 checks, but there is no
held-out risk result because val-v5 was reassigned to v4 before access and remains unread.

| Group, HELD-OUT | Measured cells | Configurations | Above-high cells | Above-high configurations | Verdict |
|---|---:|---:|---:|---:|---|
| v2 | 28 | 14 | 6/28 (21.4%) | 3/14 (21.4%) | **FAILED** both bars |
| v3 | 61 | 31 | 9/61 (14.8%) | 5/31 (16.1%) | **FAILED** both bars |

Source: [v2 held-out report](benchmarks/phase7e/multicell_v2_heldout.md) and
[v3 held-out report](benchmarks/phase7e/multicell_v3_heldout.md).

The Phase 7 deterministic Tier 1 gate also **FAILED**: it exceeded the preregistered deadline-firing bar and was
reverted. The v3 DEV cell criterion for zero above-high on the expanded cell group **FAILED** (2/66 cells; both
`copy_fillna/mixed`). The C3 risk-v2 candidate was selected on DEV and passed its DEV criteria, not held-out validation.

Sources: [Phase 7b DEV report](benchmarks/phase7b/README.md),
[risk C3 report](benchmarks/phase7b/risk_v3/risk_dev.md), and
[Phase 8 freeze limitations](benchmarks/frozen-manifest.md).

## Phase 8: frozen v4 results

### Single-operation RAM and calibrated highs — DEV

The v4 regression comparison used identical stored actuals; no measurements were rerun. Tier 1 single-operation RAM
results are summarized below.

| Tier 1 DEV metric | Points | Median error | P90 error | Bias (expected/actual) | Range coverage | Above-high | Below-low |
|---|---:|---:|---:|---:|---:|---:|---:|
| All supported operations | 109 | 2% | 17% | 1.01 | 99% | 0% | 1% |

Source: [final v4 single-operation regression](benchmarks/phase8/final_regression/before_after.md).

The separate high-bound calibration used 524 DEV points across 239 configurations. In-sample and LOCO results were
0/524 points and 0/239 configurations above high, with 93.9% range coverage. The preregistered LOCO bar was met.
W(a) was 1.000 and met its bar; W(b) had no eligible new-coverage points and is **INCONCLUSIVE**. These are calibrated
DEV results, not a fresh held-out accuracy result.

Source: [final v4 calibration](benchmarks/phase8/calibration_final_v4.md).

### v4 multi-statement HELD-OUT results

The report records 64 cells run and measured peaks for 54. On the fully covered subset, 22 cells across 11
configurations had zero above-high cases. For zero events, the one-sided exact 95% upper bounds are approximately
12.7% for cells and 23.8% for configurations; the observed zero is therefore **consistent with**, not proof of, a
population rate below those limits.

| v4 HELD-OUT subset | Count | Result |
|---|---:|---|
| Fully covered cells | 22 cells / 11 configurations | 0 above high; one-sided 95% upper bounds about 12.7% / 23.8% |
| Partial cells with valid actuals scored | 32 | 0 lower-bound violations; 0 risk violations |
| Specifically listed as censored | 6 | 4 `set_index_ops` (textwide/indexheavy) and 2 `apply_ufunc` (textwide); unresolved |
| `deletes_v4` cells killed before measurement | 4 | Untested; the report does not identify the kill as an execution error |

**Count discrepancy:** the request summary referred to 8 censored cells and 4 errored `deletes_v4` cells. The source
report lists 6 specifically censored cells and 4 `deletes_v4` cells killed before measurement. This document preserves
those categories rather than inferring two additional censored cells or labelling the kills as execution errors.

The fully covered new model had 81.8% interval coverage versus 100% for v1 combine. `chain_v4` over-predicted
(bias 1.55, coverage 0%). The load/fill templates also over-predicted by about 16% (`load_fillna_text` bias 1.17;
`load_then_merge_left` bias 1.16). Partial lower bounds can be very loose and are not upper bounds for the whole cell.

Source: [v4 multi-statement HELD-OUT report](benchmarks/phase8/multicell_v4_heldout.md).

### Phase 8 model items and failures — DEV

The following are preregistered item outcomes; **FAILED** entries were not adopted or were only partially adopted.

| Item | Result | Finding | Source |
|---|---|---|---|
| 1a text `fillna` | PASS | The new derivation passed the probe bar. | [DEV report](benchmarks/phase8/item1a_text_fillna_dev.md) |
| 1b copy then `fillna` | PASS | Probe ratios 1.000-1.020; applicable DEV cells had no above-high result under LOCO. | [DEV report](benchmarks/phase8/item1b_copy_fillna_dev.md) |
| 1c `value_counts` | **FAILED** | Hash-table residency depended on exact keys; the 1M-unique probe was 1.69x the derivation. | [Probe output](benchmarks/phase8/probes/p8_value_counts_diag.out) |
| 1d `copy` receivers | **FAILED overall; partial adoption** | Five receiver forms passed; `head`/`tail` and unmodelled receivers remain no-estimate. | [DEV report](benchmarks/phase8/item1d_copy_receivers_dev.md) |
| `duplicated` | **FAILED** | The dense-key second derivation under-predicted by 1.294x. | [Probe output](benchmarks/phase8/probes/p8_duplicated_b2.out) |
| `dropna` | PASS | The fresh probe variants met the derivation bar. | [Probe output](benchmarks/phase8/probes/p8_dropna.out) |
| `reset_index` | **FAILED** | The derivation was invalid because its formula followed the probe output. | [Probe output](benchmarks/phase8/probes/p8_reset_index.out) |
| `Series.map` | **FAILED** | Dict and NumPy-ufunc variants exceeded the derivation bar. | [Probe output](benchmarks/phase8/probes/p8_map.out) |
| `to_numpy` | **FAILED** | The zero-copy cases did not provide a measurable incremental peak. | [Probe output](benchmarks/phase8/probes/p8_to_numpy.out) |
| Dict/multi-column `astype` | **FAILED** | Same-dtype target columns were over-counted. | [Probe output](benchmarks/phase8/probes/p8_astype_multi.out) |
| `read_csv(parse_dates=...)` | **FAILED** | Date parsing reduced peak RAM and contradicted the additive term. | [Probe output](benchmarks/phase8/probes/p8_read_csv_dates.out) |
| `numpy.zeros` / `numpy.empty` | **FAILED** | Lazy pages did not produce a measurable incremental peak. | [zeros](benchmarks/phase8/probes/p8_numpy_zeros.out); [empty](benchmarks/phase8/probes/p8_numpy_empty.out) |
| Known ndarray `numpy.array(copy=True)` | PASS, scoped | Only the known numeric ndarray form was adopted. | [Probe output](benchmarks/phase8/probes/p8_numpy_array.out) |
| `numpy.linspace` | **FAILED** | The float32 probe used three live arrays, not the derived one. | [Probe output](benchmarks/phase8/probes/p8_numpy_linspace.out) |
| `sample` | **FAILED** | Random-index workspace exceeded the derived peak. | [Probe output](benchmarks/phase8/probes/p8_sample.out) |
| `describe` | **FAILED** | Numeric workspace exceeded the derivation; a text case was censored. | [Probe output](benchmarks/phase8/probes/p8_describe.out) |
| Deferred-operation UNKNOWN behavior | PASS | Unsupported operations remain named no-estimate rather than looking safe. | [Frozen v4 deferrals](benchmarks/frozen-manifest.md) |

### Phase 8 runtime coverage and determinism — DEV

The five internal real-notebook development inputs had runtime coverage of 14/75 operation-bearing cells (18.7%), below
the preregistered 55% target: **FAILED**. The static name/form ceiling was 21/75 (28.0%); it is an optimistic upper
bound, not runtime coverage. Tier selection/deadline determinism also **FAILED**: the original check recorded 79/84
contended and 28/84 idle deadline firings; later information-only runs still exceeded the preregistered bars.

Sources: [frozen v4 limitations](benchmarks/frozen-manifest.md),
[static coverage ceiling](benchmarks/phase8/coverage_ceiling.md), and
[initial contended selection report](benchmarks/phase8/tier1_selection_cores2.md),
[initial idle selection report](benchmarks/phase8/tier1_selection_idle.md), and the
[contended](benchmarks/phase8/tier1_selection_recheck_cores2_1.md),
[contended](benchmarks/phase8/tier1_selection_recheck_cores2_2.md),
[contended](benchmarks/phase8/tier1_selection_recheck_cores2_3.md), and
[idle](benchmarks/phase8/tier1_selection_recheck_idle.md) rechecks.

### Phase 8a real notebooks — HELD-OUT, INCONCLUSIVE

The Phase 8a real-notebook run produced only 2 valid RAM points and 1 valid time point, all below the minimum of 30.
Both accuracy decisions are **INCONCLUSIVE**, not passes. Its sample was 3 notebooks from one author and one dataset;
the run stopped during loading under its resource cap. A profile audit corrected the one time point; it remained
within one bucket but still INCONCLUSIVE.

| Metric | Valid points | Observed result | Verdict |
|---|---:|---|---|
| RAM above-high | 2 | 0 above high; bias 0.56; median error 44% | **INCONCLUSIVE** |
| Time within-one | 1 | 1/1; corrected expected 7.49 s vs 8.45 s actual | **INCONCLUSIVE** |

Sources: [Phase 8a report](benchmarks/phase8a/report.md),
[detailed tables](benchmarks/phase8a/report_tables.md), and
[profile audit](benchmarks/phase6d/profile_audit.md).

The later five-notebook internal Phase 8 DEV run reached all 75 operation-bearing cells but covered only 14; the
separate static ceiling was 21/75. These are **DEV** findings and are not a replacement for the Phase 8a result.

Sources: [frozen v4 limitations](benchmarks/frozen-manifest.md),
[Phase 8 static ceiling](benchmarks/phase8/coverage_ceiling.md), and
[Phase 8 progress summary](PROGRESS.md).

## Negative results and limits

| Phase / check | Status | What the evidence says |
|---|---|---|
| Phase 5 risk R2, initial policy B | **FAILED per operation** | Merge 58.8%; read_csv 78.0%; later C3 passed on DEV only. |
| Phase 5 suggestions S3 | **FAILED** | p90 saving error 39.0 percentage points, above 35. |
| Phase 5 suggestions S4 | **FAILED** | 75.0% met the minimum saving, below 80%. |
| Phase 6 per-operation time ranges | **NOT MET for some operations** | Tier 1 groupby 87%, concat 75%, read_csv 82%, sort_values 77%; see range table. |
| Phase 6 learned residual at Tier 1 | **FAILED adoption bar** | 7.2% median-log-error improvement versus the required 10%; not included. |
| Phase 7 deterministic gate | **FAILED** | Deadline firings exceeded the preregistered limit; the gate was reverted. |
| Phase 7 multicell v2 | **FAILED** | 21.4% above-high cells and 3/14 configurations. |
| Phase 7 multicell v3 | **FAILED** | 14.8% above-high cells and 5/31 configurations. |
| Phase 8 v4 item failures | **FAILED where marked above** | Failed derivations were deferred; they were not tuned into the frozen model. |
| Phase 8 runtime coverage | **FAILED** | 14/75 (18.7%) against the 55% target. |
| Phase 8 determinism | **FAILED** | Deadline-firing thresholds were exceeded. |
| Phase 8a RAM and time | **INCONCLUSIVE** | 2 RAM and 1 time point are below the 30-point minimum. |
| Phase 8b paired real notebooks | **NOT RUN** | Owner collection fields remain; no fresh Phase 8b notebooks were opened or run. |

Source references for this table are the linked phase reports above, including the
[Phase 5 risk report](benchmarks/phase5-risk-policyB/README.md),
[suggestion report](benchmarks/phase5-suggestions-heldout/suggestions_heldout.md),
[Phase 6 evaluation](benchmarks/phase6/phase6_dev.md),
[Phase 7 held-out reports](benchmarks/phase7e/), and
[Phase 8 preregistrations and reports](benchmarks/phase8/).

The primary limitations are narrow operation coverage, machine-dependent timing, frequent Tier 1 deadline fallback on
large inputs, partial-cell lower bounds without full-cell highs, a single developer machine, and mostly synthetic data.
The next evidence step is the paired Phase 8b protocol only after its owner fields and digest-pinned manifest are
completed and committed.
