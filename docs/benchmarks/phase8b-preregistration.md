# Phase 8b pre-registration (DRAFT): a fresh real-notebook set, run once on `models-frozen-v4`

**Status: DRAFT.** First committed on 2026-11-23 for v3. Revised on 2026-11-24, before any Phase 8b held-out notebook
exists in this workspace:
* the model under test is now v4;
* the notebook count is dropped; the requirement is >= 150 run-time eligible cells.

No held-out notebook has been collected, opened, inventoried or analysed. The five notebooks in `real_notebooks/` are the
Phase 8b DEV set (their census was read) and are excluded from this batch.

The owner fills in the fields marked **[FILL IN]** from the notebooks' web pages only (title, author, licence, dataset
page), without opening any notebook file here. The final version is committed before the first notebook is copied into
the workspace, and the batch is collected only after `models-frozen-v4` is tagged (`docs/benchmarks/phase8-preregistration.md`,
Order). After that commit, changes are dated amendments that may not relax a criterion.

## 1. The sample: collection protocol and selection rule (owner)

| field | value |
|---|---|
| sources (sites / repositories searched) | **[FILL IN]** e.g. public Kaggle notebooks; GitHub repositories with a LICENSE file |
| search / listing date | **[FILL IN]** |
| selection rule, applied to the listing in a fixed order (e.g. most-voted first, or a seeded random draw), written BEFORE looking at any notebook | **[FILL IN]** |
| inclusion: pandas-heavy by its title / description (EDA, cleaning, feature engineering, joins, aggregation) | yes |
| exclusion (decided from the page): needs a GPU, internet access during the run, Colab paths or credentials; dataset > 1 GiB on disk; licence missing or not permitting local copy and execution; a notebook by the owner; the three Phase 8a notebooks, the five `real_notebooks/` dev notebooks, or forks of either | yes |
| collection target | 15-20 notebooks (a target for collection, not a criterion) |
| distinct authors (>= 10) | **[FILL IN]** |
| licences (notebook and dataset, per notebook) | **[FILL IN]** in `manifest.csv` |
| dataset sizes (bytes on disk, per notebook) | **[FILL IN]** in `manifest.csv` |
| location (outside the repository) | **[FILL IN]** e.g. `C:\dev\nexus-data\phase8b\` |

`manifest.csv` has the columns `notebook, author, source_url, notebook_licence, dataset, dataset_url, dataset_licence,
dataset_bytes, sha256_notebook, sha256_dataset, needs_gpu, needs_internet`. It is filled from the web pages, and the
digests are added when the files are copied. The selection is final once `manifest.csv` is committed: a notebook that
later fails to run stays in the denominator as "failed".

**Size requirement:** >= 150 eligible cells, counted at run time. An eligible cell is a code cell in which the frozen v4
analyser detects >= 1 pandas / NumPy operation and which executes without error in the harness. With fewer, every
Phase 8b criterion is INCONCLUSIVE. A top-up batch is allowed only through an amendment committed before that batch is
collected, sealed the same way. No count of any kind is taken before the run.

## 2. Environment

* `models-frozen-v4` (freeze guard 0 problems), pandas 3.1.1 / numpy 2.5.5, no pyarrow (unless decided here: **[FILL IN]**).
* The reference machine profile; **mains power only** (the held-out entry points refuse `--allow-battery`).
* The Phase 8a harness unchanged: copies of the notebooks, cell by cell in a spawned IPython shell; shell cells skipped; a
  watchdog cap of 70% of the free RAM; records hold hashes, operation names, shapes and numbers only (no code, data or outputs).

## 3. Coverage measure (the Phase 8 criterion: v4 - v3 >= 15 percentage points)

* **Primary, at run time:** a code cell with >= 1 detected operation is COVERED when, as the cell is about to run on its
  live namespace, **every detected operation has an estimate**. That means a model matched it, accepted its arguments and
  receiver (no `NoEstimateError`), and produced a range. **A cell where the hard deadline fired counts as NOT covered.**
  The share = covered cells / cells with >= 1 detected operation, over all executed cells of all notebooks.
  * Measured for v4 in the Phase 8b run itself.
  * Measured for v3 in a second run of the same notebooks on `models-frozen-v3`, used for this share only.
  * Cells reached in one run but not the other are reported, and the share is also given on the cells reached in both
    (the paired share is the criterion).
* **Secondary, static (labelled OVERSTATING; run only after the v4 run):** the share of cells whose every detected
  operation has a model matching its NAME (`tools/static_ops.py`). It ignores arguments and receivers. Reported for both
  stacks; no verdict uses it.
* **Criterion:** the paired run-time share of v4 minus that of v3 >= 15 percentage points. Fewer than 30 cells with a
  detected operation in both runs: INCONCLUSIVE.

## 4. Accuracy, risk and failure

As in the Phase 8 pre-registration (`docs/benchmarks/phase8-preregistration.md`), section 2:
* RAM above_high <= 3% of valid points, quoted with the one-sided 95% upper bound ("consistent with <= x%"). Cells
  labelled "excludes `<op>`" are not scored here (Rule 1);
* the excludes-label criterion: 0 cells labelled "excludes `<op>`" that are OK at a simulated headroom their actual peak
  exceeds;
* the uncovered-operation rule for cells with no estimated operation;
* time within-one, Tier 1, >= 95% (Wilson lower bound quoted);
* range width W;
* secondary, not deciding: above_high with the "excludes" cells scored the v3 way;
* fewer than 30 valid points: INCONCLUSIVE;
* risk classes reported; R1-R3 claimed only at limits with >= 20 positives.

Failure rules: the Phase 8 pre-registration, section 4. The set becomes dev after its one evaluation.

## 5. Commands (once, after the final version of this file is committed and the batch is collected)

    git checkout models-frozen-v4 && python -m benchmarks.frozen check
    python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b/<name> --tier 1
    python -m benchmarks.realworld.evaluate_real benchmarks/results/realworld/phase8b/* --out docs/benchmarks/phase8b/report.md
    git checkout models-frozen-v3 && python -m benchmarks.realworld.run_notebook <copy> --out benchmarks/results/realworld/phase8b_v3/<name> --tier 1
    python tools/static_ops.py <folder>    # secondary, OVERSTATING; only after the runs above

The v3 run (coverage share only) needs the run-time coverage field in the harness records: one field per cell,
`covered`, with deadline firings recorded as not covered. It must be added to `run_notebook` before the final version
of this file. It is outside the freeze.
