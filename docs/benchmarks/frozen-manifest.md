# Frozen model stack `models-frozen-v4`

Written by `python -m benchmarks.frozen manifest` from `HEAD` (commit `8d3a4f0b6c36`); the annotated tag `models-frozen-v4` is on the commit containing this manifest, whose frozen files are byte-identical to these. Held-out runs (multicell v2 / v3 / v4, val-v5, test-v2, Phase 8b) call `benchmarks.frozen.require_frozen()`, which compares the SHA-256 (LF line endings) of every frozen file with the tag's own copy and **aborts if any differs, is missing, or a new file matches a frozen pattern**. **Any change to a frozen file after `models-frozen-v4` invalidates the held-out status of those runs** (a new freeze, tag and held-out groups would be needed).

## History

- `models-frozen-v1` (Phase 6): time calibration, ranges, the measurement instrument (manifest: `docs/benchmarks/frozen-manifest-v1.md`)
- `models-frozen-v2` (Phase 6c): cell-level peak model, read_csv Tier 1 with sep / header, copy and fillna models, Tier 1 as the extension default (manifest: `docs/benchmarks/frozen-manifest-v2.md`)
- `models-frozen-v3` (Phase 7d): read_csv reader paths and arguments, merge output term, consolidation check, conservative rebinding release, frames created in the cell, apply(np.<ufunc>), set_index, cell-seeded sampler, risk v2 (C3) and named UNKNOWN (manifest: `docs/benchmarks/frozen-manifest-v3.md`; `docs/benchmarks/phase7b/README.md`)
- `models-frozen-v4` (Phase 8): derived operation additions and explicit no-estimate cases, calibrated RAM high (`calibration/upper-v1.json`), cell-seeded sampler, Tier 0 fallback on cooperative Tier 1 deadlines, and partial cell lower-bound display (`docs/benchmarks/phase8-preregistration.md`)

## Frozen files: 15 changed, 4 added, 31 unchanged since `models-frozen-v3`

| file | status | role | sha256 models-frozen-v3 | sha256 models-frozen-v4 |
|---|---|---|---|---|
| `src/nexus/cellframes.py` | changed | frames created earlier in the cell: shape propagation / shadowing (Phase 7b) | `60a334f20379432a31530c0234a35c0b1e95cf837395c41d8e561404fab4b149` | `1f7650a583b25bb83e9a5ced7cc12669474c96a61d06699e0cb65f33c1f9a16b` |
| `src/nexus/cellpeak.py` | changed | cell-level peak model (Phase 6c) | `ca5db7274d1cc3a521a27e05e47188bd25b0165769d2e47038c320cff212ece4` | `535e9d7d24598bcded13f573ec96e5b5be7711cd6cf467719780b5b1a418db38` |
| `src/nexus/models/_output.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `731a8a61b42c01a71273b87fa367037cee267337595eaf68228da9af3b7ae67e` | `b921a1aaaf85e255774fb2776c4c2ac2bc0219cd3e442ea78d67c4e39244bf72` |
| `src/nexus/models/astype.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `489f557066bf3ee3a7511843029c5b5511ad4b46504446f3a23a474e34cd5268` | `79d30b077796b116390d70a8cd4c3442efe81f5a4ff870aecc8c4b22093abe75` |
| `src/nexus/models/base.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `069d88d7d529fa3d1500f238d5f9dd1107662d076c0a12c867fb14fefd4aad5e` | `d71565af487455f1595620dc8017a9a1a3567dbf09c7c3d3a9f6389e58cfd429` |
| `src/nexus/models/builtin.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `cced394068552b5cf5523aa4f4caa8149f938cb346085ba9fff266e9d7e0039d` | `1654b4932e9553dfdf11db604d933919e0eea2ce889ebfdd735f15e49077248e` |
| `src/nexus/models/concat.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1edb35a0fee1c3eb57b3b7330e40ab5e02996fb1a4bed33b42d8ec18f40248cb` | `19ca4a0d07fd34b0eb9b00d04dcb1dea2d729c043f233f0d4a19f28b297c5c54` |
| `src/nexus/models/copy_fillna.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `03dec0dc358ca9b400d864310b8ff7af59d91ab6228359b17c91a7cc7a4c9bf6` | `59bbe9bf5a6895fc963157a717f1a0a0ddd3888dbf02c07e8d82e3b58915aca4` |
| `src/nexus/models/drop_duplicates.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b4a5ab4693c0e4a41a1cb2b3a56b6d1f8ebf56b2b4794458397972c31f95f094` | `e83553c7a0a0e987bc90524fa5304b4b4e421f5b68d6d9ca3f7399d259cb206d` |
| `src/nexus/models/groupby.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `44ae61ecf92e1aaa9df83d245926f3e48aaf22d0061a1e5ba9db75de0f2d7ed2` | `a3af8c2c10df25d7a00b2104d0e8e69fdedf19623ed54e169eec48a9b486df2c` |
| `src/nexus/models/read_csv.py` | changed | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `e98bba8c152d94594fde2c6ca6a44726e227372c2e299f5bc59c8e6fd2492171` | `e9897dec10644da9aea2d992b73678faa264e8735e9e4a05737bbbc5cce1920c` |
| `src/nexus/pipeline.py` | changed | analyze -> inspect -> models, policy and time calibration applied | `e73e07d422e8ff26b8cd7eb83b7d5ce69a0d3cebe592dfe02004a15192cf145e` | `c17c908e90a31d4fb4d6b210292d878e76acbd7f9a341eeef6ff34cfe6403704` |
| `src/nexus/risk.py` | changed | risk-engine classes and thresholds | `ea6f5f2750a1066dea50da4dcb8f882a5088deb05920734b4721d7e427bbaf4a` | `589ed754bd8a4b9fda530fab6b21a7f2384376d193e77880b86d4e004c2026f6` |
| `src/nexus/state.py` | changed | state inspection: the descriptors the models read | `70408ee9240ca6e2e4dd33a33c4506e93fd08149e64b8f172a0188377d54fba5` | `af161b0dc261dd40c68ef0aa24e7ef6839e2e70ceb7f5a0a99982533d5c7f662` |
| `src/nexus/stats.py` | changed | Tier 1 statistics | `9b31bf90afaf9bd4218849c40797a3a25ee1227dba539e3f290bf44bfd2747dc` | `d4a364fd53169ec124ee93db23082a7362f7338cacab6c98b5894e66e87a2ee8` |
| `src/nexus/calibration/upper-v1.json` | added | calibration artifact and reference machine profile | `-` | `b224abadce10b37d919d70f572eab45171f531ce8c7c026ce8b16edbbf0f9195` |
| `src/nexus/models/dropna.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `6e7e2aa0c6bd79299cbfc40e9fda9589e7bab427e8ac0768ba83dbad3dd5bb25` |
| `src/nexus/models/v4_easy.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `c557994cb87f1acedccbf62a0770f583a10fa4456f13f9f237fb404ad150456a` |
| `src/nexus/models/v4_outputs.py` | added | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `-` | `70e627d87c0a8a5ae6359deafb5376bc9ea144ee3bb63c25547f87700c064e35` |
| `src/nexus/_dryrun_child.py` | unchanged | Tier 2 sandbox child | `7dbf5fcb348509c2d7ebe7c921306aea778c7035b14827a306d460e85b0a54b9` | `7dbf5fcb348509c2d7ebe7c921306aea778c7035b14827a306d460e85b0a54b9` |
| `src/nexus/analyzer.py` | unchanged | which operations a cell contains (what gets estimated) | `3ff34432d187fe9bf4783bd549f241816e8d3532aac107838d8d6d1cf24eb4e1` | `3ff34432d187fe9bf4783bd549f241816e8d3532aac107838d8d6d1cf24eb4e1` |
| `src/nexus/calibrate.py` | unchanged | what the machine profile measures | `07be83e4ba943f8469757901e994b9e6e6c5903a7e2cf7836465668d4088f399` | `07be83e4ba943f8469757901e994b9e6e6c5903a7e2cf7836465668d4088f399` |
| `src/nexus/calibration/calibration-v1.json` | unchanged | calibration artifact and reference machine profile | `5d1ac0809b5d4285d4e18ae485420e4d326c4eaf569a2cf1fa689395a70a5464` | `5d1ac0809b5d4285d4e18ae485420e4d326c4eaf569a2cf1fa689395a70a5464` |
| `src/nexus/calibration/reference_machine.json` | unchanged | calibration artifact and reference machine profile | `b481efef6901467720ee9ab0d0f90c2fe8addd11475acd33bbb21a230900d23b` | `b481efef6901467720ee9ab0d0f90c2fe8addd11475acd33bbb21a230900d23b` |
| `src/nexus/controller.py` | unchanged | Tier 2 controller rules and thresholds | `269539502b5e9c0dc0d36c0dfcdcc3a23f58849b8b5650f450210ad96532c19e` | `269539502b5e9c0dc0d36c0dfcdcc3a23f58849b8b5650f450210ad96532c19e` |
| `src/nexus/dryrun.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `dbb6f554212911bf556881837c9cd86b22e39e4e08dc097e861b957a5f2dcfe7` | `dbb6f554212911bf556881837c9cd86b22e39e4e08dc097e861b957a5f2dcfe7` |
| `src/nexus/dryrun_fit.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `b08ce264d96a3ef1cbee1a6d462e6c5ea43e3faddad8e4422da4839d91d1e180` | `b08ce264d96a3ef1cbee1a6d462e6c5ea43e3faddad8e4422da4839d91d1e180` |
| `src/nexus/dryrun_io.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `d0488477ba114a37659536978f4ccc65eec81b02ccb8a213768aee922fcc797f` | `d0488477ba114a37659536978f4ccc65eec81b02ccb8a213768aee922fcc797f` |
| `src/nexus/dryrun_safety.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `73b68265756cd9b983490b73e94e894d2d2cc14d0cab9502f8816fe874f4bc28` | `73b68265756cd9b983490b73e94e894d2d2cc14d0cab9502f8816fe874f4bc28` |
| `src/nexus/dryrun_sample.py` | unchanged | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `0a9fbfda21759f5aa61950f8adfd558ec2ba7b636d3af5aa568a3fa4f7937b54` | `0a9fbfda21759f5aa61950f8adfd558ec2ba7b636d3af5aa568a3fa4f7937b54` |
| `src/nexus/failsafe.py` | unchanged | deadlines: the Tier 1 time budget | `a7bc6be6b4fe7b5e805e260cc5b4d46d5c2e8c1424e0859d3081e71f2d4d310e` | `a7bc6be6b4fe7b5e805e260cc5b4d46d5c2e8c1424e0859d3081e71f2d4d310e` |
| `src/nexus/guard.py` | unchanged | Tier 1 sanity guard | `0664a1e1db1546d4e5d61c823cebc558791687230bf85117fa734dcdf2d9366f` | `0664a1e1db1546d4e5d61c823cebc558791687230bf85117fa734dcdf2d9366f` |
| `src/nexus/machine.py` | unchanged | machine profile format 3 and the generic profile | `12c123c2b8e81e20bb11baf71c46287a01e04416d56c4135163e557fdb4c9800` | `12c123c2b8e81e20bb11baf71c46287a01e04416d56c4135163e557fdb4c9800` |
| `src/nexus/measure.py` | unchanged | the measurement instrument (peak RAM, time) of every held-out actual | `7931d7b0e596edc8b646ec8ec1bb5e79ed96754f9776cadd1c3576ce35be4ade` | `7931d7b0e596edc8b646ec8ec1bb5e79ed96754f9776cadd1c3576ce35be4ade` |
| `src/nexus/models/__init__.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7e5c45ec3a81ff92a909a77f94b6a86dd41662a22d226e310c6b83e9477ad161` | `7e5c45ec3a81ff92a909a77f94b6a86dd41662a22d226e310c6b83e9477ad161` |
| `src/nexus/models/_time.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `0e2947ce188f4a0398fa71914d971ca362ffe4487fda953691f6546e18413bb6` | `0e2947ce188f4a0398fa71914d971ca362ffe4487fda953691f6546e18413bb6` |
| `src/nexus/models/_util.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `2175c4433c8f2e66596362c17c9c061229d0610945cadd0d46204a449c686e69` | `2175c4433c8f2e66596362c17c9c061229d0610945cadd0d46204a449c686e69` |
| `src/nexus/models/explode_apply.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `f485544511ab25b3cbe9e1eb5049317d24fe3c11c5bb1f107ec60cd7414f72b2` | `f485544511ab25b3cbe9e1eb5049317d24fe3c11c5bb1f107ec60cd7414f72b2` |
| `src/nexus/models/matmul.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `145cc0f2b6e84b6624d249b93b6ddcc5037948f9ed0a6d36d1d0bdaed2fa489e` | `145cc0f2b6e84b6624d249b93b6ddcc5037948f9ed0a6d36d1d0bdaed2fa489e` |
| `src/nexus/models/merge.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `dce329d2a788394c46cde22313d931a79fe17c6adbb4a8345f67fb8fbc71813b` | `dce329d2a788394c46cde22313d931a79fe17c6adbb4a8345f67fb8fbc71813b` |
| `src/nexus/models/noop.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `80cd6fbcc5a5ec71f3c212f83cbb62ad150dc1f3221c7a07dc19800fd401b1f7` | `80cd6fbcc5a5ec71f3c212f83cbb62ad150dc1f3221c7a07dc19800fd401b1f7` |
| `src/nexus/models/np_sort.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `38e6d4b15162d47c50165786bbfa23d814fef13961144d59698d48cc7f9c01b9` | `38e6d4b15162d47c50165786bbfa23d814fef13961144d59698d48cc7f9c01b9` |
| `src/nexus/models/set_index.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `431739c5ed97ad221252633cadcf182b9dc5ce8a7e914b55bb8c7aee63eaa8ef` | `431739c5ed97ad221252633cadcf182b9dc5ce8a7e914b55bb8c7aee63eaa8ef` |
| `src/nexus/models/sort_values.py` | unchanged | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7bab7e20c1f36036899599a7afc4eff4602c730865d3c6485f4b60db69f01892` | `7bab7e20c1f36036899599a7afc4eff4602c730865d3c6485f4b60db69f01892` |
| `src/nexus/ranges.py` | unchanged | RAM range policy B | `f2dcf1f242c59ccb89b78b66e603508a2899ec5963e445c3867ba2b915f7179a` | `f2dcf1f242c59ccb89b78b66e603508a2899ec5963e445c3867ba2b915f7179a` |
| `src/nexus/registry.py` | unchanged | model registry | `01d36368eecd118fd5695e379d4cab4bf0191fc984319dd6fb38fd824c77556a` | `01d36368eecd118fd5695e379d4cab4bf0191fc984319dd6fb38fd824c77556a` |
| `src/nexus/suggestions/engine.py` | unchanged | suggestion filter thresholds | `76183491336da2807ab71acd95424ade16d2c8284e7204f96995e64fc59d304e` | `76183491336da2807ab71acd95424ade16d2c8284e7204f96995e64fc59d304e` |
| `src/nexus/timebuckets.py` | unchanged | user-facing time buckets | `c4f7460065b2f78421e9d64ae308b820208d04817fd4b51d825b4fb52a9510df` | `c4f7460065b2f78421e9d64ae308b820208d04817fd4b51d825b4fb52a9510df` |
| `src/nexus/timecal.py` | unchanged | applies the time calibration artifact (ranges, flags, widening) | `5d2181104cd7efb5d9926fab3b536e11c4ae0a6ee536a9ecf1c1147079f746b4` | `5d2181104cd7efb5d9926fab3b536e11c4ae0a6ee536a9ecf1c1147079f746b4` |
| `tests/test_measure_validation.py` | unchanged | the instrument's validation (known allocations within 10%) | `4f66725ee4aab9b912a6c64955692d6806e8af0b9aae8738dec05f499d02d660` | `4f66725ee4aab9b912a6c64955692d6806e8af0b9aae8738dec05f499d02d660` |

The table shows full SHA-256 hashes after normalizing line endings to LF; the guard recomputes them from the tag on every check.

## Deliberately outside the freeze

- docs/ (reports, access logs, this manifest)
- benchmarks/ (harness, evaluation scripts, split.json, which has its own digest checks)
- tests/ except tests/test_measure_validation.py, .github/ (CI), .gitignore, pyproject.toml
- src/nexus/calfit.py (refits an artifact; the shipped artifact itself is frozen)
- UX modules: extension.py, session.py, magics.py, render.py (fallback wording), suggestions/ rules and formatting
- the real-notebook harness (benchmarks/realworld/), the multicell runner and splits (benchmarks/multicell/)
- benchmarks/childproc.py, benchmarks/powerguard.py (--allow-battery: dev-only, refused for held-out runs), benchmarks/repredict.py, benchmarks/risk_eval.py (the R1-R3 replay of evaluate --val)

## Known limitations of `models-frozen-v4`

- **T. Tier 1/Tier 0 selection independent of wall-clock time: FAILED.** The preregistered check recorded 79/84 firings on 2 contended cores and 28/84 idle. The later information-only repeats recorded 48/84, 31/84 and 30/84 contended (109/252 pooled), and 44/84 idle; all exceed the <=5% contended and 0% idle bars. Cooperative deadline firings visibly fall back to Tier 0, retain its high under policy B, and count as not estimated.
- **Runtime coverage criterion FAILED**: 14/75 operation-bearing cells (18.7%) had every operation estimated, below the preregistered 55% target; the earlier 15/74 figure was superseded by the full run.
- **Coverage remains narrow**: adopted v4 additions include text fillna, copy-through-fillna, five copy receiver forms, dropna, and known numeric ndarray numpy.array(copy=True); unsupported receiver forms and unknown operations remain unestimated rather than guessed.
- **Partial cells**: the display is a lower bound for covered operations only (`at least X`, covers k of n); it has no upper bound for the whole cell. Partial risk remains UNKNOWN/HIGH_RISK and is not an OK or above-high claim.
- **Tier 1 hard-deadline fallback share**: in the stored idle prediction-only rerun, firings were 11/39 (28.2%) at 1M rows, 9/21 (42.9%) at 3M, and 24/24 (100%) at 10M. These are one laptop's dev inputs, not a population rate.
- **CPU-dependent `read_csv` path**: pandas may select serial or parallel parsing based on the input and available CPU/worker count; the same call can follow different model paths on different machines.
- **Deferred operations and reasons**: `value_counts` and `duplicated` depend on key-specific hash-table page residency; `reset_index`'s derivation was invalid because its formula followed the probe; `Series.map` exceeded the derivation bar due to mapper workspace; zero-copy `to_numpy` has no measurable incremental peak; dict/multi-column `astype` over-counts same-dtype targets; `read_csv(parse_dates=...)` reduced peak memory, contradicting the additive term; `numpy.zeros`/`empty` expose lazy pages with no measurable incremental peak; `linspace`'s float32 case used three live arrays; `sample` needs random-index workspace; `describe` has unmodelled numeric workspace and a censored string case. Python-function `apply`/`map`, `to_csv`, `join`, `get_dummies`, and `corr` remain explicitly named unknowns because no model was derived.
- **One developer machine and synthetic data**: derivations and dev evaluation use one Windows laptop; val-v5, test-v2, multicell v4, and the fresh Phase 8b held-out notebooks remain sealed and unrun.
- **Supported environment**: derived and validated with pandas 3.1.1 on Windows and Linux only. Python 3.10 resolves pandas 2.x and is unsupported; macOS is unvalidated/report-only for peak measurement.
- **Tier 2 is not a general fallback**: it remains opt-in for qualifying safe operations; coverage gaps still produce no estimate. General sandboxed extrapolation is a v5 direction, not part of this freeze.

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
