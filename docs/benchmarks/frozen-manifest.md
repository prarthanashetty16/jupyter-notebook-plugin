# Frozen model stack `models-frozen-v1`

Written by `python -m benchmarks.frozen manifest` at the freeze. Held-out runs (val-v5, the Phase 8a real-notebook test, test-v2) check out this tag and abort if the tracked files outside `docs/` differ from it (`benchmarks/frozen.py`). **Any model change after the freeze invalidates their held-out status.** Hashes are SHA-256 of the file with LF line endings.

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

## File hashes

| file | sha256 |
|---|---|
| `benchmarks/split.json` | `a4714e6943a6e580e5f92228b0d206a53f604d2d17fabfa312726c04d4eda10e` |
| `src/nexus/_dryrun_child.py` | `7dbf5fcb348509c2d7ebe7c921306aea778c7035b14827a306d460e85b0a54b9` |
| `src/nexus/analyzer.py` | `3ff34432d187fe9bf4783bd549f241816e8d3532aac107838d8d6d1cf24eb4e1` |
| `src/nexus/calfit.py` | `640259c6c45ce75ec98c16e9e2c351f15fd9389d18d158b257c5d0e84d1cb7f6` |
| `src/nexus/calibrate.py` | `07be83e4ba943f8469757901e994b9e6e6c5903a7e2cf7836465668d4088f399` |
| `src/nexus/calibration/calibration-v1.json` | `5d1ac0809b5d4285d4e18ae485420e4d326c4eaf569a2cf1fa689395a70a5464` |
| `src/nexus/calibration/reference_machine.json` | `b481efef6901467720ee9ab0d0f90c2fe8addd11475acd33bbb21a230900d23b` |
| `src/nexus/controller.py` | `269539502b5e9c0dc0d36c0dfcdcc3a23f58849b8b5650f450210ad96532c19e` |
| `src/nexus/dryrun.py` | `dbb6f554212911bf556881837c9cd86b22e39e4e08dc097e861b957a5f2dcfe7` |
| `src/nexus/dryrun_fit.py` | `b08ce264d96a3ef1cbee1a6d462e6c5ea43e3faddad8e4422da4839d91d1e180` |
| `src/nexus/dryrun_io.py` | `d0488477ba114a37659536978f4ccc65eec81b02ccb8a213768aee922fcc797f` |
| `src/nexus/dryrun_safety.py` | `73b68265756cd9b983490b73e94e894d2d2cc14d0cab9502f8816fe874f4bc28` |
| `src/nexus/dryrun_sample.py` | `0a9fbfda21759f5aa61950f8adfd558ec2ba7b636d3af5aa568a3fa4f7937b54` |
| `src/nexus/guard.py` | `0664a1e1db1546d4e5d61c823cebc558791687230bf85117fa734dcdf2d9366f` |
| `src/nexus/machine.py` | `12c123c2b8e81e20bb11baf71c46287a01e04416d56c4135163e557fdb4c9800` |
| `src/nexus/measure.py` | `7931d7b0e596edc8b646ec8ec1bb5e79ed96754f9776cadd1c3576ce35be4ade` |
| `src/nexus/models/__init__.py` | `7e5c45ec3a81ff92a909a77f94b6a86dd41662a22d226e310c6b83e9477ad161` |
| `src/nexus/models/_time.py` | `ddc2261e26807122d50bec5b4c3c39d86e59a4cde90f1e35f394182da135fc25` |
| `src/nexus/models/_util.py` | `2175c4433c8f2e66596362c17c9c061229d0610945cadd0d46204a449c686e69` |
| `src/nexus/models/astype.py` | `489f557066bf3ee3a7511843029c5b5511ad4b46504446f3a23a474e34cd5268` |
| `src/nexus/models/base.py` | `069d88d7d529fa3d1500f238d5f9dd1107662d076c0a12c867fb14fefd4aad5e` |
| `src/nexus/models/builtin.py` | `682d9ea063d65e1d1e35a3e609d6c6a8c0a199fe594f339371cce8f66c9e7066` |
| `src/nexus/models/concat.py` | `1edb35a0fee1c3eb57b3b7330e40ab5e02996fb1a4bed33b42d8ec18f40248cb` |
| `src/nexus/models/drop_duplicates.py` | `b4a5ab4693c0e4a41a1cb2b3a56b6d1f8ebf56b2b4794458397972c31f95f094` |
| `src/nexus/models/groupby.py` | `44ae61ecf92e1aaa9df83d245926f3e48aaf22d0061a1e5ba9db75de0f2d7ed2` |
| `src/nexus/models/matmul.py` | `145cc0f2b6e84b6624d249b93b6ddcc5037948f9ed0a6d36d1d0bdaed2fa489e` |
| `src/nexus/models/merge.py` | `1268942893fe2788d2372b0344a487666448632a495e367decfa31275aa34ad3` |
| `src/nexus/models/noop.py` | `80cd6fbcc5a5ec71f3c212f83cbb62ad150dc1f3221c7a07dc19800fd401b1f7` |
| `src/nexus/models/np_sort.py` | `38e6d4b15162d47c50165786bbfa23d814fef13961144d59698d48cc7f9c01b9` |
| `src/nexus/models/read_csv.py` | `b099bb8c65603aae44b9462dc60075956b11a3c16997d24623556a95bd358888` |
| `src/nexus/models/sort_values.py` | `7bab7e20c1f36036899599a7afc4eff4602c730865d3c6485f4b60db69f01892` |
| `src/nexus/pipeline.py` | `093028d712d5c07bab5a4f726196023c69e4d5636de72dfd27a2d355496e46af` |
| `src/nexus/ranges.py` | `f2dcf1f242c59ccb89b78b66e603508a2899ec5963e445c3867ba2b915f7179a` |
| `src/nexus/risk.py` | `1b0008159d6d486a1afefd832d086cb58524bcc0db68b9b40076ac252b383d57` |
| `src/nexus/state.py` | `ce7405088c5b26ea71ce486002ccfd02e49fa734f573a7b0c54910865a8c935d` |
| `src/nexus/stats.py` | `b10e7987db6a9c3799877a8d2d8e5f567478ae7548c361a07ea9ad994df4e8f1` |
| `src/nexus/suggestions/__init__.py` | `55ee17e063440286939172228314f88c9460d0f2ee1fd613c0f272c72606897a` |
| `src/nexus/suggestions/base.py` | `6f65b597533330cfcd06e22738186f8c7278daaf1f0807c9e08623fc2cad2c54` |
| `src/nexus/suggestions/engine.py` | `76183491336da2807ab71acd95424ade16d2c8284e7204f96995e64fc59d304e` |
| `src/nexus/suggestions/format.py` | `0611daa66337f892e579ba9f8e66df34e04ed4e10d9ed816c06419af25627453` |
| `src/nexus/suggestions/liveness.py` | `39af88250e139368cd661f3a96d8be9cd3b5d98a77e58300a7972634379568b9` |
| `src/nexus/suggestions/patch.py` | `e87314dde7b39c6bf33a8f3e94e7274e6bac9d0ccf628e4eda6dfb2fc82c358b` |
| `src/nexus/suggestions/reestimate.py` | `7a01162d63a7b5760b8f07c64d011a6b729dcbb3cf7c4d8e90835332f293efaa` |
| `src/nexus/suggestions/rules/__init__.py` | `9267f5527e28b6adc2e9d84b4828434d9d9df0f01e3f44384b248e5fc63e59fd` |
| `src/nexus/suggestions/rules/_common.py` | `53016060cc0e5611eea976a616da2b5087e3cba8640cb9ef5f87ad9f0e9adf9b` |
| `src/nexus/suggestions/rules/dtypes.py` | `f5f0046ff510b6a13d1b3eb097c5af86952cf822521c35f52264355b8887444a` |
| `src/nexus/suggestions/rules/read_csv.py` | `9be6057c3e48a8de42ea9b1e3842a5a72a8cecfc02dc49a8fe933e8dcab3ec3c` |
| `src/nexus/suggestions/rules/select_columns.py` | `54d0b5b4f3f7ff716aa673c9c553648d3d0e01bbfc406605514c5507a5aa3722` |
| `src/nexus/suggestions/rules/variables.py` | `5216ec6a47d5611b40982abff94e8242f217accfabd8e50819489521bfad61d9` |
| `src/nexus/suggestions/virtual.py` | `db283d7bc4465c805c041ba4382309aca5c01baf72980b6cdbef090754932fde` |
| `src/nexus/timebuckets.py` | `c4f7460065b2f78421e9d64ae308b820208d04817fd4b51d825b4fb52a9510df` |
| `src/nexus/timecal.py` | `5d2181104cd7efb5d9926fab3b536e11c4ae0a6ee536a9ecf1c1147079f746b4` |
