"""Frozen dev / exposed-v1 / test-v2 split, the guard, and log redaction for the sealed split."""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
import re
from pathlib import Path

import pytest

from benchmarks import split as split_mod
from benchmarks.datasets import DatasetConfig
from benchmarks.evaluate import load_joined, load_sealed, write_final_report, write_report
from benchmarks.runner import ACTUAL_FIELDS, PREDICTION_FIELDS, RunConfig, run_suite
from benchmarks.split import (
    DEV,
    EXPOSED,
    LOG_HEADING,
    TEST,
    SealedAccessError,
    digest,
    load_split,
    open_test_split,
    seen_cases,
    supersede_to_v2,
)
from benchmarks.suite import (
    BASE,
    CASES,
    SUITES,
    ArrayInput,
    CsvInput,
    FrameInput,
    GridPoint,
    JoinInput,
    build_grid,
)

ROOT = Path(__file__).parent.parent
MB = 2**20
DEV_CASE = "drop_duplicates/mixed_dup0"
EXPOSED_CASE = "drop_duplicates/realistic_nulls_dup30"
TEST_CASE = "v2/drop_duplicates/clustered_nulls_varstr_dup60"


# -- the frozen split ----------------------------------------------------------------------------
def test_split_loads_and_covers_every_case_exactly_once():
    sp = load_split()
    names = {c.name for c in CASES}
    assert sp.dev | sp.exposed | sp.test == names
    assert not (sp.dev & sp.exposed) and not (sp.dev & sp.test) and not (sp.exposed & sp.test)
    assert (len(sp.dev), len(sp.exposed), len(sp.test)) == (29, 18, 17)
    assert all(n.startswith("v2/") for n in sp.test)


def test_every_operation_has_dev_exposed_and_test_v2_configurations():
    sp = load_split()
    for op in {c.op for c in CASES}:
        for group in (sp.dev, sp.exposed, sp.test):
            assert any(c.op == op and c.name in group for c in CASES), (op, sorted(group)[:1])


def test_history_records_the_exposure_and_the_old_test_digest():
    meta = load_split().meta
    assert meta["version"] == 2 and len(meta["history"]) == 2
    old = meta["history"][0]["sha256"]["test"]
    assert old == digest(load_split().exposed)  # exposed-v1 is exactly the old sealed list
    assert "exposure" in meta["history"][1]["event"] or "exposed" in meta["history"][1]["event"]


def test_test_v2_cases_were_never_seen_in_any_committed_report():
    sp = load_split()
    seen = seen_cases()
    assert seen, "expected committed reports under docs/benchmarks"
    assert not (sp.test & seen), sorted(sp.test & seen)


def _specs(case):
    return case.make_inputs(1000 if case.size_kind == "rows" else 64)


def _seeds(spec):
    if isinstance(spec, (FrameInput, CsvInput)):
        return {spec.cfg.seed}
    if isinstance(spec, JoinInput):
        return {spec.left.seed, spec.right_seed}
    if isinstance(spec, ArrayInput):
        return {spec.seed}
    return set()


def test_test_v2_configurations_differ_from_every_dev_and_exposed_configuration():
    sp = load_split()
    seen_reprs, seen_seeds = set(), set()
    for c in CASES:
        if c.name in sp.dev | sp.exposed:
            for spec in _specs(c):
                seen_reprs.add(repr(dataclasses.replace(spec, **_blank_size(spec))))
                seen_seeds |= _seeds(spec)
    for c in CASES:
        if c.name in sp.test:
            for spec in _specs(c):
                assert repr(dataclasses.replace(spec, **_blank_size(spec))) not in seen_reprs, (
                    c.name
                )
                assert not (_seeds(spec) & seen_seeds), (c.name, _seeds(spec) & seen_seeds)


def _blank_size(spec):
    """Compare configurations independent of the row count used to build them."""
    if isinstance(spec, (FrameInput, CsvInput)):
        return {"cfg": spec.cfg.with_(n_rows=1)}
    if isinstance(spec, JoinInput):
        return {"left": spec.left.with_(n_rows=1), "right_rows": 1}
    return {"shape": (1,)}


def test_most_test_v2_cases_use_generator_knobs_no_dev_case_uses():
    novel_defaults = DatasetConfig(n_rows=1)
    uses = 0
    for c in CASES:
        if not c.name.startswith("v2/"):
            continue
        for spec in _specs(c):
            cfg = getattr(spec, "cfg", None) or getattr(spec, "left", None)
            novel = cfg is not None and any(
                getattr(cfg, k) != getattr(novel_defaults, k)
                for k in ("zipf_exponent", "null_pattern", "str_len_dist", "ordering")
            )
            novel |= isinstance(spec, JoinInput) and spec.right_key_dist != "uniform"
            novel |= isinstance(spec, ArrayInput) and spec.pattern in (
                "nearly_sorted",
                "few_unique",
            )
            uses += novel
    assert uses >= 10
    for c in CASES:  # and none of those knobs appears in dev or exposed-v1
        if c.name.startswith("v2/"):
            continue
        for spec in _specs(c):
            cfg = getattr(spec, "cfg", None) or getattr(spec, "left", None)
            if cfg is not None:
                for k in ("zipf_exponent", "null_pattern", "str_len_dist", "ordering"):
                    assert getattr(cfg, k) == getattr(novel_defaults, k), (c.name, k)
            if isinstance(spec, JoinInput):
                assert spec.right_key_dist == "uniform", c.name


def test_split_is_by_configuration_not_by_size():
    for suite in SUITES:
        by_case: dict[str, set[str]] = {}
        for p in build_grid(suite, splits=(DEV, EXPOSED, TEST)):
            by_case.setdefault(p.case, set()).add(p.split)
        assert all(len(v) == 1 for v in by_case.values())


def test_grid_default_excludes_the_sealed_group_and_orders_groups():
    assert {p.split for p in build_grid("small")} == {DEV, EXPOSED}
    everything = [p.split for p in build_grid("small", splits=(DEV, EXPOSED, TEST))]
    order = {DEV: 0, EXPOSED: 1, TEST: 2}
    assert everything == sorted(everything, key=order.get) and set(everything) == {
        DEV,
        EXPOSED,
        TEST,
    }
    assert {p.split for p in build_grid("small", splits=(TEST,))} == {TEST}


def test_every_test_v2_case_runs_and_gets_an_estimate_at_tiny_size(tmp_path):
    """Generators, sources and Tier 0 availability for test-v2 (tiny sizes; no values asserted)."""
    import numpy as np
    import pandas as pd

    from benchmarks.store import load, save
    from nexus.pipeline import Pipeline

    sp = load_split()
    pipeline = Pipeline(tier=0)
    for c in CASES:
        if c.name not in sp.test:
            continue
        size = 48 if c.size_kind == "dim" else 2000
        ns: dict = {"pd": pd, "np": np}
        for spec in c.make_inputs(size):
            if isinstance(spec, CsvInput):
                path = tmp_path / (c.name.replace("/", "_") + ".csv")
                from benchmarks.datasets import make_frame

                make_frame(spec.cfg).to_csv(path, index=False)
                ns["path"] = str(path)
            else:
                ns.update(spec.generate())
        source = c.source.format(csv=ns.get("path")) if "{csv" in c.source else c.source
        result = eval(source, ns)  # noqa: S307
        assert result is not None
        report = pipeline.run(source, ns)
        assert any(e.op.name == c.op for e in report.estimates), c.name
    assert callable(save) and callable(load)


def test_full_suite_reaches_floor_and_large_points():
    grid = build_grid("full")
    sort_sizes = {p.size for p in grid if p.case == "np_sort/random"}
    assert min(sort_sizes) >= 5_000_000 and max(sort_sizes) >= 100_000_000
    assert max(p.est_footprint_bytes() for p in grid) > 4 * 2**30
    assert any(1 * 2**30 < p.est_footprint_bytes() < 4 * 2**30 for p in grid)
    assert min(p.size for p in grid if p.case.startswith("drop_duplicates")) >= 1_000_000


def test_tampering_is_detected(tmp_path):
    raw = json.loads(split_mod.SPLIT_PATH.read_text())
    raw["groups"]["dev"]["cases"].append("made/up")
    bad = tmp_path / "split.json"
    bad.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="modified after freezing"):
        load_split(bad)
    raw["groups"]["dev"]["cases"].pop()
    raw["groups"]["test-v2"]["cases"].append(raw["groups"]["dev"]["cases"][0])
    raw["groups"]["test-v2"]["sha256"] = digest(raw["groups"]["test-v2"]["cases"])
    bad.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="two groups"):
        load_split(bad)


def test_supersede_refuses_a_version_2_file_and_reused_cases(tmp_path):
    with pytest.raises(ValueError, match="not a version-1"):
        supersede_to_v2(["new/case"], "again", path=split_mod.SPLIT_PATH)
    v1 = {"version": 1, "frozen": "2026-01-01", "dev": ["a/1"], "test": ["b/1"],
          "sha256": {"dev": digest(["a/1"]), "test": digest(["b/1"])}}  # fmt: skip
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(v1))
    with pytest.raises(ValueError, match="reuses existing"):
        supersede_to_v2(["b/1"], "bad", path=path)
    supersede_to_v2(["c/1"], "ok", path=path)
    sp = load_split(path)
    assert (sp.dev, sp.exposed, sp.test) == ({"a/1"}, {"b/1"}, {"c/1"})


def test_unclassified_case_is_an_error_but_group_of_defaults_to_dev():
    with pytest.raises(ValueError, match="not classified"):
        load_split().of("no/such_case")
    assert split_mod.group_of("no/such_case") == DEV


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
    (a_dev, p_dev), (a_exp, p_exp), (a_test, p_test) = (
        _point(DEV_CASE, 1),
        _point(EXPOSED_CASE, 1),
        _point(TEST_CASE, 1),
    )
    _write(out / "actuals.csv", ACTUAL_FIELDS, [a_dev, a_exp])
    _write(out / "predictions.csv", PREDICTION_FIELDS, [p_dev, p_exp])
    _write(out / "sealed" / "actuals.csv", ACTUAL_FIELDS, [a_test])
    _write(out / "sealed" / "predictions.csv", PREDICTION_FIELDS, [p_test])
    (out / "meta.json").write_text(json.dumps({"suite": "t", "cap_bytes": 10**10}))
    return out


def test_development_loading_returns_dev_and_exposed_but_never_test_v2(results):
    df = load_joined(results)
    assert set(df["case"]) == {DEV_CASE, EXPOSED_CASE}
    assert dict(zip(df["case"], df["split"], strict=True)) == {DEV_CASE: DEV, EXPOSED_CASE: EXPOSED}


def test_development_files_containing_a_test_v2_case_are_refused(tmp_path):
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


def test_normal_report_shows_dev_and_exposed_but_hides_test_v2(results):
    text = write_report(results).read_text(encoding="utf-8")
    assert (
        "## Dev split" in text
        and "## Exposed-v1 split (development and diagnosis only; never final claims)" in text
    )
    assert "Test-v2 split (sealed)" in text and "1 test-v2 points measured" in text
    assert TEST_CASE not in text
    assert DEV_CASE in text and EXPOSED_CASE in text
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
    assert "reason:" not in progress.read_text(encoding="utf-8")

    report = write_final_report(results, "first look", progress_path=progress, command="cmd1")
    write_final_report(results, "second look", progress_path=progress, command="cmd2")
    text = report.read_text(encoding="utf-8")
    assert (
        "## Dev split" in text and "## Test-v2 split" in text and "not evidence for claims" in text
    )
    assert TEST_CASE in text
    log = progress.read_text(encoding="utf-8")
    assert log.count("- 20") == 2 and "first look" in log and "second look" in log
    assert "test-v2" in log and "1 test points" in log and "`cmd1`" in log
    assert log.index(LOG_HEADING) < log.index("first look") < log.index("second look")
    assert log.index("first look") < log.index("## Later section")


def test_open_test_split_creates_the_heading(tmp_path):
    progress = tmp_path / "P.md"
    token = open_test_split(
        "why", results_dir=tmp_path, command="c", n_points=3, progress_path=progress
    )
    assert token.reason == "why" and LOG_HEADING in progress.read_text(encoding="utf-8")


# -- runner: routing and log redaction -------------------------------------------------------------
def _grid_point(case, split, **cfg):
    return GridPoint(id=f"{case}|n=2000", case=case, op="drop_duplicates", source="df.drop_duplicates()",
                     size=2000, inputs=(FrameInput(BASE.with_(n_rows=2000, **cfg)),), repeats=1,
                     footprint_factor=3.0, split=split)  # fmt: skip


def test_runner_routes_groups_and_redacts_sealed_log_lines(tmp_path, caplog):
    out = tmp_path / "results" / "t"
    points = [
        _grid_point(DEV_CASE, DEV),
        _grid_point(EXPOSED_CASE, EXPOSED, null_rate=0.05),
        _grid_point(TEST_CASE, TEST, null_rate=0.05, seed=101),
    ]
    with caplog.at_level(logging.INFO, logger="benchmarks"):
        run_suite(RunConfig(suite="small", out_dir=out, calibrate=False), points)
    dev_rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    sealed_rows = list(csv.DictReader((out / "sealed" / "actuals.csv").open(encoding="utf-8")))
    assert {r["case"]: r["split"] for r in dev_rows} == {DEV_CASE: DEV, EXPOSED_CASE: EXPOSED}
    assert [r["case"] for r in sealed_rows] == [TEST_CASE] and sealed_rows[0]["split"] == TEST
    assert (out / "sealed" / "predictions.csv").exists()
    progress = json.loads((out / "progress.json").read_text())
    assert progress["state"] == "finished" and progress["counts"]["measured"] == 3

    lines = [r.getMessage() for r in caplog.records]
    sealed_lines = [m for m in lines if TEST_CASE in m]
    assert sealed_lines, "the sealed point should still be logged (id/status/elapsed)"
    leak = re.compile(r"ram=|pred=|MB|\bt=|censored|tier\d|below_|\bs\b.*\bs\b")
    for m in sealed_lines:
        assert re.fullmatch(rf"\[\d+/\d+\] {re.escape(TEST_CASE)}\|n=2000: ok \[\d+s\]", m), m
        assert not leak.search(m), m
    for case in (DEV_CASE, EXPOSED_CASE):  # positive control: other groups still log values
        assert any(case in m and "ram=" in m and "pred=" in m for m in lines), case


def test_sealed_harness_errors_log_no_message_or_traceback(tmp_path, caplog, monkeypatch):
    import benchmarks.runner as runner

    def boom(*args, **kwargs):
        raise ValueError("secret measured value 123.4 MB")

    monkeypatch.setattr(runner, "run_actual", boom)
    out = tmp_path / "results" / "t"
    with caplog.at_level(logging.INFO, logger="benchmarks"):
        run_suite(
            RunConfig(suite="small", out_dir=out, calibrate=False),
            [_grid_point(TEST_CASE, TEST, seed=101)],
        )
    text = " ".join(r.getMessage() for r in caplog.records) + " ".join(
        str(r.exc_info) for r in caplog.records
    )
    assert "harness error (ValueError)" in text
    assert "secret" not in text and "123.4" not in text
    assert all(r.exc_info is None for r in caplog.records if TEST_CASE in r.getMessage())


def test_status_command_shows_counts_only_for_the_sealed_group(results, capsys):
    import argparse

    from benchmarks.__main__ import cmd_status

    (results / "run.log").write_text(
        f"00:00:01 [3/3] {TEST_CASE}|n=2000: ok [4s]\n", encoding="utf-8"
    )
    cmd_status(argparse.Namespace(results=results))
    out = capsys.readouterr().out
    assert "test-v2 (count only)" in out and "{'ok': 1}" in out
    assert "MB" not in out and "ram" not in out.lower().replace("results", "")


# -- source tree guard -------------------------------------------------------------------------------
def test_only_the_final_path_touches_sealed_files():
    """Dev tooling (calibration, comparison, diagnosis, state, models) must not use the sealed API."""
    allowed = {"split.py", "evaluate.py", "runner.py", "__main__.py", "maintenance.py"}
    pattern = re.compile(
        r"SEALED_DIR|SEALED_GROUPS|open_test_split|load_sealed|require_token|SealedAccessToken"
    )
    offenders = []
    for path in [*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath("benchmarks").rglob("*.py")]:
        if path.name not in allowed and pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_calibration_never_imports_benchmark_code():
    source = (ROOT / "src" / "nexus" / "calibrate.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+benchmarks", source, re.MULTILINE)
