"""The frozen suggestion-benchmark split: digest, coverage and leak protection (Phase 5)."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.suggestions import run, split
from benchmarks.suggestions.cases import all_configs

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = re.compile(r"evaluate_heldout|heldout_dir|load_heldout|ACCESS_LOG")


def test_split_is_frozen_and_meets_the_pre_registered_sizes():
    sp = split.load()
    assert len(sp.dev) + len(sp.heldout) >= 40 and len(sp.heldout) >= 14
    fam = lambda keys: Counter(k.split("/")[0] for k in keys)  # noqa: E731
    assert set(fam(sp.dev)) == set(fam(sp.heldout))  # every rule family on both sides
    dev_cells = [c for c in run._cells(sp.dev) if c[0].family != "delete_unreferenced"]
    assert len(dev_cells) >= 30


def test_assignment_is_reproducible_from_the_stored_rule():
    sp = split.load()
    by_family: dict[str, list[str]] = {}
    for c in all_configs():
        by_family.setdefault(c.family, []).append(c.key)
    dev, held = split.assign(by_family)
    assert tuple(dev) == sp.dev and tuple(held) == sp.heldout


def test_an_edited_split_file_is_refused(tmp_path):
    data = json.loads(split.SPLIT_FILE.read_text(encoding="utf-8"))
    data["heldout"] = data["heldout"][:-1]
    bad = tmp_path / "split.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        split.load(bad)
    with pytest.raises(FileExistsError):
        split.create(split.SPLIT_FILE)


def test_only_the_run_and_split_modules_touch_held_out_results():
    offenders = []
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "benchmarks").rglob("*.py")):
        if path.parent.name == "suggestions" and path.name in ("run.py", "__main__.py", "split.py"):
            continue
        if PROTECTED.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_dev_evaluation_refuses_held_out_rows(tmp_path):
    sp = split.load()
    d = tmp_path / "dev"
    d.mkdir()
    (d / "results.jsonl").write_text(
        json.dumps({"row_id": "x", "kind": "base", "config": sp.heldout[0]}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        run.evaluate_dev(tmp_path)


def test_heldout_evaluation_needs_a_reason(tmp_path):
    with pytest.raises(SystemExit):
        run.evaluate_heldout("  ", tmp_path)
    with pytest.raises(SystemExit):
        run.run(heldout=True, reason="", results=tmp_path)


def _row(measured_mod, *, preserving_identical=True, shown=True, lb=False):
    base = {"status": "ok", "censored": False, "delta": 500 * 2**20, "bound": 0}
    mod = {
        "status": "ok",
        "censored": lb,
        "delta": None if lb else measured_mod,
        "bound": measured_mod,
    }
    return {
        "kind": "suggestion", "cell": "c", "config": "x", "family": "f", "base": base, "mod": mod,
        "suggestion": {"rule": "r", "semantics": "preserving", "shown": shown, "before": [1, 2, 3],
                       "saving_frac": 0.5, "hidden_reason": ""},
        "verify": {"comparable": True, "identical": preserving_identical},
    }  # fmt: skip


def test_analysis_flags_preserving_bugs_harm_and_increases():
    mb = 2**20
    a = run.analyse([_row(100 * mb), _row(100 * mb, preserving_identical=False), _row(700 * mb)])
    assert len(a["bugs"]) == 1 and len(a["harm"]) == 1 and len(a["increased"]) == 1
    only_lb = run.analyse([_row(100 * mb, lb=True)])
    assert only_lb["items"][0]["meas"]["lower_bound"] and only_lb["err"] == []
    text = run.report([{"kind": "base", "risky": True}, _row(100 * mb)], "t", "s")
    assert "S1 no `preserving` bug" in text and "S2 do no harm" in text
