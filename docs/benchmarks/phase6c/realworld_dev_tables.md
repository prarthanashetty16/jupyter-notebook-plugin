# Phase 8a results (real notebooks; evaluation only, nothing tuned)

## Cells by group

| group | cells |
|---|---|
| no operation | 41 |
| detection-only | 34 |
| failed | 20 |
| validated-model, valid actual | 9 |
| skipped | 5 |

## Accuracy on valid points (primary: Pipeline(tier=2) with the controller)

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 8 | 0.94 | 22.5% | 62.5% | 87.5% | 12.5% | 1 | 0.0% | 2.65 |

| metric | n | within_one | same | err_med | err_p90 | bias | coverage |
|---|---|---|---|---|---|---|---|
| time | 9 | 88.9% | 77.8% | 21.1% | 91.9% | 0.79 | 77.8% |

* **RAM verdict (above_high <= 3%):** INCONCLUSIVE (8 valid points < 30)
* **Time verdict (within-one >= 95%):** INCONCLUSIVE (9 valid points < 30)

Secondary (Tier 0, what `%load_ext nexus` uses today; no verdict):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM tier 0 | 8 | 0.72 | 32.3% | 62.5% | 87.5% | 12.5% | 1 | 0.0% | 3.42 |
| time tier 0 | 9 | 0.72 | 27.5% | 96.4% | 44.4% | None | None | None | None |

Fully covered subset (every detected operation has an estimate):

| metric | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| RAM | 6 | 0.94 | 22.5% | 46.6% | 83.3% | 16.7% | 1 | 0.0% | 2.81 |
| time | 7 | 0.79 | 20.8% | 55.1% | 85.7% | None | None | None | None |

RAM per dominant operation:

| op | n | bias | err_med | err_p90 | coverage | above_high | above_high_n | below_low | width |
|---|---|---|---|---|---|---|---|---|---|
| groupby | 1 | 1.07 | 7.0% | 7.0% | 100.0% | 0.0% | 0 | 0.0% | 0.81 |
| merge | 1 | 0.36 | 64.0% | 64.0% | 100.0% | 0.0% | 0 | 0.0% | 3.53 |
| pandas.concat | 1 | 0.38 | 61.9% | 61.9% | 0.0% | 100.0% | 1 | 0.0% | 1.54 |
| pandas.read_csv | 5 | 0.97 | 18.0% | 29.6% | 100.0% | 0.0% | 0 | 0.0% | 3.07 |

Worst RAM predictions (operation and input shapes only):

| notebook | cell | ops | expected MiB | actual MiB | inputs |
|---|---|---|---|---|---|
| amazon_solution_old | c6d435f215a1 | set_index,set_index,merge,apply | 52 | 145 | DataFrame [1108633, 6] {'str': 6}; DataFrame [1163953, 6] {'str': 6}; DataFrame [458940, 7] {'str': 4, 'int64': 2, 'bool': 1}; DataFrame [485451, 6] {'str': 6} |
| amazon_ml_solution | 199b7bcc3606 | groupby,pandas.concat | 156 | 409 | DataFrame [1163953, 9] {'str': 4, 'string': 5}; DataFrame [1108633, 9] {'str': 4, 'string': 5}; DataFrame [1163953, 9] {'str': 4, 'string': 5} |
| amazon_ml_solution | c30b211c70a7 | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 637 | 873 |  |
| amazon_solution_old | 2445178c6d22 | pandas.read_csv | 449 | 342 |  |
| amazon_solution_old | 14f2c58aa325 | pandas.read_csv | 430 | 365 |  |
| amazon_solution_old | 0cd64f795edd | pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv,pandas.read_csv | 1,486 | 1,641 |  |
| amazon_ml_solution | 5285621cd383 | groupby,reset_index,groupby,reset_index,merge,merge,fillna,astype,fillna,astype | 154 | 144 | DataFrame [1108633, 6] {'str': 4, 'string': 2}; DataFrame [1163953, 6] {'str': 4, 'string': 2}; DataFrame [485451, 6] {'str': 4, 'string': 2} |
| amazon_solution_old | f95ee46fd2b9 | pandas.read_csv | 188 | 193 |  |

## Risk engine

Classes as the engine saw them (live free RAM), cells with a detected operation:

| class | cells |
|---|---|
| OK | 7 |
| UNKNOWN | 49 |

UNKNOWN reasons:

| reason | cells |
|---|---|
| no estimate for this cell | 46 |
| 3 operation(s) of this cell have no estimate; the rest fits | 2 |
| 8 operation(s) of this cell have no estimate; the rest fits | 1 |

Simulated limits on valid RAM points:

| limit | pairs | positives | recall | false_alarm | high_n | high_precision | missed |
|---|---|---|---|---|---|---|---|
| 1024 MiB | 8 | 8 | 100.0% | - | 6 | 100.0% | 0 |
| 2048 MiB | 8 | 4 | 100.0% | 75.0% | 4 | 100.0% | 0 |
| free RAM at start | 8 | 0 | - | 12.5% | 0 | - | 0 |

* claim limits (>= 20 positives): none: too few positives, no claim

Missed overruns (positive, not alerted):

(none)

## Suggestions (never executed)

Cells with an estimate: 10; with at least one suggestion shown: 1.

| rule | semantics | shown |
|---|---|---|
| delete_unreferenced | changes_results | 1 |
