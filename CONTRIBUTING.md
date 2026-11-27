# Contributing

NEXUS is a research-backed estimator. Changes should improve correctness and make uncertainty explicit; unsupported
inputs must remain no-estimate rather than receiving a guess.

## Development setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

Use Python 3.11 or later and pandas 3.1 or later. Model derivations and reported evaluations use pandas 3.1.1; Windows
and Linux are the supported measurement platforms. macOS peak-memory measurement is unsupported.

## Before changing a model

1. Read the relevant model, tests, phase report, and current frozen manifest.
2. Derive the operation cost from the library behavior and write the derivation before measuring.
3. Add a focused isolated probe with representative edge cases. Keep inputs synthetic or otherwise explicitly licensed,
   and do not read protected held-out data.
4. Adopt a model only if every preregistered probe variant meets its stated bar. Record contradictions and defer forms
   that fail.
5. Add focused tests for the accepted form, refusals, range invariants, and any Tier 1 deadline behavior.
6. Run the affected tests, then the full test suite and Ruff when appropriate.

See [Writing a model](docs/WRITING_A_MODEL.md) for the interface and a worked example.

## Evaluation and frozen files

- Update the relevant preregistration before collecting or inspecting a held-out set.
- Keep development and held-out results clearly labeled. A failed criterion remains FAILED; do not retune against the
  same held-out values.
- Never open or run sealed data, including `val-v5`, `test-v2`, or the fresh Phase 8b notebooks, unless the
  preregistered evaluation explicitly authorizes that exact run.
- Do not modify any file listed in `docs/benchmarks/frozen-manifest.md` without a new freeze and new held-out group.
- Run `python -m benchmarks.frozen check` after documentation or packaging work to ensure the current frozen tag still
  matches.

## Checks

```bash
pytest
ruff check .
ruff format --check .
python -m benchmarks.frozen check
```

Do not run tests, builds, or other resource-heavy work while a benchmark is measuring. Do not upload distributions to
PyPI as part of a contribution.

## Pull requests

Keep changes focused. Explain why a change is needed, the evidence supporting it, tests run, and any remaining
limitations. Do not claim a model or release is validated beyond the evidence in [docs/EVALUATION.md](docs/EVALUATION.md).
