"""Evaluation metrics on hand-computed synthetic results, plus runner resume."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from benchmarks.evaluate import (
    Floors,
    accuracy_table,
    censor_breakdown,
    classify_points,
    instrument_crosscheck,
    load_joined,
    md_table,
    oom_table,
    overhead_table,
    tier1_fallback_markdown,
    write_report,
)
from benchmarks.runner import ACTUAL_FIELDS, PREDICTION_FIELDS, ResultStore

MB = 2**20


def make_df(rows):
    base = {
        "status": "ok", "pred_status": "ok", "tier": 0, "op": "x", "case": "x/a",
        "has_estimate": True, "input_bytes": 0, "inspected_bytes": 0, "cap_bytes": 10**12,
        "ram_class": "valid", "ram_bound_bytes": 0, "time_class": "valid", "time_value": 1.0,
        "time_low": 0.5, "time_expected": 1.0, "time_high": 2.0,
        "overhead_cold_s": 0.01, "overhead_warm_s": 0.005,
    }  # fmt: skip
    out = pd.DataFrame([{**base, **r} for r in rows])
    if "peak_bytes" in out:
        out["ram_value"] = out.pop("peak_bytes")
    return out


def test_accuracy_metrics_hand_computed():
    df = make_df(
        [
            # actual 100 MB; expected 150 (err 50%), range covers
            {
                "peak_bytes": 100 * MB,
                "ram_low": 80 * MB,
                "ram_expected": 150 * MB,
                "ram_high": 200 * MB,
            },
            # actual 100 MB; expected 50 (err 50%), actual above high
            {
                "peak_bytes": 100 * MB,
                "ram_low": 20 * MB,
                "ram_expected": 50 * MB,
                "ram_high": 90 * MB,
            },
            # actual 100 MB; expected 100 (err 0), covered
            {
                "peak_bytes": 100 * MB,
                "ram_low": 50 * MB,
                "ram_expected": 100 * MB,
                "ram_high": 400 * MB,
            },
            # actual 100 MB; expected 400 (err 300%), actual below low
            {
                "peak_bytes": 100 * MB,
                "ram_low": 120 * MB,
                "ram_expected": 400 * MB,
                "ram_high": 800 * MB,
            },
        ]
    )
    row = accuracy_table(df, ["tier", "op"]).iloc[0]
    assert row["ram_n"] == 4 and row["ram_valid"] == 4
    assert row["ram_err_med"] == pytest.approx(0.5)
    assert row["ram_err_p90"] == pytest.approx(np.quantile([0.5, 0.5, 0.0, 3.0], 0.9))
    assert row["ram_bias"] == pytest.approx(np.median([1.5, 0.5, 1.0, 4.0]))
    assert row["ram_cov"] == pytest.approx(0.5)
    assert row["ram_above_high"] == pytest.approx(0.25)
    assert row["ram_below_low"] == pytest.approx(0.25)
    assert row["ram_width"] == pytest.approx(np.mean([120 / 150, 70 / 50, 350 / 100, 680 / 400]))
    assert row["time_cov"] == 1.0 and row["time_err_med"] == 0.0


def test_classes_are_counted_separately_and_only_valid_enters_metrics():
    ok = {"ram_low": 1, "ram_expected": 2, "ram_high": 3}
    df = make_df(
        [
            {"peak_bytes": 100 * MB, **ok},
            {"peak_bytes": 5 * MB, "ram_class": "censored", **ok},
            {"peak_bytes": np.nan, "ram_class": "censored", **ok},
            {"peak_bytes": 90 * MB, "ram_class": "excluded", **ok},
            {"peak_bytes": 100 * MB, "has_estimate": False},
            {"peak_bytes": 100 * MB, "status": "error", **ok},
        ]
    )
    row = accuracy_table(df, ["tier", "op"]).iloc[0]
    assert (row["points"], row["estimated"]) == (5, 4)
    assert (row["ram_valid"], row["ram_censored"], row["ram_excluded"]) == (2, 2, 1)
    assert row["ram_n"] == 1


def test_classify_points_from_raw_repeats():
    raw = pd.DataFrame(
        [
            {"status": "ok", "ram_delta_all": json.dumps([100 * MB, 104 * MB, 102 * MB]),
             "time_s_all": json.dumps([0.5, 0.52, 0.51])},
            {"status": "ok", "ram_delta_all": json.dumps([None, None]),
             "time_s_all": json.dumps([0.01, 0.01])},
            {"status": "ok", "ram_delta_all": json.dumps([40 * MB, 90 * MB, 41 * MB]),
             "time_s_all": json.dumps([0.2, 0.2])},
            {"status": "ok", "ram_delta_all": json.dumps([5 * MB]), "time_s_all": json.dumps([0.5])},
            {"status": "timeout", "ram_delta_all": "", "time_s_all": ""},
        ]
    )  # fmt: skip
    out = classify_points(raw, Floors())
    assert list(out["ram_class"][:4]) == ["valid", "censored", "excluded", "censored"]
    assert pd.isna(out["ram_class"][4])
    assert list(out["ram_reason"][:4]) == ["", "below_setup_peak", "spread", "below_floor"]
    assert list(out["time_class"][:4]) == ["valid", "censored", "valid", "valid"]
    assert out["ram_value"][0] == 102 * MB
    loose = classify_points(raw, Floors(ram_bytes=MB, time_s=0.0, max_spread=10.0))
    assert loose["ram_class"][2] == "valid" and loose["ram_class"][3] == "valid"


def test_oom_precision_recall():
    est = {"ram_low": 0, "ram_expected": 0, "has_estimate": True}
    df = make_df(
        [
            {"peak_bytes": 500 * MB, "ram_high": 600 * MB, **est},  # true pos at 256 MB
            {"peak_bytes": 500 * MB, "ram_high": 100 * MB, **est},  # missed (false neg)
            {"peak_bytes": 10 * MB, "ram_high": 600 * MB, **est},  # false alarm
            {"peak_bytes": 10 * MB, "ram_high": 20 * MB, **est},  # true neg
            {"peak_bytes": 500 * MB, "has_estimate": False, "ram_high": np.nan,
             "ram_expected": np.nan, "ram_low": np.nan},  # no estimate -> never warns
            {"peak_bytes": 500 * MB, "ram_class": "excluded", "ram_high": 600 * MB, **est},
        ]
    )  # fmt: skip
    t = oom_table(df, 0, (256,))
    r = t[(t["rule"] == "high")].iloc[0]
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (1, 1, 2, 1)
    assert r["precision"] == pytest.approx(0.5) and r["recall"] == pytest.approx(1 / 3)


def test_oom_uses_upper_bound_for_censored_points():
    est = {"ram_low": 0, "ram_expected": 0, "ram_high": 0, "has_estimate": True}
    cens = {"ram_class": "censored", "peak_bytes": np.nan, "ram_bound_bytes": 300 * MB, **est}
    t = oom_table(make_df([cens]), 0, (256,))
    assert t[t["rule"] == "high"].iloc[0]["positives"] == 1


def test_oom_counts_killed_points_as_positives_below_cap():
    killed = {"status": "memory_limit", "peak_bytes": 0, "cap_bytes": 300 * MB, "ram_class": None,
              "ram_low": 0, "ram_expected": 0, "ram_high": 900 * MB}  # fmt: skip
    t = oom_table(make_df([killed]), 0, (256, 1024))
    low = t[(t["limit_mb"] == 256) & (t["rule"] == "high")].iloc[0]
    assert (low["tp"], low["positives"]) == (1, 1)
    assert t[t["limit_mb"] == 1024]["positives"].sum() == 0


def test_overhead_table():
    df = make_df([{"overhead_cold_s": 0.3}, {"overhead_cold_s": 0.1}])
    t = overhead_table(df, 0)
    assert t.iloc[-1]["op"] == "ALL" and t.iloc[-1]["over_budget"] == 1


def test_censor_breakdown_and_crosscheck():
    raw = pd.DataFrame(
        [
            {"point_id": "a", "op": "x", "status": "ok", "ram_class": "valid", "ram_reason": "",
             "time_class": "valid", "time_reason": "", "ram_delta_all": json.dumps([100 * MB]),
             "poll_delta_all": json.dumps([60 * MB])},
            {"point_id": "b", "op": "x", "status": "ok", "ram_class": "censored",
             "ram_reason": "below_setup_peak", "time_class": "censored",
             "time_reason": "below_floor", "ram_delta_all": json.dumps([None]),
             "poll_delta_all": json.dumps([0])},
        ]
    )  # fmt: skip
    b = censor_breakdown(raw).iloc[-1]
    assert (b["ram_valid"], b["ram_cens_setup_peak"], b["time_cens_floor"]) == (1, 1, 1)
    c = instrument_crosscheck(raw).iloc[-1]
    assert c["uncensored_runs"] == 1 and c["poll_over_os"] == 0
    assert c["median_poll_ratio"] == pytest.approx(0.6)
    bad = raw.assign(poll_delta_all=json.dumps([300 * MB]))
    assert instrument_crosscheck(bad).iloc[-1]["poll_over_os"] == 1


def test_md_table_handles_nan_and_percent():
    out = md_table(pd.DataFrame({"a": [0.5, math.nan], "b": ["x", "y"]}), ("a",))
    assert "50%" in out and "–" in out
    assert md_table(pd.DataFrame()) == "_no data_\n"


def test_tier1_fallback_report_is_per_operation_and_excludes_worker_failures():
    df = pd.DataFrame(
        [
            {
                "point_id": "m1",
                "op": "merge",
                "tier": 1,
                "pred_status": "ok",
                "hard_deadline_fired": "True",
            },
            {
                "point_id": "m2",
                "op": "merge",
                "tier": 1,
                "pred_status": "ok",
                "hard_deadline_fired": "False",
            },
            {
                "point_id": "m3",
                "op": "merge",
                "tier": 1,
                "pred_status": "memory_limit",
                "hard_deadline_fired": "False",
            },
            {
                "point_id": "a1",
                "op": "astype",
                "tier": 1,
                "pred_status": "ok",
                "hard_deadline_fired": "False",
            },
            {
                "point_id": "m1",
                "op": "merge",
                "tier": 0,
                "pred_status": "ok",
                "hard_deadline_fired": "False",
            },
        ]
    )
    report = tier1_fallback_markdown(df)
    assert "| merge | 2 | 1 | 50% |" in report
    assert "| astype | 1 | 0 | 0% |" in report
    assert "excluded from the denominator" in report and "`merge` 1" in report


def _write(path: Path, fields, rows):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in fields})


def test_end_to_end_report_from_csv(tmp_path):
    actual = {"point_id": "x/a|n=1", "suite": "t", "case": "x/a", "op": "x", "size": 1,
              "status": "ok", "ram_delta_all": json.dumps([100 * MB, 101 * MB, 99 * MB]),
              "poll_delta_all": json.dumps([90 * MB, 95 * MB, 80 * MB]),
              "time_s_all": json.dumps([1.0, 1.01, 0.99]), "input_bytes": 10 * MB,
              "cap_bytes": 10**10, "instrument": "os-peak-v2"}  # fmt: skip
    pred = {"point_id": "x/a|n=1", "tier": 0, "status": "ok", "has_estimate": True, "model": "m",
            "ram_low": 50 * MB, "ram_expected": 120 * MB, "ram_high": 300 * MB, "time_low": 0.5,
            "time_expected": 1.2, "time_high": 3.0, "confidence": 0.5, "overhead_cold_s": 0.01,
            "overhead_warm_s": 0.005, "inspected_bytes": 10 * MB}  # fmt: skip
    skipped = {**actual, "point_id": "x/a|n=2", "status": "skipped_cap"}
    _write(tmp_path / "actuals.csv", ACTUAL_FIELDS, [actual, skipped])
    _write(tmp_path / "predictions.csv", PREDICTION_FIELDS, [pred])
    (tmp_path / "meta.json").write_text(json.dumps({"suite": "t", "cap_bytes": 10**10}))
    df = load_joined(tmp_path)
    assert len(df) == 2 and df["tier"].notna().sum() == 1
    assert df.loc[0, "ram_class"] == "valid" and df.loc[0, "ram_value"] == 100 * MB
    report = write_report(tmp_path).read_text(encoding="utf-8")
    for needle in ("Tier 0", "skipped_cap", "RAM accuracy", "Instrument cross-check", "Floors:"):
        assert needle in report
    assert (tmp_path / "classification_by_op.csv").exists()
    assert (tmp_path / "fig_coverage_by_op_tier0.png").exists()


def test_result_store_resume_and_last_row_wins(tmp_path):
    path = tmp_path / "r.csv"
    store = ResultStore(path, ["point_id", "status"], ("point_id",))
    assert store.has(point_id="a") is None
    store.add({"point_id": "a", "status": "error"})
    store.add({"point_id": "a", "status": "ok"})
    again = ResultStore(path, ["point_id", "status"], ("point_id",))
    assert again.has(point_id="a")["status"] == "ok"
