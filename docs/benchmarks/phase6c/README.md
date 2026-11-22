# Phase 6c: derived fix round (dev results), then `models-frozen-v2`

Pre-registration: `../phase6c-preregistration.md` (commit `91581ac`, before any change). Everything here is **dev**;
the two Amazon notebooks are dev data. Probes: `probes/README.md`. Mains power for every probe and run (recorded).

## What changed

| item | adopted | evidence |
|---|---|---|
| 1. cell-level peak model (`nexus/cellpeak.py`, `models/_output.py`; `risk.assess` uses it, v1 aggregation kept as the fallback for loops / functions / try / with / comprehensions) | yes | probe: 7 multi-statement cells, measured = retained + current **exactly**; multi-statement benchmark dev bars MET |
| 2. read_csv Tier 1 with a one-character `sep` / `delimiter` and `header` 0 / None | yes | probe: TSV and header=None cost identical to the default read |
| 2. read_csv Tier 1 with `dtype`, `usecols`, `nrows` | **no** (contradicted: 0.68x, 0.22x, 0.37x) | probe; Tier 0 kept with "reduced-accuracy estimate: statistics unavailable (unsupported arguments)" |
| 3. `copy` model | yes | probe 1.00 (consolidated) / 1.00 (fragmented, after the source-derived correction) |
| 3. `fillna` model (numpy blocks) | yes | probe 1.00 after the source-derived 4-mask correction; pandas-3 `str` / extension columns refused |
| 4. extension default Tier 1, `%nexus tier 0/1/2`, fallback wording | yes | tests; wording changes no estimate |

## A. Multi-statement benchmark, dev part (`multicell_dev.md`; 44 cells, 22 configurations)

| aggregation | bias | median error | p90 error | coverage | above_high (cells / configs) | width |
|---|---|---|---|---|---|---|
| **new (cellpeak)** | 1.13 | 12.6% | 77.4% | 63.6% | **0% / 0 of 22 (bars MET)** | 2.87 |
| v1 (combine) | 0.99 | 17.8% | 57.8% | 93.2% | 0% / 0 | 5.84 |

The new model halves the width and lowers the median error; 36% of the cells are below its `low` (over-predicted with a
narrow range: chains, copy + fillna). The large biases are the read_csv arguments that keep Tier 0 (`load_dtype_nrows`
2.91x, `loads3_tsv` with `usecols` 1.71x). `load_then_merge` (a merge on a frame created in the cell: no estimate) and
`concat_loads` (concat of calls: no estimate for the concat) are coverage gaps that stayed under `high` here. Held-out
part (22 cells) NOT run.

## B. Regression on all existing dev data (`regression_dev.md`; 646 (point, tier) rows)

RAM above_high 0% for every operation and tier before and after; coverage unchanged. 16 rows changed RAM and 51 time, all in
operations whose code did not change (drop_duplicates, groupby, concat, astype): Tier 1 sample sizes depend on the 250 ms
budget, and two 10M-row points fell back to Tier 0 in one of the runs (`concat/three_frames`, `null_heavy_full`). Listed
regressions: drop_duplicates Tier 1 RAM width 0.775 -> 0.788 and time coverage 100% -> 94.7%; concat Tier 1 RAM width
0.847 -> 0.869; groupby Tier 1 width (floating point only). **Decision: keep** (run-to-run statistics, not a model change;
the model files of these operations are byte-identical to v1).

**Bug found and fixed on the way:** a Phase 6b test (`test_power`) called `monkeypatch.undo()`, which also undid the test
suite's isolation of the machine-profile path, so every full test run since Phase 6b overwrote the user's real profile with a
1-second quick profile measured on battery. It affected time estimates computed after such a run (the Phase 6c regression
time comparison until the profile was restored; very likely the single valid time point of Phase 8a); RAM is not affected.
The real profile was restored from the shipped reference (the same mains measurement), the test fixed, and a session-wide
guard now fails the test run if the user's profile file changes.

## D. Real notebooks, 22% row subsamples (DEV, information only; `realworld_dev.md`)
8 valid RAM points (bias 0.94, median error 22.5%, 1 above high), 9 time points (within-one 88.9%); 49 of 56 cells with a
detected operation are UNKNOWN (no model: set_index, value_counts, apply, explode, ...). Details and limits in `realworld_dev.md`.
