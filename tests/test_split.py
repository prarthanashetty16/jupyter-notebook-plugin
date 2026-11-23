"""Frozen dev / test-v2 / val-v5 split (version 6), the guards, and log redaction."""

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
from benchmarks.evaluate import (
    load_joined,
    load_sealed,
    load_validation,
    write_final_report,
    write_report,
    write_validation_report,
)
from benchmarks.runner import ACTUAL_FIELDS, PREDICTION_FIELDS, RunConfig, run_suite
from benchmarks.split import (
    DEV,
    LOG_HEADING,
    TEST,
    VAL,
    SealedAccessError,
    digest,
    load_split,
    open_test_split,
    open_validation_split,
    seen_cases,
    supersede_to_v2,
    supersede_to_v3,
    supersede_to_v4,
    supersede_to_v5,
    supersede_to_v6,
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
EXPOSED_CASE = "drop_duplicates/realistic_nulls_dup30"  # former exposed-v1: dev since v3
TEST_CASE = "v2/drop_duplicates/clustered_nulls_varstr_dup60"
VAL_CASE = "v5/drop_duplicates/null_heavy_full"


# -- the frozen split ----------------------------------------------------------------------------
def test_split_loads_and_covers_every_case_exactly_once():
    sp = load_split()
    names = {c.name for c in CASES}
    assert sp.dev | sp.test | sp.val == names
    assert not (sp.dev & sp.test) and not (sp.dev & sp.val) and not (sp.test & sp.val)
    assert (len(sp.dev), len(sp.test), len(sp.val)) == (123, 17, 47)
    assert all(n.startswith("v2/") for n in sp.test) and all(n.startswith("v5/") for n in sp.val)
    assert len(sp.exposed) == 18 and sp.exposed <= sp.dev  # exposed-v1 is dev, kept as provenance
    assert len(sp.val3) == 36 and len(sp.val4) == 40 and (sp.val3 | sp.val4) <= sp.dev
    assert sp.of(EXPOSED_CASE) == DEV


def test_every_operation_has_dev_and_test_v2_configurations():
    sp = load_split()
    for op in {c.op for c in CASES}:
        for group in (sp.dev, sp.test):
            assert any(c.op == op and c.name in group for c in CASES), (op, sorted(group)[:1])


def test_val_v5_covers_the_failing_families_and_the_ones_that_worked():
    names = sorted(load_split().val)
    for needle in (
        "merge/inner_small_out", "merge/left_small_out", "merge/outer_zipf", "merge/right_text", "merge/inner_large_out",
        "drop_duplicates/null_heavy_full", "drop_duplicates/null_subset_floats", "drop_duplicates/null_subset_texts",
        "drop_duplicates/null_subset_cat_date", "astype/str_to_category_card9000", "astype/str_to_category_card200000",
        "astype/int_to_category", "astype/float_to_str_nulls", "astype/datetime_to_str_nulls", "groupby/str_card9_",
        "groupby/two_keys_card70", "groupby/two_keys_card17000", "groupby/zipf_int", "concat/two_category_heavy4",
        "read_csv/wide_floats16", "matmul/float32_tall_thin_big", "np_sort/sorted_int64", "sort_values/datetime_nulls",
    ):  # fmt: skip
        assert any(needle in n for n in names), needle
    assert len(names) >= 40


def test_val_v5_reaches_the_multi_gib_regime_and_fits_a_32gb_machine_plan():
    big = list(build_grid("full", splits=(VAL,), max_size=400_000_000))
    assert max(p.size for p in big if p.op != "operator.matmul") >= 30_000_000
    assert max(p.size for p in big if p.op == "operator.matmul") >= 16_000
    assert max(p.est_input_bytes() for p in big) > 2 * 2**30  # multi-GiB inputs
    cap = 24 * 2**30
    runnable = [p for p in big if p.est_footprint_bytes() <= cap]
    assert len(runnable) >= 0.6 * len(
        big
    )  # most of it runs under the 24 GiB cap of a 32 GB machine


def test_history_records_the_exposure_and_the_reclassifications():
    meta = load_split().meta
    assert meta["version"] == 6 and len(meta["history"]) == 6
    old = meta["history"][0]["sha256"]["test"]
    assert old == digest(load_split().exposed)  # exposed-v1 is exactly the old sealed list
    assert "exposure" in meta["history"][1]["event"] or "exposed" in meta["history"][1]["event"]
    assert "reclassify exposed-v1 as dev" in meta["history"][2]["event"]
    assert "reclassify val-v3 as dev" in meta["history"][3]["event"]
    assert "reclassify val-v4 as dev" in meta["history"][4]["event"]
    assert "freeze val-v5" in meta["history"][5]["event"]
    assert meta["provenance"]["exposed-v1"]["sha256"] == digest(load_split().exposed)
    sp = load_split()
    assert meta["provenance"]["val-v3"]["sha256"] == digest(sp.val3)
    assert len(sp.val3) == 36 and sp.val3 <= sp.dev and not (sp.val3 & sp.val)  # val-v3 is dev now
    assert all(n.startswith("v3/") for n in sp.val3)
    assert (
        meta["provenance"]["val-v4"]["sha256"] == digest(sp.val4)
        and sp.val
        and not (sp.val & sp.dev)
    )


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


def _blank_size(spec):
    """Compare configurations independent of the row count used to build them."""
    if isinstance(spec, (FrameInput, CsvInput)):
        return {"cfg": spec.cfg.with_(n_rows=1)}
    if isinstance(spec, JoinInput):
        return {"left": spec.left.with_(n_rows=1), "right_rows": 1}
    return {"shape": (1,)}


def _configs(group):
    """(reprs, seeds) of every input specification of the cases in ``group``."""
    reprs, seeds = set(), set()
    for c in CASES:
        if c.name in group:
            for spec in _specs(c):
                reprs.add(repr(dataclasses.replace(spec, **_blank_size(spec))))
                seeds |= _seeds(spec)
    return reprs, seeds


def _knob_values(group):
    """Non-default values of the numeric generator knobs and join/array parameters in ``group``."""
    default = DatasetConfig(n_rows=1)
    knobs = ("cardinality", "dup_rate", "null_rate", "str_len", "zipf_exponent")
    values: set[tuple[str, object]] = set()
    for c in CASES:
        if c.name not in group:
            continue
        for spec in _specs(c):
            cfg = getattr(spec, "cfg", None) or getattr(spec, "left", None)
            if cfg is not None:
                values |= {
                    (k, getattr(cfg, k)) for k in knobs if getattr(cfg, k) != getattr(default, k)
                }
            if isinstance(spec, JoinInput):
                values |= {("overlap", spec.overlap), ("fanout", spec.fanout)}
                values.add(("right_ratio", round(spec.right_rows / 1000, 3)))
            if isinstance(spec, ArrayInput):
                values.add(
                    (
                        "array",
                        (
                            spec.pattern,
                            spec.dtype,
                            len(spec.shape),
                            round(spec.shape[0] / max(spec.shape[-1], 1), 3),
                        ),
                    )
                )
    return values


@pytest.mark.parametrize("fresh", ["test", "val"])
def test_fresh_splits_differ_from_every_other_configuration(fresh):
    sp = load_split()
    mine = getattr(sp, fresh)
    others = {"test": sp.dev, "val": sp.dev | sp.test}[fresh]
    r_mine, s_mine = _configs(mine)
    r_other, s_other = _configs(others)
    assert not (r_mine & r_other)
    assert not (s_mine & s_other), s_mine & s_other


def test_val_v5_shares_no_generator_parameter_value_or_seed_with_any_dev_split_or_test_v2():
    sp = load_split()
    others = sp.dev | sp.test
    shared = _knob_values(sp.val) & _knob_values(others)
    assert not shared, sorted(map(str, shared))
    r_val, s_val = _configs(sp.val)
    r_other, s_other = _configs(others)
    assert not (s_val & s_other) and not (r_val & r_other)
    assert min(s_val - {0, 1}) >= 501  # outside every dev (<= 450, 1103+ for test-v2) seed


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
    for c in CASES:  # and none of those knobs appears in dev (the val-v3 cases are dev now)
        if c.name not in load_split().dev or c.name in (load_split().val3 | load_split().val4):
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
        for p in build_grid(suite, splits=(DEV, TEST, VAL)):
            by_case.setdefault(p.case, set()).add(p.split)
        assert all(len(v) == 1 for v in by_case.values())


def test_grid_default_excludes_protected_groups_and_orders_groups():
    assert {p.split for p in build_grid("small")} == {DEV}
    everything = [p.split for p in build_grid("small", splits=(DEV, TEST, VAL))]
    order = {DEV: 0, TEST: 1, VAL: 2}
    assert everything == sorted(everything, key=order.get)
    assert set(everything) == {DEV, TEST, VAL}
    assert {p.split for p in build_grid("small", splits=(TEST,))} == {TEST}
    assert {p.split for p in build_grid("small", splits=(VAL,))} == {VAL}


@pytest.mark.parametrize("group", ["test", "val"])
def test_every_protected_case_runs_and_gets_an_estimate_at_tiny_size(tmp_path, group):
    """Generators, sources and Tier 0 availability (tiny sizes; no values asserted)."""
    import numpy as np
    import pandas as pd

    from nexus.pipeline import Pipeline

    names = getattr(load_split(), group)
    pipeline = Pipeline(tier=0)
    for c in CASES:
        if c.name not in names:
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
    assert (sp.dev, sp.exposed, sp.test, sp.val) == ({"a/1", "b/1"}, {"b/1"}, {"c/1"}, set())
    with pytest.raises(ValueError, match="not a version-2"):
        supersede_to_v3(["x/1"], "again", path=split_mod.SPLIT_PATH)  # already version 3
    with pytest.raises(ValueError, match="reuses existing"):
        supersede_to_v3(["a/1"], "bad", path=path)
    supersede_to_v3(["d/1"], "reclassify", path=path)
    sp = load_split(path)
    assert (sp.dev, sp.exposed, sp.test, sp.val) == (
        {"a/1", "b/1"},
        {"b/1"},
        {"c/1"},
        {"d/1"},
    )
    assert sp.meta["version"] == 3 and len(sp.meta["history"]) == 3


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
    (a_dev, p_dev), (a_exp, p_exp), (a_test, p_test), (a_val, p_val) = (
        _point(DEV_CASE, 1),
        _point(EXPOSED_CASE, 1),
        _point(TEST_CASE, 1),
        _point(VAL_CASE, 1),
    )
    _write(out / "actuals.csv", ACTUAL_FIELDS, [a_dev, a_exp])
    _write(out / "predictions.csv", PREDICTION_FIELDS, [p_dev, p_exp])
    _write(out / "sealed" / "actuals.csv", ACTUAL_FIELDS, [a_test])
    _write(out / "sealed" / "predictions.csv", PREDICTION_FIELDS, [p_test])
    _write(out / "validation" / "actuals.csv", ACTUAL_FIELDS, [a_val])
    _write(out / "validation" / "predictions.csv", PREDICTION_FIELDS, [p_val])
    (out / "meta.json").write_text(json.dumps({"suite": "t", "cap_bytes": 10**10}))
    return out


def test_development_loading_returns_dev_only_with_exposed_origin_kept(results):
    df = load_joined(results)
    assert set(df["case"]) == {DEV_CASE, EXPOSED_CASE}
    assert dict(zip(df["case"], df["split"], strict=True)) == {DEV_CASE: DEV, EXPOSED_CASE: DEV}
    assert dict(zip(df["case"], df["origin"], strict=True)) == {
        DEV_CASE: DEV,
        EXPOSED_CASE: "exposed-v1",
    }


@pytest.mark.parametrize("case", [TEST_CASE, VAL_CASE])
def test_development_files_containing_a_protected_case_are_refused(tmp_path, case):
    out = tmp_path / "leaky"
    a, p = _point(case, 1)
    _write(out / "actuals.csv", ACTUAL_FIELDS, [a])
    _write(out / "predictions.csv", PREDICTION_FIELDS, [p])
    with pytest.raises(SealedAccessError):
        load_joined(out)


def test_protected_loading_needs_a_logged_token_of_the_right_group(results, tmp_path):
    for bad in (None, "token", object()):
        with pytest.raises(SealedAccessError):
            load_sealed(results, None, bad)
        with pytest.raises(SealedAccessError):
            load_validation(results, None, bad)
    progress = tmp_path / "P.md"
    val_token = open_validation_split(
        "why", results_dir=results, command="c", n_points=1, progress_path=progress
    )
    test_token = open_test_split(
        "why", results_dir=results, command="c", n_points=1, progress_path=progress
    )
    with pytest.raises(SealedAccessError):  # a val token does not open test-v2, and vice versa
        load_sealed(results, None, val_token)
    with pytest.raises(SealedAccessError):
        load_validation(results, None, test_token)
    assert set(load_validation(results, None, val_token)["case"]) == {VAL_CASE}
    log = progress.read_text(encoding="utf-8")
    assert "| val-v5 |" in log and "| test-v2 |" in log


def test_normal_report_shows_dev_but_hides_test_v2_and_val_v5(results):
    text = write_report(results).read_text(encoding="utf-8")
    assert "## Dev split" in text and "Exposed-v1 split" not in text
    assert "Test-v2 split (sealed)" in text and "1 test-v2 points measured" in text
    assert "Val-v5 split (held-out validation)" in text and "1 val-v5 points measured" in text
    assert TEST_CASE not in text and VAL_CASE not in text
    assert DEV_CASE in text and EXPOSED_CASE in text
    for csv_file in results.glob("*.csv"):
        content = csv_file.read_text(encoding="utf-8")
        assert TEST_CASE not in content and VAL_CASE not in content, csv_file.name


def test_validation_report_requires_a_reason_and_logs_every_use(results, tmp_path):
    progress = tmp_path / "PROGRESS.md"
    progress.write_text(f"# Progress\n\n{LOG_HEADING}\n\n(none yet)\n", encoding="utf-8")
    with pytest.raises(SealedAccessError):
        write_validation_report(results, " ", progress_path=progress)
    report = write_validation_report(results, "first look", progress_path=progress, command="c1")
    text = report.read_text(encoding="utf-8")
    assert "## Val-v5 split" in text and VAL_CASE in text and TEST_CASE not in text
    assert "Risk engine on val-v5 (pre-registered R1-R3)" in text  # Phase 7c: the R1-R3 replay
    assert "LEGACY: Phase 4d controller criteria S1-S5" in text  # Phase 7d: S1-S5 labelled legacy
    assert "Phase 7 acceptance verdict" in text  # the authoritative Phase 7 section
    log = progress.read_text(encoding="utf-8")
    assert log.count("- 20") == 1 and "| val-v5 |" in log and "first look" in log


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
    assert "## Dev split" in text and "## Test-v2 split" in text
    assert TEST_CASE in text and VAL_CASE not in text
    log = progress.read_text(encoding="utf-8")
    assert log.count("- 20") == 2 and "first look" in log and "second look" in log
    assert "test-v2" in log and "1 test-v2 points" in log and "`cmd1`" in log
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
        _grid_point(EXPOSED_CASE, DEV, null_rate=0.05),
        _grid_point(TEST_CASE, TEST, null_rate=0.05, seed=101),
        _grid_point(VAL_CASE, VAL, null_rate=0.35, seed=501),
    ]
    with caplog.at_level(logging.INFO, logger="benchmarks"):
        run_suite(RunConfig(suite="small", out_dir=out, calibrate=False), points)
    dev_rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    sealed_rows = list(csv.DictReader((out / "sealed" / "actuals.csv").open(encoding="utf-8")))
    val_rows = list(csv.DictReader((out / "validation" / "actuals.csv").open(encoding="utf-8")))
    assert {r["case"]: r["split"] for r in dev_rows} == {DEV_CASE: DEV, EXPOSED_CASE: DEV}
    assert [r["case"] for r in sealed_rows] == [TEST_CASE] and sealed_rows[0]["split"] == TEST
    assert [r["case"] for r in val_rows] == [VAL_CASE] and val_rows[0]["split"] == VAL
    assert (out / "sealed" / "predictions.csv").exists()
    assert (out / "validation" / "predictions.csv").exists()
    progress = json.loads((out / "progress.json").read_text())
    assert progress["state"] == "finished" and progress["counts"]["measured"] == 4

    lines = [r.getMessage() for r in caplog.records]
    leak = re.compile(r"ram=|pred=|MB|\bt=|censored|tier\d|below_|\bs\b.*\bs\b")
    for protected in (TEST_CASE, VAL_CASE):
        protected_lines = [m for m in lines if protected in m]
        assert protected_lines, "the protected point should still be logged (id/status/elapsed)"
        for m in protected_lines:
            assert re.fullmatch(rf"\[\d+/\d+\] {re.escape(protected)}\|n=2000: ok \[\d+s\]", m), m
            assert not leak.search(m), m
    for case in (DEV_CASE, EXPOSED_CASE):  # positive control: dev still logs values
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
            [_grid_point(TEST_CASE, TEST, seed=101), _grid_point(VAL_CASE, VAL, seed=501)],
        )
    text = " ".join(r.getMessage() for r in caplog.records) + " ".join(
        str(r.exc_info) for r in caplog.records
    )
    assert "harness error (ValueError)" in text
    assert "secret" not in text and "123.4" not in text
    assert all(
        r.exc_info is None
        for r in caplog.records
        if TEST_CASE in r.getMessage() or VAL_CASE in r.getMessage()
    )


def test_status_command_shows_counts_only_for_the_sealed_group(results, capsys):
    import argparse

    from benchmarks.__main__ import cmd_status

    (results / "run.log").write_text(
        f"00:00:01 [3/3] {TEST_CASE}|n=2000: ok [4s]\n", encoding="utf-8"
    )
    cmd_status(argparse.Namespace(results=results))
    out = capsys.readouterr().out
    assert "test-v2 (count only)" in out and "val-v5 (count only)" in out
    assert out.count("{'ok': 1}") == 2 and "exposed" not in out
    assert "MB" not in out and "ram" not in out.lower().replace("results", "")


# -- source tree guard -------------------------------------------------------------------------------
def test_only_the_final_path_touches_sealed_files():
    """Dev tooling (calibration, comparison, diagnosis, state, models) must not use the sealed API."""
    allowed = {"split.py", "evaluate.py", "runner.py", "__main__.py", "maintenance.py"}
    pattern = re.compile(
        r"SEALED_DIR|SEALED_GROUPS|VAL_DIR|open_test_split|open_validation_split|open_sealed_group"
        r"|load_sealed|load_validation|require_token|SealedAccessToken"
    )
    offenders = []
    for path in [*ROOT.joinpath("src").rglob("*.py"), *ROOT.joinpath("benchmarks").rglob("*.py")]:
        if path.name not in allowed and pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_calibration_never_imports_benchmark_code():
    source = (ROOT / "src" / "nexus" / "calibrate.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+benchmarks", source, re.MULTILINE)


# -- validation report robustness (val-only run, memory-limit hits, summary guard) ---------------------
def _val_only_dir(tmp_path, status="ok"):
    out = tmp_path / "valonly"
    a, p = _point(VAL_CASE, 1)
    a = {**a, "status": status, "cap_bytes": 2 * 1024**3, "baseline_bytes": 100 * MB}
    if status != "ok":
        a["ram_delta_all"] = "[]"
        a["time_s_all"] = "[]"
    _write(out / "validation" / "actuals.csv", ACTUAL_FIELDS, [a])
    _write(out / "validation" / "predictions.csv", PREDICTION_FIELDS, [p])
    (out / "meta.json").write_text(json.dumps({"suite": "t", "cap_bytes": 10**10}))
    return out


def test_validation_report_works_without_dev_results_and_says_dev_was_omitted(tmp_path):
    out = _val_only_dir(tmp_path)
    progress = tmp_path / "P.md"
    progress.write_text(f"# P\n\n{LOG_HEADING}\n\n", encoding="utf-8")
    text = write_validation_report(out, "why", progress_path=progress).read_text(encoding="utf-8")
    assert "Omitted:" in text and "no development results" in text
    assert VAL_CASE in text and TEST_CASE not in text
    assert progress.read_text(encoding="utf-8").count("| val-v5 |") == 1


def test_a_failed_validation_attempt_leaves_no_access_log_entry(tmp_path):
    progress = tmp_path / "P.md"
    progress.write_text(f"# P\n\n{LOG_HEADING}\n\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        write_validation_report(tmp_path / "empty", "why", progress_path=progress)
    assert "| val-v5 |" not in progress.read_text(encoding="utf-8")


def test_a_memory_limit_hit_counts_as_a_lower_bound_of_the_incremental_peak():
    import pandas as pd

    from benchmarks.evaluate import Floors, accuracy_table, classify_points

    def row(size, status, baseline, error=""):
        return {"point_id": f"c|n={size}", "case": "c", "op": "o", "size": size, "status": status,
                "baseline_bytes": baseline, "error": error, "cap_bytes": 2 * 1024**3,
                "ram_delta_all": json.dumps([200 * MB, 201 * MB] if status == "ok" else []),
                "time_s_all": json.dumps([1.0, 1.01] if status == "ok" else [])}  # fmt: skip

    gib = 1024**3
    df = pd.DataFrame(
        [
            row(1_000_000, "ok", 300 * MB),
            row(3_000_000, "ok", 900 * MB),
            row(10_000_000, "memory_limit", 0, str(int(2.2 * gib))),
        ]
    )
    out = classify_points(df, Floors())
    kill = out.iloc[2]
    # baseline extrapolated through (1M, 300 MB) and (3M, 900 MB): 3000 MB at 10M ... above the RSS
    # at the kill, so no incremental peak can be inferred (not "the cap"): lower bound 0
    assert (
        kill["ram_class"] == "valid" and kill["ram_value"] == 0.0 and bool(kill["ram_lower_bound"])
    )
    df.loc[2, "error"] = str(int(4 * gib))  # RSS at kill 4096 MB -> bound = 4096 - 3000 MB
    kill = classify_points(df, Floors()).iloc[2]
    assert kill["ram_value"] == pytest.approx(4 * gib - 3000 * MB)  # NOT the cap (2 GiB)
    assert pd.isna(kill["time_value"]) and pd.isna(kill["time_class"])
    scored = classify_points(df, Floors()).assign(tier=0.0, has_estimate=True)
    acc = accuracy_table(
        scored.assign(
            ram_expected=3e8,
            ram_low=2e8,
            ram_high=1e9,
            time_expected=1.0,
            time_low=0.5,
            time_high=2.0,
        ),
        ["op"],
    )
    assert acc.iloc[0]["ram_n"] == 3 and acc.iloc[0]["ram_lower_bound"] == 1
    # an estimate whose `high` is below the proven lower bound is an under-prediction
    acc = accuracy_table(
        scored.assign(
            ram_expected=3e8,
            ram_low=2e8,
            ram_high=1e8,
            time_expected=1.0,
            time_low=0.5,
            time_high=2.0,
        ),
        ["op"],
    )
    assert acc.iloc[0]["ram_above_high"] > 0
    lone = pd.DataFrame([row(10_000_000, "memory_limit", 0, str(2 * gib))])  # no measured sibling
    assert pd.isna(classify_points(lone, Floors()).iloc[0]["ram_class"])


def test_run_summary_does_not_crash_when_no_run_produced_a_time():
    from benchmarks.runner import _summary
    from nexus.measure import Measurement

    text = _summary(Measurement(status="memory_limit", error="killed"))
    assert "ram=n/a" in text and "t=n/a" in text


def test_supersede_to_v4_merges_val_v3_into_dev_and_keeps_provenance(tmp_path):
    v1 = {"version": 1, "frozen": "2026-01-01", "dev": ["a/1"], "test": ["b/1"],
          "sha256": {"dev": digest(["a/1"]), "test": digest(["b/1"])}}  # fmt: skip
    path = tmp_path / "split.json"
    path.write_text(json.dumps(v1))
    with pytest.raises(ValueError, match="not a version-3"):
        supersede_to_v4(["e/1"], "too early", path=path)
    supersede_to_v2(["c/1"], "v2", path=path)
    supersede_to_v3(["d/1"], "v3", path=path)
    assert load_split(path).val == {"d/1"}  # a version-3 file calls it val-v3
    with pytest.raises(ValueError, match="reuses existing"):
        supersede_to_v4(["d/1"], "bad", path=path)
    supersede_to_v4(["e/1"], "reclassify val-v3 as dev", path=path)
    sp = load_split(path)
    assert (sp.dev, sp.test, sp.val, sp.val3) == ({"a/1", "b/1", "d/1"}, {"c/1"}, {"e/1"}, {"d/1"})
    assert sp.meta["version"] == 4 and len(sp.meta["history"]) == 4
    with pytest.raises(ValueError, match="not a version-3"):
        supersede_to_v4(["f/1"], "again", path=path)
    supersede_to_v5("reclassify val-v4 as dev", path=path)
    sp = load_split(path)
    assert (sp.dev, sp.val, sp.val4) == ({"a/1", "b/1", "d/1", "e/1"}, set(), {"e/1"})
    assert sp.meta["version"] == 5 and "val-v4" not in json.loads(path.read_text())["groups"]
    with pytest.raises(ValueError, match="not a version-4"):
        supersede_to_v5("again", path=path)
    with pytest.raises(ValueError, match="reuses existing"):
        supersede_to_v6(["a/1"], "bad", path=path)
    supersede_to_v6(["f/1"], "freeze val-v5", path=path)
    sp = load_split(path)
    assert (sp.val, sp.val4, "f/1" in sp.dev) == ({"f/1"}, {"e/1"}, False) and sp.meta[
        "version"
    ] == 6
    with pytest.raises(ValueError, match="not a version-5"):
        supersede_to_v6(["g/1"], "again", path=path)


def test_migrate_val3_copies_only_former_val_v3_rows_into_dev_files(tmp_path):
    from benchmarks.maintenance import migrate_val3

    val3_case = sorted(load_split().val3)[0]
    src, dest = tmp_path / "src", tmp_path / "dest"
    arows, prows = [], []
    for case in (val3_case, VAL_CASE):
        a, p = _point(case, 1_000_000)
        arows.append({**a, "split": "val-v3"})
        prows.append({**p, "split": "val-v3"})
    _write(src / "validation" / "actuals.csv", ACTUAL_FIELDS, arows)
    _write(src / "validation" / "predictions.csv", PREDICTION_FIELDS, prows)
    assert migrate_val3(src, dest) == {"actuals": 1, "predictions": 1}
    assert migrate_val3(src, dest) == {"actuals": 0, "predictions": 0}  # idempotent
    rows = list(csv.DictReader((dest / "actuals.csv").open(encoding="utf-8")))
    assert [r["case"] for r in rows] == [val3_case] and rows[0]["split"] == "dev"
    assert VAL_CASE not in (dest / "actuals.csv").read_text(encoding="utf-8")  # val-v4 stays out
