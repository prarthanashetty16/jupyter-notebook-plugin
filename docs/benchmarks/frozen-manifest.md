# Frozen model stack `models-frozen-v3`

Written by `python -m benchmarks.frozen manifest` from `HEAD` (commit `dd029724056f`); the annotated tag `models-frozen-v3` is created on the commit that adds this file, whose frozen files are byte-identical to these. Held-out runs (multicell v2 / v3, val-v5, test-v2, Phase 8b) call `benchmarks.frozen.require_frozen()`, which compares the SHA-256 (LF line endings) of every frozen file with the tag's own copy and **aborts if any differs, is missing, or a new file matches a frozen pattern**. **Any change to a frozen file after `models-frozen-v3` invalidates the held-out status of those runs** (a new freeze, tag and held-out groups would be needed).

## History

- `models-frozen-v1` (Phase 6): time calibration, ranges, the measurement instrument (manifest: `docs/benchmarks/frozen-manifest-v1.md`)
- `models-frozen-v2` (Phase 6c): cell-level peak model, read_csv Tier 1 with sep / header, copy and fillna models, Tier 1 as the extension default (manifest: `docs/benchmarks/frozen-manifest-v2.md`)
- `models-frozen-v3` (Phase 7d): read_csv reader paths and arguments, merge output term, consolidation check, conservative rebinding release, frames created in the cell, apply(np.<ufunc>), set_index, cell-seeded sampler, risk v2 (C3) and named UNKNOWN (`docs/benchmarks/phase7b/README.md`)

## Frozen files: 9 changed, 3 added, 34 unchanged since `models-frozen-v2`

| file | status | role | sha256 models-frozen-v2 | sha256 models-frozen-v3 |
|---|---|---|---|---|
| `src/nexus/cellpeak.py` | changed | cell-level peak model (Phase 6c) | `c25633def5b3f11a` | `ca5db7274d1cc3a5` |
| `src/nexus/models/_output.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `8b6065462482c473` | `731a8a61b42c01a7` |
| `src/nexus/models/builtin.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b8c5e00870282f79` | `cced394068552b5c` |
| `src/nexus/models/merge.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1268942893fe2788` | `dce329d2a788394c` |
| `src/nexus/models/read_csv.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `9711c519a4ce37f8` | `e98bba8c152d9459` |
| `src/nexus/pipeline.py` | changed | analyze -> inspect -> models, policy and time calibration applied | `50bf49b6927a08cc` | `e73e07d422e8ff26` |
| `src/nexus/risk.py` | changed | risk-engine classes and thresholds | `5265aab5a28a5cc6` | `ea6f5f2750a1066d` |
| `src/nexus/state.py` | changed | state inspection: the descriptors the models read | `ce7405088c5b26ea` | `70408ee9240ca6e2` |
| `src/nexus/stats.py` | changed | Tier 1 statistics | `d60cb148b491ae66` | `9b31bf90afaf9bd4` |
| `src/nexus/cellframes.py` | added | frames created earlier in the cell: shape propagation / shadowing (Phase 7b) | `-` | `60a334f20379432a` |
| `src/nexus/models/explode_apply.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `f485544511ab25b3` |
| `src/nexus/models/set_index.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `431739c5ed97ad22` |
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
| `src/nexus/models/_time.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `0e2947ce188f4a03` | `0e2947ce188f4a03` |
| `src/nexus/models/_util.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `2175c4433c8f2e66` | `2175c4433c8f2e66` |
| `src/nexus/models/astype.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `489f557066bf3ee3` | `489f557066bf3ee3` |
| `src/nexus/models/base.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `069d88d7d529fa3d` | `069d88d7d529fa3d` |
| `src/nexus/models/concat.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1edb35a0fee1c3eb` | `1edb35a0fee1c3eb` |
| `src/nexus/models/copy_fillna.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `03dec0dc358ca9b4` | `03dec0dc358ca9b4` |
| `src/nexus/models/drop_duplicates.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b4a5ab4693c0e4a4` | `b4a5ab4693c0e4a4` |
| `src/nexus/models/groupby.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `44ae61ecf92e1aaa` | `44ae61ecf92e1aaa` |
| `src/nexus/models/matmul.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `145cc0f2b6e84b66` | `145cc0f2b6e84b66` |
| `src/nexus/models/noop.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `80cd6fbcc5a5ec71` | `80cd6fbcc5a5ec71` |
| `src/nexus/models/np_sort.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `38e6d4b15162d47c` | `38e6d4b15162d47c` |
| `src/nexus/models/sort_values.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7bab7e20c1f36036` | `7bab7e20c1f36036` |
| `src/nexus/ranges.py` | unchanged | RAM range policy B | `f2dcf1f242c59ccb` | `f2dcf1f242c59ccb` |
| `src/nexus/registry.py` | unchanged | model registry | `01d36368eecd118f` | `01d36368eecd118f` |
| `src/nexus/suggestions/engine.py` | unchanged | suggestion filter thresholds | `76183491336da280` | `76183491336da280` |
| `src/nexus/timebuckets.py` | unchanged | user-facing time buckets | `c4f7460065b2f784` | `c4f7460065b2f784` |
| `src/nexus/timecal.py` | unchanged | applies the time calibration artifact (ranges, flags, widening) | `5d2181104cd7efb5` | `5d2181104cd7efb5` |
| `tests/test_measure_validation.py` | unchanged | the instrument's validation (known allocations within 10%) | `4f66725ee4aab9b9` | `4f66725ee4aab9b9` |

The table shows the first 16 hex digits; the guard recomputes full hashes from the tag on every check.

## Deliberately outside the freeze

- docs/ (reports, access logs, this manifest)
- benchmarks/ (harness, evaluation scripts, split.json, which has its own digest checks)
- tests/ except tests/test_measure_validation.py, .github/ (CI), .gitignore, pyproject.toml
- src/nexus/calfit.py (refits an artifact; the shipped artifact itself is frozen)
- UX modules: extension.py, session.py, magics.py, render.py (fallback wording), suggestions/ rules and formatting
- the real-notebook harness (benchmarks/realworld/), the multicell runner and splits (benchmarks/multicell/)
- benchmarks/childproc.py, benchmarks/powerguard.py (--allow-battery: dev-only, refused for held-out runs), benchmarks/repredict.py, benchmarks/risk_eval.py (the R1-R3 replay of evaluate --val)

## Known limitations of `models-frozen-v3`

- **Determinism NOT achieved on contended machines**: the deterministic statistics gate failed its pre-registered rule (the deadline fired after admission on 12 of 29 2-core inputs, 41% > 10%) and was **reverted** to v2's adaptive gate; final code: 12 of 28 inputs flip Tier 1 / Tier 0 on 2 contended CPUs, 0 of 28 on 16 CPUs; same-tier spreads remain (drop_duplicates strings 10M ~22%, groupby 10M 0.05%).
- **Item (2) dev criterion FAILED**: 2 of 66 v1 multi-statement cells above the v3 high (copy_fillna/mixed, 88 vs 65 and 176 vs 130 MiB; an uncovered fillna on text columns); risk UNKNOWN or HIGH_RISK, never OK.
- **Uncovered**: value_counts, explode, apply with Python functions, set_index with text / several keys / append, fillna on text columns, parse_dates, text columns on the parallel read_csv path (v2 term), operations on merge / groupby / drop_duplicates results made in the cell; no column statistics carried between statements.
- **CPU-dependent read_csv path**: parallel (file >= 5 MiB and pandas' worker count > 1; affinity / cgroup on Linux only) or serial; the same call can get another estimate on another machine.
- **One laptop, synthetic data**: every probe and dev figure comes from one Windows 11 laptop and synthetic frames (plus two dev notebooks); Linux only through the planned val-v5 VM run.
- **Supported environment**: pandas >= 3.1 (Python >= 3.11) on Windows and Linux. Models and the instrument's validation assume pandas 3 copy-on-write (Python 3.10 resolves pandas 2.x: unsupported, report-only in CI); on macOS the instrument cannot isolate an operation's peak (report-only in CI). Derived from pandas 3.1.1 only.
- **R2 is a dev selection**: risk v2 (C3) was selected on dev by a rule written beforehand (dev R2 pooled 17.1%, merge 9.4%, read_csv 39.0%); it is a claim only if val-v5 confirms it.

## Versions

- python 3.12.5, pandas 3.1.1, numpy 2.5.5 (the dev machine)
- calibration artifact `calibration-v1` format 1 (unchanged since v1), selected candidate D+m, validated pandas 3.1, 41 fitted parameters
- machine profile format 3; curves blas32_flops, blas64_flops, copy_bps, np_sort_s, num_argsort_s, num_factorize_s, object_take_s, read_bps, text_argsort_s, text_factorize_s; reference profile id 987c455be3cc (the generic profile is it with every cost x2)

## Policy and thresholds in force

- RAM: range policy B (Tier 1 low / expected, Tier 0 high; `nexus/ranges.py`, unchanged), guard (`nexus/guard.py`, unchanged); cell level: `nexus/cellpeak.py` (retained outputs + current peak, conservative rebinding release)
- time: calibration artifact, nominal coverage 90% per operation (>= 8 configurations), generic band 95%; widen x3 uncalibrated machine, x2 unvalidated pandas, x3 no artifact
- risk: WARN margin 0.85, confidence floor 0.3 (unchanged); risk v2: WARN on the own Tier 1 high for merge, read_csv when statistics ran; time shown as buckets
- suggestions: saving >= 20% and >= 64 MiB, `select_columns` off by default
- extension default: Tier 1 (Tier 2 dry runs opt-in with `%nexus tier 2`)
