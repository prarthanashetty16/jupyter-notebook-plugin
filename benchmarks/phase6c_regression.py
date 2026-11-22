"""Phase 6c regression check on all existing dev data (pre-registration B).

    python -m benchmarks.phase6c_regression --before benchmarks/results/phase6-dev-mains \
        --after benchmarks/results/phase6c-dev --out docs/benchmarks/phase6c/regression_dev.md

Both folders hold prediction re-runs on the same stored dev actuals: ``before`` with the
``models-frozen-v1`` stack, ``after`` with the Phase 6c stack. RAM figures are compared as stored (both
under policy B). Time is recomputed from each run's stored features with the current models and then
calibrated with the shipped artifact (``nexus.timecal``), exactly as at run time, so both sides are
comparable. Per operation and tier: RAM above_high / coverage / width; time median and p90 error,
same-bucket, within-one, coverage. Any change for the worse is listed.
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
from nexus import timecal
from nexus.models.base import NoEstimateError
from nexus.pipeline import load_builtin_models
from nexus.registry import default_registry
from nexus.timebuckets import bucket_index


def _recompute(rows: pd.DataFrame) -> pd.DataFrame:
    load_builtin_models()
    models = {m.name: m for m in default_registry}
    lo, ex, hi = [], [], []
    for model, tier, feats in zip(rows["model"], rows["tier"], rows["features"], strict=True):
        try:
            f = json.loads(feats)
            m = models[model]
            try:
                e = m.estimate(f, int(tier))
            except NoEstimateError:
                e = m.estimate(f, 0)
            e = timecal.calibrate(model, e)
            lo.append(e.time_low)
            ex.append(e.time_expected)
            hi.append(e.time_high)
        except Exception:
            lo.append(math.nan)
            ex.append(math.nan)
            hi.append(math.nan)
    return rows.assign(t_low=lo, t_exp=ex, t_high=hi)


def load(path: Path) -> pd.DataFrame:
    d = load_joined(path)
    d = d[d["has_estimate"] & d["tier"].isin([0, 1])].copy()
    return _recompute(d)


def metrics(g: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    r = g[g["ram_class"] == "valid"]
    if len(r):
        a = r["ram_value"]
        out.update(ram_n=len(r), above_high=float((a > r["ram_high"]).mean()),
                   ram_cov=float(((r["ram_low"] <= a) & (a <= r["ram_high"])).mean()),
                   ram_width=float(((r["ram_high"] - r["ram_low"]) / r["ram_expected"]).mean()))  # fmt: skip
    t = g[(g["time_class"] == "valid") & g["t_exp"].notna()]
    if len(t):
        a, e = t["time_value"], t["t_exp"]
        rel = (e - a).abs() / a
        eb, ab = e.map(bucket_index), a.map(bucket_index)
        out.update(time_n=len(t), t_err_med=float(rel.median()), t_err_p90=float(rel.quantile(0.9)),
                   same_n=int((eb == ab).sum()), within_one_n=int(((eb - ab).abs() <= 1).sum()),
                   t_cov=float(((t["t_low"] <= a) & (a <= t["t_high"])).mean()))  # fmt: skip
    return out


def worse(b: dict[str, Any], a: dict[str, Any]) -> list[str]:
    out = []
    for key, bad in (("above_high", lambda x, y: y > x), ("ram_cov", lambda x, y: y < x - 1e-9),
                     ("ram_width", lambda x, y: y > x + 1e-9), ("t_err_med", lambda x, y: y > x + 0.02),
                     ("t_err_p90", lambda x, y: y > x + 0.05), ("same_n", lambda x, y: y < x),
                     ("within_one_n", lambda x, y: y < x), ("t_cov", lambda x, y: y < x - 1e-9)):  # fmt: skip
        if key in b and key in a and bad(b[key], a[key]):
            out.append(f"{key} {b[key]:.4g} -> {a[key]:.4g}")
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--before", type=Path, required=True)
    p.add_argument("--after", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    b, a = load(args.before), load(args.after)
    key = ["point_id", "tier"]
    j = b.merge(a, on=key, suffixes=("_b", "_a"))
    ram_changed = j[(j["ram_low_b"] != j["ram_low_a"]) | (j["ram_expected_b"] != j["ram_expected_a"])
                    | (j["ram_high_b"] != j["ram_high_a"])]  # fmt: skip
    t_changed = j[~np.isclose(j["t_exp_b"], j["t_exp_a"], rtol=1e-9, equal_nan=True)]
    lines = ["# Phase 6c regression check on all existing dev data (pre-registration B)", "",
             f"Before: `{args.before}` (models-frozen-v1); after: `{args.after}` (Phase 6c). {len(j)} (point, tier) rows "
             f"in both; only in before: {len(b) - len(j)}, only in after: {len(a) - len(j)}.", "",
             f"* rows whose RAM low / expected / high changed: **{len(ram_changed)}** "
             f"({', '.join(sorted(set(ram_changed['op_b']))) or 'none'})",
             f"* rows whose calibrated expected time changed: **{len(t_changed)}** "
             f"({', '.join(sorted(set(t_changed['op_b']))) or 'none'})", ""]  # fmt: skip
    rows, regressions = [], []
    for (op, tier), gb in b.groupby(["op", "tier"]):
        ga = a[(a["op"] == op) & (a["tier"] == tier)]
        mb, ma = metrics(gb), metrics(ga)
        rows.append({"op": op, "tier": int(tier), **{f"{k} before": v for k, v in mb.items()},
                     **{f"{k} after": v for k, v in ma.items()}})  # fmt: skip
        regressions += [f"{op} tier {int(tier)}: {w}" for w in worse(mb, ma)]
    cols = ["op", "tier", "above_high before", "above_high after", "ram_cov before", "ram_cov after",
            "ram_width before", "ram_width after", "t_err_med before", "t_err_med after", "same_n before",
            "same_n after", "within_one_n before", "within_one_n after", "t_cov before", "t_cov after"]  # fmt: skip
    lines += ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c, "-")
            cells.append(f"{v:.3g}" if isinstance(v, float) else str(v))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "## Regressions (pre-registered B)", ""] + (
        [f"- {x}" for x in regressions] or ["- none"]
    )
    if len(ram_changed):
        lines += ["", "## Rows whose RAM changed", ""]
        for _, r in ram_changed.iterrows():
            lines.append(f"- {r['point_id']} tier {int(r['tier'])}: {int(r['ram_expected_b']) >> 20} -> "
                         f"{int(r['ram_expected_a']) >> 20} MiB expected, high {int(r['ram_high_b']) >> 20} -> "
                         f"{int(r['ram_high_a']) >> 20}")  # fmt: skip
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
