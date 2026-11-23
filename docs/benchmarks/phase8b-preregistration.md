# Phase 8b pre-registration (DRAFT): a fresh real-notebook set, run once on `models-frozen-v3`

**Status: DRAFT, committed 2026-11-23 before any Phase 8b notebook exists in this workspace.** No notebook has been
collected, opened, inventoried or analysed. The owner fills in the fields marked **[FILL IN]** from the notebooks' web
pages only (title, author, licence, dataset page), without opening any notebook file here. The final version is committed
before the first notebook is copied into the workspace. After that commit, changes are dated amendments that may not relax
a criterion.

## 1. The sample: collection protocol and selection rule (owner)

| field | value |
|---|---|
| sources (sites / repositories searched) | **[FILL IN]** e.g. public Kaggle notebooks; GitHub repositories with a LICENSE file |
| search / listing date | **[FILL IN]** |
| selection rule, applied to the listing in a fixed order (e.g. most-voted first, or a seeded random draw), written BEFORE looking at any notebook | **[FILL IN]** |
| inclusion: pandas-heavy by its title / description (EDA, cleaning, feature engineering, joins, aggregation) | yes |
| exclusion (decided from the page): needs a GPU, internet access during the run, Colab paths or credentials; dataset > 1 GiB on disk; licence missing or not permitting local copy and execution; a notebook by the owner; the three Phase 8a notebooks or their forks | yes |
| number of notebooks (>= 30) / distinct authors (>= 10) | **[FILL IN]** / **[FILL IN]** |
| licences (notebook and dataset, per notebook) | **[FILL IN]** in `manifest.csv` |
| dataset sizes (bytes on disk, per notebook) | **[FILL IN]** in `manifest.csv` |
| location (outside the repository) | **[FILL IN]** e.g. `C:\dev\nexus-data\phase8b\` |

`manifest.csv` has the columns `notebook, author, source_url, notebook_licence, dataset, dataset_url, dataset_licence,
dataset_bytes, needs_gpu, needs_internet`. It is filled from the web pages. The selection is final once this file is committed:
a notebook that later fails to run stays in the denominator as "failed".

## 2. Environment

* `models-frozen-v3` (freeze guard 0 problems), pandas 3.1.1 / numpy 2.5.5, no pyarrow (unless decided here: **[FILL IN]**).
* The reference machine profile; **mains power only** (the held-out entry points refuse `--allow-battery`).
* The Phase 8a harness unchanged: copies of the notebooks, cell by cell in a spawned IPython shell; shell cells skipped; a
  watchdog cap of 70% of the free RAM; records hold hashes, operation names, shapes and numbers only (no code, data or outputs).

## 3. Coverage measure (the Phase 7 criterion: v3 - v2 >= 10 percentage points)

* **Primary, at run time:** a code cell with >= 1 detected operation is COVERED when, as the cell is about to run on its
  live namespace, **every detected operation has an estimate**. That means a model matched it, accepted its arguments and
  receiver (no `NoEstimateError`), and produced a range. The share = covered cells / cells with >= 1 detected operation,
  over all executed cells of all notebooks.
  * Measured for v3 in the Phase 8b run itself.
  * Measured for v2 in a second run of the same notebooks on `models-frozen-v2`, used for this share only.
  * Cells reached in one run but not the other are reported, and the share is also given on the cells reached in both
    (the paired share is the criterion).
* **Secondary, static (labelled OVERSTATING):** the share of cells whose every detected operation has a model matching its
  NAME (`docs/benchmarks/phase7b/static_coverage.py`). It ignores arguments and receivers, so it counts, for example, every
  `apply` and every `set_index` as covered. Reported for both stacks; no verdict uses it.
* **Criterion:** the paired run-time share of v3 minus that of v2 >= 10 percentage points. Fewer than 30 cells with a
  detected operation in both runs: INCONCLUSIVE.

## 4. Accuracy, risk and failure

As in the Phase 7 pre-registration, section 2:
* RAM above_high <= 3% of valid points, quoted with the one-sided 95% upper bound ("consistent with <= x%");
* time within-one >= 95% (Wilson lower bound quoted);
* fewer than 30 valid points: INCONCLUSIVE;
* risk classes reported; R1-R3 claimed only at limits with >= 20 positives;
* the uncovered-operation rule (amendment 1): a cell with an uncovered operation must never be OK when its actual exceeds
  the simulated headroom.

Failure rules: the Phase 7 pre-registration, section 4. The set becomes dev after its one evaluation.

## 5. Commands (once, after the final version of this file is committed)

    git checkout models-frozen-v3 && python -m benchmarks.frozen check
    python -m benchmarks.realworld.coverage <folder> --out docs/benchmarks/phase8b/coverage
    python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b/<name> --tier 1
    python -m benchmarks.realworld.evaluate_real benchmarks/results/realworld/phase8b/* --out docs/benchmarks/phase8b/report.md
    git checkout models-frozen-v2 && python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b_v2/<name> --tier 1

The last command (v2, coverage share only) needs the run-time coverage field in the harness records. It must be added
to `run_notebook` before the final version of this file: one field per cell, `covered`. It is outside the freeze.
