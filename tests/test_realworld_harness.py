"""Phase 8a harness validation on SYNTHETIC notebooks with known behaviour (no real notebook involved).

Each test runs a generated notebook in a fresh spawned kernel and checks what the harness recorded:
known allocations within 10%, censoring, failing / skipped cells, the watchdog, the per-cell timeout,
the consecutive-failure stop, NEXUS records, no cell code in the logs, and the two refusals (freeze
guard, battery power).
"""

from __future__ import annotations

import json
import sys

import pytest

from benchmarks.realworld import run_notebook as rn
from benchmarks.realworld import synthetic

MIB = 2**20
pytestmark = pytest.mark.skipif(
    sys.platform == "darwin", reason="peak counter of a child: Windows/Linux"
)


@pytest.fixture(scope="module")
def books(tmp_path_factory):
    return synthetic.write(tmp_path_factory.mktemp("syn"), rows=300_000)


def _run(books, name, tmp_path, **limits):
    s = rn.run(books[name], tmp_path / name, rn.Limits(**limits), allow_battery=True, dev=True)
    rows = [json.loads(line) for line in (tmp_path / name / "cells.jsonl").open(encoding="utf-8")]
    return s, {r["index"]: r for r in rows}, (tmp_path / name / "cells.jsonl").read_text("utf-8")


def test_known_allocations_and_censoring(books, tmp_path):
    s, rows, _ = _run(books, "syn_alloc", tmp_path)
    assert s.outcome == "completed" and s.failed == 0
    a = rows[1]
    assert a["ram_class"] == "valid"
    assert a["ram_value"] == pytest.approx(synthetic.KNOWN_ALLOC_MIB * MIB, rel=0.10)
    assert rows[2]["ram_class"] == "censored"
    # freed first, then a smaller allocation: the historical peak is not raised (or by a few pages only)
    assert rows[2]["ram_reason"] in ("below the previous historical peak", "below the floor")
    assert rows[2]["ram_value"] is None and rows[2]["ram_poll"] < 150 * MIB
    c = rows[3]
    assert c["ram_class"] == "valid"
    assert c["ram_value"] == pytest.approx(2 * synthetic.KNOWN_ALLOC_MIB * MIB, rel=0.10)
    assert (
        c["ram_poll"] <= c["ram_value"] * 1.05
    )  # the sampler cross-check never exceeds the OS peak


def test_failing_cell_records_the_type_only_and_shell_cells_never_run(books, tmp_path):
    s, rows, text = _run(books, "syn_fail", tmp_path)
    assert rows[1]["status"] == "error" and rows[1]["error_type"] == "ValueError"
    assert rows[2]["status"] == "skipped"
    assert rows[3]["status"] == "ok"
    assert s.outcome == "completed" and s.failed == 1 and s.skipped == 1
    assert "a failing cell" not in text and "echo" not in text  # no message, no code


def test_watchdog_kills_and_scores_a_lower_bound(books, tmp_path):
    s, rows, _ = _run(books, "syn_watchdog", tmp_path, cap_bytes=700 * MIB)
    r = rows[1]
    assert r["status"] == "watchdog" and r["ram_lower_bound"] is True and r["ram_class"] == "valid"
    assert r["ram_value"] > 0 and r["rss_start"] + r["ram_value"] >= 700 * MIB * 0.95
    assert s.outcome == "stopped" and 2 not in rows


def test_cell_timeout_stops_the_notebook(books, tmp_path):
    s, rows, _ = _run(books, "syn_timeout", tmp_path, cell_timeout_s=3.0)
    assert rows[1]["status"] == "timeout" and rows[1]["time_value"] is None
    assert s.outcome == "stopped" and 2 not in rows


def test_consecutive_failures_stop(books, tmp_path):
    s, rows, _ = _run(books, "syn_consecutive", tmp_path, max_consecutive_failures=5)
    assert s.failed == 5 and s.outcome == "stopped" and "consecutive" in s.stop_reason
    assert max(rows) == 5  # cells 1..5 failed, nothing after


def test_nexus_records_on_known_operations(books, tmp_path, monkeypatch):
    import nexus.power

    # the non-dev path (frozen tag recorded) refuses --allow-battery: run it as on mains power
    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    s = rn.run(books["syn_ops"], tmp_path / "syn_ops", rn.Limits())
    rows = {
        json.loads(x)["index"]: json.loads(x)
        for x in (tmp_path / "syn_ops" / "cells.jsonl").open(encoding="utf-8")
    }
    text = (tmp_path / "syn_ops" / "cells.jsonl").read_text("utf-8")
    assert s.outcome == "completed"
    by_op = {tuple(r.get("ops") or []): r for r in rows.values()}
    for op in ("groupby", "merge", "astype", "sort_values", "drop_duplicates", "pandas.read_csv"):
        r = next(v for k, v in by_op.items() if op in k)
        assert r["cell"] is not None and r["cell"]["ram_expected"] > 0, op
        assert r["risk"]["class"] in ("OK", "WARN", "HIGH_RISK", "UNKNOWN")
        assert r["cell_tier0"] is not None
    assert "groupby('k')" not in text and "rng.integers" not in text  # no cell code in the log
    assert s.frozen["frozen_tag"] and s.power


def test_refuses_on_battery(books, tmp_path, monkeypatch):
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "battery")
    with pytest.raises(SystemExit, match="battery"):
        rn.run(books["syn_fail"], tmp_path / "batt", rn.Limits())
    assert not (tmp_path / "batt" / "cells.jsonl").exists()


def test_aborts_when_a_frozen_file_differs(books, tmp_path, monkeypatch):
    import benchmarks.frozen as frozen

    if frozen.frozen_state()["tag_commit"] is None:
        pytest.skip(
            f"freeze-guard test skipped: {frozen.FROZEN_TAG} is not in this checkout (CI: actions/checkout "
            "with fetch-depth: 0 and fetch-tags: true)"
        )
    real = frozen.tag_hashes()
    changed = {**real, "src/nexus/models/merge.py": "0" * 64}  # as if merge.py had been modified
    monkeypatch.setattr(frozen, "tag_hashes", lambda tag=frozen.FROZEN_TAG: changed)
    monkeypatch.setattr(
        frozen,
        "require_frozen",
        lambda tag=frozen.FROZEN_TAG: frozen.check_state(frozen.frozen_state(tag)),
    )
    with pytest.raises(frozen.NotFrozenError, match="merge.py"):
        rn.run(books["syn_fail"], tmp_path / "guard", rn.Limits(), allow_battery=True)
    assert not (tmp_path / "guard" / "cells.jsonl").exists()
