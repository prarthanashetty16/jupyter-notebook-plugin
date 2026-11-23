"""The Phase 7 acceptance verdict of evaluate --val (benchmarks.phase7_verdict): bars, bounds, INCONCLUSIVE rule."""

from __future__ import annotations

import pandas as pd
import pytest

from benchmarks import phase7_verdict as p7

MB = 2**20


def _rows(n_points: int, n_above: int, cases: int = 12, time_ok: int | None = None) -> pd.DataFrame:
    """Tier 1 rows: ``n_above`` of ``n_points`` above high; ``time_ok`` within one bucket (default all)."""
    time_ok = n_points if time_ok is None else time_ok
    rows = []
    for i in range(n_points):
        actual = 300 * MB if i < n_above else 100 * MB
        rows.append({
            "point_id": f"p{i}", "case": f"c{i % cases}", "op": "merge", "size": 1, "tier": 1,
            "has_estimate": True, "pred_status": "ok", "status": "ok", "confidence": 0.5,
            "ram_class": "valid", "ram_value": actual, "ram_low": 50 * MB, "ram_expected": 100 * MB,
            "ram_high": 200 * MB, "time_class": "valid", "time_value": 1.0 if i < time_ok else 1000.0,
            "time_low": 0.5, "time_expected": 1.0, "time_high": 2.0, "cap_bytes": 10**12,
            "ram_bound_bytes": None, "input_bytes": 10 * MB, "inspected_bytes": 10 * MB,
        })  # fmt: skip
    return pd.DataFrame(rows)


def test_bounds_match_the_values_quoted_in_the_preregistration():
    assert p7.clopper_pearson_upper(0, 30) == pytest.approx(0.095, abs=0.001)
    assert p7.clopper_pearson_upper(0, 100) == pytest.approx(0.030, abs=0.001)
    assert p7.clopper_pearson_upper(0, 15) == pytest.approx(0.181, abs=0.001)
    assert p7.clopper_pearson_upper(1, 10) == pytest.approx(0.394, abs=0.001)  # exact one-sided 95%
    assert 0.0 < p7.wilson_lower(95, 100) < 0.95


def test_ram_per_point_bar_and_the_inconclusive_rule():
    assert (
        p7.ram_points(_rows(29, 0))["verdict"] == "INCONCLUSIVE"
    )  # < 30 valid points: never a pass
    assert p7.ram_points(_rows(40, 1))["verdict"] == "MET"  # 2.5%
    r = p7.ram_points(_rows(40, 2))  # 5%
    assert r["verdict"] == "FAILED" and r["upper"] > r["rate"]


def test_ram_per_configuration_counts_a_case_with_any_point_above_high():
    r = p7.ram_configurations(_rows(40, 2, cases=12))  # points 0 and 1: cases c0 and c1
    assert (
        (r["k"], r["n"]) == (2, 12)
        and r["configs_above"] == ["c0", "c1"]
        and r["verdict"] == "FAILED"
    )
    assert (
        p7.ram_configurations(_rows(40, 0, cases=9))["verdict"] == "INCONCLUSIVE"
    )  # < 10 configurations


def test_time_within_one_bucket_bar():
    assert p7.time_within_one(_rows(40, 0, time_ok=39))["verdict"] == "MET"  # 97.5%
    assert p7.time_within_one(_rows(40, 0, time_ok=37))["verdict"] == "FAILED"  # 92.5%


def test_section_states_its_source_flags_incomplete_runs_and_never_relabels_s1_s5():
    text = p7.section(_rows(40, 2), planned=141)
    assert "Phase 7 acceptance verdict" in text and "phase7-preregistration.md" in text
    assert "LEGACY" in text and "NOT the Phase 7 acceptance criteria" in text
    assert "INCOMPLETE RUN: 40 of 141" in text
    assert "FAILED its held-out check" in text and "RAM per point" in text
    assert "does not apply to val-v5" in text
    assert "INCOMPLETE" not in p7.section(_rows(40, 0), planned=40)


def _rows_tier(df: pd.DataFrame, tier: int) -> pd.DataFrame:
    out = df.copy()
    out["tier"] = tier
    return out


def test_time_tier_is_a_labelled_interpretation_and_tier0_is_shown_separately():
    t1 = _rows(40, 0, time_ok=39)  # Tier 1: 97.5% within one -> MET
    t0 = _rows_tier(_rows(40, 0, time_ok=30), 0)  # Tier 0: 75% within one (information only)
    text = p7.section(pd.concat([t1, t0], ignore_index=True))
    assert "PROVISIONAL INTERPRETATION" in text
    assert "does NOT specify a tier for the time criterion" in text
    assert "not a pre-registered requirement" in text
    assert "time within-one bucket, Tier 0 (information only) | 40 | 30 | 75.0%" in text
    assert "no verdict" in text and "DISAGREE" in text
    # the verdict uses Tier 1 only; the Tier 0 numbers never change it, and the bar is unchanged
    assert p7.time_within_one(pd.concat([t1, t0]))["verdict"] == "MET" and p7.TIME_BAR == 0.95
    assert "mandated" not in text
