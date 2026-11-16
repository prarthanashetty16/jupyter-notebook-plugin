"""Frozen dev/test split and the guard around the test split."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pytest

from benchmarks import split as split_mod
from benchmarks.evaluate import (
    load_joined,
    load_sealed,
    write_final_report,
    write_report,
)
from benchmarks.runner import ACTUAL_FIELDS, PREDICTION_FIELDS, RunConfig, run_suite
from benchmarks.split import (
    LOG_HEADING,
    SealedAccessError,
    digest,
    freeze_from_docs,
    load_split,
    open_test_split,
    seen_cases,
)
from benchmarks.suite import BASE, CASES, SUITES, FrameInput, GridPoint, build_grid

ROOT = Path(__file__).parent.parent
MB = 2**20
TEST_CASE = "drop_duplicates/realistic_nulls_dup30"
DEV_CASE = "drop_duplicates/mixed_dup0"


# -- the frozen split ----------------------------------------------------------------------------
def test_split_loads_and_covers_every_case_exactly_once():
    sp = load_split()
    names = {c.name for c in CASES}
    assert sp.dev | sp.test == names and not (sp.dev & sp.test)
    assert len(sp.dev) >= 20 and len(sp.test) >= 10


def test_every_operation_has_both_dev_and_test_configurations():
    sp = load_split()
    ops = {c.op for c in CASES}
    for op in ops:
        assert any(c.op == op and c.name in sp.dev for c in CASES), op
        assert any(c.op == op and c.name in sp.test for c in CASES), op


def test_test_cases_were_never_seen_in_any_committed_report():
    sp = load_split()
    seen = seen_cases()
    assert seen, "expected committed reports under docs/benchmarks"
    assert not (sp.test & seen), sorted(sp.test & seen)
    assert sp.dev <= seen | {c for c in sp.dev if c not in seen}  # dev may include later additions


def test_split_is_by_configuration_not_by_size():
    for suite in SUITES:
        by_case: dict[str, set[str]] = {}
        for p in build_grid(suite):
            by_case.setdefault(p.case, set()).add(p.split)
        assert all(len(v) == 1 for v in by_case.values())


def test_grid_runs_dev_first_and_splits_filter():
    grid = build_grid("small")
    kinds = [p.split for p in grid]
    assert kinds == sorted(kinds, key=lambda s: s != "dev") and set(kinds) == {"dev", "test"}
    assert {p.split for p in build_grid("small", splits=("dev",))} == {"dev"}
    assert max(p.size for p in build_grid("full", max_size=10_000_000)) <= 10_000_000


def test_full_suite_reaches_floor_and_large_points():
    grid = build_grid("full")
    sort_sizes = {p.size for p in grid if p.case == "np_sort/random"}
    assert min(sort_sizes) >= 5_000_000 and max(sort_sizes) >= 100_000_000
    assert max(p.est_footprint_bytes() for p in grid) > 4 * 2**30  # points reach several GB
    assert any(1 * 2**30 < p.est_footprint_bytes() < 4 * 2**30 for p in grid)
    assert min(p.size for p in grid if p.case.startswith("drop_duplicates")) >= 1_000_000


def test_tampering_is_detected(tmp_path):
    raw = json.loads(split_mod.SPLIT_PATH.read_text())
    raw["dev"].append("made/up")
    bad = tmp_path / "split.json"
    bad.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="modified after freezing"):
        load_split(bad)
    raw["dev"].pop()
    raw["test"].append(raw["dev"][0])
    raw["sha256"] = {"dev": digest(raw["dev"]), "test": digest(raw["test"])}
    bad.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="both dev and test"):
        load_split(bad)


def test_freeze_refuses_to_overwrite():
    with pytest.raises(FileExistsError):
        freeze_from_docs([c.name for c in CASES])


def test_unclassified_case_is_an_error():
    with pytest.raises(ValueError, match="not classified"):
        load_split().of("no/such_case")


# -- the guard -----------------------------------------------------------------------------------
def _write(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in fields})


def _point(case, n):
    base = {"suite": "t", "op": "drop_duplicates", "size": 1, "status": "ok",
            "ram_delta_all": json.dumps([100 * MB, 101 * MB]), "poll_delta_all": json.dumps([99 * MB, 99 * MB]),
            "time_s_all": json.dumps([1.0, 1.01]), "input_bytes": 10 * MB, "cap_bytes": 10**10}  # fmt: skip
    pred = {"tier": 0, "status": "ok", "has_estimate": True, "model": "m", "ram_low": 50 * MB,
            "ram_expected": 120 * MB, "ram_high": 300 * MB, "time_low": 0.5, "time_expected": 1.2,
            "time_high": 3.0, "overhead_cold_s": 0.01, "overhead_warm_s": 0.005,
            "inspected_bytes": 10 * MB}  # fmt: skip
    pid = f"{case}|n={n}"
    return {**base, "point_id": pid, "case": case}, {**pred, "point_id": pid}


@pytest.fixture
def results(tmp_path):
    out = tmp_path / "res"
    (a_dev, p_dev), (a_test, p_test) = _point(DEV_CASE, 1), _point(TEST_CASE, 1)
    _write(out / "actuals.csv", ACTUAL_FIELDS, [a_dev])
    _write(out / "predictions.csv", PREDICTION_FIELDS, [p_dev])
    _write(out / "sealed" / "actuals.csv", ACTUAL_FIELDS, [a_test])
    _write(out / "sealed" / "predictions.csv", PREDICTION_FIELDS, [p_test])
    (out / "meta.json").write_text(json.dumps({"suite": "t", "cap_bytes": 10**10}))
    return out


def test_dev_loading_never_returns_test_rows(results):
    df = load_joined(results)
    assert set(df["case"]) == {DEV_CASE}


def test_dev_files_containing_a_test_case_are_refused(tmp_path):
    out = tmp_path / "leaky"
    a, p = _point(TEST_CASE, 1)
    _write(out / "actuals.csv", ACTUAL_FIELDS, [a])
    _write(out / "predictions.csv", PREDICTION_FIELDS, [p])
    with pytest.raises(SealedAccessError):
        load_joined(out)


def test_sealed_loading_needs_a_logged_token(results):
    for bad in (None, "token", object()):
        with pytest.raises(SealedAccessError):
            load_sealed(results, None, bad)


def test_normal_report_hides_the_test_split(results):
    text = write_report(results).read_text(encoding="utf-8")
    assert "Test split (sealed)" in text and "1 test points measured" in text
    assert TEST_CASE not in text
    for csv_file in results.glob("*.csv"):
        assert TEST_CASE not in csv_file.read_text(encoding="utf-8"), csv_file.name


def test_final_report_requires_a_reason_and_logs_every_use(results, tmp_path):
    progress = tmp_path / "PROGRESS.md"
    progress.write_text(
        f"# Progress\n\nstuff\n\n{LOG_HEADING}\n\n(none yet)\n\n## Later section\n\nmore\n",
        encoding="utf-8",
    )
    with pytest.raises(SealedAccessError):
        write_final_report(results, "  ", progress_path=progress)
    assert "reason:" not in progress.read_text(encoding="utf-8")  # nothing logged on refusal

    report = write_final_report(results, "first look", progress_path=progress, command="cmd1")
    write_final_report(results, "second look", progress_path=progress, command="cmd2")
    text = report.read_text(encoding="utf-8")
    assert "## Dev split" in text and "## Test split" in text
    assert text.index("## Dev split") < text.index(TEST_CASE) or TEST_CASE in text
    log = progress.read_text(encoding="utf-8")
    assert log.count("- 20") == 2 and "first look" in log and "second look" in log
    assert "1 test points" in log and "`cmd1`" in log
    assert log.index(LOG_HEADING) < log.index("first look") < log.index("second look")
    assert log.index("first look") < log.index("## Later section")  # inserted inside its section


def test_open_test_split_creates_the_heading(tmp_path):
    progress = tmp_path / "P.md"
    token = open_test_split(
        "why", results_dir=tmp_path, command="c", n_points=3, progress_path=progress
    )
    assert token.reason == "why" and LOG_HEADING in progress.read_text(encoding="utf-8")


def test_runner_routes_test_points_to_sealed(tmp_path):
    out = tmp_path / "results" / "t"
    dev = GridPoint(id=f"{DEV_CASE}|n=2000", case=DEV_CASE, op="drop_duplicates",
                    source="df.drop_duplicates()", size=2000,
                    inputs=(FrameInput(BASE.with_(n_rows=2000)),), repeats=1,
                    footprint_factor=3.0, split="dev")  # fmt: skip
    test = GridPoint(id=f"{TEST_CASE}|n=2000", case=TEST_CASE, op="drop_duplicates",
                     source="df.drop_duplicates()", size=2000,
                     inputs=(FrameInput(BASE.with_(n_rows=2000, null_rate=0.05)),), repeats=1,
                     footprint_factor=3.0, split="test")  # fmt: skip
    run_suite(RunConfig(suite="small", out_dir=out, calibrate=False), [dev, test])
    dev_rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    sealed_rows = list(csv.DictReader((out / "sealed" / "actuals.csv").open(encoding="utf-8")))
    assert [r["case"] for r in dev_rows] == [DEV_CASE] and dev_rows[0]["split"] == "dev"
    assert [r["case"] for r in sealed_rows] == [TEST_CASE] and sealed_rows[0]["split"] == "test"
    assert (out / "sealed" / "predictions.csv").exists()
    progress = json.loads((out / "progress.json").read_text())
    assert progress["state"] == "finished" and progress["counts"]["measured"] == 2


def test_only_the_final_path_touches_sealed_files():
    """Dev tooling (calibration, comparison, state, models) must not reference the sealed area."""
    allowed = {"split.py", "evaluate.py", "runner.py", "__main__.py", "suite.py"}
    offenders = []
    for path in [*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath("benchmarks").rglob("*.py")]:
        if path.name in allowed:
            continue
        if re.search(
            r"sealed|SEALED_DIR|open_test_split|load_sealed", path.read_text(encoding="utf-8")
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_calibration_never_imports_benchmark_code():
    source = (ROOT / "src" / "nexus" / "calibrate.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+benchmarks", source, re.MULTILINE)
