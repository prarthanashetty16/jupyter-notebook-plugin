"""Tier 2 vs Tier 1 on DEVELOPMENT data (every number is dev: nothing here is held out).

Reads a results directory whose predictions hold Tier 0, Tier 1 and Tier 2 rows for the same
actuals (``python -m benchmarks full --splits dev --tiers 2 ...``). Tier 2 rows carry the dry run's
diagnostics in ``features["tier2"]``; a quantity (RAM or time) counts as "Tier 2" only where its fit
was accepted, otherwise the row repeats Tier 1 and is excluded from the Tier 2 columns.

Compared, per operation, for RAM and time: Tier 1 (with the global range policy: Tier 1 low and
expected, Tier 0 high), Tier 2 alone, and two combinations chosen by principle, not by fit:

* ``hull``: Tier 2's expected value, the union of Tier 2's and Tier 1's native ranges (the safe side);
* ``geomean``: the geometric mean of both expected values, the same union range.

Also: availability and reasons for "no estimate", the dry run's overhead in seconds and as a fraction
of the measured run time, where Tier 2 pays off by input size, the cases where it is worse, and the
merge points with the non-unique-right / small-output RAM residual.

    python -m benchmarks.tier2_eval benchmarks/results/tier2-dev --out docs/benchmarks/tier2-dev
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

MIB = 2**20


def _t2(features: Any) -> dict[str, Any]:
    try:
        return json.loads(features).get("tier2", {}) or {}
    except (TypeError, ValueError):
        return {}


def build(results: Path) -> pd.DataFrame:
    """One row per development point with Tier 1 / Tier 2 / Tier 0 figures and the dry-run diagnostics."""
    df = load_joined(results)
    df = df[df["has_estimate"].astype(bool) & (df["status"] == "ok")]
    keep = ["op", "case", "size", "origin", "ram_class", "ram_value", "time_class", "time_value",
            "ram_low", "ram_expected", "ram_high", "time_low", "time_expected", "time_high"]  # fmt: skip
    t0, t1, t2 = (df[df["tier"] == t].set_index("point_id") for t in (0, 1, 2))
    out = t1[keep].loc[t1.index.isin(t2.index)].copy()  # only points that have a Tier 2 row
    out["t0_ram_high"] = t0["ram_high"].reindex(out.index)
    for c in ("ram_low", "ram_expected", "ram_high", "time_low", "time_expected", "time_high"):
        out["t2_" + c] = t2[c].reindex(out.index)
    info = t2["features"].reindex(out.index).map(_t2)
    out["dry"] = info
    out["ram_ok"] = info.map(lambda d: bool((d.get("ram") or {}).get("ok")))
    out["time_ok"] = info.map(lambda d: bool((d.get("time") or {}).get("ok")))
    out["overhead_s"] = info.map(lambda d: d.get("overhead_s", np.nan))
    out["reason"] = info.map(lambda d: d.get("reason") or "")
    out["ram_reason"] = info.map(lambda d: (d.get("ram") or {}).get("reason", ""))
    out["time_reason"] = info.map(lambda d: (d.get("time") or {}).get("reason", ""))
    out["crosses_cap"] = info.map(lambda d: "crosses_presize_cap" in (d.get("notes") or []))
    out["kind"] = info.map(lambda d: d.get("kind", ""))
    return out.reset_index()


def _ranges(d: pd.DataFrame, what: str) -> dict[str, pd.DataFrame]:
    """Candidate (low, expected, high) per point for RAM or time (rows where Tier 2 was accepted)."""
    ok = d[d[f"{'ram' if what == 'ram' else 'time'}_ok"]]
    p = what + "_"
    t1_low, t1_exp, t1_high = ok[p + "low"], ok[p + "expected"], ok[p + "high"]
    t1_hi_policy = (
        ok["t0_ram_high"].where(ok["t0_ram_high"] > t1_exp, t1_high) if what == "ram" else t1_high
    )
    t2_low, t2_exp, t2_high = (
        ok["t2_" + p + "low"],
        ok["t2_" + p + "expected"],
        ok["t2_" + p + "high"],
    )
    union_lo, union_hi = np.minimum(t1_low, t2_low), np.maximum(t1_high, t2_high)
    geo = np.sqrt(t1_exp * t2_exp)
    mk = lambda lo, e, hi: pd.DataFrame({"low": lo, "expected": e, "high": hi})  # noqa: E731
    return {
        "tier1": mk(t1_low, t1_exp, t1_hi_policy if what == "ram" else t1_high),
        "tier1_native": mk(t1_low, t1_exp, t1_high),
        "tier2": mk(t2_low, t2_exp, t2_high),
        "hull": mk(union_lo, t2_exp, union_hi),
        "geomean": mk(union_lo, geo, union_hi),
    }


def metrics(act: pd.Series, r: pd.DataFrame) -> dict[str, float]:
    a = act.to_numpy(dtype=float)
    e, lo, hi = r["expected"].to_numpy(float), r["low"].to_numpy(float), r["high"].to_numpy(float)
    fold = e / a
    return {
        "n": len(a), "err_med": float(np.median(np.abs(fold - 1))), "err_p90": float(np.quantile(np.abs(fold - 1), 0.9)),
        "bias": float(np.median(fold)), "coverage": float(np.mean((a >= lo) & (a <= hi))),
        "above_high": float(np.mean(a > hi)), "below_low": float(np.mean(a < lo)), "width": float(np.mean((hi - lo) / e)),
    }  # fmt: skip


def table(d: pd.DataFrame, what: str) -> pd.DataFrame:
    valid = d[(d[f"{what}_class"] == "valid")]
    rows = []
    for op, g in [*sorted(valid.groupby("op")), ("ALL", valid)]:
        g = g[g[f"{what}_ok"]]
        if g.empty:
            continue
        cands = _ranges(g, what)
        for name, r in cands.items():
            rows.append({"op": op, "variant": name, **metrics(g[f"{what}_value"], r)})
    return pd.DataFrame(rows)


def availability(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for op, g in [*sorted(d.groupby("op")), ("ALL", d)]:
        rows.append({"op": op, "points": len(g), "safe_and_sampled": int((g["reason"] == "").sum()),
                     "ram_fit": int(g["ram_ok"].sum()), "time_fit": int(g["time_ok"].sum())})  # fmt: skip
    return pd.DataFrame(rows)


def overhead(d: pd.DataFrame) -> pd.DataFrame:
    v = d[(d["time_class"] == "valid") & d["overhead_s"].notna()].copy()
    v["fraction"] = v["overhead_s"] / v["time_value"]
    rows = []
    for op, g in [*sorted(v.groupby("op")), ("ALL", v)]:
        rows.append({"op": op, "n": len(g), "overhead_med_s": g["overhead_s"].median(), "overhead_max_s": g["overhead_s"].max(),
                     "fraction_med": g["fraction"].median(), "share_overhead_below_run": float((g["fraction"] <= 1).mean())})  # fmt: skip
    return pd.DataFrame(rows)


def by_size(d: pd.DataFrame) -> pd.DataFrame:
    """Where Tier 2 pays off: cheaper than the run itself AND closer than Tier 1 (RAM or time)."""
    v = d[(d["ram_class"] == "valid") & d["ram_ok"]].copy()
    v["gain"] = np.abs(np.log(v["ram_expected"] / v["ram_value"])) - np.abs(
        np.log(v["t2_ram_expected"] / v["ram_value"])
    )
    v["cheap"] = v["overhead_s"] <= v["time_value"].fillna(np.inf)
    v["bucket"] = pd.cut(v["size"], [0, 1_500_000, 5_000_000, 1e9], labels=["<=1M", "3M", "10M+"])
    return v.groupby(["bucket"], observed=True).agg(points=("gain", "size"), t2_closer=("gain", lambda x: float((x > 0).mean())),
                                                   median_gain_log=("gain", "median"), overhead_med_s=("overhead_s", "median"),
                                                   run_time_med_s=("time_value", "median")).reset_index()  # fmt: skip


def merge_residual(d: pd.DataFrame) -> pd.DataFrame:
    m = d[
        (d["op"] == "merge") & d["case"].str.contains("overlap(?:20|25|35)_fanout|inner_overlap10")
    ]
    m = m[m["ram_class"] == "valid"]
    rows = []
    for _, r in m.iterrows():
        rows.append({"point": r["point_id"], "actual_MiB": r["ram_value"] / MIB, "t1_fold": r["ram_expected"] / r["ram_value"],
                     "t2_ram_ok": r["ram_ok"], "t2_fold": r["t2_ram_expected"] / r["ram_value"] if r["ram_ok"] else math.nan,
                     "t2_in_range": bool(r["t2_ram_low"] <= r["ram_value"] <= r["t2_ram_high"]) if r["ram_ok"] else None,
                     "reason": r["ram_reason"][:70]})  # fmt: skip
    return pd.DataFrame(rows)


def worse_cases(d: pd.DataFrame, what: str, k: int = 12) -> pd.DataFrame:
    v = d[(d[f"{what}_class"] == "valid") & d[f"{what}_ok"]].copy()
    v["t1_err"] = np.abs(np.log(v[f"{what}_expected"] / v[f"{what}_value"]))
    v["t2_err"] = np.abs(np.log(v[f"t2_{what}_expected"] / v[f"{what}_value"]))
    v["worse_by"] = v["t2_err"] - v["t1_err"]
    cols = ["point_id", "kind", "t1_err", "t2_err", "worse_by", "crosses_cap"]
    return v.sort_values("worse_by", ascending=False).head(k)[cols]


def _md(df: pd.DataFrame, pct: tuple[str, ...] = ()) -> str:
    if df.empty:
        return "_no data_\n"
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    body = ""
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            cells.append(
                f"{v:.0%}"
                if c in pct and isinstance(v, float) and not math.isnan(v)
                else f"{v:.3g}"
                if isinstance(v, float)
                else str(v)
            )
        body += "| " + " | ".join(cells) + " |\n"
    return head + body


PCT = (
    "err_med",
    "err_p90",
    "coverage",
    "above_high",
    "below_low",
    "width",
    "t2_closer",
    "share_overhead_below_run",
)


def report(d: pd.DataFrame) -> str:
    lines = ["# Tier 2 vs Tier 1 on development data (ALL numbers are dev; nothing is held out)\n",
             f"{len(d)} development points with Tier 1 and Tier 2 predictions.\n", "## Availability of a Tier 2 estimate\n",
             _md(availability(d))]  # fmt: skip
    reasons = (
        d.loc[~d["ram_ok"], "ram_reason"]
        .str.replace(r"[\d.e+]+", "#", regex=True)
        .str[:80]
        .value_counts()
        .head(8)
    )
    lines += [
        "\nReasons RAM got no Tier 2 estimate (numbers masked):\n",
        _md(reasons.rename("points").reset_index().rename(columns={"ram_reason": "reason"})),
    ]
    for what in ("ram", "time"):
        t = table(d, what)
        lines += [f"\n## {what.upper()}: Tier 1 (global range policy) vs Tier 2 vs combinations (valid points where the Tier 2 fit was accepted)\n",
                  _md(t, PCT)]  # fmt: skip
    lines += ["\n## Overhead of the dry run\n", _md(overhead(d), PCT), "\n## Where it pays off (RAM, by input size)\n", _md(by_size(d), PCT),
              "\n## Merge residual points (non-unique right keys, small output)\n", _md(merge_residual(d)),
              "\n## Worst RAM cases for Tier 2 (log error of Tier 2 minus Tier 1)\n", _md(worse_cases(d, "ram")),
              "\n## Worst time cases for Tier 2\n", _md(worse_cases(d, "time"))]  # fmt: skip
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    d = build(a.results)
    text = report(d)
    print(text)
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "tier2_vs_tier1.md").write_text(text, encoding="utf-8")
        d.drop(columns=["dry"]).to_csv(a.out / "points_tier2.csv", index=False)


if __name__ == "__main__":
    main()
