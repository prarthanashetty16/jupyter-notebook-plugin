"""Pilot mode, val-v5 priority order, and checkpoint / resume of an interrupted run."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from benchmarks import pilot
from benchmarks.runner import (
    ACTUAL_FIELDS,
    PREDICTION_FIELDS,
    ResultStore,
    RunConfig,
    repair_partial_rows,
    run_suite,
)
from benchmarks.suite import build_grid, priority_of
from tests._resume_worker import points

ROOT = Path(__file__).resolve().parents[1]


# -- priority order ---------------------------------------------------------------------------------------
def test_val_v5_runs_in_priority_order_cases_and_sizes_kept():
    grid = build_grid("full", splits=("val-v5",))
    prios = [priority_of(p.op) for p in grid]
    assert prios == sorted(prios) and set(prios) == {1, 2, 3}
    assert {p.op for p in grid if priority_of(p.op) == 1} == {
        "merge",
        "groupby",
        "astype",
        "drop_duplicates",
        "pandas.read_csv",
    }
    assert {p.op for p in grid if priority_of(p.op) == 2} == {"pandas.concat", "sort_values"}
    assert {p.op for p in grid if priority_of(p.op) == 3} == {"numpy.sort", "operator.matmul"}
    merge = [p for p in grid if p.op == "merge"][:3]
    assert len({p.case for p in merge}) == 1
    assert [p.size for p in merge] == sorted(p.size for p in merge)  # case by case, sizes ascending


def test_dev_order_is_untouched_by_the_priority_rule():
    dev = build_grid("small", splits=("dev",))
    assert len({priority_of(p.op) for p in dev}) > 1
    assert [p.op for p in dev] != sorted((p.op for p in dev), key=priority_of)  # suite order kept


# -- pilot extrapolation --------------------------------------------------------------------------------------
def test_extrapolation_uses_the_mean_of_the_same_size_and_scales_unseen_sizes():
    timed = [
        {"op": "merge", "size": 3_000_000, "seconds": 100.0},
        {"op": "merge", "size": 3_000_000, "seconds": 140.0},
        {"op": "merge", "size": 10_000_000, "seconds": 400.0},
    ]
    rest = [
        {"id": "a", "op": "groupby", "size": 3_000_000},
        {"id": "b", "op": "groupby", "size": 10_000_000},
        {"id": "c", "op": "groupby", "size": 30_000_000},
    ]
    e = pilot.extrapolate(timed, rest)
    assert e["ok"] and e["points_scaled"] == 1
    assert e["seconds_expected"] == pytest.approx(120.0 + 400.0 + 400.0 * 3)  # 30M scaled from 10M
    assert e["seconds_low"] < e["seconds_expected"] < e["seconds_high"]


def test_matmul_scales_quadratically_in_the_dimension_and_no_pilot_gives_no_estimate():
    timed = [{"op": "operator.matmul", "size": 8000, "seconds": 60.0}]
    e = pilot.extrapolate(timed, [{"id": "x", "op": "operator.matmul", "size": 16000}])
    assert e["seconds_expected"] == pytest.approx(240.0)
    assert not pilot.extrapolate([], [{"id": "x", "op": "merge", "size": 1}])["ok"]


def test_pilot_runs_only_n_points_and_writes_the_extrapolation(tmp_path):
    out = tmp_path / "results" / "t"
    cfg = RunConfig(suite="small", out_dir=out, calibrate=False, plan_with_model=False, pilot=2)
    run_suite(cfg, points(5))
    rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    assert len(rows) == 2  # only the first N points ran
    report = json.loads((out / "pilot.json").read_text())
    assert report["pilot_points"] == 2 and report["measured_points"] == 2
    est = report["estimate_remaining"]
    assert est["ok"] and est["points_remaining"] == 3 and est["hours_expected"] > 0
    assert "remaining 3 points" in pilot.summary(report)


# -- torn writes --------------------------------------------------------------------------------------------------
def _store_with_rows(path: Path, n: int) -> None:
    store = ResultStore(path, ACTUAL_FIELDS, ("point_id",))
    for i in range(n):
        store.add({"point_id": f"p{i}", "status": "ok", "case": "c", "error": "multi\nline"})


def test_a_half_written_last_row_is_dropped_and_earlier_rows_survive(tmp_path):
    path = tmp_path / "actuals.csv"
    _store_with_rows(path, 3)
    with path.open("ab") as fh:
        fh.write(b"p3,suite,case,op,12")  # killed mid-write: no terminator, far too few fields
    assert repair_partial_rows(path, ACTUAL_FIELDS) == 1
    store = ResultStore(path, ACTUAL_FIELDS, ("point_id",))
    assert sorted(store.done) == [("p0",), ("p1",), ("p2",)] and store.has(point_id="p3") is None
    store.add({"point_id": "p3", "status": "ok"})  # the file is appendable again
    assert len(list(csv.DictReader(path.open(newline="", encoding="utf-8")))) == 4


def test_a_torn_row_that_contains_a_quoted_newline_is_also_dropped(tmp_path):
    path = tmp_path / "actuals.csv"
    _store_with_rows(path, 2)
    with path.open("ab") as fh:
        fh.write(b'p2,suite,case,op,1,src,error,"half of a\nmultiline message')
    store = ResultStore(path, ACTUAL_FIELDS, ("point_id",))
    assert store.repaired >= 1 and sorted(store.done) == [("p0",), ("p1",)]


def test_an_intact_file_is_left_alone(tmp_path):
    path = tmp_path / "predictions.csv"
    store = ResultStore(path, PREDICTION_FIELDS, ("point_id", "tier"))
    store.add({"point_id": "p", "tier": 0, "status": "ok"})
    before = path.read_bytes()
    assert repair_partial_rows(path, PREDICTION_FIELDS) == 0 and path.read_bytes() == before


# -- kill the runner mid-run and resume -------------------------------------------------------------------------------
def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(proc.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass
    proc.wait(30)


def test_a_killed_runner_resumes_without_remeasuring_finished_points_or_corrupting_the_csv(
    tmp_path,
):
    out = tmp_path / "results" / "t"
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests._resume_worker", str(out)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    actuals = out / "actuals.csv"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and proc.poll() is None:
        if actuals.exists() and actuals.read_text(encoding="utf-8").count("resume/case") >= 1:
            break
        time.sleep(0.02)
    _kill_tree(proc)  # mid-run: the next point is in flight
    first = actuals.read_text(encoding="utf-8")
    finished = [ln for ln in first.splitlines() if ln.startswith("resume/case")]
    assert finished and len(finished) < 4, "the kill must land before the run finished"
    kept_row = finished[0]

    run_suite(
        RunConfig(suite="small", out_dir=out, calibrate=False, plan_with_model=False), points()
    )

    assert kept_row in actuals.read_text(encoding="utf-8")  # byte-identical: not measured again
    rows = list(csv.DictReader(actuals.open(newline="", encoding="utf-8")))
    ids = [r["point_id"] for r in rows]
    assert sorted(ids) == sorted({p.id for p in points()}) and len(ids) == len(set(ids)) == 4
    assert all(r["status"] == "ok" for r in rows)
    with actuals.open(
        newline="", encoding="utf-8"
    ) as fh:  # no corrupted row: header width everywhere
        assert {len(r) for r in csv.reader(fh)} == {len(ACTUAL_FIELDS)}
    preds = list(csv.DictReader((out / "predictions.csv").open(newline="", encoding="utf-8")))
    assert sorted(r["point_id"] for r in preds) == sorted(
        ids
    )  # a prediction cut off by the kill is filled in


def test_resuming_a_finished_run_does_nothing(tmp_path):
    out = tmp_path / "results" / "t"
    cfg = RunConfig(suite="small", out_dir=out, calibrate=False, plan_with_model=False)
    run_suite(cfg, points(2))
    before = (out / "actuals.csv").read_bytes(), (out / "predictions.csv").read_bytes()
    run_suite(cfg, points(2))
    assert ((out / "actuals.csv").read_bytes(), (out / "predictions.csv").read_bytes()) == before
