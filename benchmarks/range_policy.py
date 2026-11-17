"""Phase 4b.2 range policy: how Tier 1 turns its expected RAM value into a (low, high) range.

PRE-REGISTERED SELECTION CRITERION (written, and committed, before any number was computed on the
re-run predictions; the script only smoke-tested on the OLD predictions):

* Population: development points (including the former val-v3) whose RAM actual is *valid* and
  whose Tier 1 estimate actually used statistics. Points killed by the memory cap are lower bounds
  and are not used to fit or select. Points whose Tier 1 fell back to Tier 0 keep the Tier 0 range.
* Candidates, all built from the same Tier 1 ``expected``:
    A    the current Tier 1 range (``low``, ``high`` as the model emits them);
    B_a  ``expected * [exp(q_lo), exp(q_hi)]`` with q the (1-a) and a quantiles of the per-operation
         residual ``log(actual / expected)``, a in {0.90, 0.95, 0.97, 0.99};
    C    ``[Tier 1 low, expected, Tier 0 high]`` (Tier 0's high as the upper end);
    D_a  B_a with its upper end capped at Tier 0's high (Tier 0's high as a safety ceiling).
* B and D are fitted under LEAVE-ONE-CONFIGURATION-OUT: the quantiles that score a configuration
  come only from the other configurations of the same operation (all operations pooled if fewer
  than 8 residuals remain). A and C have nothing to fit.
* Admissible: overall per-point ``above_high`` <= 3% AND per-configuration ``above_high`` share
  (a configuration counts if any of its points is above high) <= 5%.
* Winner: among the admissible candidates the smallest overall mean width ((high - low) /
  expected, per point). If none is admissible the least-bad (smallest above_high, then width) is
  reported as a FAILURE of the criterion, not silently accepted.
* The winner's per-operation constants are then fitted on ALL development points
  (``nexus.ranges.TIER1_BANDS``) and are NOT re-tuned afterwards.

Reported per operation and overall, per point and per configuration: coverage, above_high,
below_low, width. Everything here is development data: the leave-one-out scheme guards the
selection against optimism, the held-out check is val-v4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.evaluate import Floors, load_joined

ALPHAS = (0.90, 0.95, 0.97, 0.99)
MIN_RESIDUALS = 8
MAX_ABOVE_HIGH_POINTS = 0.03
MAX_ABOVE_HIGH_CONFIGS = 0.05


def _used_tier1(features: Any) -> bool:
    try:
        return bool(json.loads(features).get("tier1", {}).get("used", False))
    except (TypeError, ValueError):
        return False


def population(results_dir: Path, floors: Floors | None = None) -> pd.DataFrame:
    """One row per development point: actual, Tier 1 range and Tier 0 high."""
    df = load_joined(results_dir, floors or Floors())
    ok = df[(df["ram_class"] == "valid") & df["has_estimate"].fillna(False).astype(bool)]
    t1 = ok[ok["tier"] == 1].set_index("point_id")
    t0 = ok[ok["tier"] == 0].set_index("point_id")
    out = t1[["case", "op", "ram_value", "ram_low", "ram_expected", "ram_high", "features"]].copy()
    out = out.rename(
        columns={
            "ram_value": "actual",
            "ram_low": "low",
            "ram_expected": "expected",
            "ram_high": "high",
        }
    )
    out["t0_high"] = t0["ram_high"].reindex(out.index)
    out["used"] = out["features"].map(_used_tier1)
    out = out.drop(columns="features").dropna(subset=["actual", "expected", "t0_high"])
    return out[out["expected"] > 0].reset_index()


def _quantile_band(resid: np.ndarray, alpha: float) -> tuple[float, float]:
    return float(np.exp(np.quantile(resid, 1 - alpha))), float(np.exp(np.quantile(resid, alpha)))


def fit_bands(pop: pd.DataFrame, alpha: float) -> dict[str, tuple[float, float]]:
    """Per-operation (low, high) multipliers of ``expected`` fitted on every given point."""
    used = pop[pop["used"]]
    pooled = np.log(used["actual"] / used["expected"]).to_numpy()
    out = {}
    for op, g in used.groupby("op"):
        resid = np.log(g["actual"] / g["expected"]).to_numpy()
        out[op] = _quantile_band(resid if len(resid) >= MIN_RESIDUALS else pooled, alpha)
    return out


def loco_ranges(pop: pd.DataFrame, alpha: float, ceiling: bool) -> pd.DataFrame:
    """B_a / D_a ranges of every point, each fitted without the point's own configuration."""
    rows = []
    for case, held in pop.groupby("case"):
        train = pop[pop["case"] != case]
        train_used = train[train["used"]]
        pooled = np.log(train_used["actual"] / train_used["expected"]).to_numpy()
        for _, r in held.iterrows():
            if not r["used"]:
                lo, hi = r["low"], r["high"]
            else:
                same = train_used[train_used["op"] == r["op"]]
                resid = np.log(same["actual"] / same["expected"]).to_numpy()
                m_lo, m_hi = _quantile_band(resid if len(resid) >= MIN_RESIDUALS else pooled, alpha)
                lo, hi = r["expected"] * min(m_lo, 1.0), r["expected"] * max(m_hi, 1.0)
                if ceiling:
                    hi = max(min(hi, r["t0_high"]), r["expected"])
            rows.append((r["point_id"], lo, hi))
    out = pd.DataFrame(rows, columns=["point_id", "low", "high"]).set_index("point_id")
    return out.reindex(pop["point_id"]).reset_index(drop=True)


def candidates(pop: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Name -> frame with ``low`` and ``high`` (aligned with ``pop``)."""
    out = {"A current": pop[["low", "high"]].reset_index(drop=True)}
    out["C [T1 low, T0 high]"] = pd.DataFrame(
        {
            "low": pop["low"].to_numpy(),
            "high": np.maximum(pop["t0_high"], pop["expected"]).to_numpy(),
        }
    )
    for a in ALPHAS:
        out[f"B_{a:.2f}"] = loco_ranges(pop, a, ceiling=False)
        out[f"D_{a:.2f}"] = loco_ranges(pop, a, ceiling=True)
    return out


def score(pop: pd.DataFrame, rng: pd.DataFrame) -> dict[str, float]:
    """Coverage / above_high / below_low / width, per point and per configuration."""
    act = pop["actual"].to_numpy()
    lo, hi, exp = rng["low"].to_numpy(), rng["high"].to_numpy(), pop["expected"].to_numpy()
    above, below = act > hi, act < lo
    width = (hi - lo) / exp
    cfg = (
        pop.assign(above=above, below=below, width=width)
        .groupby("case")
        .agg(above=("above", "any"), below=("below", "any"), width=("width", "mean"))
    )
    return {
        "points": len(pop),
        "coverage": float(1 - (above | below).mean()),
        "above_high": float(above.mean()),
        "below_low": float(below.mean()),
        "width": float(width.mean()),
        "configs": len(cfg),
        "cfg_above_high": float(cfg["above"].mean()),
        "cfg_below_low": float(cfg["below"].mean()),
        "cfg_width": float(cfg["width"].mean()),
    }


def admissible(s: dict[str, float]) -> bool:
    return (
        s["above_high"] <= MAX_ABOVE_HIGH_POINTS and s["cfg_above_high"] <= MAX_ABOVE_HIGH_CONFIGS
    )


def evaluate(pop: pd.DataFrame) -> tuple[pd.DataFrame, str | None, dict[str, pd.DataFrame]]:
    """Overall table, the winner's name (None: none admissible -> least bad) and per-op tables."""
    cands = candidates(pop)
    rows, per_op = [], {}
    for name, rng in cands.items():
        s = score(pop, rng)
        rows.append({"candidate": name, **s, "admissible": admissible(s)})
        per_op[name] = pd.DataFrame(
            {
                op: score(
                    pop[pop["op"] == op].reset_index(drop=True),
                    rng[(pop["op"] == op).to_numpy()].reset_index(drop=True),
                )
                for op in sorted(pop["op"].unique())
            }
        ).T
    table = pd.DataFrame(rows).set_index("candidate")
    ok = table[table["admissible"]]
    if len(ok):
        winner = ok["width"].idxmin()
        return table, winner, per_op
    least_bad = table.sort_values(["above_high", "width"]).index[0]
    return table, None if least_bad is None else f"NONE ADMISSIBLE (least bad: {least_bad})", per_op


def markdown(table: pd.DataFrame, winner: str | None, per_op: dict[str, pd.DataFrame]) -> str:
    fmt = dict.fromkeys(
        ("coverage", "above_high", "below_low", "cfg_above_high", "cfg_below_low"), "{:.1%}"
    )
    show = table.copy()
    for c, f in fmt.items():
        show[c] = show[c].map(f.format)
    for c in ("width", "cfg_width"):
        show[c] = show[c].map("{:.2f}".format)
    lines = [
        "| candidate | points | coverage | above_high | below_low | width | configs | cfg above_high | cfg below_low | cfg width | admissible |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in show.iterrows():
        lines.append(
            f"| {name} | {r['points']} | {r['coverage']} | {r['above_high']} | {r['below_low']} | {r['width']} | "
            f"{r['configs']} | {r['cfg_above_high']} | {r['cfg_below_low']} | {r['cfg_width']} | {'yes' if r['admissible'] else 'no'} |"
        )
    out = ["\n".join(lines), f"\n**Winner under the pre-registered criterion:** {winner}\n"]
    chosen = (winner or "").split(" (least bad: ")[-1].rstrip(")") if winner else None
    if chosen in per_op:
        p = per_op[chosen].copy()
        out.append(f"\nPer operation for `{chosen}`:\n")
        out.append(
            "| op | points | coverage | above_high | below_low | width | configs | cfg above_high |\n|---|---|---|---|---|---|---|---|"
        )
        for op, r in p.iterrows():
            out.append(
                f"| {op} | {int(r['points'])} | {r['coverage']:.0%} | {r['above_high']:.0%} | {r['below_low']:.0%} | "
                f"{r['width']:.2f} | {int(r['configs'])} | {r['cfg_above_high']:.0%} |"
            )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "results", type=Path, help="results directory with dev actuals and Tier 0/1 predictions"
    )
    ap.add_argument("--out", type=Path, help="write the markdown report here")
    args = ap.parse_args(argv)
    pop = population(args.results)
    table, winner, per_op = evaluate(pop)
    text = markdown(table, winner, per_op)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
