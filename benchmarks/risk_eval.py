"""Risk-engine evaluation on DEVELOPMENT data (Phase 5, pre-registration Part A6).

No new measurements: stored Tier 1 predictions (range policy B) and stored actuals are replayed
through ``nexus.risk.classify`` with simulated memory limits. A point is *positive* at limit L by the
exact definition of ``benchmarks.evaluate.oom_table`` (input bytes + measured peak > L, or killed at
a cap >= L); the headroom given to the risk engine is ``L - inspected_bytes`` (the baseline of that
table). ALERT = WARN or HIGH_RISK; UNKNOWN and OK are not alerts, so a positive point classified
either way is a miss.

    python -m benchmarks.risk_eval benchmarks/results/tier1-v3 --out docs/benchmarks/phase5-risk-dev
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import OOM_LIMITS_MB, load_joined, md_table
from nexus.models.base import Estimate
from nexus.risk import RiskClass, classify

MIB = 2**20
PCT = ("recall", "recall_wilson_low", "false_alarm", "precision", "high_precision")
MIN_POSITIVES = 20
RECALL_TARGET = 0.98
FAR_TARGET = 0.30
FAR_PER_OP_TARGET = 0.50
HIGH_PRECISION_TARGET = 0.75


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return math.nan
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - margin) / d


def _estimate(row: pd.Series) -> Estimate | None:
    if not bool(row["has_estimate"]):
        return None
    try:
        t = [
            float(row[c]) if pd.notna(row[c]) else 0.0
            for c in ("time_low", "time_expected", "time_high")
        ]
        return Estimate(
            ram_low=int(row["ram_low"]), ram_expected=int(row["ram_expected"]), ram_high=int(row["ram_high"]),
            time_low=t[0], time_expected=t[1], time_high=t[2],
            confidence=float(row["confidence"]), tier=int(row["tier"]),
        )  # fmt: skip
    except (ValueError, TypeError):
        return None


def valid_points(df: pd.DataFrame, tier: int = 1) -> pd.DataFrame:
    d = df[(df["tier"] == tier) & (df["pred_status"] == "ok")]
    killed = d["status"] == "memory_limit"
    return d[((d["status"] == "ok") & (d["ram_class"] != "excluded")) | killed]


def classify_all(
    df: pd.DataFrame, limits_mb: tuple[int, ...] = OOM_LIMITS_MB, tier: int = 1
) -> pd.DataFrame:
    """One row per (valid point, limit): positive flag and the risk class."""
    d = valid_points(df, tier)
    est = {
        pid: _estimate(r)
        for pid, r in zip(d["point_id"], (row for _, row in d.iterrows()), strict=True)
    }
    killed_all = d["status"] == "memory_limit"
    rows = []
    for limit_mb in limits_mb:
        limit = limit_mb * MIB
        killed = d["status"] == "memory_limit"
        keep = (~killed) | (d["cap_bytes"] >= limit)
        v = d[keep]
        ram = v["ram_value"].fillna(v["ram_bound_bytes"]).fillna(0)
        footprint = v["input_bytes"].fillna(v["inspected_bytes"]) + ram
        positive = (v["status"] == "memory_limit") | (footprint > limit)
        for (_, r), pos, fp in zip(v.iterrows(), positive, footprint, strict=True):
            e = est[r["point_id"]]
            head = int(limit - (r["inspected_bytes"] if pd.notna(r["inspected_bytes"]) else 0))
            rep = classify([e] if e else [], headroom=head)
            rows.append(
                {
                    "limit_mb": limit_mb, "point_id": r["point_id"], "op": r["op"], "size": r["size"],
                    "positive": bool(pos), "risk": rep.risk.value, "alert": rep.risk.is_alert,
                    "footprint_mb": fp / MIB, "predicted_expected_mb": (e.ram_expected / MIB) if e else None,
                    "predicted_high_mb": (e.ram_high / MIB) if e else None, "headroom_mb": head / MIB,
                }
            )  # fmt: skip
    del killed_all
    return pd.DataFrame(rows)


def _rates(g: pd.DataFrame) -> dict[str, float | int]:
    pos = g[g["positive"]]
    neg = g[~g["positive"]]
    tp, fn = int(pos["alert"].sum()), int((~pos["alert"]).sum())
    fp, tn = int(neg["alert"].sum()), int((~neg["alert"]).sum())
    high = g[g["risk"] == RiskClass.HIGH_RISK.value]
    return {
        "n": len(g), "positives": len(pos), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "recall": tp / len(pos) if len(pos) else math.nan,
        "recall_wilson_low": wilson_lower(tp, len(pos)),
        "false_alarm": fp / len(neg) if len(neg) else math.nan,
        "precision": tp / (tp + fp) if tp + fp else math.nan,
        "high_n": len(high), "high_precision": float(high["positive"].mean()) if len(high) else math.nan,
        "unknown": int((g["risk"] == "UNKNOWN").sum()), "ok": int((g["risk"] == "OK").sum()),
    }  # fmt: skip


def evaluate(df: pd.DataFrame) -> dict[str, object]:
    c = classify_all(df)
    per_limit = pd.DataFrame([{"limit_mb": lim, **_rates(g)} for lim, g in c.groupby("limit_mb")])
    claim = per_limit[per_limit["positives"] >= MIN_POSITIVES]["limit_mb"].tolist()
    cc = c[c["limit_mb"].isin(claim)]
    pooled_all = _rates(c)
    pooled_claim = _rates(cc) if len(cc) else {}
    per_op = (
        pd.DataFrame([{"op": op, **_rates(g)} for op, g in cc.groupby("op")])
        if len(cc)
        else pd.DataFrame()
    )
    per_size = (
        pd.DataFrame([{"size": s, **_rates(g)} for s, g in cc.groupby("size")])
        if len(cc)
        else pd.DataFrame()
    )
    hl = per_limit[per_limit["high_n"] >= MIN_POSITIVES]["limit_mb"].tolist()
    hh = c[(c["limit_mb"].isin(hl)) & (c["risk"] == "HIGH_RISK")]
    high_precision = float(hh["positive"].mean()) if len(hh) else math.nan
    missed = c[c["positive"] & ~c["alert"]].sort_values(["limit_mb", "point_id"])
    verdict = {
        "R1a": [(int(r.limit_mb), r.recall) for r in per_limit.itertuples() if r.positives >= MIN_POSITIVES and r.recall < RECALL_TARGET],
        "R1b": pooled_all["recall"],
        "R2_pooled": pooled_claim.get("false_alarm", math.nan),
        "R2_ops": [(r.op, r.false_alarm) for r in per_op.itertuples() if (r.tn + r.fp) >= MIN_POSITIVES and r.false_alarm > FAR_PER_OP_TARGET] if len(per_op) else [],
        "R3": high_precision,
    }  # fmt: skip
    return {"classified": c, "per_limit": per_limit, "claim_limits": claim, "pooled_all": pooled_all,
            "pooled_claim": pooled_claim, "per_op": per_op, "per_size": per_size, "missed": missed,
            "high_limits": hl, "verdict": verdict}  # fmt: skip


def _pf(x: object) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1%}"


def report(res: dict[str, object], source: str) -> str:
    v = res["verdict"]
    assert isinstance(v, dict)
    pa, pc = res["pooled_all"], res["pooled_claim"]
    assert isinstance(pa, dict) and isinstance(pc, dict)
    r1 = (not v["R1a"]) and pa["recall"] >= RECALL_TARGET
    r2 = pc and pc["false_alarm"] <= FAR_TARGET and not v["R2_ops"]
    r3 = not math.isnan(v["R3"]) and v["R3"] >= HIGH_PRECISION_TARGET
    lines = [
        "# Risk engine on DEVELOPMENT data (Phase 5)\n",
        f"Source: `{source}` (stored Tier 1 predictions under range policy B and stored actuals; no new measurement). "
        "**Dev data, not validation.** Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part A6. "
        "Alert = WARN or HIGH_RISK; UNKNOWN and OK are misses on positive points.\n",
        "## Verdicts\n",
        f"* **R1 recall >= {RECALL_TARGET:.0%}:** {'PASS' if r1 else 'FAIL'}. Pooled over all (point, limit) pairs "
        f"{_pf(pa['recall'])} ({pa['tp']}/{pa['positives']}, Wilson 95% lower {_pf(pa['recall_wilson_low'])}). "
        f"Limits with >= {MIN_POSITIVES} positives: {res['claim_limits']}; below target: {v['R1a'] or 'none'}.",
        f"* **R2 false alarms (pooled <= {FAR_TARGET:.0%}, no operation > {FAR_PER_OP_TARGET:.0%}):** {'PASS' if r2 else 'FAIL'}. "
        f"Pooled over the claim limits {_pf(v['R2_pooled'])}; operations above the per-op bar: {v['R2_ops'] or 'none'}.",
        f"* **R3 HIGH_RISK precision >= {HIGH_PRECISION_TARGET:.0%}:** "
        f"{('PASS' if r3 else 'FAIL') if not math.isnan(v['R3']) else 'NOT EVALUATED (fewer than 20 HIGH_RISK points at any limit)'}. "
        f"Pooled over limits {res['high_limits']}: {_pf(v['R3'])}.",
        f"* **R4 UNKNOWN:** {pa['unknown']} of {pa['n']} (point, limit) pairs are UNKNOWN, {pa['ok']} are OK.\n",
        "## Per limit\n",
    ]
    pl = res["per_limit"]
    assert isinstance(pl, pd.DataFrame)
    lines.append(md_table(pl.astype(object), PCT))
    for title, key in (
        ("Per operation (claim limits only)", "per_op"),
        ("Per size (claim limits only)", "per_size"),
    ):
        t = res[key]
        assert isinstance(t, pd.DataFrame)
        lines += [f"\n## {title}\n", md_table(t.astype(object), PCT) if len(t) else "none"]
    m = res["missed"]
    assert isinstance(m, pd.DataFrame)
    lines += [f"\n## Missed crashes (positive, not alerted): {len(m)}\n"]
    lines.append(
        md_table(
            m[
                [
                    "limit_mb",
                    "point_id",
                    "op",
                    "risk",
                    "footprint_mb",
                    "predicted_expected_mb",
                    "predicted_high_mb",
                    "headroom_mb",
                ]
            ].round(1)
        )
        if len(m)
        else "none"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    res = evaluate(load_joined(args.results))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "risk_dev.md").write_text(report(res, str(args.results)), encoding="utf-8")
    for key in ("classified", "per_limit", "per_op", "per_size", "missed"):
        res[key].to_csv(args.out / f"{key}.csv", index=False)  # type: ignore[union-attr]
    print((args.out / "risk_dev.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
