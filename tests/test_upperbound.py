"""v4 item C: the split-conformal upper bound (benchmarks.upper_calibration) and its runtime hook (nexus.upperbound)."""

from __future__ import annotations

import pandas as pd
import pytest

from benchmarks import upper_calibration as uc
from nexus import upperbound
from nexus.models.base import Estimate


def _est(tier: int = 1, exp: int = 100, high: int = 120) -> Estimate:
    return Estimate(ram_low=50, ram_expected=exp, ram_high=high, time_low=0.1, time_expected=0.2,
                    time_high=0.3, confidence=0.5, tier=tier)  # fmt: skip


def test_conformal_rank_is_ceil_n_plus_1_times_1_minus_alpha():
    xs = [float(i) for i in range(1, 101)]  # n = 100: rank ceil(101 x 0.98) = 99
    f = uc.conformal_factor(xs, 0.02)
    assert (f.q, f.n, f.at_max) == (99.0, 100, False)


def test_rank_beyond_n_uses_the_sample_maximum_with_the_margin():
    f = uc.conformal_factor([1.0] * 29 + [1.5], 0.02)  # n = 30: rank 31 > 30
    assert f.at_max and f.q == pytest.approx(1.5 * uc.AT_MAX_MARGIN)


def _points(n_a: int, n_b: int) -> pd.DataFrame:
    rows = [{"unit": f"a{i}", "family": "a", "residual": 1.0 + i / 1000, "expected": 100.0, "high": 110.0,
             "actual": 100.0, "low": 50.0} for i in range(n_a)]  # fmt: skip
    rows += [{"unit": f"b{i}", "family": "b", "residual": 2.0, "expected": 100.0, "high": 110.0,
              "actual": 200.0, "low": 50.0} for i in range(n_b)]  # fmt: skip
    return pd.DataFrame(rows)


def test_families_below_30_configurations_use_the_pooled_factor():
    pts = _points(40, 5)
    pooled, own = uc.fit(uc.units_of(pts))
    assert set(own) == {"a"} and own["a"].n == 40 and pooled.n == 45
    high = uc.calibrated_high(pts, pooled, own)
    assert (high[pts["family"] == "b"] == 100.0 * pooled.q).all()


def test_calibration_only_raises_the_high():
    pts = _points(40, 0)
    pts["high"] = 10_000.0
    pooled, own = uc.fit(uc.units_of(pts))
    assert (uc.calibrated_high(pts, pooled, own) == 10_000.0).all()


def test_loco_never_uses_the_left_out_configuration():
    # one extreme configuration: without it the pooled factor is the a-family's
    pts = _points(40, 1)
    lo = uc.loco(pts)
    b = pts["family"] == "b"
    assert (pts.loc[b, "actual"] > lo[b]).all()  # left out, it is not covered by its own residual


def test_runtime_hook_raises_tier1_high_only(monkeypatch: pytest.MonkeyPatch):
    art = {"pooled": {"q": 1.5}, "families": {"merge": {"q": 3.0}}}
    monkeypatch.setattr(upperbound, "_factors", lambda: art)
    assert upperbound.apply("merge", _est()).ram_high == 300
    assert upperbound.apply("copy", _est()).ram_high == 150
    assert upperbound.apply("copy", _est(high=999)).ram_high == 999
    assert upperbound.apply("copy", _est(tier=0)).ram_high == 120
    e = upperbound.apply("copy", _est())
    assert (e.ram_low, e.ram_expected) == (50, 100)


def test_runtime_hook_without_artifact_changes_nothing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(upperbound, "_factors", lambda: None)
    assert upperbound.apply("merge", _est()) == _est()


def test_dev_tools_read_only_consumed_held_out_parts():
    from benchmarks.multicell import split

    assert split.CONSUMED == (1, 2, 3)
    with pytest.raises(PermissionError):
        split.consumed_heldout_results(4, "test")
