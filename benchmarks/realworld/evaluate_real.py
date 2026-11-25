"""Evaluate v3/v4 paired harness records without loading notebook or dataset contents.

The evaluator validates each result root's frozen tag and every cell row. Legacy v3 rows receive
their version from the validated run summary because that frozen harness predates row-level tags.

    python -m benchmarks.realworld.evaluate_real <v3-results-root> <v4-results-root> --out <report.md>
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.frozen import FROZEN_TAG, PREVIOUS_TAG
from benchmarks.phase8_verdict import clopper_pearson_upper, wilson_lower
from nexus.models.base import Estimate
from nexus.risk import RiskClass, classify
from nexus.timebuckets import bucket_index

MIB = 2**20
MIN_POINTS = 30
MIN_ELIGIBLE_CELLS = 150
RAM_ABOVE_HIGH_MAX = 0.03
TIME_WITHIN_ONE_MIN = 0.95
MIN_COVERAGE_GAIN = 0.10
V3_MODEL_VERSION = PREVIOUS_TAG
V4_MODEL_VERSION = FROZEN_TAG
LIMITS_MIB = (2048, 1024)
RECALL_TARGET, FAR_TARGET, FAR_PER_OP_TARGET, HIGH_PRECISION_TARGET = 0.98, 0.30, 0.50, 0.75
MIN_POSITIVES = 20
PARTIAL_HEADROOMS_MIB = (64, 128, 256, 512, 1024, 2048, 4096, 8192)


def _read_run_metadata(summary_path: Path, expected_version: str) -> tuple[str, Path]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    version = summary.get("model_version") or summary.get("frozen", {}).get("frozen_tag")
    if version != expected_version:
        raise ValueError(
            f"{summary_path} records model_version {version!r}, expected {expected_version!r}"
        )
    notebook = summary.get("notebook")
    if not isinstance(notebook, str) or not notebook:
        raise ValueError(f"{summary_path} has no notebook identifier")
    cells_path = summary_path.parent / "cells.jsonl"
    if not cells_path.is_file():
        raise ValueError(f"missing cell records for {notebook!r}: {cells_path}")
    return notebook, cells_path


def _read_cell_rows(cells_path: Path, notebook: str, expected_version: str) -> list[dict[str, Any]]:
    rows = []
    with cells_path.open(encoding="utf-8") as cells:
        for line_number, line in enumerate(cells, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            row_version = row.get("model_version")
            if row_version is None and expected_version == V3_MODEL_VERSION:
                row_version = expected_version
                row["model_version"] = row_version
            if row_version != expected_version:
                raise ValueError(
                    f"{cells_path}:{line_number} records model_version {row_version!r}, "
                    f"expected {expected_version!r}"
                )
            if row.get("notebook") != notebook:
                raise ValueError(
                    f"{cells_path}:{line_number} notebook identifier does not match "
                    f"{cells_path.parent / 'summary.json'}"
                )
            rows.append(row)
    return rows


def load_versioned(
    results_root: Path, expected_version: str
) -> tuple[pd.DataFrame, frozenset[str]]:
    """Load result metadata only, validating the tag and every persisted row."""
    if not results_root.is_dir():
        raise ValueError(f"result root does not exist or is not a directory: {results_root}")
    summaries = sorted(results_root.rglob("summary.json"))
    if not summaries:
        raise ValueError(f"no summary.json files found under {results_root}")

    rows: list[dict[str, Any]] = []
    notebooks: set[str] = set()
    for summary_path in summaries:
        notebook, cells_path = _read_run_metadata(summary_path, expected_version)
        if notebook in notebooks:
            raise ValueError(f"duplicate notebook result folder for {notebook!r} in {results_root}")
        notebooks.add(notebook)
        rows.extend(_read_cell_rows(cells_path, notebook, expected_version))
    return pd.DataFrame(rows), frozenset(notebooks)


def load_paired(v3_root: Path, v4_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    v3, v3_notebooks = load_versioned(v3_root, V3_MODEL_VERSION)
    v4, v4_notebooks = load_versioned(v4_root, V4_MODEL_VERSION)
    if v3_notebooks != v4_notebooks:
        only_v3 = sorted(v3_notebooks - v4_notebooks)
        only_v4 = sorted(v4_notebooks - v3_notebooks)
        raise ValueError(
            "v3 and v4 result roots must contain the same notebooks; "
            f"only v3: {only_v3}; only v4: {only_v4}"
        )
    return v3, v4


def _row_key(row: dict[str, Any]) -> tuple[str, int, str]:
    try:
        return str(row["notebook"]), int(row["index"]), str(row["hash"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"cell result is missing a valid notebook/index/hash key: {row}") from exc


def _row_index(df: pd.DataFrame) -> dict[tuple[str, int, str], dict[str, Any]]:
    indexed = {}
    for row in df.to_dict("records"):
        key = _row_key(row)
        if key in indexed:
            raise ValueError(f"duplicate cell result key: {key}")
        indexed[key] = row
    return indexed


def _has_operations(row: dict[str, Any]) -> bool:
    return isinstance(row.get("ops"), list) and bool(row["ops"])


def _is_covered(row: dict[str, Any]) -> bool:
    if not _has_operations(row) or row.get("hard_deadline_fired") is True:
        return False
    try:
        if int(row.get("uncovered", 0) or 0) != 0:
            return False
    except (TypeError, ValueError):
        return False
    if "covered" in row:
        return row["covered"] is True
    return True


def paired_coverage(v3: pd.DataFrame, v4: pd.DataFrame) -> dict[str, Any]:
    """Compare run-time coverage only on the same operation-bearing cells."""
    old, new = _row_index(v3), _row_index(v4)
    shared = old.keys() & new.keys()
    eligible = [key for key in shared if _has_operations(old[key]) or _has_operations(new[key])]
    n = len(eligible)
    v3_covered = sum(_is_covered(old[key]) for key in eligible)
    v4_covered = sum(_is_covered(new[key]) for key in eligible)
    v3_only, v4_only = old.keys() - new.keys(), new.keys() - old.keys()
    v3_only_ops = sum(_has_operations(old[key]) for key in v3_only)
    v4_only_ops = sum(_has_operations(new[key]) for key in v4_only)
    delta = (v4_covered - v3_covered) / n if n else math.nan
    if n < MIN_POINTS:
        result = f"INCONCLUSIVE ({n} paired operation cells < {MIN_POINTS})"
    elif (v4_covered - v3_covered) * 100 >= n * MIN_COVERAGE_GAIN * 100:
        result = "MET"
    else:
        result = "FAILED"
    return {
        "n": n,
        "v3_covered": v3_covered,
        "v3_share": v3_covered / n if n else math.nan,
        "v4_covered": v4_covered,
        "v4_share": v4_covered / n if n else math.nan,
        "delta": delta,
        "verdict": result,
        "v3_only_cells": len(v3_only),
        "v3_only_operation_cells": v3_only_ops,
        "v4_only_cells": len(v4_only),
        "v4_only_operation_cells": v4_only_ops,
    }


def width_metrics(v3: pd.DataFrame, v4: pd.DataFrame) -> dict[str, Any]:
    """Evaluate the pre-registered W(a)/W(b) range-width comparisons."""
    old, new = _row_index(v3), _row_index(v4)
    a_ratios, b_widths = [], []
    for key, new_row in new.items():
        new_est = new_row.get("cell")
        if not isinstance(new_est, dict) or not _is_covered(new_row):
            continue
        new_expected = float(new_est["ram_expected"])
        if new_expected <= 0:
            continue
        new_width = float(new_est["ram_high"]) / new_expected
        old_row = old.get(key)
        old_est = old_row.get("cell") if old_row is not None else None
        if old_row is not None and _is_covered(old_row) and isinstance(old_est, dict):
            old_expected = float(old_est["ram_expected"])
            if old_expected > 0:
                a_ratios.append(new_width / (float(old_est["ram_high"]) / old_expected))
        else:
            b_widths.append(new_width)

    a_n = len(a_ratios)
    b_n = len(b_widths)
    a_median = float(np.median(a_ratios)) if a_n else math.nan
    b_median = float(np.median(b_widths)) if b_n else math.nan
    b_p90 = float(np.quantile(b_widths, 0.9)) if b_n else math.nan
    return {
        "a_n": a_n,
        "a_median": a_median,
        "a_verdict": verdict(a_n, a_median <= 1.30),
        "b_n": b_n,
        "b_median": b_median,
        "b_p90": b_p90,
        "b_verdict": verdict(b_n, b_median <= 2.0 and b_p90 <= 4.0),
    }


def group_of(r: pd.Series) -> str:
    if r.get("status") == "skipped":
        return "skipped"
    if r.get("status") in ("error", "kernel_died", "timeout"):
        return "failed"
    has_est = isinstance(r.get("cell"), dict)
    if not has_est:
        return "detection-only" if r.get("ops") else "no operation"
    if r.get("ram_class") == "valid" or r.get("time_class") == "valid":
        return "validated-model, valid actual"
    if r.get("ram_reason") == "below the previous historical peak":
        return "censored"
    return "cheap"


def dominant_op(r: pd.Series) -> str:
    est = r.get("estimates") or []
    if not est:
        return "-"
    return max(est, key=lambda e: e["ram_expected"])["op"]


def ram_metrics(d: pd.DataFrame, key: str) -> dict[str, Any]:
    if d.empty:
        return {"n": 0}
    a = d["ram_value"].astype(float)
    lo = d[key].map(lambda c: c["ram_low"])
    e = d[key].map(lambda c: c["ram_expected"]).astype(float)
    hi = d[key].map(lambda c: c["ram_high"])
    above = a > hi  # a watchdog lower bound counts only if the bound itself exceeds high
    above_count = int(above.sum())
    rel = (e - a).abs() / a
    return {
        "n": len(d), "bias": float((e / a).median()), "err_med": float(rel.median()),
        "err_p90": float(rel.quantile(0.9)), "coverage": float(((lo <= a) & (a <= hi)).mean()),
        "above_high": float(above.mean()), "above_high_n": above_count,
        "above_high_upper95": clopper_pearson_upper(above_count, len(d)),
        "below_low": float((a < lo).mean()), "width": float(((hi - lo) / e.where(e > 0)).mean()),
    }  # fmt: skip


def time_metrics(d: pd.DataFrame, key: str) -> dict[str, Any]:
    if d.empty:
        return {"n": 0}
    a = d["time_value"].astype(float)
    e = d[key].map(lambda c: c["time_expected"]).astype(float).clip(lower=1e-9)
    lo = d[key].map(lambda c: c["time_low"])
    hi = d[key].map(lambda c: c["time_high"])
    eb, ab = e.map(bucket_index), a.map(bucket_index)
    rel = (e - a).abs() / a
    return {
        "n": len(d), "within_one": float(((eb - ab).abs() <= 1).mean()),
        "within_one_lower95": wilson_lower(int(((eb - ab).abs() <= 1).sum()), len(d)),
        "same": float((eb == ab).mean()), "err_med": float(rel.median()),
        "err_p90": float(rel.quantile(0.9)), "bias": float((e / a).median()),
        "coverage": float(((lo <= a) & (a <= hi)).mean()),
    }  # fmt: skip


def verdict(n: int, ok: bool) -> str:
    if n < MIN_POINTS:
        return f"INCONCLUSIVE ({n} valid points < {MIN_POINTS})"
    return "MET" if ok else "FAILED"


def phase_verdict(n: int, ok: bool, eligible_count: int) -> str:
    if eligible_count < MIN_ELIGIBLE_CELLS:
        return f"INCONCLUSIVE ({eligible_count} v4 eligible cells < {MIN_ELIGIBLE_CELLS})"
    return verdict(n, ok)


def safety_verdict(n: int, violations: int, missing_classes: int = 0) -> str:
    if missing_classes:
        return f"INCONCLUSIVE ({missing_classes} rows lack simulated risk classes)"
    if n == 0:
        return "INCONCLUSIVE (no measured cells)"
    return "MET" if violations == 0 else "FAILED"


def _estimates(r: pd.Series) -> list[Estimate]:
    out = []
    for e in r.get("estimates") or []:
        out.append(Estimate(ram_low=int(e["ram_low"]), ram_expected=int(e["ram_expected"]),
                            ram_high=int(e["ram_high"]), time_low=float(e["time_low"]),
                            time_expected=float(e["time_expected"]), time_high=float(e["time_high"]),
                            confidence=float(e["confidence"]), tier=int(e["tier"])))  # fmt: skip
    return out


def _estimate_from_dict(value: Any) -> Estimate | None:
    if not isinstance(value, dict):
        return None
    return Estimate(
        ram_low=int(value["ram_low"]),
        ram_expected=int(value["ram_expected"]),
        ram_high=int(value["ram_high"]),
        time_low=float(value["time_low"]),
        time_expected=float(value["time_expected"]),
        time_high=float(value["time_high"]),
        confidence=float(value["confidence"]),
        tier=int(value["tier"]),
    )


def partial_safety(d: pd.DataFrame) -> dict[str, Any]:
    """Score only partial and wholly uncovered rows with valid actual peaks."""
    partial, uncovered = [], []
    for _, row in d.iterrows():
        ops = row.get("ops")
        total = len(ops) if isinstance(ops, list) else 0
        missing_value = row.get("uncovered")
        missing = 0 if pd.isna(missing_value) else int(missing_value)
        if total and 0 < missing < total:
            partial.append(row)
        elif total and missing == total:
            uncovered.append(row)

    def score(rows: list[pd.Series], include_lower: bool) -> dict[str, Any]:
        measured = [row for row in rows if row.get("ram_class") == "valid"]
        lower = [
            str(row["hash"])
            for row in measured
            if include_lower
            and isinstance(row.get("cell"), dict)
            and int(row["cell"]["ram_low"]) > float(row["ram_value"])
        ]
        missing_lower = [
            str(row["hash"])
            for row in measured
            if include_lower and not isinstance(row.get("cell"), dict)
        ]
        missing_classes = []
        risk = []
        for row in measured:
            classes = row.get("simulated_risk_classes")
            if not isinstance(classes, dict) or any(
                str(h) not in classes for h in PARTIAL_HEADROOMS_MIB
            ):
                missing_classes.append(str(row["hash"]))
                continue
            for headroom in PARTIAL_HEADROOMS_MIB:
                if classes[str(headroom)] == "OK" and float(row["ram_value"]) > headroom * MIB:
                    risk.append((str(row["hash"]), headroom))
        return {
            "n": len(measured),
            "lower_violations": lower,
            "missing_lower_bounds": missing_lower,
            "risk_violations": risk,
            "missing_classes": missing_classes,
        }

    return {"partial": score(partial, True), "uncovered": score(uncovered, False)}


def risk_eval(valid: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """One row per (valid RAM point, simulated limit)."""
    rows = []
    for _, r in valid.iterrows():
        est = _estimates(r)
        if not est:
            continue
        a, rss = float(r["ram_value"]), float(r["rss_start"])
        for name, head, positive in (
            ("free RAM at start", float(r["avail_start"]), a > float(r["avail_start"])),
            *[(f"{L} MiB", L * MIB - rss, rss + a > L * MIB) for L in LIMITS_MIB],
        ):
            cell = _estimate_from_dict(r.get("cell"))
            warn = r.get("cell_warn")
            rep = classify(
                est,
                headroom=int(max(head, 0)),
                uncovered=int(r.get("uncovered") or 0),
                cell=cell,
                warn_high=int(warn["ram_high"]) if isinstance(warn, dict) else None,
                covered_operations=len(est),
                total_operations=len(r.get("ops")) if isinstance(r.get("ops"), list) else 0,
            )
            alert = rep.risk in (RiskClass.WARN, RiskClass.HIGH_RISK)
            rows.append({"limit": name, "op": dominant_op(r), "positive": bool(positive), "alert": alert,
                         "high": rep.risk == RiskClass.HIGH_RISK, "class": rep.risk.value,
                         "hash": r["hash"], "notebook": r["notebook"]})  # fmt: skip
    t = pd.DataFrame(rows)
    res: dict[str, Any] = {}
    if t.empty:
        return t, res
    per_limit = []
    for lim, g in t.groupby("limit"):
        pos, neg = g[g.positive], g[~g.positive]
        per_limit.append({"limit": lim, "pairs": len(g), "positives": len(pos),
                          "recall": pos.alert.mean() if len(pos) else math.nan,
                          "false_alarm": neg.alert.mean() if len(neg) else math.nan,
                          "high_n": int(g.high.sum()),
                          "high_precision": g[g.high].positive.mean() if g.high.any() else math.nan,
                          "missed": int((pos.alert == False).sum())})  # noqa: E712  # fmt: skip
    res["per_limit"] = pd.DataFrame(per_limit)
    claim = res["per_limit"][res["per_limit"]["positives"] >= MIN_POSITIVES]["limit"].tolist()
    tc = t[t["limit"].isin(claim)]
    pos, neg = tc[tc.positive], tc[~tc.positive]
    res["claim_limits"] = claim
    res["R1"] = pos.alert.mean() if len(pos) else math.nan
    res["R2_pooled"] = neg.alert.mean() if len(neg) else math.nan
    per_op = {op: (g.alert.mean(), len(g)) for op, g in neg.groupby("op")}
    res["R2_ops_over"] = {
        op: v for op, (v, n) in per_op.items() if n >= MIN_POSITIVES and v > FAR_PER_OP_TARGET
    }
    res["R2_ops_n"] = {op: n for op, (v, n) in per_op.items()}
    res["R3"] = tc[tc.high].positive.mean() if tc.high.any() else math.nan
    res["missed"] = t[t.positive & ~t.alert][["notebook", "hash", "op", "limit", "class"]]
    return t, res


RATIO_COLUMNS = ("bias", "width")


def _fmt(v: Any, col: str = "") -> str:
    if isinstance(v, float) and col in RATIO_COLUMNS:
        return "-" if math.isnan(v) else f"{v:.2f}"
    if isinstance(v, float):
        return "-" if math.isnan(v) else f"{v:.1%}" if abs(v) <= 10 else f"{v:,.0f}"
    return str(v)


def _table(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["(none)"]
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(_fmt(r.get(c), c) for c in cols) + " |" for r in rows]
    return out


def report(df: pd.DataFrame, *, eligible_count: int) -> str:  # noqa: C901
    df = df.copy()
    if df.empty:
        return (
            "# Phase 8b v4 results\n\n"
            f"Eligible v4 cells: {eligible_count} (< {MIN_ELIGIBLE_CELLS}); "
            "all Phase 8b criteria are INCONCLUSIVE. No cell result rows were recorded.\n"
        )
    for column in (
        "cell",
        "cell_tier0",
        "ram_class",
        "time_class",
        "status",
        "risk",
        "suggestions",
        "ops",
        "inputs",
        "uncovered",
        "covered",
        "hard_deadline_fired",
        "simulated_risk_classes",
    ):
        if column not in df:
            df[column] = None
    if "uncovered" not in df:
        df["uncovered"] = 0
    else:
        df["uncovered"] = pd.to_numeric(df["uncovered"], errors="coerce").fillna(0)
    df["runtime_covered"] = df.apply(lambda r: _is_covered(r.to_dict()), axis=1)
    df["group"] = df.apply(group_of, axis=1)
    lines = ["## v4 accuracy, risk and cell details", ""]
    lines += [
        f"Eligible v4 cells (operation detected, status OK): {eligible_count}; "
        f"requirement: {MIN_ELIGIBLE_CELLS}.",
        "",
        "## Cells by group",
        "",
        *_table([{"group": g, "cells": n} for g, n in df["group"].value_counts().items()]),
        "",
    ]
    has = df["cell"].map(lambda c: isinstance(c, dict))
    vr = df[has & (df["ram_class"] == "valid")]
    vt = df[has & (df["time_class"] == "valid") & (df["status"] == "ok")]
    vr_full = vr[vr["runtime_covered"]]
    vt_full = vt[vt["runtime_covered"]]
    lines += [
        "## Accuracy on valid points (Tier 1)",
        "",
        "RAM above-high is scored only on fully covered cells; partial cells are scored separately below. "
        "Time within-one uses fully covered valid time points.",
        "",
    ]
    rm, tm = ram_metrics(vr_full, "cell"), time_metrics(vt_full, "cell")
    lines += _table([{"metric": "RAM", **rm}]) + [""] + _table([{"metric": "time", **tm}]) + [""]
    lines.append(
        f"* **RAM verdict (one-sided 95% upper bound <= 3%):** "
        f"{phase_verdict(rm.get('n', 0), rm.get('above_high_upper95', 1) <= RAM_ABOVE_HIGH_MAX, eligible_count)}"
    )
    lines.append(
        f"* **Time verdict (Wilson 95% lower bound >= 95%):** "
        f"{phase_verdict(tm.get('n', 0), tm.get('within_one_lower95', 0) >= TIME_WITHIN_ONE_MIN, eligible_count)}"
    )
    vr0 = vr[vr["cell_tier0"].map(lambda c: isinstance(c, dict))]
    vt0 = vt[vt["cell_tier0"].map(lambda c: isinstance(c, dict))]
    lines += ["", "Secondary (Tier 0, what `%load_ext nexus` uses today; no verdict):", ""]
    lines += _table([{"metric": "RAM tier 0", **ram_metrics(vr0, "cell_tier0")},
                     {"metric": "time tier 0", **time_metrics(vt0, "cell_tier0")}])  # fmt: skip
    full = vr_full
    lines += ["", "Fully covered subset (every detected operation has an estimate):", ""]
    lines += _table([{"metric": "RAM", **ram_metrics(full, "cell")},
                     {"metric": "time", **time_metrics(vt_full, "cell")}])  # fmt: skip
    if len(vr_full):
        vr_full = vr_full.assign(op=vr_full.apply(dominant_op, axis=1))
        lines += ["", "RAM per dominant operation:", ""]
        lines += _table([{"op": op, **ram_metrics(g, "cell")} for op, g in vr_full.groupby("op")])
        vr_full = vr_full.assign(
            logerr=np.log(
                vr_full["cell"].map(lambda c: max(c["ram_expected"], 1)) / vr_full["ram_value"]
            ).abs()
        )
        lines += ["", "Worst RAM predictions (operation and input shapes only):", ""]
        worst = []
        for _, r in vr_full.sort_values("logerr", ascending=False).head(10).iterrows():
            shapes = "; ".join(
                f"{v['kind']} {v['shape']} {v.get('dtypes')}"
                for v in (r.get("inputs") or {}).values()
            )
            worst.append({"notebook": r["notebook"], "cell": r["hash"], "ops": ",".join(r["ops"]),
                          "expected MiB": r["cell"]["ram_expected"] / MIB, "actual MiB": r["ram_value"] / MIB,
                          "inputs": shapes[:160]})  # fmt: skip
        lines += _table(worst)
    safety = partial_safety(df)
    partial_result, uncovered_result = safety["partial"], safety["uncovered"]

    def safety_decision(n: int, violations: int, missing: int = 0) -> str:
        if eligible_count < MIN_ELIGIBLE_CELLS:
            return f"INCONCLUSIVE ({eligible_count} v4 eligible cells < {MIN_ELIGIBLE_CELLS})"
        return safety_verdict(n, violations, missing)

    lines += [
        "",
        "## Partial-cell scoring (Phase 8 preregistration Amendment 7)",
        "",
        f"Partial cells with valid measured RAM: {partial_result['n']}; lower-bound violations "
        f"(displayed low > actual): {len(partial_result['lower_violations'])}; missing covered lower bounds: "
        f"{len(partial_result['missing_lower_bounds'])} -> "
        f"{safety_decision(partial_result['n'], len(partial_result['lower_violations']) + len(partial_result['missing_lower_bounds']))}.",
        f"Partial risk violations (OK while actual > simulated headroom): "
        f"{len(partial_result['risk_violations'])} -> "
        f"{safety_decision(partial_result['n'], len(partial_result['risk_violations']), len(partial_result['missing_classes']))}.",
        f"Wholly uncovered cells with valid measured RAM: {uncovered_result['n']}; risk violations "
        f"(OK while actual > simulated headroom): {len(uncovered_result['risk_violations'])} -> "
        f"{safety_decision(uncovered_result['n'], len(uncovered_result['risk_violations']), len(uncovered_result['missing_classes']))}.",
    ]
    if partial_result["missing_classes"] or uncovered_result["missing_classes"]:
        lines.append(
            "Risk-safety scoring is INCONCLUSIVE where simulated headroom classes are missing: "
            f"partial {partial_result['missing_classes']}; wholly uncovered {uncovered_result['missing_classes']}."
        )
    # risk
    risk = df[df["risk"].map(lambda x: isinstance(x, dict))]
    lines += [
        "",
        "## Risk engine",
        "",
        "Classes as the engine saw them (live free RAM), cells with a detected operation:",
        "",
    ]
    if risk.empty:
        lines += ["No risk records were recorded."]
    else:
        lines += _table(
            [
                {"class": k, "cells": v}
                for k, v in Counter(risk["risk"].map(lambda x: x["class"])).items()
            ]
        )
        unk = risk[risk["risk"].map(lambda x: x["class"] == "UNKNOWN")]
        lines += ["", "UNKNOWN reasons:", ""]
        lines += _table(
            [
                {"reason": k, "cells": v}
                for k, v in Counter(unk["risk"].map(lambda x: x["reason_kind"])).items()
            ]
        )
    t, res = risk_eval(vr)
    if res:
        lines += [
            "",
            "Simulated limits on valid RAM points:",
            "",
            *_table(res["per_limit"].to_dict("records")),
            "",
        ]
        lines.append(
            f"* claim limits (>= {MIN_POSITIVES} positives): {res['claim_limits'] or 'none: too few positives, no claim'}"
        )
        if res["claim_limits"]:
            lines.append(
                f"* R1 recall: {_fmt(res['R1'])} -> "
                f"{phase_verdict(len(vr), res['R1'] >= RECALL_TARGET, eligible_count)}"
            )
            r2 = res["R2_pooled"] <= FAR_TARGET and not res["R2_ops_over"]
            lines.append(
                f"* R2 false alarms pooled {_fmt(res['R2_pooled'])}, operations over 50%: "
                f"{res['R2_ops_over'] or 'none'} -> "
                f"{phase_verdict(len(vr), r2, eligible_count)}"
            )
            r3 = (
                f"INCONCLUSIVE ({int(t['high'].sum())} HIGH_RISK points < {MIN_POSITIVES})"
                if int(t["high"].sum()) < MIN_POSITIVES
                else phase_verdict(len(vr), res["R3"] >= HIGH_PRECISION_TARGET, eligible_count)
            )
            lines.append(f"* R3 HIGH_RISK precision: {_fmt(res['R3'])} -> {r3}")
        lines += [
            "",
            "Missed overruns (positive, not alerted):",
            "",
            *_table(res["missed"].to_dict("records")),
        ]
    else:
        lines += [
            "",
            "No valid RAM point with an estimate: the risk engine cannot be evaluated (INCONCLUSIVE).",
        ]
    # suggestions
    est = df[has]
    sg = est["suggestions"].map(lambda x: x if isinstance(x, list) else [])
    lines += ["", "## Suggestions (never executed)", "",
              f"Cells with an estimate: {len(est)}; with at least one suggestion shown: {int((sg.map(len) > 0).sum())}.", ""]  # fmt: skip
    lines += _table([{"rule": k[0], "semantics": k[1], "shown": v}
                     for k, v in Counter((s["rule"], s["semantics"]) for x in sg for s in x).items()])  # fmt: skip
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.realworld.evaluate_real")
    ap.add_argument("v3_results", type=Path)
    ap.add_argument("v4_results", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    v3, v4 = load_paired(args.v3_results, args.v4_results)
    comparison = paired_coverage(v3, v4)
    eligible_v3 = int(
        sum(_has_operations(row) and row.get("status") == "ok" for row in v3.to_dict("records"))
    )
    eligible_v4 = int(
        sum(_has_operations(row) and row.get("status") == "ok" for row in v4.to_dict("records"))
    )
    if eligible_v4 < MIN_ELIGIBLE_CELLS:
        comparison["verdict"] = (
            f"INCONCLUSIVE ({eligible_v4} v4 eligible cells < {MIN_ELIGIBLE_CELLS})"
        )
    widths = width_metrics(v3, v4)
    if eligible_v4 < MIN_ELIGIBLE_CELLS:
        widths["a_verdict"] = widths["b_verdict"] = (
            f"INCONCLUSIVE ({eligible_v4} v4 eligible cells < {MIN_ELIGIBLE_CELLS})"
        )
    coverage_lines = [
        "# Phase 8b paired real-notebook evaluation",
        "",
        f"Model versions: `{V3_MODEL_VERSION}` and `{V4_MODEL_VERSION}`.",
        f"Eligible run-time cells (operation detected, status OK): v3 {eligible_v3}; "
        f"v4 {eligible_v4}; the v4 minimum is {MIN_ELIGIBLE_CELLS}.",
        "",
        "## Paired run-time coverage",
        "",
        f"Paired operation-bearing cells: {comparison['n']}. "
        "The denominator contains a cell only when both versions recorded the same "
        "(notebook, index, hash) and at least one version detected an operation. "
        "A version with no detected operation, no estimate for any detected operation, "
        "or a hard-deadline firing counts as not covered.",
        "",
        f"v3: {comparison['v3_covered']}/{comparison['n']} "
        f"({comparison['v3_share']:.1%}); v4: {comparison['v4_covered']}/{comparison['n']} "
        f"({comparison['v4_share']:.1%}); v4 - v3: {comparison['delta']:.1%} "
        f"({comparison['delta'] * 100:.1f} percentage points) -> {comparison['verdict']}.",
        "",
        f"Unpaired records, excluded from the paired denominator: v3-only "
        f"{comparison['v3_only_cells']} cells ({comparison['v3_only_operation_cells']} "
        f"with an operation); v4-only {comparison['v4_only_cells']} cells "
        f"({comparison['v4_only_operation_cells']} with an operation).",
        "They are reported, not treated as covered; a cell without an operation on both "
        "sides is also excluded.",
        "",
        "## Range width W",
        "",
        f"W(a), common fully covered cells: n={widths['a_n']}, median ratio "
        f"{_fmt(widths['a_median'], 'width')} -> {widths['a_verdict']}.",
        f"W(b), fully covered v4 cells without a v3 estimate: n={widths['b_n']}, "
        f"median {_fmt(widths['b_median'], 'width')}, p90 {_fmt(widths['b_p90'], 'width')} "
        f"-> {widths['b_verdict']}.",
        "",
        report(v4, eligible_count=eligible_v4),
    ]
    text = "\n".join(coverage_lines)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
