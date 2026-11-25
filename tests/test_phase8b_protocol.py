import json

import pandas as pd
import pytest

from benchmarks.realworld.evaluate_real import (
    V3_MODEL_VERSION,
    V4_MODEL_VERSION,
    load_paired,
    load_versioned,
    main,
    paired_coverage,
)
from benchmarks.realworld.run_notebook import _assert_output_model_version
from tools.static_ops import classify


def test_static_metric_counts_only_operation_name_matches():
    class Operation:
        name = "fillna"
        args = ["an unsupported receiver form"]

    class Registry:
        def find(self, op):
            return [object()] if op.name == "fillna" else []

    assert classify(Operation(), Registry()) == "covered"


def _row(index, *, covered, ops=None, deadline=False, version=None):
    row = {
        "notebook": "sample",
        "index": index,
        "hash": f"cell-{index}",
        "ops": ["sort_values"] if ops is None else ops,
        "uncovered": 0 if covered else 1,
        "covered": covered,
        "hard_deadline_fired": deadline,
    }
    if version is not None:
        row["model_version"] = version
    return row


def _write_run(root, notebook, version, rows, *, legacy_v3=False):
    run_dir = root / notebook
    run_dir.mkdir(parents=True)
    frozen = {"frozen_tag": version}
    summary = {"notebook": notebook, "frozen": frozen}
    if not legacy_v3:
        summary["model_version"] = version
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_dir / "cells.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_output_folder_refuses_a_different_model_version(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "cells.jsonl").write_text(
        json.dumps({"model_version": V3_MODEL_VERSION}) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="use a fresh output folder"):
        _assert_output_model_version(out, V4_MODEL_VERSION)


def test_v3_legacy_rows_get_the_tag_from_the_frozen_summary(tmp_path):
    root = tmp_path / "v3"
    _write_run(root, "sample", V3_MODEL_VERSION, [_row(0, covered=True)], legacy_v3=True)

    rows, notebooks = load_versioned(root, V3_MODEL_VERSION)

    assert notebooks == frozenset({"sample"})
    assert rows.loc[0, "model_version"] == V3_MODEL_VERSION


def test_loader_refuses_mixed_versions_in_one_result_root(tmp_path):
    root = tmp_path / "v4"
    row = _row(0, covered=True, version=V3_MODEL_VERSION)
    _write_run(root, "sample", V4_MODEL_VERSION, [row])

    with pytest.raises(ValueError, match="records model_version"):
        load_versioned(root, V4_MODEL_VERSION)


def test_paired_coverage_counts_deadlines_and_unpaired_cells_correctly():
    v3_rows = [_row(i, covered=i < 15) for i in range(30)]
    v4_rows = [
        _row(i, covered=i < 19, deadline=i == 18, version=V4_MODEL_VERSION) for i in range(30)
    ]
    v4_rows[18]["covered"] = True
    v3_rows[29]["ops"] = []
    v3_rows.append(_row(30, covered=True))
    v4_rows.append(
        {
            **_row(31, covered=True, version=V4_MODEL_VERSION),
            "notebook": "sample",
        }
    )

    result = paired_coverage(pd.DataFrame(v3_rows), pd.DataFrame(v4_rows))

    assert result["n"] == 30
    assert result["v3_covered"] == 15
    assert result["v4_covered"] == 18
    assert result["delta"] == pytest.approx(0.10)
    assert result["verdict"] == "MET"
    assert result["v3_only_cells"] == 1
    assert result["v3_only_operation_cells"] == 1
    assert result["v4_only_cells"] == 1
    assert result["v4_only_operation_cells"] == 1


def test_paired_loader_requires_the_same_notebook_set(tmp_path):
    v3_root, v4_root = tmp_path / "v3", tmp_path / "v4"
    _write_run(v3_root, "old-name", V3_MODEL_VERSION, [], legacy_v3=True)
    _write_run(v4_root, "new-name", V4_MODEL_VERSION, [])

    with pytest.raises(ValueError, match="same notebooks"):
        load_paired(v3_root, v4_root)


def test_evaluator_reports_paired_results_and_the_global_inconclusive_gate(tmp_path):
    v3_root, v4_root = tmp_path / "v3", tmp_path / "v4"
    v3_rows = [_row(i, covered=i < 15) | {"status": "ok"} for i in range(30)]
    v4_rows = [
        _row(i, covered=i < 19, deadline=i == 18, version=V4_MODEL_VERSION) | {"status": "ok"}
        for i in range(30)
    ]
    v4_rows[18]["covered"] = True
    _write_run(v3_root, "sample", V3_MODEL_VERSION, v3_rows, legacy_v3=True)
    _write_run(v4_root, "sample", V4_MODEL_VERSION, v4_rows)
    output = tmp_path / "report.md"

    main([str(v3_root), str(v4_root), "--out", str(output)])

    report_text = output.read_text(encoding="utf-8")
    assert "Paired operation-bearing cells: 30" in report_text
    assert "10.0 percentage points" in report_text
    assert "INCONCLUSIVE (30 v4 eligible cells < 150)" in report_text
