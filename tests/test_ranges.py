"""The Tier 1 RAM-range policy hook (``nexus.ranges``)."""

from __future__ import annotations

import pytest

from nexus import ranges
from nexus.models.base import Estimate


def _est(tier=1, low=80, exp=100, high=120):
    return Estimate(ram_low=low, ram_expected=exp, ram_high=high, time_low=0.1, time_expected=0.2,
                    time_high=0.4, confidence=0.5, tier=tier, drivers=[])  # fmt: skip


@pytest.fixture(autouse=True)
def _restore():
    bands, ceiling, upper = (
        dict(ranges.TIER1_BANDS),
        ranges.CEILING_AT_TIER0_HIGH,
        ranges.UPPER_IS_TIER0_HIGH,
    )
    yield
    ranges.TIER1_BANDS.clear()
    ranges.TIER1_BANDS.update(bands)
    ranges.CEILING_AT_TIER0_HIGH, ranges.UPPER_IS_TIER0_HIGH = ceiling, upper


def test_tier_0_estimates_are_never_touched():
    ranges.TIER1_BANDS["m"] = (0.5, 3.0)
    e = _est(tier=0)
    assert ranges.apply("m", e, None) is e


def test_a_model_without_a_band_keeps_its_own_range():
    ranges.TIER1_BANDS.clear()
    ranges.UPPER_IS_TIER0_HIGH = False
    e = _est()
    assert (
        ranges.apply("unknown", e, None).ram_low,
        ranges.apply("unknown", e, None).ram_high,
    ) == (80, 120)


def test_band_multipliers_are_applied_to_the_expected_value_and_stay_ordered():
    ranges.TIER1_BANDS["m"] = (0.7, 1.5)
    out = ranges.apply("m", _est(), None)
    assert (out.ram_low, out.ram_expected, out.ram_high) == (70, 100, 150)
    ranges.TIER1_BANDS["m"] = (1.2, 0.8)  # nonsensical multipliers can never invert the range
    out = ranges.apply("m", _est(), None)
    assert out.ram_low <= out.ram_expected <= out.ram_high


def test_tier_0_high_as_a_ceiling_or_as_the_upper_end():
    ranges.TIER1_BANDS["m"] = (0.7, 3.0)
    ranges.UPPER_IS_TIER0_HIGH = False
    ranges.CEILING_AT_TIER0_HIGH = True
    assert (
        ranges.apply("m", _est(), _est(tier=0, high=200)).ram_high == 200
    )  # capped at Tier 0's high
    assert ranges.apply("m", _est(), _est(tier=0, high=400)).ram_high == 300
    ranges.CEILING_AT_TIER0_HIGH, ranges.UPPER_IS_TIER0_HIGH = False, True
    assert ranges.apply("m", _est(), _est(tier=0, high=400)).ram_high == 400


def test_the_adopted_global_policy_is_tier_1_low_expected_and_tier_0_high():
    """Phase 4b.3: fallback C adopted globally after val-v4 failed the criterion."""
    assert ranges.UPPER_IS_TIER0_HIGH and not ranges.TIER1_BANDS
    out = ranges.apply(
        "any", _est(low=80, exp=100, high=120), _est(tier=0, low=10, exp=300, high=900)
    )
    assert (out.ram_low, out.ram_expected, out.ram_high) == (80, 100, 900)
    assert ranges.apply("any", _est(), None).ram_high == 120  # no Tier 0 to take the ceiling from
