"""Authoritative Phase 8 verdict for the v4 val-v5 run."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from benchmarks.frozen import FROZEN_TAG

RAM_BAR = 0.03
TIME_BAR = 0.95
MIN_POINTS = 30
MIN_CONFIGS = 10
CONFIDENCE = 0.95
TIER = 1
WIDTH_A_BAR = 1.30
WIDTH_B_MEDIAN_BAR = 2.0
WIDTH_B_P90_BAR = 4.0


def _binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson_upper(k: int, n: int, confidence: float = CONFIDENCE) -> float:
    """One-sided exact upper confidence bound for an event rate."""
    if n == 0:
        return math.nan
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    alpha = 1.0 - confidence
    for _ in range(100):
        mid = (lo + hi) / 2
        if _binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    """Two-sided 95% Wilson lower bound for a success rate."""
    if n == 0:
        return math.nan
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def _valid(df: pd.DataFrame, tier: int, metric: str) -> pd.DataFrame:
    return df[
        (df["tier"] == tier) & df["has_estimate"].astype(bool) & (df[f"{metric}_class"] == "valid")
    ]


def ram_points(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    valid = _valid(df, tier, "ram")
    above = valid["ram_value"].astype(float) > valid["ram_high"].astype(float)
    k, n = int(above.sum()), len(valid)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_POINTS else ("MET" if rate <= RAM_BAR else "FAILED")
    return {
        "k": k,
        "n": n,
        "rate": rate,
        "upper": clopper_pearson_upper(k, n),
        "verdict": verdict,
    }


def ram_configurations(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    valid = _valid(df, tier, "ram")
    above = (
        (valid["ram_value"].astype(float) > valid["ram_high"].astype(float))
        .groupby(valid["case"])
        .any()
    )
    k, n = int(above.sum()), len(above)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_CONFIGS else ("MET" if rate <= RAM_BAR else "FAILED")
    return {
        "k": k,
        "n": n,
        "rate": rate,
        "upper": clopper_pearson_upper(k, n),
        "verdict": verdict,
        "configs_above": sorted(above[above].index),
    }


def time_within_one(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    from nexus.timebuckets import bucket_index

    valid = _valid(df, tier, "time")
    within = (
        valid["time_expected"].map(bucket_index) - valid["time_value"].map(bucket_index)
    ).abs() <= 1
    k, n = int(within.sum()), len(valid)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_POINTS else ("MET" if rate >= TIME_BAR else "FAILED")
    return {"k": k, "n": n, "rate": rate, "lower": wilson_lower(k, n), "verdict": verdict}


def risk(df: pd.DataFrame) -> dict[str, str]:
    from benchmarks.phase7_verdict import risk as phase7_risk

    return phase7_risk(df)


def width_criteria(
    df: pd.DataFrame, v3_predictions: pd.DataFrame | None
) -> dict[str, dict[str, Any]]:
    inconclusive = {
        "n": 0,
        "verdict": "INCONCLUSIVE",
        "reason": "v3 prediction-only baseline is unavailable",
    }
    if v3_predictions is None:
        return {"W(a)": dict(inconclusive), "W(b)": dict(inconclusive)}
    required = {"point_id", "v3_has_estimate", "v3_ram_expected", "v3_ram_high"}
    if not required <= set(v3_predictions.columns):
        missing = sorted(required - set(v3_predictions.columns))
        value = {
            "n": 0,
            "verdict": "INCONCLUSIVE",
            "reason": f"baseline columns missing: {missing}",
        }
        return {"W(a)": dict(value), "W(b)": dict(value)}

    valid = _valid(df, TIER, "ram").copy()
    baseline = v3_predictions[list(required)].drop_duplicates("point_id", keep="last")
    joined = valid.merge(baseline, on="point_id", how="left")
    present = joined["v3_has_estimate"].notna()
    if not present.all():
        reason = f"v3 predictions missing for {int((~present).sum())} valid v4 points"
        return {
            "W(a)": {"n": 0, "verdict": "INCONCLUSIVE", "reason": reason},
            "W(b)": {"n": 0, "verdict": "INCONCLUSIVE", "reason": reason},
        }
    joined["v3_has_estimate"] = (
        joined["v3_has_estimate"].astype(str).str.lower().isin(("true", "1"))
    )
    joined = joined[joined["ram_expected"].astype(float) > 0].copy()
    shared = joined[
        joined["v3_has_estimate"]
        & pd.to_numeric(joined["v3_ram_expected"], errors="coerce").gt(0)
        & pd.to_numeric(joined["v3_ram_high"], errors="coerce").notna()
    ]
    ratio = (shared["ram_high"].astype(float) / shared["ram_expected"].astype(float)) / (
        pd.to_numeric(shared["v3_ram_high"], errors="coerce")
        / pd.to_numeric(shared["v3_ram_expected"], errors="coerce")
    )
    ratio = ratio.replace([math.inf, -math.inf], math.nan).dropna()
    w_a = float(ratio.median()) if len(ratio) else math.nan
    w_a_verdict = (
        "INCONCLUSIVE" if len(ratio) < MIN_POINTS else ("MET" if w_a <= WIDTH_A_BAR else "FAILED")
    )

    new = joined[~joined["v3_has_estimate"]]
    widths = new["ram_high"].astype(float) / new["ram_expected"].astype(float)
    median = float(widths.median()) if len(widths) else math.nan
    p90 = float(widths.quantile(0.9)) if len(widths) else math.nan
    w_b_verdict = (
        "INCONCLUSIVE"
        if len(widths) < MIN_POINTS
        else ("MET" if median <= WIDTH_B_MEDIAN_BAR and p90 <= WIDTH_B_P90_BAR else "FAILED")
    )
    return {
        "W(a)": {"n": len(ratio), "median": w_a, "verdict": w_a_verdict},
        "W(b)": {
            "n": len(widths),
            "median": median,
            "p90": p90,
            "verdict": w_b_verdict,
        },
    }


def overall(
    ram_point: str,
    ram_config: str,
    time_value: str,
    risk_value: dict[str, str],
    width: dict[str, dict[str, Any]],
) -> str:
    whole = {
        "RAM per point": ram_point,
        "RAM per configuration": ram_config,
        "time within-one": time_value,
        "R1": risk_value["R1"],
        "W(a)": width["W(a)"]["verdict"],
        "W(b)": width["W(b)"]["verdict"],
    }
    failed = [name for name, verdict in whole.items() if verdict == "FAILED"]
    if failed:
        return f"`{FROZEN_TAG}` FAILED its Phase 8 held-out check: " + ", ".join(failed)
    if any(verdict == "INCONCLUSIVE" for verdict in whole.values()):
        return "INCONCLUSIVE (one or more Phase 8 whole-v4 criteria lack the required evidence); not a pass"
    return "the whole-v4 criteria on val-v5 are MET"


def section(
    df: pd.DataFrame,
    planned: int | None = None,
    v3_predictions: pd.DataFrame | None = None,
) -> str:
    """Render the Phase 8 v4 verdict; caller must have logged val-v5 access."""
    nl = chr(10)
    rp, rc, tm = ram_points(df), ram_configurations(df), time_within_one(df)
    t0 = time_within_one(df, tier=0)
    rk = risk(df)
    width = width_criteria(df, v3_predictions)
    measured = int(df["point_id"].nunique()) if "point_id" in df else 0

    def pct(value: float) -> str:
        return "n/a" if math.isnan(value) else f"{value:.1%}"

    def ratio(value: float) -> str:
        return "n/a" if math.isnan(value) else f"{value:.2f}x"

    lines = [
        f"## Phase 8 acceptance verdict (`{FROZEN_TAG}`; authoritative)",
        "",
        "Source: `docs/benchmarks/phase8-preregistration.md`, section 2 and amendments 1-7. "
        "Legacy Phase 4d controller criteria S1-S5 are not the v4 acceptance verdict.",
        "",
    ]
    if planned is not None and measured < planned:
        lines += [
            f"**INCOMPLETE RUN: {measured} of {planned} planned val-v5 points have results; "
            "the verdict below covers measured points only.**",
            "",
        ]
    lines += [
        "| criterion | n | events | rate | 95% bound | bar | verdict |",
        "|---|---|---|---|---|---|---|",
        f"| RAM above_high per point (Tier 1) | {rp['n']} | {rp['k']} | {pct(rp['rate'])} | upper "
        f"{pct(rp['upper'])} | <= 3% | **{rp['verdict']}** |",
        f"| RAM above_high per configuration (Tier 1) | {rc['n']} | {rc['k']} | {pct(rc['rate'])} | upper "
        f"{pct(rc['upper'])} | <= 3% | **{rc['verdict']}** |",
        f"| time within-one bucket, Tier 1 | {tm['n']} | {tm['k']} | {pct(tm['rate'])} | lower "
        f"{pct(tm['lower'])} | >= 95% | **{tm['verdict']}** |",
        f"| time within-one bucket, Tier 0 (information only) | {t0['n']} | {t0['k']} | {pct(t0['rate'])} | lower "
        f"{pct(t0['lower'])} | no verdict | no verdict |",
        f"| R1 recall (risk replay) | - | - | - | - | >= 98% pooled and eligible limits | **{rk['R1']}** |",
        f"| R2 false alarms (risk replay; item criterion) | - | - | - | - | pooled <= 30%, per op <= 50% | "
        f"**{rk['R2']}** |",
        f"| R3 HIGH_RISK precision (risk replay; item criterion) | - | - | - | - | >= 75% | **{rk['R3']}** |",
        f"| W(a), shared v3/v4 points | {width['W(a)']['n']} | - | "
        f"{ratio(width['W(a)'].get('median', math.nan))} | - | <= 1.30x | **{width['W(a)']['verdict']}** |",
        f"| W(b), v4-only coverage points | {width['W(b)']['n']} | - | "
        f"{ratio(width['W(b)'].get('median', math.nan))} | p90 "
        f"{ratio(width['W(b)'].get('p90', math.nan))} | median <= 2.0x; p90 <= 4.0x | "
        f"**{width['W(b)']['verdict']}** |",
        "",
        f"* Configurations above high: {', '.join(rc['configs_above']) or 'none'}. Fewer than {MIN_POINTS} valid "
        f"points (configurations: fewer than {MIN_CONFIGS}) is INCONCLUSIVE, never a pass.",
        "* val-v5 contains single-operation cells, so partial-cell scoring does not apply to this set.",
        "* W(a) compares displayed width ratios on shared points; W(b) applies only to points v3 did not estimate. "
        "The v3 baseline is prediction-only and contains no actual values.",
        "",
        f"**Overall: {overall(rp['verdict'], rc['verdict'], tm['verdict'], rk, width)}.** R2 and R3 failures "
        "withdraw those item claims but do not alone fail v4 as a whole.",
        "",
    ]
    return nl.join(lines)
