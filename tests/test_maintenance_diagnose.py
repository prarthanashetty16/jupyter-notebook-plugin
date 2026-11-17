"""Maintenance (migrate exposed rows, scrub logs), diagnosis tool and the read_csv engine check."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from benchmarks.diagnose import fold, write_findings
from benchmarks.maintenance import migrate_exposed, redact_line, scrub_logs
from benchmarks.runner import (
    ACTUAL_FIELDS,
    ENV_FIELDS,
    PREDICTION_FIELDS,
    env_info,
    read_csv_defaults,
)

MB = 2**20
DEV_CASE = "drop_duplicates/mixed_dup0"
EXPOSED_CASE = "drop_duplicates/realistic_nulls_dup30"
TEST_CASE = "v2/drop_duplicates/clustered_nulls_varstr_dup60"


def _write(path: Path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({f: r.get(f, "") for f in fields})


def _read(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# -- log redaction ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (f"23:41:24 [45/136] {EXPOSED_CASE}|n=3000000: ok ram=545.9 MB [censored:below_floor] t=3.182 s | tier0 pred=545.9 MB t=3.182 s  [63s elapsed]",
         f"23:41:24 [45/136] {EXPOSED_CASE}|n=3000000: ok [63s]"),
        (f"23:41:25 [46/136] {TEST_CASE}|n=1000000: actual kept (ok) | tier0 pred=58.6 MB t=0.076 s  [64s elapsed]",
         f"23:41:25 [46/136] {TEST_CASE}|n=1000000: actual kept (ok) [64s]"),
        (f"23:41:26 [47/136] {TEST_CASE}|n=3000000: skipped (estimated footprint above memory cap)",
         f"23:41:26 [47/136] {TEST_CASE}|n=3000000: skipped (estimated footprint above memory cap)"),
        (f"23:41:27 [48/136] {EXPOSED_CASE}|n=1000000: timeout ram=n/a [censored:below_setup_peak] t=0.000 s  [70s elapsed]",
         f"23:41:27 [48/136] {EXPOSED_CASE}|n=1000000: timeout [70s]"),
    ],
)  # fmt: skip
def test_redact_line_keeps_only_id_status_elapsed(line, expected):
    assert redact_line(line) == expected


def test_scrub_logs_redacts_exposed_and_sealed_lines_only_and_is_idempotent(tmp_path):
    log = tmp_path / "run.log"
    nested = tmp_path / "sealed" / "old.log"
    nested.parent.mkdir()
    dev = f"00:00:01 [1/4] {DEV_CASE}|n=1000000: ok ram=12.0 MB t=0.5 s | tier0 pred=11.0 MB t=0.4 s  [5s elapsed]"
    exp = f"00:00:02 [2/4] {EXPOSED_CASE}|n=1000000: ok ram=99.5 MB [censored:below_floor] t=1.5 s | tier0 pred=88.8 MB t=1.4 s  [9s elapsed]"
    tst = f"00:00:03 [3/4] {TEST_CASE}|n=1000000: ok ram=77.7 MB t=2.5 s | tier0 pred=66.6 MB t=2.4 s  [14s elapsed]"
    other = "00:00:04 suite=full points=136 (runnable 124 under the 2560 MB cap) -> out"
    log.write_text("\n".join([dev, exp, tst, other]) + "\n", encoding="utf-8")
    nested.write_text(tst + "\n", encoding="utf-8")
    assert scrub_logs(tmp_path) == 3
    text = log.read_text(encoding="utf-8") + nested.read_text(encoding="utf-8")
    for secret in ("99.5", "88.8", "77.7", "66.6", "censored"):
        assert secret not in text
    assert dev in text and other in text  # dev and unrelated lines untouched
    assert scrub_logs(tmp_path) == 0


# -- migrating exposed rows ----------------------------------------------------------------------------
def test_migrate_exposed_moves_only_exposed_rows(tmp_path):
    base = {"suite": "full", "status": "ok", "op": "drop_duplicates", "size": 1, "split": "test"}
    dev_row = {**base, "point_id": f"{DEV_CASE}|n=1", "case": DEV_CASE, "split": "dev"}
    exp_row = {**base, "point_id": f"{EXPOSED_CASE}|n=1", "case": EXPOSED_CASE}
    tst_row = {**base, "point_id": f"{TEST_CASE}|n=1", "case": TEST_CASE, "split": "test-v2"}
    _write(tmp_path / "actuals.csv", ACTUAL_FIELDS, [dev_row])
    _write(tmp_path / "sealed" / "actuals.csv", ACTUAL_FIELDS, [exp_row, tst_row])
    pred = {"tier": 0, "status": "ok", "has_estimate": True}
    _write(
        tmp_path / "sealed" / "predictions.csv",
        PREDICTION_FIELDS,
        [{**pred, "point_id": exp_row["point_id"]}],
    )

    moved = migrate_exposed(tmp_path)
    assert moved["actuals"] == 1 and moved["predictions"] == 1 and moved["left_sealed"] == 1
    main = {r["case"]: r["split"] for r in _read(tmp_path / "actuals.csv")}
    assert main == {DEV_CASE: "dev", EXPOSED_CASE: "exposed-v1"}
    assert [r["case"] for r in _read(tmp_path / "sealed" / "actuals.csv")] == [TEST_CASE]
    assert not (tmp_path / "sealed" / "predictions.csv").exists()
    assert len(_read(tmp_path / "predictions.csv")) == 1
    assert migrate_exposed(tmp_path)["actuals"] == 0  # idempotent


# -- diagnosis -------------------------------------------------------------------------------------------
def test_fold_signs():
    f = fold(pd.Series([3.0, 1.0, 5.0]), pd.Series([1.0, 4.0, 5.0]))
    assert list(f) == [3.0, -4.0, 1.0]


def _synthetic(tmp_path):
    """Three operations with known structure, built from real dev case names."""
    sizes = [1_000_000, 3_000_000, 10_000_000]
    actual_rows, pred_rows = [], []

    def add(case, op, n, ram_actual, ram_pred, time_actual, time_pred, split="dev"):
        pid = f"{case}|n={n}"
        actual_rows.append({"point_id": pid, "suite": "full", "case": case, "op": op, "size": n,
                            "status": "ok", "source": "x", "split": split,
                            "ram_delta_all": json.dumps([ram_actual] * 3),
                            "poll_delta_all": json.dumps([ram_actual] * 3),
                            "time_s_all": json.dumps([time_actual] * 3), "input_bytes": 10 * MB,
                            "cap_bytes": 10**10})  # fmt: skip
        pred_rows.append({"point_id": pid, "tier": 0, "status": "ok", "has_estimate": True, "model": "m",
                          "ram_low": ram_pred / 2, "ram_expected": ram_pred, "ram_high": ram_pred * 2,
                          "time_low": time_pred / 2, "time_expected": time_pred, "time_high": time_pred * 2,
                          "overhead_cold_s": 0.01, "overhead_warm_s": 0.005,
                          "inspected_bytes": 10 * MB})  # fmt: skip

    for case in (
        "drop_duplicates/mixed_dup0",
        "drop_duplicates/mixed_dup50",
        "drop_duplicates/numeric_dup50",
    ):
        for n in sizes:  # structural constant factor: RAM x3 over everywhere; time actual ~ n^1.5
            ram = 100 * MB * n / 1e6
            add(case, "drop_duplicates", n, ram, 3 * ram, 0.5 * (n / 1e6) ** 1.5, 0.5 * (n / 1e6))
    for case, factor in (
        ("merge/inner_1to1", 0.3),
        ("merge/inner_overlap10", 1.0),
        ("merge/inner_fanout3", 4.0),
    ):
        for n in sizes:  # data-dependent: the fold depends on the scenario, not on size
            ram = 100 * MB * n / 1e6
            add(case, "merge", n, ram, factor * ram, 0.5 * (n / 1e6), 0.5 * (n / 1e6))
    for case in ("sort_values/by_int", "sort_values/by_str", "sort_values/by_int_float"):
        for n in sizes:  # structural scaling: the fold grows with n (predicted exponent too high)
            ram = 100 * MB * n / 1e6
            add(
                case,
                "sort_values",
                n,
                ram,
                ram * (n / 1e6) ** 0.4,
                0.5 * (n / 1e6),
                0.5 * (n / 1e6),
            )
    # an exposed-v1 case, and a sealed test-v2 case that must never appear
    for n in sizes:
        ram = 100 * MB * n / 1e6
        add(
            EXPOSED_CASE,
            "drop_duplicates",
            n,
            ram,
            3 * ram,
            0.5 * (n / 1e6) ** 1.5,
            0.5 * (n / 1e6),
            "exposed-v1",
        )
    out = tmp_path / "res"
    _write(out / "actuals.csv", ACTUAL_FIELDS, actual_rows)
    _write(out / "predictions.csv", PREDICTION_FIELDS, pred_rows)
    sealed_a, sealed_p = [], []
    for a, p in zip(actual_rows[:3], pred_rows[:3], strict=True):
        pid = a["point_id"].replace(DEV_CASE, TEST_CASE)
        sealed_a.append({**a, "point_id": pid, "case": TEST_CASE, "split": "test-v2",
                         "ram_delta_all": json.dumps([777 * MB] * 3)})  # fmt: skip
        sealed_p.append({**p, "point_id": pid, "ram_expected": 1.0})
    _write(out / "sealed" / "actuals.csv", ACTUAL_FIELDS, sealed_a)
    _write(out / "sealed" / "predictions.csv", PREDICTION_FIELDS, sealed_p)
    return out


def test_diagnose_recovers_slopes_and_classifies_structure(tmp_path):
    results = _synthetic(tmp_path)
    out = tmp_path / "diag"
    path = write_findings(results, out)
    text = path.read_text(encoding="utf-8")
    struct = pd.read_csv(out / "error_structure.csv").set_index(["op", "metric"])
    assert (
        struct.loc[("drop_duplicates", "RAM"), "classification"] == "structural (constant factor)"
    )
    assert struct.loc[("drop_duplicates", "RAM"), "bias_fold"] == pytest.approx(3.0, rel=0.01)
    assert struct.loc[("merge", "RAM"), "classification"] == "data-dependent"
    assert struct.loc[("sort_values", "RAM"), "classification"] == "structural (scaling exponent)"
    assert struct.loc[("sort_values", "RAM"), "trend_per_decade"] == pytest.approx(0.4, abs=0.02)
    assert struct.loc[("merge", "TIME"), "classification"] == "no dominant error"

    slopes = pd.read_csv(out / "scaling_slopes.csv")
    dd = slopes[slopes["op"] == "drop_duplicates"]
    assert dd["time_slope_actual"].median() == pytest.approx(1.5, abs=0.02)
    assert dd["time_slope_pred"].median() == pytest.approx(1.0, abs=0.02)
    assert dd["ram_slope_actual"].median() == pytest.approx(1.0, abs=0.02)
    op_slopes = text.split("## 2.")[1]
    assert "True" in op_slopes  # drop_duplicates flagged superlinear

    pts = pd.read_csv(out / "points_ratio.csv")
    assert set(pts["split"]) == {"dev", "exposed-v1"}
    assert (pts["ram_fold"].dropna() < 0).sum() == len(pts[pts["scenario"] == "merge/inner_1to1"])
    assert "UNDER" in text and "exposed-v1" in text


def test_diagnose_never_reads_the_sealed_split(tmp_path):
    out = tmp_path / "diag"
    write_findings(_synthetic(tmp_path), out)
    for file in out.iterdir():
        content = file.read_text(encoding="utf-8")
        assert TEST_CASE not in content and "test-v2 (sealed)" not in content, file.name
    assert len(pd.read_csv(out / "points_ratio.csv")) == 30  # 27 dev + 3 exposed; no sealed rows


# -- read_csv engine assumption --------------------------------------------------------------------------
def test_benchmark_assumes_the_default_c_parser_and_records_it():
    engine, text_dtype = read_csv_defaults()
    assert engine == "CParserWrapper", (
        "pandas changed its default read_csv engine: revisit the benchmark"
    )
    info = env_info()
    assert {"read_csv_engine", "read_csv_text_dtype"} <= set(ENV_FIELDS)
    assert info["read_csv_engine"] == engine and info["read_csv_text_dtype"] == text_dtype


def test_read_csv_sources_in_the_suite_use_the_default_engine():
    from benchmarks.suite import CASES

    for case in CASES:
        if case.op == "pandas.read_csv":
            assert "engine" not in case.source, case.name


def test_upgrade_header_realigns_mixed_width_rows(tmp_path):
    """Rows written under an old header and rows in the new layout must both survive."""
    import csv

    from benchmarks.runner import upgrade_header

    path = tmp_path / "t.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    with path.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["3", "x", "4", "y"])
    assert upgrade_header(path, ["a", "x1", "b", "y1"]) is True
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    assert rows[0] == {"a": "1", "x1": "", "b": "2", "y1": ""}
    assert rows[1] == {"a": "3", "x1": "x", "b": "4", "y1": "y"}
    assert upgrade_header(path, ["a", "x1", "b", "y1"]) is False
