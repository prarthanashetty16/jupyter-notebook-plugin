# Tier 2 safety analyzer on 51 realistic multi-statement cells (analyzer unchanged)

**Accepted: 6 of 51 (12%):** control merge, control groupby, control sort, control astype, control matmul, time then op.

## By category

| category | cells | accepted |
|---|---|---|
| control | 5 | 5 |
| variable argument | 8 | 0 |
| intermediate | 7 | 0 |
| method chain | 9 | 0 |
| filter / expression | 6 | 0 |
| pipeline | 5 | 0 |
| imports / display | 3 | 1 |
| control flow / functions | 5 | 0 |
| mutation | 3 | 0 |

## Why the rest were rejected (first reason)

| reason | cells |
|---|---|
| more than one statement | 17 |
| method chain or computed receiver | 15 |
| non-literal argument (a variable, expression or call) | 7 |
| other statement type (import, def, for, if, with, ...) or magic | 3 |
| assignment to a subscript / attribute / tuple (mutation) | 1 |
| in-place operation | 1 |
| operation or keyword outside the allowlist | 1 |

## Every cell

| cell | category | accepted | reason |
|---|---|---|---|
| control merge | control | yes |  |
| control groupby | control | yes |  |
| control sort | control | yes |  |
| control astype | control | yes |  |
| control matmul | control | yes |  |
| keys variable in groupby | variable argument | no | argument is not a literal (Name) |
| on= variable in merge | variable argument | no | argument is not a literal (Name) |
| column variable in sort | variable argument | no | argument is not a literal (Name) |
| target dtype variable | variable argument | no | argument is not a literal (Name) |
| keys defined in the cell | variable argument | no | 2 statements (exactly one is required) |
| subset variable | variable argument | no | argument is not a literal (Name) |
| frames list variable in concat | variable argument | no | pd.concat needs one literal list of variables |
| path variable in read_csv | variable argument | no | argument is not a literal (Name) |
| merge then groupby | intermediate | no | 2 statements (exactly one is required) |
| sort then dedup | intermediate | no | 2 statements (exactly one is required) |
| clean then merge | intermediate | no | 2 statements (exactly one is required) |
| several results | intermediate | no | 2 statements (exactly one is required) |
| copy then sort | intermediate | no | 2 statements (exactly one is required) |
| alias then op | intermediate | no | 2 statements (exactly one is required) |
| result printed | intermediate | no | 2 statements (exactly one is required) |
| sort then head | method chain | no | method chain or computed receiver |
| merge then groupby chain | method chain | no | groupby on a computed receiver |
| sort drop_duplicates chain | method chain | no | method chain or computed receiver |
| groupby reset_index | method chain | no | method chain or computed receiver |
| groupby agg dict | method chain | no | method chain or computed receiver |
| groupby named agg | method chain | no | method chain or computed receiver |
| astype chain | method chain | no | not a supported call |
| merge then sort | method chain | no | method chain or computed receiver |
| assign then groupby | method chain | no | groupby on a computed receiver |
| filter then groupby | filter / expression | no | groupby on a computed receiver |
| query then sort | filter / expression | no | method chain or computed receiver |
| loc then merge | filter / expression | no | method chain or computed receiver |
| column arithmetic | filter / expression | no | assignment target is not a plain name (subscript / attribute / unpacking) |
| dropna then dedup | filter / expression | no | method chain or computed receiver |
| rename then merge | filter / expression | no | method chain or computed receiver |
| read then groupby | pipeline | no | 2 statements (exactly one is required) |
| merge, filter, groupby | pipeline | no | 3 statements (exactly one is required) |
| two independent ops | pipeline | no | 2 statements (exactly one is required) |
| concat then dedup | pipeline | no | 2 statements (exactly one is required) |
| matmul then sum | pipeline | no | 2 statements (exactly one is required) |
| import then op | imports / display | no | 2 statements (exactly one is required) |
| time then op | imports / display | yes |  |
| plot after groupby | imports / display | no | 2 statements (exactly one is required) |
| for loop over keys | control flow / functions | no | statement type For is not allowed |
| list comprehension | control flow / functions | no | not a supported call |
| function definition | control flow / functions | no | 2 statements (exactly one is required) |
| if branch | control flow / functions | no | statement type If is not allowed |
| with timer | control flow / functions | no | statement type With is not allowed |
| inplace sort | mutation | no | inplace is never dry-run |
| assign column then sort | mutation | no | 2 statements (exactly one is required) |
| drop columns inplace | mutation | no | method 'drop' is not in the allowlist |

## Candidate relaxations (PROPOSALS ONLY: nothing below is implemented; each needs its own safety review and a fresh split)

| # | proposal | would accept | risk |
|---|---|---|---|
| P1 | resolve non-literal arguments (`keys`, `col`, `on=keys`, `target`) from the namespace when the value is an immutable literal-like object (str, int, tuple / list of str) | variable-argument cells (8 of 51 here) | a list or frame bound to the name can be mutated between cells, so the value seen at analysis time may differ from the value at run time; an earlier statement of the cell may rebind the name. Mitigation: only names not assigned in the cell |
| P2 | per-statement dry runs: split the cell into statements, accept each that passes alone, dry-run only the one that matches a supported operation | multi-statement cells whose expensive statement is a supported single operation (`clean = df.drop_duplicates()` before `out = clean.merge(...)`) | an earlier statement may have side effects or rebind the operand (`df = df[df.f > 0]`), so the sample is drawn from a different object than the later statement sees; needs a data-flow check that the operand is unchanged |
| P3 | execute short whitelisted chains in the child (`sort_values -> drop_duplicates`, `groupby -> agg -> reset_index`) with the sampling of the first operation | method chains (9 of 51) | the sampling is designed for the first operation (key-hash for merge) and is not valid for later ones; the extrapolation law of a chain is not one operation's |
| P4 | accept pure result wrappers (`.head(n)`, `.reset_index()`) after a supported operation | wrapper cells | `print` and plots are side effects; only pure wrappers should pass |
| P5 | accept boolean-mask / `query` filters before a supported operation | filter cells (6 of 51) | needs evaluating an arbitrary expression in the child (an eval of user code), the largest hole; or restrict to comparisons against literals on a named column |
| P6 | accept aggregation dictionaries / named aggregations in `groupby(...).agg(...)` | groupby cells with `agg` | callables inside the dictionary; literal strings only would be safe |
| P7 | accept `import pandas as pd`-style imports | cells starting with imports | an import runs module code; only `pandas` / `numpy` / `time` could be whitelisted |

Each proposal widens what is executed on SAMPLES in a sandbox; the sandbox bounds the damage (timeout, memory cap, no
shared address space), but a relaxation that lets user code run in the child (P5) gives it the user's data. The mutation
cells in this set (in-place calls, column assignment) must stay rejected under every proposal.
