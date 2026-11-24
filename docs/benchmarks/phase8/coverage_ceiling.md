# v4 static coverage CEILING, real DEV notebooks

75 code cells with a detected operation; **45 (60.0%)** would have every operation covered if every remaining Should / Easy item lands. Dev target (run-time share): >= 55% -> **the ceiling allows it**.

| operation | calls | status |
|---|---|---|
| `value_counts` | 15 | not covered |
| `copy` | 13 | covered |
| `astype` | 10 | covered |
| `fillna` | 10 | covered |
| `duplicated` | 9 | covered |
| `to_csv` | 9 | not covered |
| `copy` | 7 | not covered |
| `describe` | 7 | covered |
| `groupby` | 6 | covered |
| `map` | 6 | covered (optimistic: a name) |
| `reset_index` | 6 | covered |
| `sample` | 6 | covered |
| `apply` | 5 | not covered |
| `pandas.concat` | 5 | covered |
| `sort_values` | 5 | covered |
| `dropna` | 4 | covered |
| `pandas.read_csv` | 4 | covered |
| `to_numpy` | 4 | covered |
| `drop_duplicates` | 3 | covered |
| `join` | 3 | not covered |
| `numpy.linspace` | 3 | covered |
| `corr` | 1 | not covered |
| `numpy.array` | 1 | not covered |
| `numpy.empty` | 1 | covered |
| `numpy.zeros` | 1 | covered |
| `pandas.get_dummies` | 1 | not covered |
| `ravel` | 1 | not covered |
| `sort_index` | 1 | not covered |

**`map` arguments resolved statically:** all 6 `map(name)` calls are in `notebook2.ipynb`, and each name (`rep`, `r`) is
bound to a dict literal in that notebook, so they take the dict-mapper path (a Should item), not a Python function.
Counting them as NOT covered would give 39 / 75 = 52.0%; resolved, the ceiling is **45 / 75 = 60.0%**. The margin over
the 55% target is 3 cells (42 needed), and the target is a run-time share, which the static ceiling bounds from above.
