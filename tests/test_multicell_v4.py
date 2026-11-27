"""Metadata and reporting checks for the sealed Phase 8c multicell group."""

from __future__ import annotations

import json

from benchmarks.multicell import cases_v4, split
from benchmarks.multicell.run import MIB, report


def test_v4_split_has_preregistered_size_and_partial_templates(tmp_path):
    path = tmp_path / "split_v4.json"
    frozen = split.create(path, version=4)
    heldout = set(frozen.heldout)

    assert len(cases_v4.TEMPLATES) == 16
    assert len(frozen.heldout) == 32
    assert len(cases_v4.all_cells(heldout)) == 64
    assert all(
        sum(key.startswith(f"{template}/") for key in heldout) == 2
        for template in cases_v4.TEMPLATES
    )
    deferred_forms = (
        ".corr(",
        ".to_csv(",
        ".join(",
        ".value_counts(",
        ".apply(lambda",
        ".map(lambda",
        "get_dummies(",
    )
    partial_templates = {
        name
        for name, source in cases_v4.TEMPLATES.items()
        if any(form in source for form in deferred_forms)
    }
    assert len(partial_templates) >= 4
    paths = {name: f"C:\\cache\\{name}" for name in ("P1", "P2", "P3", "T1")}
    for cell in cases_v4.all_cells(heldout):
        compile(cases_v4.source(cell, paths), "cell", "exec")
    assert json.loads(path.read_text(encoding="utf-8"))["digest"] == frozen.digest


def test_v4_report_scores_partial_cells_without_an_upper_bound():
    full = {
        "id": "full@1",
        "config": "full",
        "template": "full",
        "ops": ["sort_values"],
        "estimates": [{"model": "sort_values"}],
        "actual": 10 * MIB,
        "new": {"ram_low": 5 * MIB, "ram_expected": 8 * MIB, "ram_high": 9 * MIB},
        "v1": {"ram_low": 5 * MIB, "ram_expected": 8 * MIB, "ram_high": 9 * MIB},
        "uncovered": 0,
        "classes": {},
        "mode": "statements",
    }
    partial = {
        **full,
        "id": "partial@1",
        "config": "partial",
        "template": "partial",
        "ops": ["sort_values", "value_counts"],
        "estimates": [{"model": "sort_values"}],
        "actual": 20 * MIB,
        "new": {"ram_low": 12 * MIB, "ram_expected": 16 * MIB, "ram_high": 30 * MIB},
        "uncovered": 1,
        "classes": {"8": "OK", "16": "UNKNOWN"},
    }

    text = report([full, partial], "v4 report", version=4)
    assert "1 fully covered, 1 partial, 0 wholly uncovered" in text
    assert "Partial lower-bound violations (displayed low > actual): 0 -> MET" in text
    assert "Partial risk violations (OK while actual > simulated headroom): 1 -> FAILED" in text
    assert "at least 12 (covers 1 of 2)" in text
    assert "12 / 16 / 30" not in text
    assert "above_high" in text


def test_v4_configuration_bar_is_three_percent():
    rows = []
    for index in range(32):
        actual = 10 * MIB if index == 0 else 8 * MIB
        rows.append(
            {
                "id": f"cell-{index}",
                "config": f"config-{index}",
                "template": "fully_covered",
                "ops": ["sort_values"],
                "estimates": [{"model": "sort_values"}],
                "actual": actual,
                "new": {"ram_low": MIB, "ram_expected": 5 * MIB, "ram_high": 9 * MIB},
                "v1": None,
                "uncovered": 0,
                "classes": {},
                "mode": "statements",
            }
        )

    text = report(rows, "v4 report", version=4)

    assert "above_high <= 3% of configurations" in text
    assert "1 of 32 (3.1%) -> FAILED" in text
