# Phase 8b pre-registration: paired v3/v4 real-notebook evaluation

**Status: pending the owner fields in section 1.** No Phase 8b notebook, dataset, or result has been opened, run, or read.
The five `real_notebooks/` files are the Phase 8b dev set and are excluded.

**Pre-registration amendment (2026-11-25, before collection):** this protocol supersedes the earlier DRAFT's 15
percentage-point coverage threshold and 15-20 notebook target. Phase 8b now requires at least 30 notebooks from at least
10 authors and a paired v4-minus-v3 run-time coverage gain of at least 10 percentage points. No Phase 8b held-out data
exists. This change applies only to Phase 8b; the other Phase 8 criteria remain as written in
[phase8-preregistration.md](./phase8-preregistration.md).

The v4 model tag is `models-frozen-v4`. This protocol and the evaluation/collection tooling are outside the frozen
model set. No static census or cell reading is permitted before this pre-registration is complete and committed.

## 1. Collection checklist and owner fields

The owner completes **only** the marked fields below. All other protocol choices are fixed here.

| Owner field | Value to provide |
|---|---|
| Sources (sites / repositories searched) | **OWNER: fill in sources** |
| Selection rule, written before collection | **OWNER: fill in the rule and fixed tie-breaker** |
| Collection date | **OWNER: fill in date** |
| Notebook and dataset licences | **OWNER: record per item in `manifest.csv`** |
| Dataset sizes | **OWNER: record total required data bytes per notebook in `manifest.csv`** |
| Counts | **OWNER: record selected notebooks (at least 30), distinct authors (at least 10), and final eligible cells** |

Collection must satisfy every item:

- [ ] Select at least 30 public, pandas-heavy notebooks from at least 10 distinct authors. Pandas-heavy selection is based
  only on public titles/descriptions (for example, EDA, cleaning, joins, aggregation, or feature engineering).
- [ ] Write the selection rule before collecting any notebook. It must define the source listings, ranking or random
  selection, fixed tie-breaker, and how the first 30 qualifying notebooks are chosen. For example: choose the N
  highest-voted pandas-tagged notebooks for each of several named datasets, breaking vote ties by canonical URL.
- [ ] Check the notebook and dataset licences from their public pages; each must permit local copying and execution.
- [ ] Exclude notebooks requiring a GPU, internet access during execution, credentials, or machine-specific hosted paths.
  Exclude a notebook if the total required dataset files exceed 1 GiB on disk, or if it duplicates a Phase 8a/dev
  notebook or is a fork of one.
- [ ] Store the notebook files, all datasets, harness copies, and raw result folders outside the repository. The default
  external root is `C:\dev\nexus-data\phase8b\`.
- [ ] Complete `manifest.csv` from public metadata and copied-file hashes. Required columns:
  `notebook, author, source_url, notebook_licence, dataset, dataset_url, dataset_licence, dataset_bytes,
  sha256_notebook, sha256_dataset, needs_gpu, needs_internet`.
  The `notebook` value is a unique copied `.ipynb` filename, and each `dataset_bytes` value is the total required
  dataset size for that notebook; the total must be at most 1 GiB.
- [ ] Commit the final pre-registration and the manifest containing SHA-256 digests **before opening any notebook file**.
  Until then, hashing file bytes is allowed, but do not read cell contents, conduct a static operation census, or run a
  notebook.
- [ ] Keep every selected notebook in the batch even if it errors, times out, or cannot complete. No substitution after
  collection starts. A top-up requires a dated amendment committed before collecting the added batch.

The frozen v4 analyser must reach at least **150 eligible cells** at run time. An eligible cell has at least one detected
pandas/NumPy operation and finishes without an execution error. The evaluator reports the count; it is not estimated by
opening or statically counting cells. If fewer than 150 eligible v4 cells are reached, **every Phase 8b criterion is
INCONCLUSIVE**.

## 2. Environment and result integrity

- Run on the reference Windows laptop, with mains power only. Do not pass `--allow-battery`.
- Use pandas 3.1.1 and NumPy 2.5.5. `pyarrow` is not installed; do not add it for this evaluation.
- Use the frozen v3 and v4 tags in separate checkouts. Run the exact same digest-pinned notebooks and datasets once under
  each tag, in manifest order. No model or notebook edits are allowed.
- Before each version's run, `python -m benchmarks.frozen check` must report zero problems. The held-out harness checks
  mains power and its environment profile. Each notebook output directory is a separate run and receives its own
  profile pin; keep the same reference machine profile for both versions.
- The harness runs a copy cell by cell in a spawned IPython shell, skips shell/package cells, and uses the existing
  watchdog cap of 70% of available RAM. Logs contain hashes, operation names, shapes, and numeric estimates/actuals,
  never cell code, outputs, or data values.
- V4 rows persist `model_version` on every cell record. The frozen v3 harness predates that field; for v3 only, the
  evaluator validates `summary.json`'s `frozen.frozen_tag` and attaches `model_version=models-frozen-v3` to each
  normalized in-memory row. It refuses a mismatched summary or any row tagged with another version. This does not alter
  the v3 freeze or raw records.
- V3 actuals are retained by its harness but are not scored as v4 accuracy results. Its run is used for paired coverage
  and the pre-registered v3/v4 range-width comparison; no result is inspected until both versions finish.
- `evaluate_real` requires two distinct result roots, validates that every run summary has the expected version, rejects
  mixed-version rows, and requires the same notebook identifiers in both roots. Pairing key is `(notebook, index, hash)`.

## 3. Primary and secondary coverage measures

**Primary, paired run-time coverage.** For each cell present in both result roots under the pairing key, it is covered
for one version only if that version detected at least one operation, estimated every detected operation, and did not
fire the hard deadline. A hard-deadline Tier 0 fallback is not covered. For v3, the evaluator derives this field from
the recorded operation list, uncovered count, and deadline flag because the frozen v3 harness predates the explicit
`covered` field. The denominator contains cells where at least one version detected an operation; if one side detected
none, that side is not covered. Cells with no detected operation on either side are excluded.

The evaluator reports v3 and v4 covered shares on this same paired denominator and their percentage-point difference.
Cells recorded by only one version are reported separately (including operation-bearing counts) and excluded from the
paired denominator; they are never counted as covered. Within a shared cell, if only one version detects operations,
the cell stays in the denominator and the version detecting none is not covered. At least 30 paired operation-bearing
cells are required, else coverage is INCONCLUSIVE. **Decision bar: v4 minus v3 is at least 10 percentage points.**

**Secondary, static name matching (OVERSTATING; not deciding).** After both runtime runs, execute
`tools/static_ops.py` once with each tag's registry against the same notebook folder. It counts a cell covered when
every statically detected operation name has a registered model name, ignoring arguments, receiver forms, live state,
and deadlines. Report the resulting share for both versions and label it **OVERSTATING**. It is not a substitute for,
and never decides, the paired run-time criterion. Do not run this census before both runtime runs are complete.

## 4. Accuracy, partial cells, risk, and decisions

The Phase 8 rules in [phase8-preregistration.md](./phase8-preregistration.md), including Amendment 7, remain authoritative
except for the Phase 8b-specific coverage change in the dated amendment above.

- **RAM above-high:** score only valid, fully covered v4 cells. Report the observed rate and one-sided 95% exact
  Clopper-Pearson upper bound; the bar is an upper bound no greater than 3%. Partial and deadline-fallback cells are
  excluded from this denominator.
- **Partial cells:** report counts separately. At each simulated headroom from 64 MiB through 8 GiB, there must be zero
  cases where risk is OK while actual peak exceeds headroom. The displayed covered lower bound must never exceed actual
  peak. Missing risk classes or a missing lower bound make the corresponding safety score INCONCLUSIVE. Partial cells
  have no full-cell upper bound.
- **Wholly uncovered cells:** zero cases where risk is OK while actual peak exceeds a simulated headroom.
- **Time within-one:** use valid, fully covered Tier 1 predictions; report the Wilson 95% lower bound. The bar is a lower
  bound of at least 95%.
- **Range width W:** W(a), on common fully covered v3/v4 cells, is the median of
  `(high_v4 / expected_v4) / (high_v3 / expected_v3)` and must be at most 1.30. W(b), on fully covered v4 cells where
  v3 has no estimate, must have median `high_v4 / expected_v4` at most 2.0 and p90 at most 4.0.
- **Risk engine:** report risk classes and R1/R2/R3 under the Phase 8 limits. R1 requires at least 98% recall at limits
  with at least 20 positives; R2 requires pooled false alarms at most 30% and at most 50% per operation when that
  operation has at least 20 non-positive pairs; R3 requires at least 75% HIGH_RISK precision and is not claimed with
  fewer than 20 HIGH_RISK points.
- **Minimum evidence:** fewer than 30 valid points for an accuracy metric, fewer than 30 paired operation-bearing cells
  for coverage, or fewer than 150 eligible v4 cells makes the applicable criterion INCONCLUSIVE (the 150-cell shortfall
  makes all Phase 8b criteria INCONCLUSIVE). INCONCLUSIVE is never a pass.
- Suggestion counts and Tier 0 comparisons are descriptive only.

**Failure statement.** Report every criterion as MET, FAILED, or INCONCLUSIVE with its denominator and required
confidence bound. A failed Phase 8b criterion withdraws that Phase 8b claim; it is not repaired or retuned against this
batch, and the batch becomes dev after its one evaluation. It does not by itself relabel the entire v4 freeze as failed;
the whole-v4 failure conditions remain those in section 4 of the Phase 8 pre-registration.

## 5. Run sequence (each notebook once per version)

Set `$root` to the external directory containing the committed manifest, notebooks, datasets, and results. The `notebook`
manifest field is each unique copied `.ipynb` filename; CSV row order is the fixed run order. The notebooks and data
remain outside both checkouts. Run v3 first, once per manifest row, in its separate checkout and results folder; only after that
batch finishes, run v4 once per same manifest row in its separate checkout and results folder. Do not resume or rerun a
notebook, including after an error or interruption. Use one output subdirectory per notebook so each run has its own
profile pin.

1. **Prepare the outside-freeze tools checkout** used for the v4 harness metadata, evaluator, and static tool:

       git clone https://github.com/prarthanashetty16/jupyter-notebook-plugin.git C:\dev\nexus-tools
       git -C C:\dev\nexus-tools checkout v4-dev
       Set-Location C:\dev\nexus-tools
       python -m benchmarks.frozen check

2. **V3 first, in its own checkout and result root:**

       git clone https://github.com/prarthanashetty16/jupyter-notebook-plugin.git C:\dev\nexus-v3
       git -C C:\dev\nexus-v3 checkout --detach models-frozen-v3
       Set-Location C:\dev\nexus-v3
       python -m benchmarks.frozen check
       $root = 'C:\dev\nexus-data\phase8b'
       $notebooks = Join-Path $root 'notebooks'
       $manifestRows = Import-Csv (Join-Path $root 'manifest.csv')
       foreach ($entry in $manifestRows) {
           $notebook = Join-Path $notebooks $entry.notebook
           $out = Join-Path (Join-Path $root 'results\v3') ([IO.Path]::GetFileNameWithoutExtension($entry.notebook))
           python -m benchmarks.realworld.run_notebook $notebook --out $out --tier 1
           if ($LASTEXITCODE -ne 0) { throw "V3 run failed for $($entry.notebook); do not rerun or substitute it." }
       }

3. **Then v4, in a separate checkout and result root, after the v3 batch is complete.** Copy the outside-freeze v4
   harness change so each v4 JSONL row records `model_version`, then re-check the frozen model files before running:

       git clone https://github.com/prarthanashetty16/jupyter-notebook-plugin.git C:\dev\nexus-v4
       git -C C:\dev\nexus-v4 checkout --detach models-frozen-v4
       Copy-Item C:\dev\nexus-tools\benchmarks\realworld\run_notebook.py C:\dev\nexus-v4\benchmarks\realworld\run_notebook.py
       Set-Location C:\dev\nexus-v4
       python -m benchmarks.frozen check
       $root = 'C:\dev\nexus-data\phase8b'
       $notebooks = Join-Path $root 'notebooks'
       $manifestRows = Import-Csv (Join-Path $root 'manifest.csv')
       foreach ($entry in $manifestRows) {
           $notebook = Join-Path $notebooks $entry.notebook
           $out = Join-Path (Join-Path $root 'results\v4') ([IO.Path]::GetFileNameWithoutExtension($entry.notebook))
           python -m benchmarks.realworld.run_notebook $notebook --out $out --tier 1
           if ($LASTEXITCODE -ne 0) { throw "V4 run failed for $($entry.notebook); do not rerun or substitute it." }
       }

4. **Evaluate the paired result roots once, from the tools checkout:**

       Set-Location C:\dev\nexus-tools
       python -m benchmarks.frozen check
       python -m benchmarks.realworld.evaluate_real C:\dev\nexus-data\phase8b\results\v3 C:\dev\nexus-data\phase8b\results\v4 --out docs\benchmarks\phase8b\report.md

5. **Only after both runtime runs, compute the static secondary.** Copy the current outside-freeze
   `tools\static_ops.py` into the v3 checkout so the same name-only implementation is used; then run it once under each
   checkout's own model registry:

       Copy-Item C:\dev\nexus-tools\tools\static_ops.py C:\dev\nexus-v3\tools\static_ops.py
       Set-Location C:\dev\nexus-v3
       python -m benchmarks.frozen check
       python tools\static_ops.py C:\dev\nexus-data\phase8b\notebooks --model-version models-frozen-v3 | Set-Content C:\dev\nexus-data\phase8b\static-v3.md
       Set-Location C:\dev\nexus-tools
       python -m benchmarks.frozen check
       python tools\static_ops.py C:\dev\nexus-data\phase8b\notebooks --model-version models-frozen-v4 | Set-Content C:\dev\nexus-data\phase8b\static-v4.md

The freeze guard and mains-power refusal apply separately to both runtime batches: check the guard before each batch and
the harness refuses battery power on every notebook invocation (do not pass `--allow-battery`). Each notebook run gets
its own profile pin in its output folder; record the pinned profile for both versions and use the same reference machine.
After the one evaluation, the batch is no longer held out. Any model change after v4 invalidates the held-out status;
new model version and new held-out notebooks are required.
