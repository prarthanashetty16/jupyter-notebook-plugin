"""Risk engine: pre-registered classes and their edge cases (Phase 5, Part A)."""

from __future__ import annotations

import ast
import math

import pytest

from nexus.analyzer import DetectedOp
from nexus.models.base import Estimate
from nexus.pipeline import CellReport, OpEstimate
from nexus.risk import RiskClass, assess, classify, combine
from nexus.state import CgroupMemory, ResourceSnapshot

MB = 2**20
GB = 2**30


def est(
    low=100, expected=200, high=400, conf=0.8, tier=1, note=None, time=0.5, drivers=("hash table",)
):
    return Estimate(
        ram_low=low * MB, ram_expected=expected * MB, ram_high=high * MB,
        time_low=time / 2, time_expected=time, time_high=time * 2,
        confidence=conf, tier=tier, drivers=list(drivers), note=note,
    )  # fmt: skip


def snap(available_mb, total_mb=16384, swap_mb=None, cgroup=None):
    return ResourceSnapshot(
        total_ram=total_mb * MB, available_ram=available_mb * MB, cgroup=cgroup,
        swap_free=None if swap_mb is None else swap_mb * MB,
    )  # fmt: skip


def test_ok_when_the_high_bound_fits_with_margin():
    r = classify([est()], snap(1000))
    assert r.risk is RiskClass.OK and not r.risk.is_alert


def test_warn_when_high_exceeds_85_percent_of_headroom_but_expected_fits():
    assert classify([est(high=860)], snap(1000)).risk is RiskClass.WARN
    assert classify([est(high=850)], snap(1000)).risk is RiskClass.OK  # not above the margin


def test_high_risk_when_the_expected_peak_does_not_fit():
    r = classify([est(expected=1200, high=1500)], snap(1000))
    assert r.risk is RiskClass.HIGH_RISK and "exceeds" in r.reason and "hash table" in r.reason


def test_low_above_headroom_is_high_risk_a_fortiori():
    assert (
        classify([est(low=1100, expected=1200, high=1500)], snap(1000)).risk is RiskClass.HIGH_RISK
    )


def test_zero_free_ram():
    assert classify([est()], snap(0)).risk is RiskClass.HIGH_RISK
    zero = est(low=0, expected=0, high=0)
    assert classify([zero], snap(0)).risk in (RiskClass.OK, RiskClass.WARN, RiskClass.UNKNOWN)
    assert classify([zero], snap(0)).risk is not RiskClass.HIGH_RISK  # nothing to allocate


def test_huge_swap_never_raises_headroom_and_is_named():
    r = classify([est(expected=1200, high=1500)], snap(1000, swap_mb=64 * 1024))
    assert r.risk is RiskClass.HIGH_RISK and "swap" in r.reason
    far = classify([est(expected=10**5, high=10**5)], snap(1000, swap_mb=100))
    assert far.risk is RiskClass.HIGH_RISK and "swap" not in far.reason


def test_cgroup_limit_below_host_ram_is_the_binding_headroom():
    cg = CgroupMemory(version=2, limit=512 * MB, usage=100 * MB)
    s = snap(8000, total_mb=16384, cgroup=cg)
    assert s.effective_available == 412 * MB
    r = classify([est(expected=450, high=600)], s)
    assert r.risk is RiskClass.HIGH_RISK and r.cgroup_limit == 512 * MB and "container" in r.reason
    assert classify([est(expected=450, high=600)], snap(8000)).risk is RiskClass.OK


def test_no_estimate_is_unknown_never_ok():
    r = classify([], snap(1000))
    assert r.risk is RiskClass.UNKNOWN and "no estimate" in r.reason


def test_low_confidence_makes_an_otherwise_ok_cell_unknown_but_not_an_alert():
    assert classify([est(conf=0.29)], snap(1000)).risk is RiskClass.UNKNOWN
    assert classify([est(conf=0.30)], snap(1000)).risk is RiskClass.OK
    assert (
        classify([est(conf=0.0, expected=2000, high=3000)], snap(1000)).risk is RiskClass.HIGH_RISK
    )


def test_guard_fallback_is_reported_and_classified_by_the_tier0_range():
    r = classify([est(tier=0, note="Tier 1 rejected: non-finite figure", high=900)], snap(1000))
    assert r.risk is RiskClass.WARN and r.fallback and "rejected" in r.format()


def test_unmeasurable_or_nonfinite_input_is_unknown():
    assert classify([est()], None).risk is RiskClass.UNKNOWN
    bad = Estimate(
        ram_low=1, ram_expected=2, ram_high=3, time_low=0.0, time_expected=math.inf,
        time_high=math.inf, confidence=0.9, tier=1,
    )  # fmt: skip
    assert classify([bad], snap(1000)).risk is RiskClass.UNKNOWN


def test_partly_covered_cell_is_unknown_when_the_rest_fits_but_alerts_still_show():
    assert classify([est()], snap(1000), uncovered=1).risk is RiskClass.UNKNOWN
    assert (
        classify([est(expected=1200, high=1500)], snap(1000), uncovered=1).risk
        is RiskClass.HIGH_RISK
    )


def test_combine_uses_max_of_lows_and_expected_and_the_sum_of_highs():
    c = combine([est(100, 200, 400), est(150, 300, 500)])
    assert (c.ram_low, c.ram_expected, c.ram_high) == (150 * MB, 300 * MB, 900 * MB)
    assert classify([est(100, 200, 400), est(150, 300, 500)], snap(1000)).risk is RiskClass.WARN


def test_time_is_only_a_bucket_and_never_changes_the_memory_class():
    long = classify([est(time=300.0)], snap(1000))
    assert long.risk is RiskClass.OK and long.long_run and long.time_bucket == "1-10 min"
    assert not classify([est(time=30.0)], snap(1000)).long_run
    assert classify([est(time=5000.0)], snap(1000)).time_bucket == "over 10 min"
    assert " s " not in long.format().split("time:")[1].split("\n")[0] or "min" in long.format()


def test_explicit_headroom_overrides_the_snapshot_for_simulated_limits():
    assert classify([est()], snap(10**6), headroom=100 * MB).risk is RiskClass.HIGH_RISK


def test_assess_covers_no_ops_no_models_and_models():
    op = DetectedOp(name="merge", node=ast.parse("x").body[0])
    other = DetectedOp(name="sort_values", node=ast.parse("y").body[0])
    assert assess(CellReport()) is None
    assert assess(CellReport(ops=[op], resources=snap(1000))).risk is RiskClass.UNKNOWN
    one = OpEstimate(op=op, model="merge", estimate=est())
    assert assess(CellReport(ops=[op], estimates=[one], resources=snap(1000))).risk is RiskClass.OK
    part = assess(CellReport(ops=[op, other], estimates=[one], resources=snap(1000)))
    assert part.risk is RiskClass.UNKNOWN


@pytest.mark.parametrize("name", ["OK", "WARN", "HIGH_RISK", "UNKNOWN"])
def test_class_names_are_the_pre_registered_ones(name):
    assert RiskClass(name).value == name
