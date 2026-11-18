"""The real-notebook coverage study: static analysis only, on the handwritten cells and on synthetic notebooks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.multistatement_cells import CELLS
from benchmarks.realworld import coverage as cov


def _nb(path: Path, cells: list[tuple[str, str]], version: int = 4) -> Path:
    if version == 4:
        data = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
                for kind, src in cells
            ],
        }
    else:  # nbformat 3
        data = {
            "nbformat": 3,
            "worksheets": [{"cells": [{"cell_type": k, "input": s} for k, s in cells]}],
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_51_handwritten_cells_give_the_same_verdicts_as_with_a_live_namespace(tmp_path):
    """Stand-in operands must not change the analyzer's verdicts (pinned set from the Phase 4d study)."""
    _nb(tmp_path / "hand.ipynb", [("code", src) for _, _, src in CELLS])
    records, stats = cov.study(tmp_path)
    assert stats["code_cells"] == 51 and len(records) == 51
    accepted = {CELLS[r.index][0] for r in records if r.accepted}
    assert accepted == {
        "control merge",
        "control groupby",
        "control sort",
        "control astype",
        "control matmul",
        "time then op",
    }
    assert all(r.reason for r in records if not r.accepted)


def test_the_handwritten_report_ranks_the_relaxations_and_lists_the_reasons(tmp_path):
    _nb(tmp_path / "hand.ipynb", [("code", src) for _, _, src in CELLS])
    records, stats = cov.study(tmp_path)
    text = cov.report(records, stats)
    for heading in (
        "## Headline",
        "## By detected operation",
        "## Why cells are rejected",
        "## Candidate ranking",
        "COUNTING ONLY",
    ):
        assert heading in text
    rejected = [r for r in records if not r.accepted and r.supported]
    assert rejected and any(r.unlocked_by for r in rejected)
    ranking = [
        ln
        for ln in text.splitlines()
        if ln.startswith("| ") and ln.split("|")[2].strip() in cov.PROPOSALS
    ]
    assert len(ranking) == len(cov.PROPOSALS)
    counts = [int(ln.split("|")[3].split()[0]) for ln in ranking]
    assert counts == sorted(counts, reverse=True)  # ranked by supported-operation cells unlocked


SYNTHETIC = {
    "a.ipynb": [
        ("markdown", "# title"),
        ("code", "import pandas as pd\nimport numpy as np"),
        ("code", 'keys = ["s"]'),
        ("code", 'df.groupby(keys)["f"].sum()'),  # P1
        ("code", 'df.sort_values("f").head()'),  # P4
        ("code", 'df[df.f > 0].groupby("s")["f"].sum()'),  # P5
        ("code", 'df.groupby("s").agg({"f": "sum"})'),  # P6
        ("code", 'import time\ndf.sort_values("f")'),  # P7
        ("code", "x = df.drop_duplicates()\nprint(x.shape)"),  # P2
        ("code", 'left.merge(right, on="k").sort_values("f")'),  # P3
        ("code", 'df.sort_values("f")'),  # accepted outright
        ("code", "df.sort_values('f', inplace=True)"),  # never unlocked
        ("code", "# only a comment"),
        ("code", ""),
        ("code", 'print "python 2 syntax"'),
        ("code", "%matplotlib inline"),
        ("code", "x = 1 + 1"),
    ],
    "sub/b.ipynb": [
        ("code", "import pandas as p"),
        ("code", 'p.read_csv("data.csv")'),
        ("code", "a @ b"),
    ],
}


def _synthetic(tmp_path):
    for name, cells in SYNTHETIC.items():
        _nb(tmp_path / name, cells)
    _nb(tmp_path / "old.ipynb", [("code", "df.drop_duplicates()")], version=3)
    (tmp_path / "broken.ipynb").write_text("{not json", encoding="utf-8")
    return tmp_path


def test_counts_on_a_synthetic_notebook_folder(tmp_path):
    records, stats = cov.study(_synthetic(tmp_path))
    assert stats["notebooks"] == 3 and stats["unreadable_notebooks"] == 1
    assert (
        stats["code_cells"] == 16 + 3 + 1 and stats["blank_cells"] == 2
    )  # a comment-only and an empty cell
    by = {(r.notebook.replace("\\", "/"), r.index): r for r in records}
    assert (
        by[("a.ipynb", 8)].accepted is False and by[("a.ipynb", 8)].supported
    )  # a chain: detected but rejected
    assert by[("a.ipynb", 9)].accepted and by[("a.ipynb", 9)].supported
    assert by[("a.ipynb", 13)].reason_class == "does not parse as Python"
    unlocked = {
        (k[1]): set(r.unlocked_by) for k, r in by.items() if k[0] == "a.ipynb" and r.unlocked_by
    }
    # proposals overlap (a chain can be unlocked by P3 and by P4 alone): check membership, not equality
    expected = {2: "P1", 3: "P4", 4: "P5", 5: "P6", 6: "P7", 7: "P2", 8: "P3"}
    for index, proposal in expected.items():
        assert proposal in unlocked[index], (index, proposal, unlocked.get(index))
    assert 10 not in unlocked  # an in-place call stays rejected under every proposal
    assert (
        by[("sub/b.ipynb", 1)].accepted and by[("sub/b.ipynb", 2)].accepted
    )  # alias of pandas, a @ b stand-in arrays
    assert any(r.notebook == "old.ipynb" and r.accepted for r in records)  # nbformat 3 is read too


def test_the_alias_namespace_comes_from_the_notebooks_own_imports(tmp_path):
    _nb(
        tmp_path / "x.ipynb",
        [
            ("code", "import pandas as xx\nfrom pandas import read_csv as rc"),
            ("code", 'rc("f.csv")'),
        ],
    )
    records, _ = cov.study(tmp_path)
    assert (
        records[-1].supported and not records[-1].accepted
    )  # a bare imported name is not qualified (today)
    assert records[-1].unlocked_by == ["P8"]  # ... and P8 would unlock it


def test_cell_code_is_never_executed(tmp_path):
    marker = tmp_path / "executed.txt"
    evil = [
        ("code", f'open({str(marker)!r}, "w").write("x")'),
        ("code", f'import os\nos.system("echo hi > {marker}")'),
        ("code", f'__import__("pathlib").Path({str(marker)!r}).write_text("x")'),
        ("code", "raise SystemExit(3)"),
        ("code", "import sys\nsys.exit(4)"),
        ("code", 'df.sort_values("f", inplace=True); open("z", "w")'),
    ]
    _nb(tmp_path / "evil.ipynb", evil)
    records, stats = cov.study(tmp_path)
    assert not marker.exists() and stats["code_cells"] == 6 and len(records) == 6
    assert not any(r.accepted for r in records)


def test_the_command_line_writes_the_report_files_and_enforces_min_cells(tmp_path, capsys):
    folder = _synthetic(tmp_path / "nbs")
    out = tmp_path / "out"
    assert cov.main([str(folder), "--out", str(out)]) == 0
    assert (out / "coverage.md").read_text(encoding="utf-8").startswith("# Real-notebook coverage")
    assert (out / "cells.csv").exists() and json.loads((out / "summary.json").read_text())[
        "notebooks"
    ] == 3
    assert cov.main([str(folder), "--min-cells", "1000"]) == 1
    with pytest.raises(SystemExit):
        cov.main([str(tmp_path / "missing")])
    capsys.readouterr()


def test_an_empty_folder_gives_an_empty_but_valid_report(tmp_path):
    records, stats = cov.study(tmp_path)
    assert records == [] and stats["notebooks"] == 0
    assert "0 cells analysed" in cov.report(records, stats).replace(
        "**0 cells analysed**", "0 cells analysed"
    )
