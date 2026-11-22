# Phase 6d: audit of the machine-profile bug (2026-11-22)

**The bug.** `tests/test_power.py` (added in Phase 6b, commit `a948b01`, 2026-11-21 23:05) called `monkeypatch.undo()`, which also
undid the test suite's redirection of the machine-profile path. Every full test run from then until the restore
(2026-11-22 14:17:55) overwrote `%LOCALAPPDATA%\nexus\machine.json` with a 1-second QUICK profile measured with a faked battery.
Fixed in Phase 6c (test fixed, real profile restored from the shipped reference `987c455be3cc`, a session fixture now fails the
test run if the user's profile changes).

**What depends on the profile.** Time estimates only. RAM estimates and Tier 1 statistics (incl. the 250 ms budget fallbacks) do not:
every re-run below reproduced RAM exactly (0 differing rows of 1,188).

| artifact | when | profile used | reported numbers affected? | re-run (prediction only, restored profile) |
|---|---|---|---|---|
| Phase 6b fallback runs (`fallback-cores2`, `fallback-contended`) | 2026-11-21 23:23 - 00:05 | corrupted (quick, battery, 23:04, recorded in `meta.json`) | **no**: `fallback_rate.md` uses the Tier 1 fallback flags (profile-independent) and the Phase 6 dev errors (computed before the bug) | time recomputed from the stored features: `predictions_time_restored_profile.csv`; stored times were off by a median 1.12x (0.55x - 33x) |
| Phase 8a real run (`amazon_ml_solution`, `amazon_solution_old`) | 2026-11-22 00:24 (a full test run at 00:20) | corrupted (not recorded; inferred from the timing) | **yes**: the single valid time point | re-analysed with the frozen v1 stack (worktree of `models-frozen-v1`): expected 8.69 s -> **7.49 s** (measured 8.45 s; same 1-10 s bucket: within-one and same-bucket unchanged; error 2.9% -> 11.3%); RAM identical; verdict unchanged (INCONCLUSIVE, 1 point) |
| Phase 6c multi-statement dev cells | 2026-11-22, finished 13:53 | corrupted | **no**: `multicell_dev.md` evaluates RAM only | predictions re-run: `results_restored_profile.jsonl`; RAM identical; stored times off by a median 2.7x |
| Phase 6c regression re-run (`phase6c-dev`) | 2026-11-22 afternoon | corrupted (quick, battery, 13:35, recorded) | **no** in the final report: `regression_dev.md` recomputes time from the features and was regenerated after the restore (the first version, printed in the session only, is superseded) | time recomputed: `predictions_time_restored_profile.csv`; stored times off by a median 1.59x |
| Phase 6c real-notebook dev check (`*_sub`) | 2026-11-22 14:20 - 14:22 | restored (after 14:17:55, no test run in between) | no | not needed |
| calibration artifact, reference profile, Phase 6 results | 2026-11-18 | mains profile (before the bug) | no | not needed |

Raw numbers: `profile_audit.json` (`python -m benchmarks.profile_audit --out docs/benchmarks/phase6d/profile_audit.md` writes it).
The Phase 8a re-analysis: `benchmarks/results/realworld/phase8a_reanalysis_restored_profile.json` (local, git-ignored).
