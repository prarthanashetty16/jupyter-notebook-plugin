"""Phase 8 real-notebook evaluation of harness records (``cells.jsonl``).

``docs/benchmarks/phase8a-preregistration.md``: valid points, RAM above_high <= 3% and time
within-one >= 95% with a 30-point minimum (else INCONCLUSIVE), the risk engine at three simulated
limits (free RAM at the cell's start, 2048 MiB and 1024 MiB process limits) reported like Phase 5,
and suggestion counts. Reads only the harness records (hashes, operation names, shapes, numbers).

    python -m benchmarks.realworld.evaluate_real benchmarks/results/realworld/<nb> [...] --out docs/benchmarks/phase8a/report_tables.md
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

from nexus.models.base import Estimate
from nexus.risk import RiskClass, classify
from nexus.timebuckets import bucket_index

MIB = 2**20
MIN_POINTS = 30
RAM_ABOVE_HIGH_MAX = 0.03
TIME_WITHIN_ONE_MIN = 0.95
LIMITS_MIB = (2048, 1024)
RECALL_TARGET, FAR_TARGET, FAR_PER_OP_TARGET, HIGH_PRECISION_TARGET = 0.98, 0.30, 0.50, 0.75
MIN_POSITIVES = 20
PARTIAL_HEADROOMS_MIB = (64, 128, 256, 512, 1024, 2048, 4096, 8192)


def load(dirs: list[Path]) -> pd.DataFrame:
    rows = []
    for d in dirs:
        for line in (d / "cells.jsonl").open(encoding="utf-8"):
            rows.append(json.loads(line))
    return pd.DataFrame(rows)


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
    rel = (e - a).abs() / a
    return {
        "n": len(d), "bias": float((e / a).median()), "err_med": float(rel.median()),
        "err_p90": float(rel.quantile(0.9)), "coverage": float(((lo <= a) & (a <= hi)).mean()),
        "above_high": float(above.mean()), "above_high_n": int(above.sum()),
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
        "same": float((eb == ab).mean()), "err_med": float(rel.median()),
        "err_p90": float(rel.quantile(0.9)), "bias": float((e / a).median()),
        "coverage": float(((lo <= a) & (a <= hi)).mean()),
    }  # fmt: skip


def verdict(n: int, ok: bool) -> str:
    if n < MIN_POINTS:
        return f"INCONCLUSIVE ({n} valid points < {MIN_POINTS})"
    return "MET" if ok else "FAILED"


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


def report(df: pd.DataFrame) -> str:  # noqa: C901
    df = df.copy()
    if "uncovered" not in df:
        df["uncovered"] = 0
    else:
        df["uncovered"] = pd.to_numeric(df["uncovered"], errors="coerce").fillna(0)
    df["group"] = df.apply(group_of, axis=1)
    lines = ["# Phase 8 real-notebook results (evaluation only, nothing tuned)", ""]
    lines += [
        "## Cells by group",
        "",
        *_table([{"group": g, "cells": n} for g, n in df["group"].value_counts().items()]),
        "",
    ]
    has = df["cell"].map(lambda c: isinstance(c, dict))
    vr = df[has & (df["ram_class"] == "valid")]
    vt = df[has & (df["time_class"] == "valid") & (df["status"] == "ok")]
    vr_full = vr[vr["uncovered"].fillna(1) == 0]
    lines += [
        "## Accuracy on valid points (primary: Pipeline(tier=2) with the controller)",
        "",
        "RAM above-high is scored only on fully covered cells; partial cells are scored separately below. "
        "Time uses all valid time points.",
        "",
    ]
    rm, tm = ram_metrics(vr_full, "cell"), time_metrics(vt, "cell")
    lines += _table([{"metric": "RAM", **rm}]) + [""] + _table([{"metric": "time", **tm}]) + [""]
    lines.append(
        f"* **RAM verdict (above_high <= 3%):** {verdict(rm.get('n', 0), rm.get('above_high', 1) <= RAM_ABOVE_HIGH_MAX)}"
    )
    lines.append(
        f"* **Time verdict (within-one >= 95%):** {verdict(tm.get('n', 0), tm.get('within_one', 0) >= TIME_WITHIN_ONE_MIN)}"
    )
    vr0 = vr[vr["cell_tier0"].map(lambda c: isinstance(c, dict))]
    vt0 = vt[vt["cell_tier0"].map(lambda c: isinstance(c, dict))]
    lines += ["", "Secondary (Tier 0, what `%load_ext nexus` uses today; no verdict):", ""]
    lines += _table([{"metric": "RAM tier 0", **ram_metrics(vr0, "cell_tier0")},
                     {"metric": "time tier 0", **time_metrics(vt0, "cell_tier0")}])  # fmt: skip
    full = vr_full
    lines += ["", "Fully covered subset (every detected operation has an estimate):", ""]
    lines += _table([{"metric": "RAM", **ram_metrics(full, "cell")},
                     {"metric": "time", **time_metrics(vt[vt["uncovered"].fillna(1) == 0], "cell")}])  # fmt: skip
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
    lines += [
        "",
        "## Partial-cell scoring (Phase 8 preregistration Amendment 7)",
        "",
        f"Partial cells with valid measured RAM: {partial_result['n']}; lower-bound violations "
        f"(displayed low > actual): {len(partial_result['lower_violations'])}; missing covered lower bounds: "
        f"{len(partial_result['missing_lower_bounds'])} -> "
        f"{safety_verdict(partial_result['n'], len(partial_result['lower_violations']) + len(partial_result['missing_lower_bounds']))}.",
        f"Partial risk violations (OK while actual > simulated headroom): "
        f"{len(partial_result['risk_violations'])} -> "
        f"{safety_verdict(partial_result['n'], len(partial_result['risk_violations']), len(partial_result['missing_classes']))}.",
        f"Wholly uncovered cells with valid measured RAM: {uncovered_result['n']}; risk violations "
        f"(OK while actual > simulated headroom): {len(uncovered_result['risk_violations'])} -> "
        f"{safety_verdict(uncovered_result['n'], len(uncovered_result['risk_violations']), len(uncovered_result['missing_classes']))}.",
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
                f"* R1 recall: {_fmt(res['R1'])} -> {'MET' if res['R1'] >= RECALL_TARGET else 'FAILED'}"
            )
            r2 = res["R2_pooled"] <= FAR_TARGET and not res["R2_ops_over"]
            lines.append(
                f"* R2 false alarms pooled {_fmt(res['R2_pooled'])}, operations over 50%: {res['R2_ops_over'] or 'none'} -> {'MET' if r2 else 'FAILED'}"
            )
            lines.append(f"* R3 HIGH_RISK precision: {_fmt(res['R3'])}")
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
    ap.add_argument("dirs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    text = report(load(args.dirs))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
