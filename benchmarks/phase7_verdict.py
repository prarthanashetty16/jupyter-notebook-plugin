"""The Phase 7 acceptance verdict for val-v5 (``models-frozen-v3``), outside the frozen model set.

Source of every bar: ``docs/benchmarks/phase7-preregistration.md``, section 2 ("Held-out criteria") and section 4
("What counts as failure"). The legacy Phase 4d controller criteria S1-S5 that ``evaluate --val`` also prints are NOT
these and are not relabelled here.

* RAM above_high per POINT: Tier 1 (policy B, as displayed), valid RAM points: <= 3%; the one-sided 95%
  Clopper-Pearson upper bound is quoted.
* RAM above_high per CONFIGURATION (val-v5 case; above if any of its valid points is above high): <= 3%, with the
  same bound.
* Time within-one (order-of-magnitude bucket, ``nexus.timebuckets``): >= 95%, with the Wilson 95% lower bound. The
  pre-registration does NOT specify a tier for time. As a PROVISIONAL INTERPRETATION (not a pre-registered choice) the
  verdict row uses Tier 1, the extension default and the tier the RAM criterion names; Tier 0 time is shown in its own
  row with the same statistics and no verdict. The report labels this as an interpretation.
* R1 / R2 / R3: the ``benchmarks.risk_eval`` replay (R1 recall >= 98% pooled and at every limit with >= 20
  positives; R2 pooled <= 30% and per operation <= 50%, a repeat failure; R3 HIGH_RISK precision >= 75%).
* Fewer than 30 valid points (configurations: fewer than 10) -> INCONCLUSIVE, never a pass.
* Whole-v3 failure (section 4): RAM per point or per configuration, time, or R1 FAILED. Item failure: R2 or R3.
* The uncovered-operation rule (amendment 1) concerns multi-statement cells; val-v5 points are single operations, so it
  does not apply here.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

RAM_BAR = 0.03
CONFIG_BAR = 0.03
TIME_BAR = 0.95
MIN_POINTS = 30
MIN_CONFIGS = 10
CONFIDENCE = 0.95
TIER = 1
TIME_NOTE_REF = "time-tier note"


def binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson_upper(k: int, n: int, confidence: float = CONFIDENCE) -> float:
    """One-sided upper bound on a rate from k events in n trials (exact, by bisection)."""
    if n == 0:
        return math.nan
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    alpha = 1.0 - confidence
    for _ in range(100):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def wilson_lower(k: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return math.nan
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def _valid(df: pd.DataFrame, tier: int, what: str) -> pd.DataFrame:
    return df[
        (df["tier"] == tier) & df["has_estimate"].astype(bool) & (df[f"{what}_class"] == "valid")
    ]


def ram_points(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    v = _valid(df, tier, "ram")
    above = v["ram_value"].astype(float) > v["ram_high"].astype(float)
    k, n = int(above.sum()), len(v)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_POINTS else ("MET" if rate <= RAM_BAR else "FAILED")
    return {"k": k, "n": n, "rate": rate, "upper": clopper_pearson_upper(k, n), "verdict": verdict}


def ram_configurations(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    v = _valid(df, tier, "ram")
    above = (v["ram_value"].astype(float) > v["ram_high"].astype(float)).groupby(v["case"]).any()
    k, n = int(above.sum()), len(above)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_CONFIGS else ("MET" if rate <= CONFIG_BAR else "FAILED")
    return {"k": k, "n": n, "rate": rate, "upper": clopper_pearson_upper(k, n), "verdict": verdict,
            "configs_above": sorted(above[above].index)}  # fmt: skip


def time_within_one(df: pd.DataFrame, tier: int = TIER) -> dict[str, Any]:
    from nexus.timebuckets import bucket_index

    v = _valid(df, tier, "time")
    ok = (v["time_expected"].map(bucket_index) - v["time_value"].map(bucket_index)).abs() <= 1
    k, n = int(ok.sum()), len(v)
    rate = k / n if n else math.nan
    verdict = "INCONCLUSIVE" if n < MIN_POINTS else ("MET" if rate >= TIME_BAR else "FAILED")
    return {"k": k, "n": n, "rate": rate, "lower": wilson_lower(k, n), "verdict": verdict}


def risk(df: pd.DataFrame) -> dict[str, str]:
    from benchmarks import risk_eval

    if risk_eval.classify_all(df).empty:
        return {"R1": "INCONCLUSIVE", "R2": "INCONCLUSIVE", "R3": "INCONCLUSIVE"}
    res = risk_eval.evaluate(df)
    pa, pc, v = res["pooled_all"], res["pooled_claim"], res["verdict"]
    claim = res["claim_limits"]
    r1 = ("INCONCLUSIVE" if not claim else
          "MET" if (not v["R1a"] and pa["recall"] >= risk_eval.RECALL_TARGET) else "FAILED")  # fmt: skip
    r2 = ("INCONCLUSIVE" if not pc else
          "MET" if (pc["false_alarm"] <= risk_eval.FAR_TARGET and not v["R2_ops"]) else "FAILED")  # fmt: skip
    r3 = ("INCONCLUSIVE" if math.isnan(v["R3"]) else
          "MET" if v["R3"] >= risk_eval.HIGH_PRECISION_TARGET else "FAILED")  # fmt: skip
    return {"R1": r1, "R2": r2, "R3": r3, "R2_ops_over": str(v["R2_ops"] or "none")}


def overall(ram_p: str, ram_c: str, time_v: str, risk_v: dict[str, str]) -> str:
    whole = {
        "RAM per point": ram_p,
        "RAM per configuration": ram_c,
        "time within-one": time_v,
        "R1": risk_v["R1"],
    }
    failed = [k for k, x in whole.items() if x == "FAILED"]
    if failed:
        return "`models-frozen-v3` FAILED its held-out check (section 4): " + ", ".join(failed)
    if any(x == "INCONCLUSIVE" for x in whole.values()):
        return "INCONCLUSIVE (section 2: too few points for at least one whole-v3 criterion); not a pass"
    return "the whole-v3 criteria on val-v5 are MET"


def section(df: pd.DataFrame, planned: int | None = None) -> str:
    """Markdown for ``evaluate --val``: the Phase 7 acceptance verdict, with its sources and bounds."""
    nl = chr(10)
    rp, rc, tm = ram_points(df), ram_configurations(df), time_within_one(df)
    t0 = time_within_one(df, tier=0)
    rk = risk(df)
    measured = int(df["point_id"].nunique()) if "point_id" in df else 0

    def pct(x: float) -> str:
        return "n/a" if x != x else f"{x:.1%}"

    lines = [
        "## Phase 7 acceptance verdict (`models-frozen-v3`; authoritative)",
        "",
        "Source: `docs/benchmarks/phase7-preregistration.md`, sections 2 and 4. The S1-S5 verdict above is the LEGACY "
        "Phase 4d controller criteria (5% of configurations), NOT the Phase 7 acceptance criteria.",
        "",
    ]
    if planned is not None and measured < planned:
        lines += [f"**INCOMPLETE RUN: {measured} of {planned} planned val-v5 points have results; the verdict below "
                  "covers the measured points only.**", ""]  # fmt: skip
    lines += [
        "| criterion | n | events | rate | 95% bound | bar | verdict |",
        "|---|---|---|---|---|---|---|",
        f"| RAM above_high per point (Tier 1) | {rp['n']} | {rp['k']} | {pct(rp['rate'])} | upper {pct(rp['upper'])} "
        f"| <= 3% | **{rp['verdict']}** |",
        f"| RAM above_high per configuration (Tier 1) | {rc['n']} | {rc['k']} | {pct(rc['rate'])} | upper "
        f"{pct(rc['upper'])} | <= 3% | **{rc['verdict']}** |",
        f"| time within-one bucket, Tier 1 (PROVISIONAL INTERPRETATION, see {TIME_NOTE_REF}) | {tm['n']} | {tm['k']} | "
        f"{pct(tm['rate'])} | lower {pct(tm['lower'])} | >= 95% | **{tm['verdict']}** |",
        f"| time within-one bucket, Tier 0 (information only) | {t0['n']} | {t0['k']} | {pct(t0['rate'])} | lower "
        f"{pct(t0['lower'])} | (>= 95%) | no verdict |",
        f"| R1 recall (risk replay) | - | - | - | - | >= 98% | **{rk['R1']}** |",
        f"| R2 false alarms (risk replay; repeat failure) | - | - | - | - | pooled <= 30%, per op <= 50% | **{rk['R2']}** |",
        f"| R3 HIGH_RISK precision (risk replay) | - | - | - | - | >= 75% | **{rk['R3']}** |",
        "",
        f"* Above-high rates are reported as \"consistent with a true rate <= upper bound\" (one-sided 95% "
        f"Clopper-Pearson). Configurations above high: {', '.join(rc['configs_above']) or 'none'}.",
        f"* {TIME_NOTE_REF}: the pre-registration (section 2) specifies Tier 1 for the RAM criterion but does NOT "
        "specify a tier for the time criterion. Using Tier 1 for the time verdict is an INTERPRETATION made in Phase 7d "
        "(Tier 1 is the extension default and the RAM criterion's tier), not a pre-registered requirement. Tier 0 time "
        "is shown in its own row, with the same statistics and no verdict"
        + (f"; on these data the two tiers {'agree' if (t0['rate'] >= TIME_BAR) == (tm['rate'] >= TIME_BAR) else 'DISAGREE'}"
           " on the 95% bar." if t0["n"] and tm["n"] else "."),
        "* R1-R3 numbers: the risk-engine section above. Operations over the R2 per-operation bar: "
        f"{rk.get('R2_ops_over', 'n/a')}.",
        "* The uncovered-operation rule (amendment 1) does not apply to val-v5: its points are single operations.",
        f"* Fewer than {MIN_POINTS} valid points (configurations: {MIN_CONFIGS}) -> INCONCLUSIVE, never a pass.",
        "",
        f"**Overall: {overall(rp['verdict'], rc['verdict'], tm['verdict'], rk)}.** R2 / R3 failures are item failures "
        "(the claim is withdrawn; v3 is not failed as a whole). The time criterion in this overall line uses the "
        f"provisional Tier 1 interpretation ({TIME_NOTE_REF}).",
        "",
    ]  # fmt: skip
    return nl.join(lines)
