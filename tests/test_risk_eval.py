"""Risk evaluation helpers (Phase 5): the statistics, and a synthetic end-to-end replay."""

from __future__ import annotations

import math

import pandas as pd

from benchmarks import risk_eval as re_


def test_wilson_lower_bound_known_values():
    assert math.isnan(re_.wilson_lower(0, 0))
    assert abs(re_.wilson_lower(10, 10) - 0.7225) < 1e-3
    assert re_.wilson_lower(50, 100) < 0.5 < 0.6


def _row(pid, op, ram_exp, actual_mb, *, has=True, conf=0.5):
    mb = 2**20
    return {
        "point_id": pid, "op": op, "size": 1, "status": "ok", "ram_class": "valid", "tier": 1,
        "pred_status": "ok", "has_estimate": has, "ram_low": ram_exp // 2, "ram_expected": ram_exp,
        "ram_high": ram_exp * 2, "time_low": 0.1, "time_expected": 0.2, "time_high": 0.4,
        "confidence": conf, "cap_bytes": 10**12, "ram_value": actual_mb * mb, "ram_bound_bytes": None,
        "input_bytes": 10 * mb, "inspected_bytes": 10 * mb,
    }  # fmt: skip


def test_replay_counts_misses_and_never_counts_unknown_as_alert():
    mb = 2**20
    df = pd.DataFrame(
        [
            _row(
                "a", "x", 200 * mb, 300
            ),  # predicted fits 512 MB? high 400 -> alert at 256; real 310 MB
            _row("b", "x", 20 * mb, 600),  # under-predicted: a miss at 256 MB
            _row("c", "y", 20 * mb, 10, has=False),  # no estimate: UNKNOWN, negative
        ]
    )
    c = re_.classify_all(df, limits_mb=(256,))
    by = {r.point_id: r for r in c.itertuples()}
    assert by["a"].positive and by["a"].alert
    assert by["b"].positive and not by["b"].alert  # the miss is reported, not hidden
    assert by["c"].risk == "UNKNOWN" and not by["c"].alert and not by["c"].positive
    res = re_.evaluate(df)
    assert set(res["missed"]["point_id"]) == {"b"}


def test_section_reports_r1_r2_per_operation_and_r3():
    mb = 2**20
    rows = [
        _row(f"p{i}", "merge" if i % 2 else "groupby", (100 + i) * mb, 50 + 10 * i)
        for i in range(40)
    ]
    text = re_.section(pd.DataFrame(rows), "Risk engine on val-v5 (pre-registered R1-R3)")
    assert text.startswith("## Risk engine on val-v5")
    for needle in ("R1 recall", "R2 false alarms", "R3 HIGH_RISK precision", "### Per operation"):
        assert needle in text, needle
