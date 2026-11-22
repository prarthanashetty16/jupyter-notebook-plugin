# NEXUS: RAM and Time Prediction for Jupyter Cells

## What NEXUS is

A Python package (IPython extension, `%load_ext nexus`) that predicts, **before** a Jupyter cell runs, its peak RAM and wall-clock time. It analyzes the code (which operations it performs) and the live data in the kernel (shapes, dtypes, sizes). It compares the prediction with available resources, warns about out-of-memory risk, and gives rule-based suggestions that are themselves re-estimated. It is a research-backed developer tool, not a chatbot and not a monitoring dashboard. **Prediction accuracy and honest measurement of it are the core of the project.**

## Scope of the core project

- **Operations**: pandas and numpy operations, peak RAM and wall time, CPU only
- **Suggestions**: Rule-based (no LLM); GPU and LLM suggestions in optional later phases
- **Evaluation**: A benchmark and evaluation harness measuring predicted vs. actual is a first-class deliverable

## Environment constraints

- **Platform support**: Windows (developer machine), Linux, macOS (Google Colab is Linux)
- **Platform abstraction**: Do NOT rely on `fork` or the Unix-only `resource` module. Use `multiprocessing` with `spawn` start method. Use `psutil` for memory. Hide platform differences for peak-memory measurement behind one function
- **Python**: 3.10+
- **Build**: `pyproject.toml`, `src/nexus` layout
- **Testing**: pytest with Windows, Linux, and macOS coverage
- **Linting**: ruff
- **Dependencies**: Minimal — psutil, pandas, numpy, ipython. scikit-learn only in optional phases

## Architecture

Each cell follows a pipeline hooked on `pre_run_cell` / `post_run_cell`:

1. **Interceptor**: Gets cell source. Must NEVER break or block the user's cell; on any internal error or timeout, NEXUS stays silent. Analysis time budget: ~250 ms (Tiers 0–1)
2. **Code analyzer**: AST-based; identifies known operations and the variables they touch. Unknown code yields "no estimate", never a guess
3. **State inspector**: Collects shape, dtypes, `memory_usage(deep=True)`, bounded-sample stats, nbytes, free RAM, container/cgroup memory limit
4. **Tiered estimator**:
   - **Tier 0**: Closed-form cost model per operation
   - **Tier 1**: Adds cheap data statistics
   - **Tier 2**: Sandboxed dry-run on a sample in a spawned process, then extrapolate
   - Estimates are always ranges (low/expected/high) + confidence; escalate only when the range is too wide or risk is borderline
5. **Risk engine**: OK / WARN / HIGH_RISK with a reason naming the cost drivers
6. **Suggestion engine** (rule-based): Each suggestion is re-estimated and shown with the new range. The user decides; never edit the cell automatically
7. **Logger**: JSONL record of (cell features, predicted range, actual peak RAM, actual time, tier, analysis overhead)

Operation models are plug-ins with a common interface (`matches` / `features` / `estimate`) in a registry. Adding an operation = one new file. Each model's docstring explains its cost drivers empirically validated in the benchmark.

## Module layout (`src/nexus/`)

`extension.py` (load/unload) -> `session.py` (hooks, fail-safe, re-entrancy) -> `pipeline.py` (analyze -> inspect -> models). Supporting: `analyzer.py`, `state.py` (StateInspector, ResourceProbe), `registry.py`, `models/base.py` (`Estimate`, `OperationModel`), `models/noop.py` (tests only), `failsafe.py`, `render.py`, `magics.py` (`%nexus`). Tier 2 (opt-in, `Pipeline(tier=2)`): `dryrun.py` (orchestration, escalation), `dryrun_safety.py` (allowlist: only side-effect-free, fully understood single-operation cells; unknown means unsafe), `dryrun_sample.py` (nested key-hash / row samples), `dryrun_io.py` + `_dryrun_child.py` (the subprocess sandbox), `dryrun_fit.py` (scaling laws, forward CV), `guard.py`, `ranges.py`, `timebuckets.py`.

## Quality bar

- Type hints and docstrings throughout
- Small, focused modules; minimal global state
- Tests that pass on Windows, Linux, and macOS
- Honest reporting of errors and uncertainty
- No tuning numbers to look good; empirical validation is core

## Conventions

### Code style
- Follow PEP 8 and [PEP 257](https://www.python.org/dev/peps/pep-0257/)
- Use ruff for linting and formatting (configured in `pyproject.toml`)
- Type hints required on all public functions and classes
- Docstrings: concise module-level and function docstrings; explain WHY, not WHAT
- No comments unless the invariant or constraint is non-obvious

### How to run tests
```bash
pytest                      # Run all tests
pytest -v                   # Verbose
pytest tests/test_foo.py    # Run specific test file
pytest tests/test_foo.py::test_bar  # Run specific test
pytest --cov               # With coverage (if coverage is installed)
```

### How to run lint
```bash
ruff check .                # Check for lint issues
ruff format .               # Auto-format code
```

### Benchmarks
```bash
python -m benchmarks small    # ~3 min, resumable; writes benchmarks/results/small/report.md
python -m benchmarks full     # 1e4..1e7 rows, long, needs several GB free RAM
pip install -e ".[dev,bench]"   # matplotlib for figures
nexus-calibrate-machine       # per-machine throughputs (the runner calibrates once if missing)
```
Phase 4b.2 tooling: `python -m benchmarks.range_policy <dir>` selects the Tier 1 RAM-range policy under the pre-registered criterion (leave-one-configuration-out); `python -m benchmarks.tier1_before_after <before> <after> <out>` compares old and new predictions on identical actuals (per point and per configuration); `python -m benchmarks.planner_report <dir>` lists the points the model-based planner (baseline + NEXUS `high` vs the cap, `benchmarks/planner.py`) would skip; `python -m benchmarks.maintenance migrate-val3 <src> <dest>` copies the former val-v3 rows into a dev results dir. The probes behind the 4b.2 fixes are in `docs/benchmarks/val-v3-diagnosis/probes/` (diagnosis: `docs/benchmarks/val-v3-diagnosis.md`). `full` predicts before measuring and skips points whose model upper bound cannot fit (`--no-model-planning` restores the static rule). The user-facing time is an order-of-magnitude bucket (`nexus.timebuckets`).
Phase 6c tooling: `nexus/cellpeak.py` (cell-level peak model, used by `risk.assess`); `python -m benchmarks.multicell.run run|evaluate [--heldout --reason ...]` (multi-statement benchmark; split `benchmarks/multicell/split_v1.json` frozen; held-out part opt-in and logged); `python -m benchmarks.phase6c_regression --before <dir> --after <dir> --out <md>`; `python -m benchmarks.realworld.subsample` (seeded row subsamples of the real data, git-ignored) and `run_notebook --dev` (dev runs skip the freeze guard; never for held-out data). The freeze is `models-frozen-v2` (`benchmarks/frozen.py`; v1 documented in `docs/benchmarks/frozen-manifest-v1.md`). `%load_ext nexus` defaults to Tier 1.
Phase 6 tooling: `nexus-calibrate-machine` writes profile format 3 (working-set curves; records the power state and refuses to measure on battery unless `--allow-battery`); the derived time terms are in `nexus/models/_time.py`; `nexus-calibrate <results dir> --tier2-results <dir> --out <file>` (`nexus/calfit.py`) refits the time calibration artifact (`src/nexus/calibration/calibration-v1.json`, applied by `nexus/timecal.py`; `--local` writes a user-local copy used only with `NEXUS_CALIBRATION=local`); `python -m benchmarks.phase6_eval ...` is the dev evaluation (`docs/benchmarks/phase6/`); `python -m benchmarks.frozen check|manifest` is the freeze guard of the held-out runs (tag `models-frozen-v1`, manifest `docs/benchmarks/frozen-manifest.md`). `pytest -m pandas_mechanisms` runs the pandas-internals probe checks (CI matrix over pandas versions).
Phase 4e tooling: `python -m benchmarks full ... --pilot N` times the first N val-v5 points and extrapolates the rest (`pilot.json`); val-v5 runs in priority order (Amendment 1 of the pre-registration); `python -m benchmarks.realworld.coverage <folder of .ipynb> --out <dir>` measures what Tier 0/1 and the Tier 2 safety analyzer cover in real notebooks (static, never executes cell code); Linux smoke-test commands: `docs/benchmarks/phase4e/linux-smoke.md`.
Phase 4d tooling: `nexus/controller.py` (the pre-registered adaptive controller, `docs/benchmarks/phase4d-preregistration.md`; `Pipeline(tier=2)` uses it); `python -m benchmarks.controller_eval <dir> --out <docs dir>` replays it on dev; `python -m benchmarks.multistatement_report` measures what the Tier 2 safety analyzer accepts; Linux VM commands for val-v5: `docs/benchmarks/val-v5-linux-runbook.md` (`full --require-calibrated` aborts without `nexus-calibrate-machine`).
Phase 4c tooling: `python -m benchmarks.tier2_eval <dir> --out <docs dir>` compares Tier 1 and Tier 2 on dev; `python -m benchmarks full --tiers 2` predicts with Tier 2 (a dry run per qualifying cell, ~2 s each; dev only). Tier 2 is NOT validated.
Phase 4b.3 tooling: `python -m benchmarks.oom_misses <dir> --limit-mb 2048` lists the false negatives of the simulated OOM warning and whether the planner would have flagged them; `nexus/guard.py` rejects insane Tier 1 estimates (Tier 0 kept, reason in `Estimate.note`); `nexus/ranges.py` holds the global range policy (Tier 1 low/expected, Tier 0 high). Large-size run commands: `docs/benchmarks/large-size-linux.md`.
Phase 4a tooling: `python -m benchmarks.pressure <dir>` screens time points for memory pressure (available RAM, swap and page faults are recorded per run); `python -m benchmarks.tier0_compare <before> <after> <out>` scores old vs new predictions on identical actuals; the probe scripts behind the model derivations are in `docs/benchmarks/tier0-v2/probes/`.
RAM is measured with OS peak counters on inputs loaded from disk (`nexus.measure`); the instrument is validated by `tests/test_measure_validation.py` and must stay green.
Do not run tests or other heavy work while a benchmark runs (it distorts memory measurements).

Full run (resumable; re-run the same command to continue; `status` from a second terminal):
```bash
python -m benchmarks plan   --suite full --mem-limit-gb 2.5 --max-size 10000000
python -m benchmarks full   --mem-limit-gb 2.5 --max-size 10000000      # dev only (add --tiers 0,1)
python -m benchmarks status benchmarks/results/full
python -m benchmarks evaluate benchmarks/results/full          # dev split only
```
The cap must stay well below free RAM. **Splits (`benchmarks/split.json` version 6, frozen, digest-checked):** `dev`
(123 cases: the Phase 3-3b cases and the former exposed-v1, val-v3 and val-v4, whose reports were read; all three lists are
kept as `provenance`) may be read by all tooling (`load_joined`, reports, `diagnose`). Two groups are protected and opt-in
(`--splits test-v2` / `--splits val-v5`); runner/log/console/status output for them shows only point id, status and elapsed
time. `test-v2` (17 cases, sealed, never run; results in `<results>/sealed/`) is read only by `evaluate <dir> --final --reason
"..."`. `val-v5` (47 cases, the held-out validation group for a Linux machine with >= 32 GB RAM, created in Phase 4d, NOT yet
run; results in `<results>/validation/`) is read only by `evaluate <dir> --val --reason "..."`. Every use is logged in the "Test-split
access log" in docs/PROGRESS.md. Never print, plot or paste protected values anywhere; never edit `split.json` (create a new
version instead); never read `sealed/` or `validation/` directly. Develop and tune on dev, check on val-v5 once per frozen model
state (once read it becomes dev and a new group is needed), run test-v2 only once models are frozen.

### Commit message style
- First line: imperative, ~50 chars. Example: "Add Tier 0 estimator for DataFrame.sum()"
- Body (if needed): explain WHY, not WHAT. Keep lines ≤72 chars
- Reference issues/PRs if relevant: "Closes #42" or "See #123"
- End with the Co-Authored-By trailer configured for the session (do not hardcode a model name here)

### Project workflow
- Update `docs/PROGRESS.md` at the end of every phase with:
  - Which tasks are complete (check boxes)
  - Key decisions made and findings
  - Any blockers or questions for the next phase
- Keep this document and architecture decisions in `docs/DESIGN.md` as the codebase grows

## Phase list (see `docs/PROGRESS.md`)

1. **Foundation** — repo setup, CI/CD, dummy test (this phase)
2. **Tier 0 estimators** — AST analyzer, operation registry, closed-form models for common ops
3. **Benchmark** ✓ **checkpoint** — evaluation harness, ground-truth measurement, initial calibration
4. **Tier 1 and 2** — statistics collection, dry-run sampler, extrapolation
5. **Risk and suggestions** — risk classification, rule-based suggestion engine
6. **Calibration** — systematic error analysis, uncertainty bounds
7. **UX and robustness** — IPython extension, error handling, edge cases
8. **Real-world evaluation** ✓ **checkpoint** — test on real notebooks, refine models
9. **Docs and release** — API docs, examples, PyPI release
10. **JupyterLab UI** *(optional)* — interactive preview panel
11. **Extensions** *(optional)* — GPU, LLM suggestions, other languages
