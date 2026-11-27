import pandas as pd

from benchmarks.realworld.evaluate_real import (
    MIB,
    PARTIAL_HEADROOMS_MIB,
    partial_safety,
    report,
    risk_eval,
)


def test_partial_cell_safety_checks_lower_bound_and_all_headrooms():
    row = {
        "hash": "partial-cell",
        "ops": ["sort_values", "value_counts"],
        "uncovered": 1,
        "ram_class": "valid",
        "ram_value": 70 * MIB,
        "cell": {"ram_low": 80 * MIB},
        "simulated_risk_classes": {str(h): "OK" for h in PARTIAL_HEADROOMS_MIB},
    }

    scored = partial_safety(pd.DataFrame([row]))["partial"]

    assert scored["n"] == 1
    assert scored["lower_violations"] == ["partial-cell"]
    assert scored["risk_violations"] == [("partial-cell", 64)]
    assert not scored["missing_classes"]


def test_partial_cell_without_a_covered_lower_bound_is_reported():
    row = {
        "hash": "partial-cell",
        "ops": ["sort_values", "value_counts"],
        "uncovered": 1,
        "ram_class": "valid",
        "ram_value": MIB,
        "cell": None,
        "simulated_risk_classes": {str(h): "UNKNOWN" for h in PARTIAL_HEADROOMS_MIB},
    }

    scored = partial_safety(pd.DataFrame([row]))["partial"]

    assert scored["n"] == 1
    assert scored["missing_lower_bounds"] == ["partial-cell"]
    assert not scored["risk_violations"]


def test_missing_partial_lower_bound_makes_reported_score_inconclusive():
    row = {
        "hash": "partial-cell",
        "ops": ["sort_values", "value_counts"],
        "uncovered": 1,
        "status": "ok",
        "ram_class": "valid",
        "ram_value": MIB,
        "cell": None,
        "simulated_risk_classes": {str(h): "UNKNOWN" for h in PARTIAL_HEADROOMS_MIB},
        "suggestions": [],
    }

    text = report(pd.DataFrame([row]), eligible_count=150)

    assert "1 partial cells lack a covered lower bound" in text
    assert "-> INCONCLUSIVE" in text


def test_partial_risk_replay_uses_the_cell_estimate():
    cell = {
        "ram_low": 50 * MIB,
        "ram_expected": 80 * MIB,
        "ram_high": 100 * MIB,
        "time_low": 1.0,
        "time_expected": 2.0,
        "time_high": 4.0,
        "confidence": 0.9,
        "tier": 1,
    }
    estimate = {
        "op": "sort_values",
        "ram_low": 40 * MIB,
        "ram_expected": 70 * MIB,
        "ram_high": 90 * MIB,
        "time_low": 1.0,
        "time_expected": 2.0,
        "time_high": 4.0,
        "confidence": 0.9,
        "tier": 1,
    }
    row = {
        "hash": "partial-cell",
        "notebook": "notebook",
        "ops": ["sort_values", "value_counts"],
        "uncovered": 1,
        "estimates": [estimate],
        "cell": cell,
        "cell_warn": cell,
        "ram_value": 90 * MIB,
        "avail_start": 64 * MIB,
        "rss_start": 0,
    }

    scored, _ = risk_eval(pd.DataFrame([row]))
    by_limit = dict(zip(scored["limit"], scored["class"], strict=True))

    assert by_limit["free RAM at start"] == "HIGH_RISK"
    assert by_limit["2048 MiB"] == "UNKNOWN"
