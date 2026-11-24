# v4 static coverage CEILING, real DEV notebooks

75 code cells with a detected operation; **21 (28.0%)** have every operation covered under the adopted v4 models/forms (optimistic static upper bound). Dev target (run-time share): >= 55% -> **BELOW the target even at the ceiling**.

| operation | calls | status |
|---|---|---|
| `value_counts` | 15 | not covered |
| `copy` | 13 | covered |
| `fillna` | 10 | covered |
| `duplicated` | 9 | not covered |
| `to_csv` | 9 | not covered |
| `copy` | 7 | not covered |
| `describe` | 7 | not covered |
| `astype` | 6 | covered |
| `groupby` | 6 | covered |
| `map` | 6 | not covered |
| `reset_index` | 6 | not covered |
| `sample` | 6 | not covered |
| `apply` | 5 | not covered |
| `pandas.concat` | 5 | covered |
| `sort_values` | 5 | covered |
| `astype` | 4 | not covered |
| `dropna` | 4 | covered |
| `pandas.read_csv` | 4 | covered |
| `to_numpy` | 4 | not covered |
| `drop_duplicates` | 3 | covered |
| `join` | 3 | not covered |
| `numpy.linspace` | 3 | not covered |
| `corr` | 1 | not covered |
| `numpy.array` | 1 | not covered |
| `numpy.empty` | 1 | not covered |
| `numpy.zeros` | 1 | not covered |
| `pandas.get_dummies` | 1 | not covered |
| `ravel` | 1 | not covered |
| `sort_index` | 1 | not covered |
