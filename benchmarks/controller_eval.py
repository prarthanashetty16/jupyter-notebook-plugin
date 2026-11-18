"""Replay the adaptive controller on DEVELOPMENT data (every number is dev; nothing is held out).

The controller (``nexus.controller``, the pre-registered rules) is a function of the Tier 0 / Tier 1
estimates, the free RAM and the dry-run result. Dev points already carry all three: the stored Tier 0
and Tier 1 predictions and the stored Tier 2 dry runs (``tier2-dev-b``, the default sample sizes). The
replay feeds them to the REAL ``Controller`` class (same code path as production, with the dry run
and the safety analyzer replaced by lookups of what was measured), under declared free-RAM scenarios.

    python -m benchmarks.controller_eval benchmarks/results/tier2-dev-b --out docs/benchmarks/phase4d-dev
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.evaluate import load_joined
from nexus import dryrun
from nexus.controller import Controller, ControllerConfig
from nexus.dryrun_fit import FitResult
from nexus.dryrun_safety import Recipe, SafetyVerdict
from nexus.models.base import Estimate
from nexus.timebuckets import bucket_index

GIB = 2**30
SCENARIOS = {"2.5 GiB (the dev cap)": 2.5 * GIB, "8 GiB": 8 * GIB, "32 GiB": 32 * GIB}


def _est(row: pd.Series, p: str, tier: int, high: float | None = None) -> Estimate:
    exp = float(row[p + "ram_expected"])
    return Estimate(ram_low=int(row[p + "ram_low"]), ram_expected=int(exp), ram_high=int(high if high is not None else row[p + "ram_high"]),
                    time_low=float(row[p + "time_low"]), time_expected=float(row[p + "time_expected"]),
                    time_high=float(row[p + "time_high"]), confidence=0.5, tier=tier)  # fmt: skip


def load(results: Path) -> pd.DataFrame:
    """One row per dev point: actuals, Tier 0 / 1 / 2 figures, dry-run diagnostics."""
    return from_joined(load_joined(results))


def from_joined(df: pd.DataFrame) -> pd.DataFrame:
    """The same from a joined frame (from the evaluator): needs Tier 0, 1 and 2 rows."""
    df = df[df["has_estimate"].astype(bool) & (df["status"] == "ok")]
    base = [
        "op",
        "case",
        "size",
        "origin",
        "ram_class",
        "ram_value",
        "time_class",
        "time_value",
        "input_bytes",
        "inspected_bytes",
    ]
    cols = ["ram_low", "ram_expected", "ram_high", "time_low", "time_expected", "time_high"]
    t = {k: df[df["tier"] == k].set_index("point_id") for k in (0, 1, 2)}
    out = t[1][base + cols + ["features"]].loc[t[1].index.isin(t[2].index)].copy()
    out["features1"] = out.pop("features")
    for k in (0, 2):
        for c in cols:
            out[f"t{k}_{c}"] = t[k][c].reindex(out.index)
    info = (
        t[2]["features"]
        .reindex(out.index)
        .map(lambda f: (json.loads(f).get("tier2") or {}) if isinstance(f, str) else {})
    )
    out["dry"] = info
    if (
        "avail_start_bytes" in df
    ):  # the RAM that was really free when the point started (val: per-point scenario)
        out["avail"] = pd.to_numeric(
            df.drop_duplicates("point_id").set_index("point_id")["avail_start_bytes"],
            errors="coerce",
        ).reindex(out.index)
    return out.reset_index()


def _fit(d: dict[str, Any] | None, row: pd.Series, what: str) -> FitResult | None:
    if not d:
        return None
    if not d.get("ok"):
        return FitResult(False, str(d.get("reason", "")))
    p = f"t2_{what}_"
    return FitResult(True, "", float(row[p + "expected"]), float(row[p + "low"]), float(row[p + "high"]), d.get("best_law", ""),
                     {d.get("best_law", "linear"): {"cv": 0.0}})  # fmt: skip


def replay_point(
    row: pd.Series, free_ram: float, cfg: ControllerConfig
) -> tuple[Estimate, dict[str, Any]]:
    """Run the real controller on one dev point."""
    t1 = _est(row, "", 1)
    t1 = Estimate(
        **{**t1.__dict__, "ram_high": int(max(row["t0_ram_high"], t1.ram_expected))}
    )  # policy B
    t0 = _est(row, "t0_", 0)
    f1 = json.loads(row["features1"]) if isinstance(row["features1"], str) else {}
    dry = row["dry"] or {}
    unsafe = str(dry.get("reason", "")).startswith("not safe") or not dry
    kind = dry.get("kind", "") or ""

    def safety(source, ns):
        if unsafe or not kind:
            return SafetyVerdict(False, (dry.get("reason") or "not understood",))
        return SafetyVerdict(True, (), Recipe(kind))

    def fake_dryrun(source, ns, **kw):
        return dryrun.DryRunResult(reason=dry.get("reason", ""), kind=kind, ram=_fit(dry.get("ram"), row, "ram"),
                                   time=_fit(dry.get("time"), row, "time"), overhead_s=float(dry.get("overhead_s") or 0.0))  # fmt: skip

    ctl = Controller(config=cfg, dryrun_fn=fake_dryrun, safety_fn=safety)
    name = {v: k for k, vs in dryrun.OP_NAMES.items() for v in vs}.get(row["op"], row["op"])
    op_name = next(
        iter(dryrun.OP_NAMES.get(dryrun.kind_of_op(row["op"]) or "", {row["op"]})), row["op"]
    )
    del name
    return ctl.refine(
        op_name,
        t1,
        t0,
        f1,
        "cell",
        {},
        free_ram,
        float(row["inspected_bytes"] or 0.0),
        float(row["size"]),
    )


def run_scenario(d: pd.DataFrame, free_ram: float | None, cfg: ControllerConfig) -> pd.DataFrame:
    """``free_ram=None``: use each point's own recorded free RAM (``avail``)."""
    rows = []
    for _, r in d.iterrows():
        est, info = replay_point(r, float(r["avail"]) if free_ram is None else free_ram, cfg)
        rows.append({"point_id": r["point_id"], "ram_low": est.ram_low, "ram_expected": est.ram_expected, "ram_high": est.ram_high,
                     "time_low": est.time_low, "time_expected": est.time_expected, "time_high": est.time_high, "tier": est.tier,
                     "escalated": bool(info.get("escalated")), "attempted": bool(info.get("triggers")),
                     "fail_closed": "fail closed" in str(info.get("reason", "")), "unsafe": "unsafe cell" in str(info.get("reason", "")),
                     "triggers": ",".join(t.split(":")[0] for t in info.get("triggers", [])), "used": est.tier == 2,
                     "overhead_s": info.get("overhead_s", 0.0), "note": est.note})  # fmt: skip
    return pd.DataFrame(rows)


def baseline(d: pd.DataFrame) -> pd.DataFrame:
    """Tier 1 alone with the global range policy (Tier 1 low / expected, Tier 0 high)."""
    return pd.DataFrame({"point_id": d["point_id"], "ram_low": d["ram_low"], "ram_expected": d["ram_expected"],
                         "ram_high": np.maximum(d["t0_ram_high"], d["ram_expected"]), "time_low": d["time_low"],
                         "time_expected": d["time_expected"], "time_high": d["time_high"]})  # fmt: skip


def metrics(d: pd.DataFrame, e: pd.DataFrame) -> dict[str, float]:
    m = d.merge(e, on="point_id", suffixes=("_a", ""))
    out: dict[str, float] = {}
    v = m[m["ram_class"] == "valid"]
    if len(v):
        a, ex, lo, hi = (
            v[c].to_numpy(float) for c in ("ram_value", "ram_expected", "ram_low", "ram_high")
        )
        out.update(ram_n=len(v), ram_err_med=float(np.median(np.abs(ex / a - 1))), ram_cov=float(np.mean((a >= lo) & (a <= hi))),
                   ram_above_high=float(np.mean(a > hi)), ram_below_low=float(np.mean(a < lo)), ram_width=float(np.mean((hi - lo) / ex)))  # fmt: skip
    w = m[m["time_class"] == "valid"]
    if len(w):
        a, ex = w["time_value"].to_numpy(float), w["time_expected"].to_numpy(float)
        pb, ab = w["time_expected"].map(bucket_index), w["time_value"].map(bucket_index)
        out.update(time_n=len(w), time_err_med=float(np.median(np.abs(ex / a - 1))), time_within_one=float(np.mean((pb - ab).abs() <= 1)),
                   time_same_bucket=float(np.mean(pb == ab)),
                   time_cov=float(np.mean((a >= w["time_low"].to_numpy(float)) & (a <= w["time_high"].to_numpy(float)))))  # fmt: skip
    return out


def compare(d: pd.DataFrame, ctl: pd.DataFrame) -> pd.DataFrame:
    base = baseline(d)
    rows = []
    for op, g in [*sorted(d.groupby("op")), ("ALL", d)]:
        ids = set(g["point_id"])
        gd = d[d["point_id"].isin(ids)]
        b = metrics(gd, base[base["point_id"].isin(ids)])
        c = metrics(gd, ctl[ctl["point_id"].isin(ids)])
        cc = ctl[ctl["point_id"].isin(ids)]
        esc = cc[cc["escalated"]]
        real = gd.set_index("point_id")["time_value"]
        frac = (
            esc.set_index("point_id")["overhead_s"] / real.reindex(esc["point_id"]).to_numpy()
        ).replace([np.inf, -np.inf], np.nan)
        rows.append({"op": op, "points": len(g), "variant": "tier1", **b})
        rows.append({"op": op, "points": len(g), "variant": "controller", **c, "escalated": float(cc["escalated"].mean()),
                     "tier2_used": float(cc["used"].mean()), "fail_closed": float(cc["fail_closed"].mean()),
                     "unsafe": float(cc["unsafe"].mean()), "overhead_med_s": float(esc["overhead_s"].median()) if len(esc) else math.nan,
                     "overhead_frac_med": float(frac.median()) if len(frac.dropna()) else math.nan})  # fmt: skip
    return pd.DataFrame(rows)


def criteria(d: pd.DataFrame, ctl: pd.DataFrame) -> pd.DataFrame:
    """The pre-registered success criteria S1-S5 (docs/benchmarks/phase4d-preregistration.md)."""
    base = baseline(d)
    m = d.merge(ctl, on="point_id", suffixes=("_t1", ""))
    b = d.merge(base, on="point_id", suffixes=("_t1", ""))
    rows = []
    v, vb = m[m["ram_class"] == "valid"], b[b["ram_class"] == "valid"]
    above = (v["ram_value"] > v["ram_high"]).astype(float)
    above_b = (vb["ram_value"] > vb["ram_high"]).astype(float)
    cfg_above = v.assign(a=above).groupby("case")["a"].max().mean() if len(v) else math.nan
    s1 = (above.mean() <= 0.03) and (cfg_above <= 0.05) if len(v) else None
    rows.append(
        (
            "S1 RAM above_high <= 3% per point and <= 5% per configuration",
            f"{above.mean():.1%} / {cfg_above:.1%}",
            s1,
        )
    )
    w = m[m["time_class"] == "valid"]
    within = (
        float(
            (
                (w["time_expected"].map(bucket_index) - w["time_value"].map(bucket_index)).abs()
                <= 1
            ).mean()
        )
        if len(w)
        else math.nan
    )
    rows.append(
        (
            "S2 time bucket within one >= 95%",
            f"{within:.1%} of {len(w)}",
            within >= 0.95 if len(w) else None,
        )
    )
    esc = m[m["escalated"] & m["triggers"].str.contains("b")]
    n_ab = int((m["escalated"] & m["triggers"].str.contains("a|b")).sum())
    ratio = (esc["overhead_s"] / esc["time_value"]).replace([np.inf, -np.inf], np.nan).dropna()
    if n_ab < 20:
        s3 = None
        shown = f"INCONCLUSIVE: only {n_ab} points escalated by (a) or (b) (need 20)"
    else:
        s3 = bool(len(ratio) and ratio.median() <= 0.5 and ratio.quantile(0.9) <= 1.0)
        shown = f"median {ratio.median():.2f}, p90 {ratio.quantile(0.9):.2f} of the real run time over {len(ratio)} (b) points"
    rows.append(
        ("S3 overhead for (b) escalations: median <= 50%, p90 <= 100% of real run time", shown, s3)
    )
    lowered = int(
        ((m["ram_low"] < m["ram_low_t1"]) | (m["ram_expected"] < m["ram_expected_t1"])).sum()
    )
    wd = ((m["ram_high"] - m["ram_low"]) / m["ram_expected"]).mean()
    wb = ((b["ram_high"] - b["ram_low"]) / b["ram_expected"]).mean()
    tb = b[b["time_class"] == "valid"]
    within_b = (
        float(
            (
                (tb["time_expected"].map(bucket_index) - tb["time_value"].map(bucket_index)).abs()
                <= 1
            ).mean()
        )
        if len(tb)
        else math.nan
    )
    over = float((w["time_value"] > w["time_high"]).mean()) if len(w) else math.nan
    over_b = float((tb["time_value"] > tb["time_high"]).mean()) if len(tb) else math.nan
    checks = {
        "RAM above_high <= Tier 1's": bool(above.sum() <= above_b.sum()),
        "no RAM bound lowered": lowered == 0,
        "RAM width <= 1.25x Tier 1's": bool(wd <= 1.25 * wb),
        "time within-one >= Tier 1's - 1 pp": bool(within >= within_b - 0.01) if len(w) else True,
        "time above-high <= Tier 1's + 2 pp": bool(over <= over_b + 0.02) if len(w) else True,
    }
    detail = (
        f"above_high {int(above.sum())} vs {int(above_b.sum())}; lowered {lowered}; width {wd:.2f} vs {wb:.2f}; "
        f"within-one {within:.1%} vs {within_b:.1%}; time above-high {over:.1%} vs {over_b:.1%}"
    )
    failed = [k for k, ok in checks.items() if not ok]
    rows.append(
        (
            "S4 no harm (Amendment 1): five numeric checks",
            detail + ("; FAILED: " + ", ".join(failed) if failed else ""),
            not failed if len(v) else None,
        )
    )
    errors = int(m["note"].str.contains("controller error").sum())
    reasons = int(((m["fail_closed"] | m["unsafe"]) & (m["note"] != "")).sum())
    rows.append(
        (
            "S5 safety: no controller errors; every fail-closed / unsafe case has a reason",
            f"controller errors {errors}; fail-closed+unsafe {int((m['fail_closed'] | m['unsafe']).sum())} all with a note: {reasons == int((m['fail_closed'] | m['unsafe']).sum())}",
            errors == 0,
        )
    )
    return pd.DataFrame(rows, columns=["criterion", "result", "met"]).assign(
        met=lambda t: t["met"].map({True: "MET", False: "FAILED", None: "INCONCLUSIVE"})
    )


PRIORITY_NAMES = {
    1: "P1 (merge, groupby, astype, drop_duplicates, read_csv)",
    2: "P2 (concat, sort_values)",
    3: "P3 (numpy.sort, matmul)",
}


def completion(done_ids: set[str]) -> dict[int, tuple[int, int]]:
    """Per priority group: (points with a final status, points planned).

    Amendment 1 (b): a group is completed when every point of it has a final row (ok, memory_limit,
    error, timeout or skipped_cap); a point with no row is still pending.
    """
    from benchmarks.suite import build_grid, priority_of

    out: dict[int, list[int]] = {1: [0, 0], 2: [0, 0], 3: [0, 0]}
    for pt in build_grid("full", splits=("val-v5",)):
        g = priority_of(pt.op)
        out[g][1] += 1
        out[g][0] += pt.id in done_ids
    return {g: (v[0], v[1]) for g, v in out.items()}


def validation_section(val_joined: pd.DataFrame) -> str:
    """Markdown for ``evaluate --val``: completed groups, then S1-S5 on the completed groups only."""
    from benchmarks.suite import priority_of

    nl = chr(10)
    head = nl + "## Controller (pre-registered rules)" + nl + nl
    comp = completion(set(val_joined["point_id"]))
    done = [g for g, (k, n) in comp.items() if n and k == n]
    lines = [head + "### Which priority groups completed (Amendment 1)" + nl + nl,
             "| group | points with a final status | planned | completed |" + nl + "|---|---|---|---|" + nl]  # fmt: skip
    for g, (k, n) in comp.items():
        lines.append(
            f"| {PRIORITY_NAMES[g]} | {k} | {n} | {'yes' if n and k == n else 'NO'} |" + nl
        )
    if 1 not in done:
        lines.append(
            nl + "**val-v5 NOT EVALUATED: P1 did not complete; no criterion is judged.**" + nl
        )
        return "".join(lines)
    try:
        d = from_joined(val_joined)
    except (KeyError, ValueError):
        lines.append(
            nl
            + "no Tier 0 / 1 / 2 predictions in the validation results (run `full --tiers 0,1,2`)."
            + nl
        )
        return "".join(lines)
    d = d[d["op"].map(priority_of).isin(done)]
    if d.empty:
        lines.append(nl + "no points with Tier 2 predictions in the completed groups." + nl)
        return "".join(lines)
    free = None if "avail" in d and d["avail"].notna().all() else 32 * GIB
    note = (
        "free RAM = what was free at each point's start"
        if free is None
        else "free RAM scenario 32 GiB"
    )
    names = ", ".join(f"P{g}" for g in done)
    lines.append(nl + f"Verdicts are for the completed groups only ({names}); points of incomplete groups are excluded. "
                 f"Replayed on the stored dry runs; {note}." + nl)  # fmt: skip
    scopes = [("union of the completed groups", d)]
    if len(done) > 1:
        scopes += [(f"P{g} alone", d[d["op"].map(priority_of) == g]) for g in done]
    for name, sub in scopes:
        ctl = run_scenario(sub, free, ControllerConfig())
        lines.append(
            nl
            + f"#### {name}"
            + nl
            + nl
            + _md(criteria(sub, ctl))
            + nl
            + _md(compare(sub, ctl))
            + nl
        )
    return "".join(lines)


def _md(df: pd.DataFrame) -> str:
    pct = {"ram_err_med", "ram_cov", "ram_above_high", "ram_below_low", "ram_width", "time_err_med", "time_within_one",
           "time_same_bucket", "time_cov", "escalated", "tier2_used", "fail_closed", "unsafe"}  # fmt: skip
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    body = ""
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            cells.append(
                ""
                if isinstance(v, float) and math.isnan(v)
                else f"{v:.0%}"
                if c in pct and isinstance(v, float)
                else f"{v:.3g}"
                if isinstance(v, float)
                else str(v)
            )
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    d = load(a.results)
    text = ["# Phase 4d: the controller replayed on DEVELOPMENT data (every number is dev)\n",
            f"{len(d)} development points (dev + exposed-v1 + val-v3 + val-v4) with Tier 0 / 1 / 2 predictions; Tier 1 = Tier 1 low / expected with "
            "Tier 0's high (policy B). The real `Controller` runs on stored dry runs; see the docstring of `benchmarks/controller_eval.py`.\n"]  # fmt: skip
    cfg = ControllerConfig()
    for name, free in SCENARIOS.items():
        ctl = run_scenario(d, free, cfg)
        text += [f"\n## Free RAM scenario: {name}\n", _md(compare(d, ctl)),
                 f"\nTriggers that fired: {ctl.loc[ctl['attempted'], 'triggers'].value_counts().to_dict()}; "
                 f"fail-closed: {int(ctl['fail_closed'].sum())}; unsafe: {int(ctl['unsafe'].sum())}; "
                 f"Tier 2 used: {int(ctl['used'].sum())} of {len(ctl)}.\n"]  # fmt: skip
        if a.out:
            a.out.mkdir(parents=True, exist_ok=True)
            ctl.to_csv(a.out / f"controller_points_{name.split()[0]}gib.csv", index=False)
    what_if = ControllerConfig(min_run_s=0.0, ram_trigger_fraction=0.0)
    ctl = run_scenario(d, 32 * GIB, what_if)
    text += ["\n## WHAT-IF (not the pre-registered rules): always escalate when safe, 32 GiB free\n", _md(compare(d, ctl)),
             f"\nTier 2 used: {int(ctl['used'].sum())} of {len(ctl)}.\n"]  # fmt: skip
    out = "\n".join(text)
    print(out)
    if a.out:
        (a.out / "controller_vs_tier1.md").write_text(out, encoding="utf-8")


if __name__ == "__main__":
    main()
