.PHONY: bench-small bench-full bench-report test lint

PY ?= python

# Quick benchmark (minutes). Resumable: re-run to continue after an interruption.
bench-small:
	$(PY) -m benchmarks small

# Full benchmark (10^4..10^7 rows; long, needs several GB of free RAM).
bench-full:
	$(PY) -m benchmarks full

bench-report:
	$(PY) -m benchmarks evaluate benchmarks/results/$(SUITE)

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .
