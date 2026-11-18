# Real-notebook coverage (static analysis; no cell code was executed)

1 notebooks read (0 unreadable), 51 code cells, 0 blank / comment-only; **51 cells analysed**.

## Headline

| question | cells | share of analysed |
|---|---|---|
| a supported operation is detected (an estimate is possible with live data) | 49 | 96% |
| the Tier 2 safety analyzer accepts the cell | 6 | 12% |
| supported operation AND accepted by Tier 2 | 6 | 12% |

Among the 49 cells with a supported operation, Tier 2 accepts 6 (12%).

## By detected operation

| operation | cells containing it | accepted by Tier 2 |
|---|---|---|
| groupby | 18 | 1 (6%) |
| sort_values | 16 | 2 (12%) |
| merge | 9 | 1 (11%) |
| drop_duplicates | 7 | 0 (0%) |
| astype | 3 | 1 (33%) |
| operator.matmul | 2 | 1 (50%) |
| pandas.concat | 2 | 0 (0%) |
| pandas.read_csv | 2 | 0 (0%) |
| copy | 1 | 0 (0%) |
| reset_index | 1 | 0 (0%) |
| assign | 1 | 0 (0%) |
| query | 1 | 0 (0%) |
| dropna | 1 | 0 (0%) |

## Why cells are rejected by the Tier 2 safety analyzer

| reason | all cells | cells with a supported operation |
|---|---|---|
| more than one statement | 17 (33%) | 17 (35%) |
| method chain or computed receiver | 15 (29%) | 15 (31%) |
| non-literal argument (a variable, expression or call) | 7 (14%) | 7 (14%) |
| other statement type (import, def, for, if, with, ...) or magic | 3 (6%) | 3 (6%) |
| assignment to a subscript / attribute / tuple (mutation) | 1 (2%) | 0 (0%) |
| in-place operation | 1 (2%) | 1 (2%) |
| operation or keyword outside the allowlist | 1 (2%) | 0 (0%) |

## Candidate ranking of the Tier 2 relaxation proposals (COUNTING ONLY; nothing is implemented)

Among the 43 rejected cells with a supported operation (and, for reference, all 45 rejected cells), how many each proposal would unlock when applied ALONE as the source rewrite described in the module docstring:

| rank | proposal | unlocks (supported-op cells) | unlocks (all rejected cells) | description |
|---|---|---|---|---|
| 1 | P2 | 15 (35%) | 15 (33%) | per-statement dry runs (accept a multi-statement cell if one statement alone is accepted) |
| 2 | P3 | 8 (19%) | 8 (18%) | whitelisted chains (run the innermost supported operation of a chain) |
| 3 | P5 | 4 (9%) | 4 (9%) | filters before a supported operation (boolean mask, .query, .loc, .dropna) |
| 4 | P1 | 3 (7%) | 3 (7%) | resolve non-literal arguments from literal assignments (names bound to a str / number / list of them) |
| 5 | P4 | 2 (5%) | 2 (4%) | pure result wrappers after a supported operation (.head / .tail / .reset_index / .copy) |
| 6 | P6 | 2 (5%) | 2 (4%) | aggregation dictionaries / names in groupby(...).agg(...) |
| 7 | P7 | 1 (2%) | 1 (2%) | imports of pandas / numpy / time in front of a supported statement |
| 8 | P8 | 0 (0%) | 0 (0%) | bare function names imported from pandas / numpy (`from pandas import read_csv`; `read_csv(...)`) |

Any one proposal would unlock 32 (74%) of the rejected supported-operation cells; 11 would stay rejected (mutation, control flow, unsupported operations, unparseable code).

## Method and limits

* operands are stand-ins (see the module docstring); a cell that only works with real column names, dtypes or files may be classified differently on a live kernel;
* "supported operation" is detection by the syntactic analyzer plus a matching Tier 0 / 1 model, not a proof that live data would yield an estimate;
* an unlock is a source rewrite accepted by the UNCHANGED analyzer: it says nothing about whether the relaxation is safe (see the risks in `docs/benchmarks/phase4d-dev/multistatement.md`);
* a handful of notebooks says little: the percentages come from the folder you provided, not from notebooks in general.
