"""The adaptive controller: pre-registered rules (docs/benchmarks/phase4d-preregistration.md), mocked models."""

from __future__ import annotations

import random

import numpy as np
import pandas as pd
import psutil
import pytest

from nexus import dryrun
from nexus.controller import Controller, ControllerConfig, dryrun_need_bytes, triggers
from nexus.dryrun_fit import FitResult
from nexus.dryrun_safety import SafetyVerdict
from nexus.models.base import Estimate
from nexus.pipeline import Pipeline
from nexus.state import ResourceSnapshot

MIB = 2**20
GIB = 2**30
CFG = ControllerConfig()


def est(low=10 * MIB, exp=20 * MIB, high=40 * MIB, t=1.0, tier=1):
    return Estimate(ram_low=int(low), ram_expected=int(exp), ram_high=int(high), time_low=t / 4, time_expected=t,
                    time_high=t * 4, confidence=0.5, tier=tier)  # fmt: skip


def fit(low, exp, high, cv=0.05):
    return FitResult(True, "", exp, low, high, "linear", {"linear": {"cv": cv}})


BAD = FitResult(False, "no growth")
NS = {"df": pd.DataFrame({"f": np.arange(10.0)}), "pd": pd, "np": np}


class Spy:
    """A fake dry run that records whether it was called."""

    def __init__(self, result=None, raises=None):
        self.calls, self.result, self.raises = [], result, raises

    def __call__(self, source, ns, **kw):
        self.calls.append(kw)
        if self.raises:
            raise self.raises
        return self.result if self.result is not None else dryrun.DryRunResult(reason="nothing")


def safe(kind):
    from nexus.dryrun_safety import Recipe

    return lambda s, n: SafetyVerdict(True, (), Recipe(kind))


UNSAFE = lambda s, n: SafetyVerdict(False, ("inplace is never dry-run",))  # noqa: E731


def run(
    op,
    estimate,
    spy,
    kind=None,
    free=64 * GIB,
    features=None,
    tier0=None,
    safety=None,
    input_bytes=100 * MIB,
    rows=1e6,
):
    ctl = Controller(dryrun_fn=spy, safety_fn=safety or safe(kind or dryrun.kind_of_op(op)))
    return ctl.refine(op, estimate, tier0, features or {}, "cell", NS, free, input_bytes, rows)


# -- triggers ------------------------------------------------------------------------------------------
def test_each_pre_registered_trigger_and_only_those():
    assert triggers(est(), None, {}, 64 * GIB, CFG) == []
    assert triggers(est(high=600 * MIB), None, {}, 1 * GIB, CFG) == [
        "a:ram_high_over_half_of_free_ram"
    ]
    assert triggers(est(t=5.0), None, {}, 64 * GIB, CFG) == ["b:expected_time_over_5s"]
    assert triggers(est(t=4.9), None, {}, 64 * GIB, CFG) == []
    t0 = est(low=1 * MIB, exp=10 * MIB, high=100 * MIB, tier=0)
    tr = triggers(t0, t0, {"tier1": {"used": False, "reason": "time budget"}}, 64 * GIB, CFG)
    assert tr == ["c:statistics_exceeded_the_analysis_budget"]
    narrow = est(low=9 * MIB, exp=10 * MIB, high=11 * MIB, tier=0)
    assert (
        triggers(narrow, narrow, {"tier1": {"reason": "time budget"}}, 64 * GIB, CFG) == []
    )  # (c) needs a wide range
    assert (
        triggers(est(tier=1), None, {"tier1": {"reason": "time budget"}}, 64 * GIB, CFG) == []
    )  # and a Tier 0 fallback
    assert (
        triggers(est(high=600 * MIB), None, {}, None, CFG) == []
    )  # unknown free RAM: (a) cannot fire


def test_a_wide_range_on_a_short_cell_does_not_escalate():
    spy = Spy()
    out, info = run("merge", est(low=1 * MIB, exp=10 * MIB, high=500 * MIB, t=1.0), spy)
    assert (
        spy.calls == []
        and info["reason"] == "no trigger"
        and out.tier == 1
        and "no trigger" in out.note
    )


# -- safety and the dry-run memory budget ----------------------------------------------------------------
def test_unsafe_cells_never_start_a_dry_run():
    spy = Spy()
    out, info = run("merge", est(t=9.0), spy, safety=UNSAFE)
    assert spy.calls == [] and "unsafe cell" in info["reason"] and "kept" in out.note


def test_a_recipe_for_a_different_operation_is_not_used():
    spy = Spy()
    out, info = run("merge", est(t=9.0), spy, kind="sort_values")
    assert spy.calls == [] and "not this operation" in info["reason"]


def test_low_free_ram_fails_closed_without_starting_anything():
    spy = Spy()
    out, info = run("merge", est(high=300 * MIB, t=9.0), spy, free=500 * MIB, input_bytes=2 * GIB)
    assert (
        spy.calls == [] and "fail closed" in info["reason"] and "free RAM too low" in info["reason"]
    )
    assert info["need_bytes"] > info["budget_bytes"] == pytest.approx(0.25 * 500 * MIB)
    assert out.tier == 1 and out.ram_high == 300 * MIB  # the Tier 1 estimate is untouched


def test_unknown_free_ram_fails_closed():
    spy = Spy()
    out, info = run("merge", est(t=9.0), spy, free=None)
    assert spy.calls == [] and "free RAM unknown" in info["reason"]


def test_the_memory_budget_formula_is_the_pre_registered_one():
    need = dryrun_need_bytes(1 * GIB, 100_000_000, 4 * GIB, CFG)  # f = min(0.10, 1M / 100M) = 0.01
    assert need == pytest.approx(200 * MIB + 0.01 * (1 * GIB + 4 * GIB))
    assert dryrun_need_bytes(10 * MIB, 1_000_000, 0, CFG) == pytest.approx(
        200 * MIB + 0.10 * 10 * MIB
    )
    spy = Spy(dryrun.DryRunResult(ram=fit(1, 2, 3), time=fit(1, 2, 3)))
    run("merge", est(t=9.0), spy, free=8 * GIB)
    assert spy.calls[0]["child_mem_cap"] == int(0.25 * 8 * GIB) and spy.calls[0]["budget_s"] == 60.0


# -- R1: RAM only ever goes up -------------------------------------------------------------------------------
def test_tier_2_ram_can_raise_the_high_bound_and_nothing_else():
    spy = Spy(dryrun.DryRunResult(ram=fit(100 * MIB, 500 * MIB, 900 * MIB), time=BAD))
    out, info = run("merge", est(low=10 * MIB, exp=20 * MIB, high=40 * MIB, t=9.0), spy)
    assert (out.ram_low, out.ram_expected, out.ram_high) == (10 * MIB, 20 * MIB, 500 * MIB)
    assert out.tier == 2 and "R1" in out.note and info["rules"] and "triggers" in info


def test_tier_2_never_lowers_any_ram_bound_property():
    rnd = random.Random(7)
    for _ in range(200):
        base = est(
            rnd.uniform(1, 50) * MIB, rnd.uniform(50, 100) * MIB, rnd.uniform(100, 300) * MIB, t=9.0
        )
        lo, ex, hi = sorted(rnd.uniform(0.1, 600) * MIB for _ in range(3))
        out, _ = run(
            "merge", base, Spy(dryrun.DryRunResult(ram=fit(lo, ex, hi), time=fit(1, 2, 3)))
        )
        assert (
            out.ram_low == base.ram_low
            and out.ram_expected == base.ram_expected
            and out.ram_high >= base.ram_high
        )


# -- R2: time ------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("op", ["merge", "pandas.merge", "astype", "pandas.read_csv"])
def test_time_comes_from_tier_2_for_read_csv_astype_and_merge(op):
    spy = Spy(dryrun.DryRunResult(ram=BAD, time=fit(2.0, 3.0, 5.0)))
    out, _ = run(op, est(t=9.0), spy)
    assert (out.time_low, out.time_expected, out.time_high) == (2.0, 3.0, 5.0) and out.tier == 2
    assert (out.ram_low, out.ram_expected, out.ram_high) == (10 * MIB, 20 * MIB, 40 * MIB)


def test_groupby_time_high_gets_the_pre_registered_multiplier():
    spy = Spy(dryrun.DryRunResult(ram=BAD, time=fit(2.0, 3.0, 5.0)))
    out, _ = run("groupby", est(t=9.0), spy)
    assert (out.time_low, out.time_expected, out.time_high) == (
        2.0,
        3.0,
        7.5,
    )  # high x 1.5 = 1 / 0.667
    assert "x1.5" in out.note


@pytest.mark.parametrize(
    "op", ["drop_duplicates", "sort_values", "pandas.concat", "numpy.sort", "operator.matmul"]
)
def test_other_operations_keep_the_tier_1_time_even_if_the_dry_run_fitted_it(op):
    spy = Spy(dryrun.DryRunResult(ram=BAD, time=fit(2.0, 3.0, 5.0)))
    out, info = run(op, est(t=9.0), spy)
    assert (
        spy.calls
        and out.time_expected == 9.0
        and out.tier == 1
        and "kept" in out.note
        and info["escalated"]
    )


# -- failures: always Tier 1 and a recorded reason ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "result",
    [
        dryrun.DryRunResult(reason="time budget exhausted"),
        dryrun.DryRunResult(reason="sample run failed (timeout: )"),
        dryrun.DryRunResult(reason="sample run failed (died: )"),
        dryrun.DryRunResult(reason="sample run failed (memory_limit: )"),
        dryrun.DryRunResult(reason="no sample: input is small", ram=None, time=None),
        dryrun.DryRunResult(reason="not safe to dry-run: x"),
    ],
)
def test_a_failed_dry_run_keeps_tier_1_and_says_why(result):
    base = est(t=9.0)
    out, info = run("merge", base, Spy(result))
    assert out.tier == 1 and out.ram_high == base.ram_high and out.time_expected == 9.0
    assert result.reason in out.note and result.reason in info["reason"] and info["escalated"]


def test_an_exception_in_the_dry_run_cannot_reach_the_caller():
    out, info = run("merge", est(t=9.0), Spy(raises=RuntimeError("boom")))
    assert out.tier == 1 and "controller error (RuntimeError)" in out.note


def test_every_returned_estimate_records_its_tier_and_reason():
    cases = [
        run("merge", est(), Spy()),
        run("merge", est(t=9.0), Spy(), safety=UNSAFE),
        run("merge", est(t=9.0), Spy(), free=None),
        run("merge", est(t=9.0), Spy(dryrun.DryRunResult(reason="time budget exhausted"))),
        run("merge", est(t=9.0), Spy(dryrun.DryRunResult(time=fit(1, 2, 3)))),
    ]
    for out, info in cases:
        assert out.note and ("kept" in out.note or "Tier 2 used" in out.note)
        assert {"escalated", "triggers", "reason", "rules"} <= set(info)


# -- real child crashes through the real dry run ------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["timeout", "died", "memory_limit"])
def test_a_crashing_or_hung_child_leaves_the_estimate_and_the_kernel_alone(monkeypatch, status):
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"f": rng.random(400_000), "g": rng.random(400_000)})
    before = df.copy(deep=True)
    monkeypatch.setattr(dryrun, "run_child", lambda *a, **k: {"status": status})
    ctl = Controller()
    out, info = ctl.refine("sort_values", est(t=9.0), None, {}, 'df.sort_values("f")', {"df": df, "pd": pd, "np": np},
                           64 * GIB, df.memory_usage().sum(), len(df))  # fmt: skip
    assert out.tier == 1 and status in out.note and info["escalated"]
    pd.testing.assert_frame_equal(df, before)


# -- stress: almost no free RAM ---------------------------------------------------------------------------------------------
class TinyRam:
    def snapshot(self):
        return ResourceSnapshot(total_ram=16 * GIB, available_ram=10 * MIB)


def test_with_almost_no_free_ram_no_dry_run_starts_and_the_kernel_is_unaffected(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("a dry-run child was started with no free RAM")

    monkeypatch.setattr(dryrun, "run_child", forbidden)
    monkeypatch.setattr(dryrun, "run_dryrun", forbidden)
    rng = np.random.default_rng(1)
    df = pd.DataFrame({"f": rng.random(500_000), "g": rng.random(500_000)})
    before, kids = df.copy(deep=True), len(psutil.Process().children(recursive=True))
    report = Pipeline(tier=2, probe=TinyRam()).run(
        'df.sort_values("f")', {"df": df, "pd": pd, "np": np}
    )
    item = report.estimates[0]
    assert item.estimate.tier <= 1 and "fail closed" in item.estimate.note
    assert (
        item.features["controller"]["triggers"]
        and "free RAM too low" in item.features["controller"]["reason"]
    )
    assert len(psutil.Process().children(recursive=True)) == kids  # nothing was spawned
    pd.testing.assert_frame_equal(df, before)


def test_the_pipeline_uses_the_controller_and_records_the_decision():
    spy = Spy(dryrun.DryRunResult(kind="astype", ram=BAD, time=fit(2.0, 3.0, 5.0)))
    ctl = Controller(config=ControllerConfig(min_run_s=0.0), dryrun_fn=spy)
    df = pd.DataFrame({"f": np.arange(5000.0)})
    report = Pipeline(tier=2, controller=ctl).run(
        'df["f"].astype(str)', {"df": df, "pd": pd, "np": np}
    )
    item = report.estimates[0]
    assert spy.calls and item.estimate.tier == 2 and item.estimate.time_expected == 3.0
    assert item.features["controller"]["rules"] and "Tier 2 used" in item.estimate.note


def test_tier_1_only_pipelines_never_touch_the_controller(monkeypatch):
    monkeypatch.setattr(
        Controller, "refine", lambda *a, **k: (_ for _ in ()).throw(AssertionError("called"))
    )
    df = pd.DataFrame({"f": np.arange(5000.0)})
    report = Pipeline(tier=1).run('df["f"].astype(str)', {"df": df, "pd": pd, "np": np})
    assert report.estimates
