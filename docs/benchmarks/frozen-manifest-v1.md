# Frozen model stack `models-frozen-v1`

Tag `models-frozen-v1` = commit `c3e3ee0def91d601127c77ed9e5883af8636e9c5` (Phase 6; unchanged). Written by `python -m benchmarks.frozen manifest`. Held-out runs (val-v5, the Phase 8a real-notebook test, test-v2) call `benchmarks.frozen.require_frozen()`, which compares the SHA-256 (LF line endings) of every file listed below with the tag's own copy and **aborts if any of them differs, is missing, or a new file matches a frozen pattern**. **Any change to a frozen file invalidates their held-out status** (a new freeze, tag and held-out group would be needed).

## Scope narrowed after the tag (Phase 6b, 2026-11-21)

At the tag the guard compared every tracked file outside `docs/` with the tag, so an unrelated `.gitignore` line, a CI change or a new evaluation harness (Phase 8a) would have aborted the held-out runs or forced a new freeze. Phase 6b narrowed the check to the files that define the predictions. The tagged commit was not changed and **no frozen file changed**: at the time this manifest was written,

```
git diff --stat models-frozen-v1 -- <the 40 frozen files below>
(empty: no difference)
```

and `python -m benchmarks.frozen check` reported 0 problems.

## Scope extended (Phase 6b, 2026-11-21)

Added to the frozen set after the tag, at the user's request, so that a held-out run also aborts when the measurement instrument behind its actuals changed: `src/nexus/measure.py` and its validation test `tests/test_measure_validation.py`. Both are compared with the tag's copies like every other frozen file; at the time of the extension neither differed from the tag (`git diff models-frozen-v1 -- src/nexus/measure.py tests/test_measure_validation.py` empty) and the original frozen files were still unchanged (the `git diff` above).

## Deliberately outside the freeze

- docs/ (reports, access logs, this manifest)
- benchmarks/ (harness, evaluation scripts, split.json, which has its own digest checks)
- tests/ except tests/test_measure_validation.py, .github/ (CI), .gitignore, pyproject.toml
- src/nexus/calfit.py (refits an artifact; the shipped artifact itself is frozen)
- UX modules: extension.py, session.py, magics.py, render.py, suggestions/ rules and formatting
- the Phase 8a real-notebook harness (not written yet)

## Versions

- python 3.12.5, pandas 3.1.1, numpy 2.5.5 (the dev machine)
- calibration artifact `calibration-v1` format 1, created 2026-11-18 at commit b385fe1, selected candidate D+m, validated pandas 3.1, data benchmarks/results/phase6-dev-mains (sha256/16 c1bfbe8a39314dbb), 41 fitted parameters
- machine profile format 3; curves blas32_flops, blas64_flops, copy_bps, np_sort_s, num_argsort_s, num_factorize_s, object_take_s, read_bps, text_argsort_s, text_factorize_s; reference profile id 987c455be3cc (the generic profile is it with every cost x2)

## Policy and thresholds in force

- RAM: range policy B (Tier 1 low / expected, Tier 0 high; `nexus/ranges.py`), guard (`nexus/guard.py`)
- time: calibration artifact, nominal coverage 90% per operation (>= 8 configurations), generic band 95%; widen x3 uncalibrated machine, x2 unvalidated pandas, x3 no artifact
- risk: WARN margin 0.85, confidence floor 0.3; time shown as buckets
- suggestions: saving >= 20% and >= 64 MiB, `select_columns` off by default
- Tier 2: opt-in (`Pipeline(tier=2)`), controller rules of docs/benchmarks/phase4d-preregistration.md

## Frozen files (40; hashes of the tag's copies)

| file | role | sha256 |
|---|---|---|
| `src/nexus/_dryrun_child.py` | Tier 2 sandbox child | `7dbf5fcb348509c2d7ebe7c921306aea778c7035b14827a306d460e85b0a54b9` |
| `src/nexus/analyzer.py` | which operations a cell contains (what gets estimated) | `3ff34432d187fe9bf4783bd549f241816e8d3532aac107838d8d6d1cf24eb4e1` |
| `src/nexus/calibrate.py` | what the machine profile measures | `07be83e4ba943f8469757901e994b9e6e6c5903a7e2cf7836465668d4088f399` |
| `src/nexus/calibration/calibration-v1.json` | calibration artifact and reference machine profile | `5d1ac0809b5d4285d4e18ae485420e4d326c4eaf569a2cf1fa689395a70a5464` |
| `src/nexus/calibration/reference_machine.json` | calibration artifact and reference machine profile | `b481efef6901467720ee9ab0d0f90c2fe8addd11475acd33bbb21a230900d23b` |
| `src/nexus/controller.py` | Tier 2 controller rules and thresholds | `269539502b5e9c0dc0d36c0dfcdcc3a23f58849b8b5650f450210ad96532c19e` |
| `src/nexus/dryrun.py` | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `dbb6f554212911bf556881837c9cd86b22e39e4e08dc097e861b957a5f2dcfe7` |
| `src/nexus/dryrun_fit.py` | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `b08ce264d96a3ef1cbee1a6d462e6c5ea43e3faddad8e4422da4839d91d1e180` |
| `src/nexus/dryrun_io.py` | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `d0488477ba114a37659536978f4ccc65eec81b02ccb8a213768aee922fcc797f` |
| `src/nexus/dryrun_safety.py` | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `73b68265756cd9b983490b73e94e894d2d2cc14d0cab9502f8816fe874f4bc28` |
| `src/nexus/dryrun_sample.py` | Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits | `0a9fbfda21759f5aa61950f8adfd558ec2ba7b636d3af5aa568a3fa4f7937b54` |
| `src/nexus/failsafe.py` | deadlines: the Tier 1 time budget | `a7bc6be6b4fe7b5e805e260cc5b4d46d5c2e8c1424e0859d3081e71f2d4d310e` |
| `src/nexus/guard.py` | Tier 1 sanity guard | `0664a1e1db1546d4e5d61c823cebc558791687230bf85117fa734dcdf2d9366f` |
| `src/nexus/machine.py` | machine profile format 3 and the generic profile | `12c123c2b8e81e20bb11baf71c46287a01e04416d56c4135163e557fdb4c9800` |
| `src/nexus/measure.py` | the measurement instrument (peak RAM, time) of every held-out actual (added 2026-11-21) | `7931d7b0e596edc8b646ec8ec1bb5e79ed96754f9776cadd1c3576ce35be4ade` |
| `src/nexus/models/__init__.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7e5c45ec3a81ff92a909a77f94b6a86dd41662a22d226e310c6b83e9477ad161` |
| `src/nexus/models/_time.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `ddc2261e26807122d50bec5b4c3c39d86e59a4cde90f1e35f394182da135fc25` |
| `src/nexus/models/_util.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `2175c4433c8f2e66596362c17c9c061229d0610945cadd0d46204a449c686e69` |
| `src/nexus/models/astype.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `489f557066bf3ee3a7511843029c5b5511ad4b46504446f3a23a474e34cd5268` |
| `src/nexus/models/base.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `069d88d7d529fa3d1500f238d5f9dd1107662d076c0a12c867fb14fefd4aad5e` |
| `src/nexus/models/builtin.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `682d9ea063d65e1d1e35a3e609d6c6a8c0a199fe594f339371cce8f66c9e7066` |
| `src/nexus/models/concat.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1edb35a0fee1c3eb57b3b7330e40ab5e02996fb1a4bed33b42d8ec18f40248cb` |
| `src/nexus/models/drop_duplicates.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b4a5ab4693c0e4a41a1cb2b3a56b6d1f8ebf56b2b4794458397972c31f95f094` |
| `src/nexus/models/groupby.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `44ae61ecf92e1aaa9df83d245926f3e48aaf22d0061a1e5ba9db75de0f2d7ed2` |
| `src/nexus/models/matmul.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `145cc0f2b6e84b6624d249b93b6ddcc5037948f9ed0a6d36d1d0bdaed2fa489e` |
| `src/nexus/models/merge.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `1268942893fe2788d2372b0344a487666448632a495e367decfa31275aa34ad3` |
| `src/nexus/models/noop.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `80cd6fbcc5a5ec71f3c212f83cbb62ad150dc1f3221c7a07dc19800fd401b1f7` |
| `src/nexus/models/np_sort.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `38e6d4b15162d47c50165786bbfa23d814fef13961144d59698d48cc7f9c01b9` |
| `src/nexus/models/read_csv.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `b099bb8c65603aae44b9462dc60075956b11a3c16997d24623556a95bd358888` |
| `src/nexus/models/sort_values.py` | operation models: Tier 0 / Tier 1 RAM and the derived time terms | `7bab7e20c1f36036899599a7afc4eff4602c730865d3c6485f4b60db69f01892` |
| `src/nexus/pipeline.py` | analyze -> inspect -> models, policy and time calibration applied | `093028d712d5c07bab5a4f726196023c69e4d5636de72dfd27a2d355496e46af` |
| `src/nexus/ranges.py` | RAM range policy B | `f2dcf1f242c59ccb89b78b66e603508a2899ec5963e445c3867ba2b915f7179a` |
| `src/nexus/registry.py` | model registry | `01d36368eecd118fd5695e379d4cab4bf0191fc984319dd6fb38fd824c77556a` |
| `src/nexus/risk.py` | risk-engine classes and thresholds | `1b0008159d6d486a1afefd832d086cb58524bcc0db68b9b40076ac252b383d57` |
| `src/nexus/state.py` | state inspection: the descriptors the models read | `ce7405088c5b26ea71ce486002ccfd02e49fa734f573a7b0c54910865a8c935d` |
| `src/nexus/stats.py` | Tier 1 statistics | `b10e7987db6a9c3799877a8d2d8e5f567478ae7548c361a07ea9ad994df4e8f1` |
| `src/nexus/suggestions/engine.py` | suggestion filter thresholds | `76183491336da2807ab71acd95424ade16d2c8284e7204f96995e64fc59d304e` |
| `src/nexus/timebuckets.py` | user-facing time buckets | `c4f7460065b2f78421e9d64ae308b820208d04817fd4b51d825b4fb52a9510df` |
| `src/nexus/timecal.py` | applies the time calibration artifact (ranges, flags, widening) | `5d2181104cd7efb5d9926fab3b536e11c4ae0a6ee536a9ecf1c1147079f746b4` |
| `tests/test_measure_validation.py` | the instrument's validation (known allocations within 10%) (added 2026-11-21) | `4f66725ee4aab9b912a6c64955692d6806e8af0b9aae8738dec05f499d02d660` |
