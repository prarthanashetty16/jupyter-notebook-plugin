# Phase 8a results (real notebooks; evaluation only, nothing tuned)

## Cells by group

| group | cells |
|---|---|
| no operation | 37 |
| detection-only | 31 |
| validated-model, valid actual | 8 |
| failed | 4 |
| skipped | 3 |

## Accuracy on valid points (primary: Pipeline(tier=2) with the controller)

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 7 | 0.99 | 18.3% | 46.1% | 100.0% | 0.0% | 0 | 0.0% | 2.81 |

| metric | n | within_one | same | err_med | err_p90 | bias | coverage |
|---|---|---|---|---|---|---|---|
| time | 8 | 87.5% | 50.0% | 56.4% | 87.5% | 0.44 | 62.5% |

* **RAM verdict (above_high <= 3%):** INCONCLUSIVE (7 valid points < 30)
* **Time verdict (within-one >= 95%):** INCONCLUSIVE (8 valid points < 30)

Secondary (Tier 0, what `%load_ext nexus` uses today; no verdict):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM tier 0 | 7 | 0.73 | 27.0% | 50.7% | 100.0% | 0.0% | 0 | 0.0% | 3.69 |
| time tier 0 | 8 | 0.42 | 57.6% | 98.1% | 0.0% | None | None | None | None |

Fully covered subset (every detected operation has an estimate):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 5 | 0.99 | 18.3% | 31.3% | 100.0% | 0.0% | 0 | 0.0% | 3.06 |
| time | 6 | 0.50 | 49.8% | 61.8% | 83.3% | None | None | None | None |

RAM per dominant operation:

| op | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| groupby | 1 | 1.09 | 9.3% | 9.3% | 100.0% | 0.0% | 0 | 0.0% | 0.83 |
| merge | 1 | 0.36 | 64.0% | 64.0% | 100.0% | 0.0% | 0 | 0.0% | 3.53 |
| pandas.read_csv | 5 | 0.99 | 18.3% | 31.3% | 100.0% | 0.0% | 0 | 0.0% | 3.06 |

Worst RAM predictions (operation and input shapes only):

| notebook | cell | ops | expected MiB | actual MiB | inputs |
|---|---|---|---|---|---|
| amazon_solution_old | c6d435f215a1 | set_index,set_index,merge,apply | 52 | 145 | DataFrame [1108633, 6] {'str': 6}; DataFrame [1163953, 6] {'str': 6}; DataFrame [458940, 7] {'str': 4, 'int64': 2, 'bool': 1}; DataFrame [485451, 6] {'str': 6} |
| amazon_ml_solution | c30b211c70a7 | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 637 | 872 |  |
| amazon_solution_old | 2445178c6d22 | pandas.read_csv | 449 | 335 |  |
| amazon_solution_old | 14f2c58aa325 | pandas.read_csv | 430 | 364 |  |
| amazon_ml_solution | 5285621cd383 | groupby,reset_index,groupby,reset_index,merge,merge,fillna,astype,fillna,astype | 154 | 141 | DataFrame [1108633, 6] {'str': 4, 'string': 2}; DataFrame [1163953, 6] {'str': 4, 'string': 2}; DataFrame [485451, 6] {'str': 4, 'string': 2} |
| amazon_solution_old | 0cd64f795edd | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 1,517 | 1,644 |  |
| amazon_solution_old | f95ee46fd2b9 | pandas.read_csv | 188 | 189 |  |

## Risk engine

Classes as the engine saw them (live free RAM), cells with a detected operation:

| class | cells |
|---|---|
| WARN | 1 |
| UNKNOWN | 36 |
| OK | 5 |

UNKNOWN reasons:

| reason | cells |
|---|---|
| no estimate for this cell | 34 |
| no estimate for `train_s2.groupby(['country', 'name_clean']) | 1 |
| no estimate for `train_s2.set_index('entity_id')`, `train_s3 | 1 |

Simulated limits on valid RAM points:

| limit | pairs | positives | recall | false_alarm | high_n | high_precision | missed |
|---|---|---|---|---|---|---|---|
| 1024 MiB | 7 | 7 | 100.0% | - | 5 | 100.0% | 0 |
| 2048 MiB | 7 | 3 | 100.0% | 75.0% | 3 | 100.0% | 0 |
| free RAM at start | 7 | 0 | - | 28.6% | 0 | - | 0 |

* claim limits (>= 20 positives): none: too few positives, no claim

Missed overruns (positive, not alerted):

(none)

## Suggestions (never executed)

Cells with an estimate: 8; with at least one suggestion shown: 0.

(none)
