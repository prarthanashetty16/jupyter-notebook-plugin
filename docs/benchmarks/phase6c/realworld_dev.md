# Real notebooks on 22% row subsamples: DEV check of the Phase 6c stack (information only, no verdict)

**Every number here is DEV**: the notebooks were opened in Phase 8a and the Phase 6c fixes are motivated by them. Data:
seeded line subsamples (22% of each input's rows, same header and format; `benchmarks/realworld/subsample.py`) under the
git-ignored `benchmarks/results/realworld/subsample/`. Harness: Phase 8a's, with `--tier 1` (the new extension default) and
`--dev` (working tree before the v2 tag; recorded as "dev run, NOT the frozen stack"); mains power at every cell; the cell
estimate is the new cell model. Tables: `realworld_dev_tables.md` (its header text "Pipeline(tier=2)" is the Phase 8a
default of the shared script; this run used Tier 1).

| notebook | cells | executed | failed | outcome |
|---|---|---|---|---|
| amazon_solution_old | 195 | 74 | 8 | stopped after 5 consecutive failing cells (KeyError) |
| amazon_ml_solution | 380 | 30 | 12 | stopped after 5 consecutive failing cells (KeyError; one ModuleNotFoundError: pyarrow absent) |

Phase 8a stopped at cell 10 / cell 3 (watchdog); the subsamples let both notebooks run past their loading cells. The
KeyErrors were not investigated cell by cell (no code is read or logged); likely causes are cells depending on earlier failed
cells and keys absent from a 22% subsample.

* **RAM, 8 valid points:** bias 0.94, median error 22.5%, p90 62.5%, coverage 87.5%, 1 of 8 above `high` (a groupby + concat
  cell over frames whose text columns are pandas `str` / `string` extension dtypes: 156 vs 409 MiB). Multi-load cells: 4 x
  read_csv 637 vs 873 MiB (0.73; Phase 8a with the v1 aggregation: 0.56), 7 x read_csv 1,486 vs 1,641 MiB (0.91).
* **Time, 9 valid points:** within-one 88.9%, same-bucket 77.8%, median error 21%.
* **Risk classes** (cells with a detected operation): 7 OK, 49 UNKNOWN (46 "no estimate for this cell", 3 partly covered),
  0 WARN / HIGH_RISK. Simulated limits: fewer than 20 positives everywhere (no claim); no missed overrun.
* **Suggestions:** 10 cells with an estimate, 1 with a suggestion shown.
* **What remains uncovered here** (cells containing an operation without an estimate): set_index 16, fillna 12 (pandas-3
  `str` / `string` columns are refused; receivers created in the cell), value_counts 9, apply 9, sample 7, explode 4,
  duplicated 3, describe 3, join 3, copy 3, map 3, astype 3, sort_index 2, merge 2 (frames created in the cell).
