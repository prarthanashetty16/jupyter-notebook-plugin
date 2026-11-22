# Frozen model stack `models-frozen-v2`

Tag `models-frozen-v2` = commit `1f081246783867d19932aad7ab9f3fa966ad1034` (Phase 6c). Written by `python -m benchmarks.frozen manifest`. Held-out runs (val-v5 on the Linux VM, the Phase 6c multi-statement held-out cells, test-v2, a future fresh real-notebook test) call `benchmarks.frozen.require_frozen()`, which compares the SHA-256 (LF line endings) of every frozen file below with the tag's own copy and **aborts if any differs, is missing, or a new file matches a frozen pattern**. **Any change to a frozen file after v2 invalidates the held-out status of those runs** (a new freeze, tag and held-out group would be needed).

At the time this manifest was written `python -m benchmarks.frozen check` reported 0 problems against `models-frozen-v2`.

## History

- `models-frozen-v1` (Phase 6, commit `c3e3ee0def91`): its manifest is kept unchanged in `docs/benchmarks/frozen-manifest-v1.md` (incl. the Phase 6b scope narrowing to the prediction-defining files and the addition of the measurement instrument).
- `models-frozen-v2` (Phase 6c): the cell-level peak model, `read_csv` Tier 1 with a one-character separator / header, the `copy` and `fillna` models, Tier 1 as the extension default (`docs/benchmarks/phase6c-preregistration.md`). v1 is not deleted; the guard checks against v2.

## Frozen files: 6 changed, 3 added, 34 unchanged since `models-frozen-v1`

| file | status | role | sha256 v1 | sha256 v2 |
|---|---|---|---|---|
| `src/nexus/models/_time.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `ddc2261e26807122` | `0e2947ce188f4a03` |
| `src/nexus/models/builtin.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `682d9ea063d65e1d` | `b8c5e00870282f79` |
| `src/nexus/models/read_csv.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b099bb8c65603aae` | `9711c519a4ce37f8` |
| `src/nexus/pipeline.py` | changed | analyze -> inspect -> models, policy and time calibration applied | `093028d712d5c07b` | `50bf49b6927a08cc` |
| `src/nexus/risk.py` | changed | risk-engine classes and thresholds | `1b0008159d6d486a` | `5265aab5a28a5cc6` |
| `src/nexus/stats.py` | changed | Tier 1 statistics | `b10e7987db6a9c37` | `d60cb148b491ae66` |
| `src/nexus/cellpeak.py` | added | cell-level peak model (Phase 6c) | `-` | `c25633def5b3f11a` |
| `src/nexus/models/_output.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `8b6065462482c473` |
| `src/nexus/models/copy_fillna.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `03dec0dc358ca9b4` |
| `src/nexus/_dryrun_child.py` | unchanged | Tier 2 sandbox child | `7dbf5fcb348509c2` | `7dbf5fcb348509c2` |
| `src/nexus/analyzer.py` | unchanged | which operations a cell contains (what gets estimated) | `3ff34432d187fe9b` | `3ff34432d187fe9b` |
| `src/nexus/calibrate.py` | unchanged | what the machine profile measures | `07be83e4ba943f84` | `07be83e4ba943f84` |
| `src/nexus/calibration/calibration-v1.json` | unchanged | calibration artifact and reference machine profile | `5d1ac0809b5d4285` | `5d1ac0809b5d4285` |
| `src/nexus/calibration/reference_machine.json` | unchanged | calibration artifact and reference machine profile | `b481efef69014677` | `b481efef69014677` |
| `src/nexus/controller.py` | unchanged | Tier 2 controller rules and thresholds | `269539502b5e9c0d` | `269539502b5e9c0d` |
| `src/nexus/dryrun.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `dbb6f554212911bf` | `dbb6f554212911bf` |
| `src/nexus/dryrun_fit.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `b08ce264d96a3ef1` | `b08ce264d96a3ef1` |
| `src/nexus/dryrun_io.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `d0488477ba114a37` | `d0488477ba114a37` |
| `src/nexus/dryrun_safety.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `73b68265756cd9b9` | `73b68265756cd9b9` |
| `src/nexus/dryrun_sample.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `0a9fbfda21759f5a` | `0a9fbfda21759f5a` |
| `src/nexus/failsafe.py` | unchanged | deadlines: the Tier 1 time budget | `a7bc6be6b4fe7b5e` | `a7bc6be6b4fe7b5e` |
| `src/nexus/guard.py` | unchanged | Tier 1 sanity guard | `0664a1e1db1546d4` | `0664a1e1db1546d4` |
| `src/nexus/machine.py` | unchanged | machine profile format 3 and the generic profile | `12c123c2b8e81e20` | `12c123c2b8e81e20` |
| `src/nexus/measure.py` | unchanged | the measurement instrument (peak RAM, time) of every held-out actual | `7931d7b0e596edc8` | `7931d7b0e596edc8` |
| `src/nexus/models/__init__.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7e5c45ec3a81ff92` | `7e5c45ec3a81ff92` |
| `src/nexus/models/_util.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `2175c4433c8f2e66` | `2175c4433c8f2e66` |
| `src/nexus/models/astype.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `489f557066bf3ee3` | `489f557066bf3ee3` |
| `src/nexus/models/base.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `069d88d7d529fa3d` | `069d88d7d529fa3d` |
| `src/nexus/models/concat.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1edb35a0fee1c3eb` | `1edb35a0fee1c3eb` |
| `src/nexus/models/drop_duplicates.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b4a5ab4693c0e4a4` | `b4a5ab4693c0e4a4` |
| `src/nexus/models/groupby.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `44ae61ecf92e1aaa` | `44ae61ecf92e1aaa` |
| `src/nexus/models/matmul.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `145cc0f2b6e84b66` | `145cc0f2b6e84b66` |
| `src/nexus/models/merge.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1268942893fe2788` | `1268942893fe2788` |
| `src/nexus/models/noop.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `80cd6fbcc5a5ec71` | `80cd6fbcc5a5ec71` |
| `src/nexus/models/np_sort.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `38e6d4b15162d47c` | `38e6d4b15162d47c` |
| `src/nexus/models/sort_values.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7bab7e20c1f36036` | `7bab7e20c1f36036` |
| `src/nexus/ranges.py` | unchanged | RAM range policy B | `f2dcf1f242c59ccb` | `f2dcf1f242c59ccb` |
| `src/nexus/registry.py` | unchanged | model registry | `01d36368eecd118f` | `01d36368eecd118f` |
| `src/nexus/state.py` | unchanged | state inspection: the descriptors the models read | `ce7405088c5b26ea` | `ce7405088c5b26ea` |
| `src/nexus/suggestions/engine.py` | unchanged | suggestion filter thresholds | `76183491336da280` | `76183491336da280` |
| `src/nexus/timebuckets.py` | unchanged | user-facing time buckets | `c4f7460065b2f784` | `c4f7460065b2f784` |
| `src/nexus/timecal.py` | unchanged | applies the time calibration artifact (ranges, flags, widening) | `5d2181104cd7efb5` | `5d2181104cd7efb5` |
| `tests/test_measure_validation.py` | unchanged | the instrument's validation (known allocations within 10%) | `4f66725ee4aab9b9` | `4f66725ee4aab9b9` |

Full v2 hashes are recomputed by the guard from the tag on every check (the table shows the first 16 hex digits).

## Deliberately outside the freeze

- docs/ (reports, access logs, this manifest)
- benchmarks/ (harness, evaluation scripts, split.json, which has its own digest checks)
- tests/ except tests/test_measure_validation.py, .github/ (CI), .gitignore, pyproject.toml
- src/nexus/calfit.py (refits an artifact; the shipped artifact itself is frozen)
- UX modules: extension.py, session.py, magics.py, render.py, suggestions/ rules and formatting
- the Phase 8a real-notebook harness (not written yet)

## Versions

- python 3.12.5, pandas 3.1.1, numpy 2.5.5 (the dev machine)
- calibration artifact `calibration-v1` format 1 (unchanged since v1), selected candidate D+m, validated pandas 3.1, 41 fitted parameters
- machine profile format 3; curves blas32_flops, blas64_flops, copy_bps, np_sort_s, num_argsort_s, num_factorize_s, object_take_s, read_bps, text_argsort_s, text_factorize_s; reference profile id 987c455be3cc (the generic profile is it with every cost x2)

## Policy and thresholds in force

- RAM: range policy B (Tier 1 low / expected, Tier 0 high; `nexus/ranges.py`), guard (`nexus/guard.py`); cell level: `nexus/cellpeak.py` (retained outputs + current peak; v1 aggregation as the fallback)
- time: calibration artifact, nominal coverage 90% per operation (>= 8 configurations), generic band 95%; widen x3 uncalibrated machine, x2 unvalidated pandas, x3 no artifact
- risk: WARN margin 0.85, confidence floor 0.3 (unchanged; the Phase 5 R2 failure is NOT addressed); time shown as buckets
- suggestions: saving >= 20% and >= 64 MiB, `select_columns` off by default
- extension default: Tier 1 (Tier 2 dry runs opt-in with `%nexus tier 2`)
