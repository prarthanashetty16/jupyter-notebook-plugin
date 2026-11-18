# Real-notebook coverage (static analysis; no cell code was executed)

3 notebooks read (0 unreadable), 613 code cells, 8 blank / comment-only; **605 cells analysed**.

## Headline

| question | cells | share of analysed |
|---|---|---|
| a supported operation is detected (an estimate is possible with live data) | 190 | 31% |
| the Tier 2 safety analyzer accepts the cell | 0 | 0% |
| supported operation AND accepted by Tier 2 | 0 | 0% |

Among the 190 cells with a supported operation, Tier 2 accepts 0 (0%).

## By detected operation

| operation | cells containing it | accepted by Tier 2 |
|---|---|---|
| copy | 110 | 0 (0%) |
| astype | 74 | 0 (0%) |
| pandas.concat | 49 | 0 (0%) |
| describe | 43 | 0 (0%) |
| merge | 42 | 0 (0%) |
| nunique | 40 | 0 (0%) |
| sort_values | 38 | 0 (0%) |
| groupby | 37 | 0 (0%) |
| value_counts | 36 | 0 (0%) |
| set_index | 34 | 0 (0%) |
| apply | 34 | 0 (0%) |
| fillna | 29 | 0 (0%) |
| reset_index | 29 | 0 (0%) |
| drop_duplicates | 23 | 0 (0%) |
| explode | 22 | 0 (0%) |
| to_numpy | 17 | 0 (0%) |
| duplicated | 16 | 0 (0%) |
| sample | 15 | 0 (0%) |
| pandas.read_csv | 13 | 0 (0%) |
| map | 12 | 0 (0%) |
| numpy.array | 12 | 0 (0%) |
| sort_index | 8 | 0 (0%) |
| to_parquet | 8 | 0 (0%) |
| ravel | 7 | 0 (0%) |
| join | 6 | 0 (0%) |
| assign | 6 | 0 (0%) |
| numpy.arange | 6 | 0 (0%) |
| to_csv | 6 | 0 (0%) |
| dropna | 5 | 0 (0%) |
| numpy.concatenate | 4 | 0 (0%) |
| numpy.empty | 4 | 0 (0%) |
| pandas.read_parquet | 3 | 0 (0%) |
| pandas.crosstab | 2 | 0 (0%) |
| numpy.zeros | 1 | 0 (0%) |

## Why cells are rejected by the Tier 2 safety analyzer

| reason | all cells | cells with a supported operation |
|---|---|---|
| more than one statement | 538 (89%) | 186 (98%) |
| other statement type (import, def, for, if, with, ...) or magic | 29 (5%) | 3 (2%) |
| method chain or computed receiver | 28 (5%) | 1 (1%) |
| operation or keyword outside the allowlist | 10 (2%) | 0 (0%) |

## Candidate ranking of the Tier 2 relaxation proposals (COUNTING ONLY; nothing is implemented)

Among the 190 rejected cells with a supported operation (and, for reference, all 605 rejected cells), how many each proposal would unlock when applied ALONE as the source rewrite described in the module docstring:

| rank | proposal | unlocks (supported-op cells) | unlocks (all rejected cells) | description |
|---|---|---|---|---|
| 1 | P2 | 38 (20%) | 38 (6%) | per-statement dry runs (accept a multi-statement cell if one statement alone is accepted) |
| 2 | P3 | 2 (1%) | 2 (0%) | whitelisted chains (run the innermost supported operation of a chain) |
| 3 | P1 | 0 (0%) | 0 (0%) | resolve non-literal arguments from literal assignments (names bound to a str / number / list of them) |
| 4 | P4 | 0 (0%) | 0 (0%) | pure result wrappers after a supported operation (.head / .tail / .reset_index / .copy) |
| 5 | P5 | 0 (0%) | 0 (0%) | filters before a supported operation (boolean mask, .query, .loc, .dropna) |
| 6 | P6 | 0 (0%) | 0 (0%) | aggregation dictionaries / names in groupby(...).agg(...) |
| 7 | P7 | 0 (0%) | 0 (0%) | imports of pandas / numpy / time in front of a supported statement |
| 8 | P8 | 0 (0%) | 0 (0%) | bare function names imported from pandas / numpy (`from pandas import read_csv`; `read_csv(...)`) |

Any one proposal would unlock 40 (21%) of the rejected supported-operation cells; 150 would stay rejected (mutation, control flow, unsupported operations, unparseable code).

## Method and limits

* operands are stand-ins (see the module docstring); a cell that only works with real column names, dtypes or files may be classified differently on a live kernel;
* "supported operation" is detection by the syntactic analyzer plus a matching Tier 0 / 1 model, not a proof that live data would yield an estimate;
* an unlock is a source rewrite accepted by the UNCHANGED analyzer: it says nothing about whether the relaxation is safe (see the risks in `docs/benchmarks/phase4d-dev/multistatement.md`);
* a handful of notebooks says little: the percentages come from the folder you provided, not from notebooks in general.
