"""Tier 0 vs Tier 1 comparison on one measured group (dev, or val-v5 through ``evaluate --val``).

Takes the joined frame that ``benchmarks.evaluate`` builds (one row per grid point and tier) and
reports, per operation and metric (RAM, time):

* accuracy of each tier: points, bias (median expected / actual), median and p90 relative error,
  coverage of [low, high], range width, and **under-prediction and over-prediction separately**
  (share of points where ``expected`` is below / above the actual, the median fold of each, and the
  share of actuals beyond ``high`` / ``low``: the dangerous and the harmless direction);
* how often Tier 1 was used, how often it narrowed the range, and by how much;
* analysis overhead (warm) of each tier against the 250 ms budget;
* the cases where Tier 1 made things worse (lost coverage, or a clearly larger error).

This module reads no protected data by itself: callers pass the frame they are allowed to read.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.evaluate import md_table

WORSE_FACTOR = 1.2  # Tier 1 is "clearly worse" when its |log fold| exceeds Tier 0's by this factor


def _tier1_used(features: Any) -> bool:
    try:
        return bool(json.loads(features).get("tier1", {}).get("used"))
    except (TypeError, ValueError):
        return False


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a prediction and a valid measurement, one row per (point, tier)."""
    d = df[
        df["status"].isin(("ok", "memory_limit")) & df["tier"].notna() & df["has_estimate"]
    ].copy()
    d["tier"] = d["tier"].astype(int)
    d["t1_used"] = d["features"].map(_tier1_used) if "features" in d else False
    return d


def _fold(expected: pd.Series, actual: pd.Series) -> pd.Series:
    return expected / actual


def _metrics(g: pd.DataFrame, metric: str) -> dict[str, Any]:
    ex, lo, hi, val = (
        g[f"{metric}_expected"], g[f"{metric}_low"], g[f"{metric}_high"], g[f"{metric}_value"],
    )  # fmt: skip
    ok = g[g[f"{metric}_class"] == "valid"]
    out: dict[str, Any] = {"points": len(g), "valid": len(ok)}
    if ok.empty:
        return out
    a, e, l_, h = (
        ok[f"{metric}_value"], ok[f"{metric}_expected"], ok[f"{metric}_low"], ok[f"{metric}_high"],
    )  # fmt: skip
    fold = _fold(e, a)
    under, over = fold < 1, fold > 1
    out.update(
        bias=float(fold.median()),
        err_med=float(((e - a).abs() / a).median()),
        err_p90=float(((e - a).abs() / a).quantile(0.9)),
        coverage=float(((l_ <= a) & (a <= h)).mean()),
        width=float(((h - l_) / e.where(e > 0)).mean()),
        under_share=float(under.mean()),
        under_fold=float((1 / fold[under]).median()) if under.any() else math.nan,
        over_share=float(over.mean()),
        over_fold=float(fold[over].median()) if over.any() else math.nan,
        above_high=float((a > h).mean()),  # under-prediction beyond the range (dangerous)
        below_low=float((a < l_).mean()),  # over-prediction beyond the range
    )
    del ex, lo, hi, val
    return out


def accuracy_by_tier(d: pd.DataFrame, metric: str) -> pd.DataFrame:
    rows = []
    for (op, tier), g in d.groupby(["op", "tier"]):
        rows.append({"op": op, "tier": tier, **_metrics(g, metric)})
    pooled = d.assign(op="ALL")
    for (op, tier), g in pooled.groupby(["op", "tier"]):
        rows.append({"op": op, "tier": tier, **_metrics(g, metric)})
    return pd.DataFrame(rows)


def paired(d: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Tier 0 and Tier 1 predictions of the same point side by side (valid measurements only)."""
    keep = ["point_id", "op", "case", "size", f"{metric}_class", f"{metric}_value"]
    t0 = d[d["tier"] == 0]
    t1 = d[d["tier"] == 1]
    cols = [f"{metric}_low", f"{metric}_expected", f"{metric}_high"]
    m = t0[[*keep, *cols]].merge(
        t1[["point_id", "t1_used", *cols]], on="point_id", suffixes=("_t0", "_t1")
    )
    return m[m[f"{metric}_class"] == "valid"].copy()


def narrowing(p: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Per operation: Tier 1 usage, share of points whose range narrowed, median width change."""
    w0 = (p[f"{metric}_high_t0"] - p[f"{metric}_low_t0"]) / p[f"{metric}_expected_t0"]
    w1 = (p[f"{metric}_high_t1"] - p[f"{metric}_low_t1"]) / p[f"{metric}_expected_t1"]
    p = p.assign(w0=w0, w1=w1, narrowed=(w1 < w0 * 0.999), widened=(w1 > w0 * 1.001))
    rows = []
    for op, g in [*p.groupby("op"), ("ALL", p)]:
        rows.append(
            {
                "op": op,
                "points": len(g),
                "tier1_used": float(g["t1_used"].mean()),
                "narrowed": float(g["narrowed"].mean()),
                "widened": float(g["widened"].mean()),
                "width_t0": float(g["w0"].mean()),
                "width_t1": float(g["w1"].mean()),
            }
        )
    return pd.DataFrame(rows)


def worse_cases(p: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Points where Tier 1 lost coverage or has a clearly larger error than Tier 0."""
    a = p[f"{metric}_value"]
    f0, f1 = p[f"{metric}_expected_t0"] / a, p[f"{metric}_expected_t1"] / a
    cov0 = (p[f"{metric}_low_t0"] <= a) & (a <= p[f"{metric}_high_t0"])
    cov1 = (p[f"{metric}_low_t1"] <= a) & (a <= p[f"{metric}_high_t1"])
    err_worse = np.abs(np.log(f1)) > WORSE_FACTOR * np.abs(np.log(f0)) + 0.05
    sel = (cov0 & ~cov1) | err_worse
    out = p.loc[sel, ["op", "case", "size", "t1_used"]].copy()
    out["actual"] = a[sel]
    out["fold_t0"] = f0[sel]
    out["fold_t1"] = f1[sel]
    out["lost_coverage"] = (cov0 & ~cov1)[sel]
    out["dangerous"] = a[sel] > p.loc[sel, f"{metric}_high_t1"]
    return out.sort_values(["op", "case", "size"])


def overhead(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (op, tier), g in [*d.groupby(["op", "tier"]), *d.assign(op="ALL").groupby(["op", "tier"])]:
        warm = g["overhead_warm_s"].dropna()
        cold = g["overhead_cold_s"].dropna()
        if warm.empty:
            continue
        rows.append(
            {
                "op": op,
                "tier": tier,
                "warm_med_ms": float(warm.median() * 1e3),
                "warm_p90_ms": float(warm.quantile(0.9) * 1e3),
                "warm_max_ms": float(warm.max() * 1e3),
                "cold_med_ms": float(cold.median() * 1e3),
                "over_250ms": float((warm > 0.25).mean()),
            }
        )
    return pd.DataFrame(rows)


PCT = (
    "coverage", "above_high", "below_low", "under_share", "over_share", "err_med", "err_p90",
    "narrowed", "widened", "tier1_used", "over_250ms",
)  # fmt: skip


def markdown(df: pd.DataFrame, title: str, group: str) -> str:
    """Report section for one measured group (``group`` is a label such as 'dev' or 'val-v5')."""
    d = prepare(df)
    lines = [f"# {title}", ""]
    if d.empty or 1 not in set(d["tier"]):
        return "\n".join([*lines, "no Tier 1 predictions to compare.", ""])
    lines.append(
        f"Group: **{group}**. Tier 0 = first-tier models of Phase 4a; Tier 1 = the same models with "
        "data statistics where the sample is large enough, else Tier 0 (counted as not used). "
        "bias = median expected/actual (>1 over-predicts). `above_high` = actuals beyond the "
        "range's upper end (**under-prediction**, dangerous); `below_low` = beyond the lower end "
        "(over-prediction). `under_fold`/`over_fold` = median factor by which `expected` is too "
        "low / too high on the points where it is.\n"
    )
    for metric, name in (("ram", "RAM"), ("time", "Time")):
        acc = accuracy_by_tier(d, metric)
        cols = [
            "op", "tier", "valid", "bias", "err_med", "err_p90", "coverage", "width",
            "under_share", "under_fold", "over_share", "over_fold", "above_high", "below_low",
        ]  # fmt: skip
        lines += [f"## {name}: accuracy by tier", "", md_table(acc[cols], pct=PCT), ""]
        p = paired(d, metric)
        if not p.empty:
            lines += [
                f"## {name}: how often Tier 1 narrowed the range",
                "",
                md_table(narrowing(p, metric), pct=PCT),
                "",
            ]
            w = worse_cases(p, metric)
            lines += [f"## {name}: cases where Tier 1 did worse ({len(w)} points)", ""]
            lines += [md_table(w, pct=()) if len(w) else "none", ""]
    lines += ["## Analysis overhead (warm, per cell)", "", md_table(overhead(d), pct=PCT), ""]
    return "\n".join(lines)


def write(df: pd.DataFrame, out_dir: Path, title: str, group: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    d = prepare(df)
    for metric in ("ram", "time"):
        accuracy_by_tier(d, metric).to_csv(out_dir / f"accuracy_{metric}.csv", index=False)
        p = paired(d, metric)
        if not p.empty:
            narrowing(p, metric).to_csv(out_dir / f"narrowing_{metric}.csv", index=False)
            worse_cases(p, metric).to_csv(out_dir / f"worse_{metric}.csv", index=False)
            p.to_csv(out_dir / f"points_{metric}.csv", index=False)
    overhead(d).to_csv(out_dir / "overhead.csv", index=False)
    path = out_dir / "tier1_vs_tier0.md"
    path.write_text(markdown(df, title, group), encoding="utf-8")
    return path


def main() -> None:
    import sys

    from benchmarks.evaluate import load_joined

    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: python -m benchmarks.tier1_compare <results_dir> <out_dir>  (dev only)"
        )
    df = load_joined(Path(sys.argv[1]))
    print(write(df, Path(sys.argv[2]), "Tier 0 vs Tier 1 (dev)", "dev"))


if __name__ == "__main__":
    main()
