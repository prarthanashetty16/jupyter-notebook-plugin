# NEXUS Project Phases

## Phase Checklist

- [ ] **Phase 1: Foundation** — Repo setup, CI/CD, dummy test
- [ ] **Phase 2: Tier 0 estimators** — AST analyzer, operation registry, closed-form models
- [ ] **Phase 3: Benchmark** ✓ **checkpoint** — Evaluation harness, ground-truth measurement
- [ ] **Phase 4: Tier 1 and 2** — Statistics collection, dry-run sampler, extrapolation
- [ ] **Phase 5: Risk and suggestions** — Risk classification, rule-based suggestion engine
- [ ] **Phase 6: Calibration** — Systematic error analysis, uncertainty bounds
- [ ] **Phase 7: UX and robustness** — IPython extension, error handling, edge cases
- [ ] **Phase 8: Real-world evaluation** ✓ **checkpoint** — Test on real notebooks, refine models
- [ ] **Phase 9: Docs and release** — API docs, examples, PyPI release
- [ ] **Phase 10: JupyterLab UI** *(optional)* — Interactive preview panel
- [ ] **Phase 11: Extensions** *(optional)* — GPU, LLM suggestions, other languages

## Decisions and findings

### Phase 1 decisions
- **Platform abstraction**: Using `multiprocessing.spawn` and `psutil` for cross-platform memory measurement
- **Build system**: `pyproject.toml` with setuptools; `src/nexus` layout for clean packaging
- **Linting**: ruff for speed and ease; targets Python 3.10+
- **CI/CD**: GitHub Actions workflows for Windows, Ubuntu; macOS added when needed
- **Minimal dependencies**: Core depends only on psutil, pandas, numpy, ipython

### Open questions for Phase 2
- Which pandas/numpy operations to prioritize for Tier 0 models?
- Sampling strategy for `memory_usage(deep=True)` on large objects?
- How to safely sandbox dry-runs in Tier 2 without breaking user kernels?
