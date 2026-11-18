"""Realistic multi-statement cells vs the Tier 2 safety analyzer (the analyzer is NOT loosened in Phase 4d)."""

from __future__ import annotations

from benchmarks.multistatement_cells import CELLS, make_namespace
from benchmarks.multistatement_report import evaluate, markdown
from nexus.dryrun_safety import analyze_safety


def test_there_are_at_least_forty_realistic_cells_in_several_categories():
    assert len(CELLS) >= 40 and len({c for _, c, _ in CELLS}) >= 8
    assert len({n for n, _, _ in CELLS}) == len(CELLS)


def test_the_accepted_set_is_pinned_so_a_loosening_shows_up_in_review():
    accepted = {r["name"] for r in evaluate() if r["safe"]}
    assert accepted == {
        "control merge",
        "control groupby",
        "control sort",
        "control astype",
        "control matmul",
        "time then op",
    }


def test_mutating_and_side_effect_cells_are_never_accepted():
    risky = {"mutation", "control flow / functions"}
    for name, category, source in CELLS:
        if category in risky:
            assert not analyze_safety(source, make_namespace()).safe, name
    assert not analyze_safety('df["h"] = df["f"] * df["g"]', make_namespace()).safe


def test_every_rejection_has_a_reason_and_the_report_lists_proposals_only():
    rows = evaluate()
    assert all(r["reason"] for r in rows if not r["safe"])
    text = markdown(rows)
    assert "PROPOSALS ONLY" in text and "Accepted: 6 of 51" in text
