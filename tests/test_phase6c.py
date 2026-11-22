"""Phase 6c: the cell-level peak model, copy / fillna, read_csv arguments, extension defaults."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from nexus import cellpeak
from nexus.models._output import output_range
from nexus.models.base import Estimate
from nexus.pipeline import OpEstimate, Pipeline
from nexus.risk import assess, combine

MIB = 2**20


def _est(lo: float, exp: float, hi: float) -> Estimate:
    return Estimate(ram_low=int(lo * MIB), ram_expected=int(exp * MIB), ram_high=int(hi * MIB),
                    time_low=0.1, time_expected=0.2, time_high=0.4, confidence=0.7, tier=1)  # fmt: skip


def _ops(
    src: str, peaks: list[tuple[float, float, float]], model: str = "unknown"
) -> list[OpEstimate]:
    """OpEstimates for the calls of ``src`` in order, with the given peaks (output = whole peak)."""
    from nexus.analyzer import analyze_cell

    ops = analyze_cell(src, {"pd": pd, "df": pd.DataFrame({"a": [1]})})
    assert len(ops) == len(peaks), [o.name for o in ops]
    return [
        OpEstimate(op=o, model=model, estimate=_est(*p), features={})
        for o, p in zip(ops, peaks, strict=True)
    ]


def test_retained_loads_add_up_instead_of_taking_the_max():
    src = "a = df.sort_values('a')\nb = df.sort_values('a')"
    cell, mode, _ = cellpeak.cell_estimate(src, _ops(src, [(80, 100, 150), (80, 100, 150)]))
    assert mode == "statements"
    assert cell.ram_expected == 200 * MIB and cell.ram_high == 300 * MIB  # retained + current
    v1 = combine([_est(80, 100, 150), _est(80, 100, 150)])
    assert v1.ram_expected == 100 * MIB  # the v1 max


def test_del_releases_and_expression_statements_are_temporary():
    src = "a = df.sort_values('a')\ndel a\nb = df.sort_values('a')"
    cell, _, _ = cellpeak.cell_estimate(src, _ops(src, [(80, 100, 150), (40, 50, 60)]))
    assert cell.ram_expected == 100 * MIB  # a released before b: max(100, 50)
    src = "df.sort_values('a')\nb = df.sort_values('a')"
    cell, _, _ = cellpeak.cell_estimate(src, _ops(src, [(80, 100, 150), (40, 50, 60)]))
    assert cell.ram_expected == 100 * MIB  # the expression's result is not kept


def test_rebinding_is_not_a_release_and_chains_keep_temporaries():
    src = "a = df.sort_values('a')\na = df.sort_values('a')"
    cell, _, _ = cellpeak.cell_estimate(src, _ops(src, [(10, 100, 100), (10, 50, 50)]))
    assert cell.ram_expected == 150 * MIB  # conservative: the first result may still be referenced
    src = "r = df.sort_values('a').drop_duplicates()"
    cell, _, _ = cellpeak.cell_estimate(src, _ops(src, [(10, 100, 100), (10, 40, 40)]))
    assert cell.ram_expected == 140 * MIB  # the chain link is alive while the next runs


def test_loops_and_functions_fall_back_to_v1_with_a_flag():
    src = "for i in range(3):\n    a = df.sort_values('a')"
    cell, mode, flags = cellpeak.cell_estimate(src, _ops(src, [(10, 100, 100)]))
    assert mode == "v1" and flags and "For" in flags[0]
    src = "x = [df.sort_values('a') for _ in range(2)]"
    cell, mode, flags = cellpeak.cell_estimate(src, _ops(src, [(10, 100, 100)]))
    assert mode == "v1" and "comprehension" in flags[0]


def test_single_operation_cells_are_unchanged():
    df = pd.DataFrame({"k": np.arange(20_000) % 50, "v": np.arange(20_000.0)})
    rep = Pipeline(tier=1).run("df.groupby('k')['v'].sum()", {"df": df})
    cell, _, _ = cellpeak.cell_estimate(rep.source, rep.estimates)
    assert cell == rep.estimates[0].estimate
    risk = assess(rep)
    assert risk is not None and risk.ram_expected == rep.estimates[0].estimate.ram_expected


def test_output_range_is_bounded_by_the_operation_range():
    df = pd.DataFrame({"k": np.arange(50_000) % 50, "v": np.arange(50_000.0)})
    right = pd.DataFrame({"k": np.arange(50), "w": 1.0})
    ns = {"df": df, "right": right, "pd": pd}
    for src in ("df.merge(right, on='k')", "df.groupby('k')['v'].sum()", "df.sort_values('v')",
                "df.drop_duplicates(subset=['k'])", "df.copy()", "df.fillna(0)"):  # fmt: skip
        item = Pipeline(tier=1).run(src, ns).estimates[0]
        out = output_range(item.model, item.features, item.estimate)
        e = item.estimate
        assert out is not None, src
        assert 0 <= out[0] <= out[1] <= out[2]
        assert out[0] <= e.ram_low + 1 and out[1] <= e.ram_expected + 1 and out[2] <= e.ram_high + 1
    assert output_range("no_such_model", {}, _est(1, 2, 3)) is None


def test_copy_and_fillna_follow_the_copy_semantics():
    n = 200_000
    df = pd.DataFrame({"a": np.random.rand(n), "b": np.random.rand(n), "i": np.arange(n),
                       "s": pd.Series(["x"] * n, dtype=object)})  # fmt: skip
    df.loc[3, "a"] = (
        np.nan
    )  # before any other frame shares df's blocks (copy-on-write would split them)
    df_str = df.assign(s=df["s"].astype("str"))  # the pandas-3 default text dtype (extension)
    ns = {"df": df, "df_str": df_str, "pd": pd}

    def est(src: str, tier: int = 1) -> Estimate | None:
        r = Pipeline(tier=tier).run(src, ns)
        return r.estimates[0].estimate if r.estimates else None

    moved = 8 * n * 4  # a, b, i values + s pointers
    assert est("df.copy()").ram_expected == moved
    assert est("df.copy(deep=False)").ram_expected == 0
    full = est("df.fillna(0)")  # the float block (a, b) holds a NaN: copied + its mask
    assert full.ram_expected == 2 * 8 * n + 4 * 2 * n  # + 4 bool masks (Block.fillna -> where)
    one = est("df.fillna({'a': 0})")
    assert one.ram_expected == 8 * n + 4 * n
    assert est("df_str.fillna(0)") is None  # extension (str) column: not derived, refused
    assert est("df['i'].fillna(0)") is None or est("df['i'].fillna(0)").ram_high == 0  # int: no NA
    for refused in ("df.fillna(0, inplace=True)", "df.fillna(method='ffill')", "df.fillna(x)",
                    "df.loc[:5].copy()"):  # fmt: skip
        assert est(refused) is None, refused
    assert est("df.fillna(0)", tier=0).ram_low == 0  # Tier 0: which blocks hold a NaN is unknown


def test_multicell_split_is_frozen_and_covers_every_template():
    from benchmarks.multicell import cases, split

    sp = split.load()
    assert len(sp.heldout) == len(cases.TEMPLATES) and 2 * len(sp.heldout) >= 12
    assert len(sp.dev) + len(sp.heldout) == len(cases.all_configs())
    data = json.loads(split.SPLIT_FILE.read_text())
    data["dev"] = data["dev"][1:]
    bad = split.SPLIT_FILE.with_name("bad_split.json")
    try:
        bad.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            split.load(bad)
    finally:
        bad.unlink(missing_ok=True)


def test_multicell_report_formats_mib_and_ratio_columns():
    from benchmarks.multicell.run import MIB, report

    est = {"ram_low": 50 * MIB, "ram_expected": 60 * MIB, "ram_high": 90 * MIB}
    rows = [{"id": f"t/num@{i}", "config": "t/num", "template": "t", "actual": 52 * MIB,
             "new": est, "v1": est, "uncovered": 0, "mode": "statements"} for i in (1, 2)]  # fmt: skip
    rows.append({**rows[0], "id": "t/num@3", "actual": None})
    text = report(rows, "x")
    per_template = next(line for line in text.splitlines() if line.startswith("| t |"))
    assert per_template.split(" | ")[-2] == "1.15"  # v1_bias is a ratio, not a percentage
    assert "| t/num@1 | 52 | 50 / 60 / 90 |" in text  # actual in MiB
    assert "| t/num@3 | - |" in text  # no measured peak


def test_extension_defaults_and_fallback_wording():
    from nexus.render import FALLBACK_PREFIX, fallback_notes
    from nexus.session import DEFAULT_TIER, NexusSession

    class Shell:
        user_ns: dict = {}

    s = NexusSession(Shell())
    assert DEFAULT_TIER == 1 and s.pipeline._tier == 1
    assert "tier 1" in s.status()
    assert "dry runs enabled" in s.set_tier(2) and s.pipeline._tier == 2
    df = pd.DataFrame({"a": np.arange(1000)})
    rep = Pipeline(tier=1).run("df.sort_values('a')", {"df": df})
    assert fallback_notes(rep) == []  # a Tier-0-only model is not a fallback
    df = pd.DataFrame({"k": np.arange(20_000) % 9, "v": np.arange(20_000.0)})
    rep = Pipeline(tier=0).run("df.groupby('k')['v'].sum()", {"df": df})  # a model WITH statistics
    item = rep.estimates[0]
    faked = OpEstimate(op=item.op, model=item.model, estimate=item.estimate,
                       features={"tier1": {"used": False, "reason": "time budget"}})  # fmt: skip
    rep.estimates[0] = faked
    notes = fallback_notes(rep)
    assert notes and notes[0].startswith(FALLBACK_PREFIX) and "time budget" in notes[0]
    assert rep.estimates[0].estimate == item.estimate  # the wording changes no estimate


def test_only_the_multicell_runner_touches_its_held_out_results():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    protected = re.compile(r"phase6c-heldout-access-log|multicell/heldout|HELDOUT_LOG")
    offenders = []
    for path in list((root / "src").rglob("*.py")) + list((root / "benchmarks").rglob("*.py")):
        if path.parent.name == "multicell" and path.name in ("run.py", "split.py"):
            continue
        if protected.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
