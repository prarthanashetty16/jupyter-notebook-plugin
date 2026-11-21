# Phase 8a results (real notebooks; evaluation only, nothing tuned)

## Cells by group

| group | cells |
|---|---|
| no operation | 10 |
| skipped | 2 |
| validated-model, valid actual | 2 |
| detection-only | 1 |

## Accuracy on valid points (primary: Pipeline(tier=2) with the controller)

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 2 | 0.56 | 43.6% | 44.4% | 100.0% | 0.0% | 0 | 0.0% | 11.27 |

| metric | n | within_one | same | err_med | err_p90 | bias | coverage |
|---|---|---|---|---|---|---|---|
| time | 1 | 100.0% | 100.0% | 2.9% | 2.9% | 1.03 | 100.0% |

* **RAM verdict (above_high <= 3%):** INCONCLUSIVE (2 valid points < 30)
* **Time verdict (within-one >= 95%):** INCONCLUSIVE (1 valid points < 30)

Secondary (Tier 0, what `%load_ext nexus` uses today; no verdict):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM tier 0 | 2 | 0.56 | 43.6% | 44.4% | 100.0% | 0.0% | 0 | 0.0% | 11.27 |
| time tier 0 | 1 | 1.03 | 2.9% | 2.9% | 100.0% | None | None | None | None |

Fully covered subset (every detected operation has an estimate):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 2 | 0.56 | 43.6% | 44.4% | 100.0% | 0.0% | 0 | 0.0% | 11.27 |
| time | 1 | 1.03 | 2.9% | 2.9% | 100.0% | None | None | None | None |

RAM per dominant operation:

| op | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| pandas.read_csv | 2 | 0.56 | 43.6% | 44.4% | 100.0% | 0.0% | 0 | 0.0% | 11.27 |

Worst RAM predictions (operation and input shapes only):

| notebook | cell | ops | expected MiB | actual MiB | inputs |
|---|---|---|---|---|---|
| amazon_ml_solution | c30b211c70a7 | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 2,121 | 3,828 |  |
| amazon_solution_old | 0cd64f795edd | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 2,145 | 3,739 |  |

## Risk engine

Classes as the engine saw them (live free RAM), cells with a detected operation:

| class | cells |
|---|---|
| WARN | 2 |
| UNKNOWN | 1 |

UNKNOWN reasons:

| reason | cells |
|---|---|
| no estimate for this cell | 1 |

Simulated limits on valid RAM points:

| limit | pairs | positives | recall | false_alarm | high_n | high_precision | missed |
|---|---|---|---|---|---|---|---|
| 1024 MiB | 2 | 2 | 100.0% | - | 2 | 100.0% | 0 |
| 2048 MiB | 2 | 2 | 100.0% | - | 2 | 100.0% | 0 |
| free RAM at start | 2 | 0 | - | 100.0% | 0 | - | 0 |

* claim limits (>= 20 positives): none: too few positives, no claim

Missed overruns (positive, not alerted):

(none)

## Suggestions (never executed)

Cells with an estimate: 2; with at least one suggestion shown: 0.

(none)
