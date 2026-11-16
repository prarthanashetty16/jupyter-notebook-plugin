"""Registry, Estimate validation, fail-safe primitives and pipeline isolation."""

from __future__ import annotations

import time

import pytest

from nexus.analyzer import analyze_cell
from nexus.failsafe import Deadline, run_with_timeout, swallow
from nexus.models.base import Estimate, OperationModel
from nexus.models.noop import NoopModel
from nexus.pipeline import Pipeline
from nexus.registry import ModelRegistry


def make_estimate(**overrides):
    values = {
        "ram_low": 1,
        "ram_expected": 2,
        "ram_high": 3,
        "time_low": 0.1,
        "time_expected": 0.2,
        "time_high": 0.3,
        "confidence": 0.5,
        "tier": 0,
    }
    values.update(overrides)
    return Estimate(**values)


class Raises(OperationModel):
    name = "raises"

    def matches(self, op):
        return True

    def features(self, op, state):
        raise RuntimeError("boom")

    def estimate(self, features, tier):
        raise AssertionError("unreachable")


class MatchesRaises(Raises):
    name = "matches_raises"

    def matches(self, op):
        raise RuntimeError("boom")


class WrongType(Raises):
    name = "wrong_type"

    def features(self, op, state):
        return {}

    def estimate(self, features, tier):
        return "not an estimate"


def test_estimate_defaults_and_validation():
    assert make_estimate().drivers == []
    for bad in (
        {"ram_low": 5},
        {"time_high": 0.0},
        {"confidence": 1.5},
        {"ram_low": -1},
        {"tier": -1},
    ):
        with pytest.raises(ValueError):
            make_estimate(**bad)


def test_registry_decorator_and_lookup():
    registry = ModelRegistry()

    @registry.register
    class Mine(NoopModel):
        name = "mine"

    assert len(registry) == 1 and registry.get("mine") is not None
    (op,) = analyze_cell("df.drop_duplicates()")
    assert [m.name for m in registry.find(op)] == ["mine"]
    (other,) = analyze_cell("df.sort_values('a')")
    assert registry.find(other) == []


def test_registry_duplicate_rejected_and_remove():
    registry = ModelRegistry()
    registry.add(NoopModel())
    with pytest.raises(ValueError):
        registry.add(NoopModel())
    registry.remove("noop")
    assert len(registry) == 0


def test_registry_skips_matches_that_raise():
    registry = ModelRegistry()
    registry.add(MatchesRaises())
    registry.add(NoopModel())
    (op,) = analyze_cell("df.drop_duplicates()")
    assert [m.name for m in registry.find(op)] == ["noop"]


def test_pipeline_end_to_end_with_noop_model():
    import pandas as pd

    df = pd.DataFrame({"a": range(100), "b": range(100)})
    registry = ModelRegistry()
    registry.add(NoopModel())
    report = Pipeline(registry=registry).run("df.drop_duplicates()", {"df": df})
    assert [o.name for o in report.ops] == ["drop_duplicates"]
    assert report.inspection.variables["df"].nbytes > 0
    (item,) = report.estimates
    nbytes = report.inspection.variables["df"].nbytes
    assert item.model == "noop" and item.estimate.ram_expected == 2 * nbytes
    assert report.resources is not None and report.resources.total_ram > 0


def test_pipeline_no_ops_is_cheap_and_empty():
    report = Pipeline(registry=ModelRegistry()).run("x = 1", {})
    assert report.ops == [] and report.estimates == [] and report.resources is None


def test_pipeline_isolates_failing_models():
    registry = ModelRegistry()
    for model in (Raises(), WrongType(), NoopModel()):
        registry.add(model)
    report = Pipeline(registry=registry).run("df.drop_duplicates()", {})
    assert [e.model for e in report.estimates] == ["noop"]


def test_swallow_returns_none_and_keeps_name():
    @swallow
    def boom():
        """doc"""
        raise ValueError("x")

    assert boom() is None and boom.__name__ == "boom"
    assert swallow(lambda: 3)() == 3


def test_swallow_does_not_catch_keyboard_interrupt():
    @swallow
    def interrupted():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        interrupted()


def test_run_with_timeout_paths():
    assert run_with_timeout(lambda: 42, 1.0) == 42
    with pytest.raises(ZeroDivisionError):
        run_with_timeout(lambda: 1 / 0, 1.0)
    t0 = time.perf_counter()
    with pytest.raises(TimeoutError):
        run_with_timeout(lambda: time.sleep(2), 0.05)
    assert time.perf_counter() - t0 < 1.0


def test_deadline():
    assert not Deadline(10).expired()
    assert Deadline(10).remaining() > 9
    assert Deadline(0).expired()
    with pytest.raises(TimeoutError):
        Deadline(0).check()
