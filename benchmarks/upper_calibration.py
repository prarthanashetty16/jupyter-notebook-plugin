"""Upper-bound calibration from DEV residuals (v4 item C, ``docs/benchmarks/phase8-preregistration.md``).

The procedure is fixed by the pre-registration, so nothing here is a tuning knob:

* residual = actual RAM / displayed ``expected`` on dev valid Tier 1 points (cell model for multi-statement cells);
* unit of exchangeability = the CONFIGURATION (a single-operation case, a multicell configuration, a notebook); each
  contributes its MAXIMUM residual;
* one factor per operation family (registry model; a cell's family is its dominant-peak operation) with >= 30
  configurations, the pooled factor otherwise;
* q = the ceil((n + 1)(1 - alpha))-th smallest configuration residual, alpha = 0.02 (split conformal); a rank beyond n
  gives the largest residual x 1.10, listed as "at the sample maximum";
* calibrated high = max(model high, expected x q): it only raises the high.

``--write`` writes the frozen artifact ``src/nexus/calibration/upper-v1.json``. The pre-registration runs that ONCE, on
the final v4 models; every other run is a dev preview (report only).

    python -m benchmarks.upper_calibration --single benchmarks/results/phase7b-dev-final --out docs/benchmarks/phase8/calibration_preview.md
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ALPHA = 0.02
MIN_CONFIGS = 30
AT_MAX_MARGIN = 1.10
LOCO_BAR = 0.02
ARTIFACT = Path("src/nexus/calibration/upper-v1.json")
MULTICELL_VERSIONS = (
    1,
    2,
    3,
)  # dev parts + the consumed held-out parts (benchmarks.multicell.split.CONSUMED)
REASON = "v4 item C: upper-bound calibration residuals (dev)"
REALWORLD = [Path("benchmarks/results/realworld/amazon_ml_solution_sub_v3"),
             Path("benchmarks/results/realworld/amazon_solution_old_sub_v3")]  # fmt: skip
REPREDICT_CACHE = Path("benchmarks/results/v4-dev/multicell_repredict.jsonl")
MIB = 2**20


@dataclass(frozen=True)
class Factor:
    q: float
    n: int
    at_max: bool


def conformal_factor(maxima: list[float], alpha: float = ALPHA) -> Factor:
    """Split-conformal upper quantile of the configuration maxima (rank ceil((n + 1)(1 - alpha)))."""
    xs = sorted(maxima)
    n = len(xs)
    if n == 0:
        raise ValueError("no configuration")
    k = math.ceil((n + 1) * (1 - alpha))
    if k > n:
        return Factor(xs[-1] * AT_MAX_MARGIN, n, True)
    return Factor(xs[k - 1], n, False)


def fit(units: pd.DataFrame, alpha: float = ALPHA) -> tuple[Factor, dict[str, Factor]]:
    """(pooled factor, own factors of families with >= MIN_CONFIGS configurations). ``units``: unit, family, max."""
    pooled = conformal_factor(units["max_residual"].tolist(), alpha)
    own = {
        fam: conformal_factor(g["max_residual"].tolist(), alpha)
        for fam, g in units.groupby("family")
        if len(g) >= MIN_CONFIGS
    }
    return pooled, own


def units_of(points: pd.DataFrame) -> pd.DataFrame:
    """One row per configuration: its maximum residual and the family of that point."""
    idx = points.groupby("unit")["residual"].idxmax()
    u = points.loc[idx, ["unit", "family", "residual"]].rename(columns={"residual": "max_residual"})
    return u.reset_index(drop=True)


def calibrated_high(points: pd.DataFrame, pooled: Factor, own: dict[str, Factor]) -> pd.Series:
    q = points["family"].map(lambda f: own[f].q if f in own else pooled.q)
    return pd.concat([points["high"], points["expected"] * q], axis=1).max(axis=1)


# -- dev residuals ------------------------------------------------------------------------------------------------
def single_op_points(results_dir: Path) -> pd.DataFrame:
    from benchmarks.evaluate import load_joined

    df = load_joined(results_dir)
    v = df[(df["tier"] == 1) & df["has_estimate"].astype(bool) & (df["ram_class"] == "valid")]
    return pd.DataFrame({
        "source": "single-op", "unit": "case:" + v["case"].astype(str), "family": v["model"].astype(str),
        "actual": v["ram_value"].astype(float), "low": v["ram_low"].astype(float),
        "expected": v["ram_expected"].astype(float), "high": v["ram_high"].astype(float),
    })  # fmt: skip


def _predict_detail(paths: dict[str, str], src: str) -> dict[str, Any]:
    """Prediction only (fresh process): the cell estimate and every operation's own estimate."""
    from benchmarks.multicell.run import load_inputs
    from nexus.cellpeak import cell_estimate
    from nexus.pipeline import Pipeline

    rep = Pipeline(tier=1).run(src, load_inputs(paths, src))
    cell, mode, _ = cell_estimate(src, rep.estimates)
    pick = ("ram_low", "ram_expected", "ram_high", "tier")
    return {
        "cell": None if cell is None else {k: getattr(cell, k) for k in pick},
        "mode": mode,
        "estimates": [
            {"model": e.model, **{k: getattr(e.estimate, k) for k in pick}} for e in rep.estimates
        ],
        "uncovered": len({id(o) for o in rep.ops} - {id(e.op) for e in rep.estimates}),
    }


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def _tree_state() -> str:
    """Digest of the model sources (``src/nexus`` at HEAD + uncommitted and untracked changes there), so a cached
    prediction is reused only for the same models, whatever else was committed."""
    import hashlib

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], capture_output=True, text=True).stdout

    h = hashlib.sha256(git("rev-parse", "HEAD:src/nexus").encode())
    h.update(git("diff", "HEAD", "--", "src/nexus").encode())
    for name in sorted(git("ls-files", "--others", "--exclude-standard", "src/nexus").split()):
        h.update(name.encode() + Path(name).read_bytes())
    return f"src/nexus:{h.hexdigest()[:16]}"


def _load_cache(state: str) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    if REPREDICT_CACHE.exists():
        for line in REPREDICT_CACHE.open(encoding="utf-8"):
            r = json.loads(line)
            if r["tree"] == state:
                cache[r["id"]] = r
    return cache


def _repredict(version: int, r: dict[str, Any], key: str, state: str) -> dict[str, Any]:
    from benchmarks.childproc import ChildFailureError, run_child
    from benchmarks.multicell.run import SUITES

    mod, _res, cache_dir, _log = SUITES[version]
    cell = mod.Cell(mod.Config(r["template"], r["shape"]), r["rows"])
    paths = mod.prepare(cache_dir, r["shape"], r["rows"])
    try:
        pred = run_child(_predict_detail, paths, mod.source(cell, paths), timeout_s=600)
    except ChildFailureError as fail:
        pred = {"harness": fail.record()}
    out = {"id": key, "tree": state, **pred}
    REPREDICT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with REPREDICT_CACHE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(out, default=str) + chr(10))
    return out


def _exclusion(p: dict[str, Any]) -> str | None:
    """Why a re-predicted cell gives no residual (None: it does). v4 Rule 1: a cell with an operation without an
    estimate has no cell range; residuals are Tier 1 only (item C)."""
    c = p.get("cell")
    if p.get("harness"):
        return "harness event"
    if c is None:
        return "no estimate"
    if p["uncovered"]:
        return "uncovered operation (Rule 1)"
    if c["tier"] < 1:
        return "Tier 0 only"
    return "expected 0" if c["ram_expected"] <= 0 else None


EXCLUDED: dict[str, int] = {}


def multicell_points(repredict: bool = True) -> pd.DataFrame:
    """Every measured multicell cell (v1 / v2 / v3, all dev), re-predicted with the working tree."""
    state = _tree_state()
    cache = _load_cache(state)
    rows = []
    from benchmarks.multicell.run import SUITES
    from benchmarks.multicell.split import consumed_heldout_results

    for version in MULTICELL_VERSIONS:
        files = [
            SUITES[version][1] / "dev" / "results.jsonl",
            consumed_heldout_results(version, REASON),
        ]
        for path in (f for f in files if f.exists()):
            for line in path.open(encoding="utf-8"):
                r = json.loads(line)
                if not r.get("actual") or r.get("censored") or r.get("status") != "ok":
                    continue
                key = f"v{version}|{r['id']}"
                if key not in cache:
                    if not repredict:
                        continue
                    cache[key] = _repredict(version, r, key, state)
                p = cache[key]
                why = _exclusion(p)
                if why is not None:
                    EXCLUDED[f"multicell {why}"] = EXCLUDED.get(f"multicell {why}", 0) + 1
                    continue
                c = p["cell"]
                dom = max(p["estimates"], key=lambda e: e["ram_expected"])["model"]
                rows.append({"source": f"multicell v{version}", "unit": f"mc{version}:{r['config']}",
                             "family": dom, "actual": float(r["actual"]), "low": float(c["ram_low"]),
                             "expected": float(c["ram_expected"]), "high": float(c["ram_high"])})  # fmt: skip
    return pd.DataFrame(rows)


def realworld_points(dirs: list[Path] = REALWORLD) -> pd.DataFrame:
    rows = []
    for d in dirs:
        f = d / "cells.jsonl"
        if not f.exists():
            continue
        for line in f.open(encoding="utf-8"):
            r = json.loads(line)
            c = r.get("cell")
            if r.get("ram_class") != "valid" or c is None or r.get("uncovered") or c["tier"] < 1:
                continue
            if c["ram_expected"] <= 0:
                continue
            dom = max(r["estimates"], key=lambda e: e["ram_expected"])["model"]
            rows.append({"source": "real notebooks (8a)", "unit": f"nb:{r['notebook']}", "family": dom,
                         "actual": float(r["ram_value"]), "low": float(c["ram_low"]),
                         "expected": float(c["ram_expected"]), "high": float(c["ram_high"])})  # fmt: skip
    return pd.DataFrame(rows)


def all_points(single: Path, repredict: bool = True) -> pd.DataFrame:
    parts = [single_op_points(single), multicell_points(repredict), realworld_points()]
    df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    df = df[df["expected"] > 0].copy()
    df["residual"] = df["actual"] / df["expected"]
    return df


# -- checks -------------------------------------------------------------------------------------------------------
def loco(points: pd.DataFrame, alpha: float = ALPHA) -> pd.Series:
    """Calibrated high of every point with the factors refitted WITHOUT its configuration."""
    out = pd.Series(index=points.index, dtype=float)
    units = units_of(points)
    for unit, g in points.groupby("unit"):
        pooled, own = fit(units[units["unit"] != unit], alpha)
        out.loc[g.index] = calibrated_high(g, pooled, own)
    return out


def summary(points: pd.DataFrame, high: pd.Series) -> dict[str, Any]:
    above = points["actual"] > high
    by_unit = above.groupby(points["unit"]).any()
    width = high / points["expected"]
    err = (points["expected"] - points["actual"]).abs() / points["actual"]
    inside = (points["actual"] >= points["low"]) & ~above
    return {"points": len(points), "configs": int(by_unit.size),
            "above_pts": int(above.sum()), "above_pts_rate": float(above.mean()),
            "above_cfg": int(by_unit.sum()), "above_cfg_rate": float(by_unit.mean()),
            "median_err": float(err.median()), "coverage": float(inside.mean()),
            "width_med": float(width.median()), "width_p90": float(width.quantile(0.9))}  # fmt: skip


def report(points: pd.DataFrame, alpha: float = ALPHA, excluded: str = "not counted") -> str:
    nl = chr(10)
    units = units_of(points)
    pooled, own = fit(units, alpha)
    cal = calibrated_high(points, pooled, own)
    lo = loco(points, alpha)
    w_a = cal / points["high"]
    lines = [
        "# v4 item C: upper-bound calibration, DEV preview",
        "",
        f"Tree `{_tree_state()}`. Split conformal, alpha = {alpha}, own factor for families with >= {MIN_CONFIGS} "
        "configurations, pooled otherwise. **Preview on the current models: the frozen artifact is computed once, on "
        "the final v4 models (pre-registration, Order 5).**",
        "",
        "## Factors",
        "",
        "| family | configurations | q | at sample max |",
        "|---|---|---|---|",
        f"| (pooled) | {pooled.n} | {pooled.q:.3f} | {pooled.at_max} |",
        *[f"| {f} | {x.n} | {x.q:.3f} | {x.at_max} |" for f, x in sorted(own.items())],
        "",
        "Configurations per family: "
        + ", ".join(f"{f} {n}" for f, n in units["family"].value_counts().items()),
        "",
        "## Dev results (v3 = model high; calibrated in sample; LOCO = factor refitted without the configuration)",
        "",
        "| source | high | points | configs | above high (points) | above high (configs) | median error | coverage | "
        "high/expected median | p90 | W(a) median high_cal/high_v3 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, sel in [("all", points.index), *[(s, points.index[points["source"] == s])
                                                 for s in points["source"].unique()]]:  # fmt: skip
        p = points.loc[sel]
        for label, h in (("v3", p["high"]), ("calibrated", cal.loc[sel]), ("LOCO", lo.loc[sel])):
            s = summary(p, h)
            wa = f"{w_a.loc[sel].median():.3f}" if label != "v3" else "1"
            lines.append(
                f"| {name} | {label} | {s['points']} | {s['configs']} | {s['above_pts']} ({s['above_pts_rate']:.1%}) | "
                f"{s['above_cfg']} ({s['above_cfg_rate']:.1%}) | {s['median_err']:.1%} | {s['coverage']:.1%} | "
                f"{s['width_med']:.2f} | {s['width_p90']:.2f} | {wa} |"
            )
    big = list(own)
    s_lo = summary(points, lo)
    fam_lo = {f: summary(points[points["family"] == f], lo[points["family"] == f]) for f in big}
    ok = (
        s_lo["above_pts_rate"] <= LOCO_BAR
        and s_lo["above_cfg_rate"] <= LOCO_BAR
        and all(
            x["above_pts_rate"] <= LOCO_BAR and x["above_cfg_rate"] <= LOCO_BAR
            for x in fam_lo.values()
        )
    )
    s_cal = summary(points, cal)
    lines += [
        "",
        "## Pre-registered dev criteria",
        "",
        f"* LOCO <= 2% above high per point and per configuration, pooled and per family with >= {MIN_CONFIGS} "
        f"configurations: **{'MET' if ok else 'FAILED'}** (pooled {s_lo['above_pts_rate']:.2%} of points, "
        f"{s_lo['above_cfg_rate']:.2%} of configurations"
        + "".join(
            f"; {f} {x['above_pts_rate']:.2%} / {x['above_cfg_rate']:.2%}"
            for f, x in fam_lo.items()
        )
        + ").",
        f"* W(a), DECIDING (amendment 1), points both v3 and v4 estimate ({len(points)}; on the current models "
        f"every point is shared): median (high_v4 / exp_v4) / (high_v3 / exp_v3) <= 1.30: {w_a.median():.3f} "
        f"(**{'MET' if w_a.median() <= 1.30 else 'FAILED'}**).",
        "* W(b), DECIDING only on points v3 does not estimate: 0 such points on the current models -> "
        "**INCONCLUSIVE** (it applies once v4 adds coverage).",
        f"* W(b) on all points, NOT deciding: median {s_cal['width_med']:.2f} (2.0), p90 {s_cal['width_p90']:.2f} "
        "(4.0). Known limitation: merge / read_csv width from policy B's Tier 0 high.",
        f"* Excluded from the residuals (pre-registered): {excluded}.",
        "",
    ]
    return nl.join(lines)


def artifact(points: pd.DataFrame, alpha: float = ALPHA) -> dict[str, Any]:
    pooled, own = fit(units_of(points), alpha)
    return {
        "version": 1,
        "procedure": "docs/benchmarks/phase8-preregistration.md, item C",
        "alpha": alpha,
        "min_configs": MIN_CONFIGS,
        "tree": _tree_state(),
        "pooled": {"q": pooled.q, "n": pooled.n, "at_max": pooled.at_max},
        "families": {f: {"q": x.q, "n": x.n, "at_max": x.at_max} for f, x in sorted(own.items())},
        "sources": sorted(points["source"].unique()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.upper_calibration")
    ap.add_argument(
        "--single", type=Path, required=True, help="dev single-operation results (re-predicted)"
    )
    ap.add_argument("--out", type=Path, required=True, help="markdown report")
    ap.add_argument(
        "--no-repredict", action="store_true", help="use cached multicell predictions only"
    )
    ap.add_argument(
        "--write", action="store_true", help="write the frozen artifact (ONCE, final v4 models)"
    )
    args = ap.parse_args(argv)
    from benchmarks.powerguard import power_record

    # refuses on battery: the re-predictions spawn processes with large inputs
    power_record(False, "dev")
    points = all_points(args.single, repredict=not args.no_repredict)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    excluded = ", ".join(f"{k} {v} cells" for k, v in sorted(EXCLUDED.items())) or "none"
    args.out.write_text(report(points, excluded=excluded), encoding="utf-8")
    print(args.out.read_text(encoding="utf-8"))
    if args.write:
        ARTIFACT.write_text(json.dumps(artifact(points), indent=1) + chr(10), encoding="utf-8")
        print(f"wrote {ARTIFACT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
