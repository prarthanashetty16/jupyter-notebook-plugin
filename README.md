# NEXUS

**Predict peak RAM and wall-clock time for Jupyter cells before execution.**

NEXUS is an IPython extension that analyzes your code and kernel state to forecast memory usage and runtime for a cell *before* you run it. It combines code analysis (AST), live kernel state inspection, and tiered cost models to give honest estimates with confidence bounds, then suggests resource-conscious optimizations.

## Status

🚧 **Early development** (Phase 1 — Foundation)

This is a research-backed tool under active development. See [docs/PROGRESS.md](docs/PROGRESS.md) for the roadmap.

## Installation

(Not yet available on PyPI)

```bash
pip install -e .
```

## Quick start

```python
%load_ext nexus
# NEXUS is now active; predictions will appear before cell execution
```

## Documentation

- [CLAUDE.md](CLAUDE.md) — Project vision, architecture, quality bar
- [docs/PROGRESS.md](docs/PROGRESS.md) — Phase checklist and decisions
- [docs/DESIGN.md](docs/DESIGN.md) — Detailed design decisions *(coming soon)*

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .
ruff format .
```

## License

MIT — see [LICENSE](LICENSE)
