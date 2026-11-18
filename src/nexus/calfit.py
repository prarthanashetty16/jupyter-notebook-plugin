"""Fit the time calibration artifact from benchmark results (pre-registered method, Phase 6).

Method (``docs/benchmarks/phase6-preregistration.md`` sections 3-4), per model and tier:

* residual ``m = exp(median ln(actual / expected))`` of the DERIVED expected time (the models
  recomputed from the stored features on this machine's profile);
* time range by split-conformal quantiles of ``r = ln(actual / (m * expected))`` at levels
  ``alpha / 2`` and ``1 - alpha / 2`` with the finite-sample correction, ``alpha = 0.10``; a model
  with fewer than ``MIN_CONFIGURATIONS`` configurations gets the GENERIC band (pooled over all
  models, ``alpha = 0.05``) and the flag;
* Tier 2: normalised scores ``s = ln(a / e) / ln(h / e)`` (above) or ``ln(e / a) / ln(e / l)``
  (below) of its own range; the range exponent is their corrected ``1 - alpha`` quantile.

Evaluation uses leave-one-configuration-out (LOCO): every quantity used for a configuration's
points is fitted without that configuration. The artifact ships the fit on all configurations.

CLI ``nexus-calibrate <results dir> [--out PATH] [--local]``: recompute the derived expected times
from the stored features, fit, write the artifact (``--local`` writes the user-local copy, which is
used only when ``NEXUS_CALIBRATION=local``; the packaged artifact is never overwritten by it).
Needs a source checkout (it reads results through ``benchmarks.evaluate.load_joined``, which
refuses protected splits).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ALPHA = 0.10
GENERIC_ALPHA = 0.05
MIN_CONFIGURATIONS = 8
ARTIFACT_FORMAT = 1
TARGET_COVERAGE = (0.88, 0.95)  # pre-registered target (b)
UNCALIBRATED_BAND = (0.25, 4.0)  # the models' own band, the fallback of (b)


# -- primitives --------------------------------------------------------------------------------
def conformal_bounds(r: Iterable[float], alpha: float) -> tuple[float, float]:
    """Finite-sample corrected empirical quantiles of ``r`` at ``alpha/2`` and ``1 - alpha/2``.

    With n residuals the upper bound is the ``ceil((n + 1)(1 - alpha/2))``-th smallest, the lower the
    ``floor((n + 1) alpha/2)``-th; when n is too small for that rank the extreme residual is used
    (the coverage guarantee then does not hold, which the report states via the flag).
    """
    x = np.sort(np.asarray(list(r), dtype=float))
    n = len(x)
    if n == 0:
        return (-math.inf, math.inf)
    k_hi = math.ceil((n + 1) * (1 - alpha / 2))
    k_lo = math.floor((n + 1) * alpha / 2)
    hi = x[min(k_hi, n) - 1]
    lo = x[max(k_lo, 1) - 1]
    return float(min(lo, 0.0)), float(max(hi, 0.0))  # the range always contains the estimate


def conformal_upper(s: Iterable[float], alpha: float) -> float:
    x = np.sort(np.asarray(list(s), dtype=float))
    n = len(x)
    if n == 0:
        return math.inf
    k = math.ceil((n + 1) * (1 - alpha))
    return float(x[min(k, n) - 1])


def tier2_score(actual: float, low: float, expected: float, high: float) -> float:
    """How far outside Tier 2's own range ``actual`` lies, in units of the range's half width (log)."""
    if actual >= expected:
        span = math.log(max(high, expected * (1 + 1e-9)) / expected)
        return math.log(actual / expected) / span
    span = math.log(expected / max(min(low, expected * (1 - 1e-9)), 1e-12))
    return math.log(expected / actual) / span


def residual_multiplier(r: Iterable[float]) -> float:
    vals = list(r)
    return float(math.exp(np.median(vals))) if vals else 1.0


# -- LOCO --------------------------------------------------------------------------------------
def loco_tier01(df: pd.DataFrame, use_residual: bool = True) -> pd.DataFrame:
    """LOCO multiplier and conformal range for every row (columns: model, tier, case, expected, actual).

    Adds ``m_loco``, ``exp_cal``, ``low_cal``, ``high_cal``, ``range_kind``.
    """
    out = df.copy()
    out["r_raw"] = np.log(out["actual"] / out["expected"])
    cols: dict[str, list[Any]] = {k: [] for k in ("m_loco", "low_cal", "high_cal", "range_kind")}
    for _, row in out.iterrows():
        same = out[(out["model"] == row["model"]) & (out["tier"] == row["tier"])]
        train = same[same["case"] != row["case"]]
        m = residual_multiplier(train["r_raw"]) if use_residual and len(train) else 1.0
        n_cfg = train["case"].nunique()
        if n_cfg >= MIN_CONFIGURATIONS - 1 and same["case"].nunique() >= MIN_CONFIGURATIONS:
            r = train["r_raw"] - math.log(m)
            lo, hi = conformal_bounds(r, ALPHA)
            kind = "per-operation"
        else:
            pool = out[(out["tier"] == row["tier"]) & (out["case"] != row["case"])]
            ms = pool.groupby("model")["r_raw"].transform("median") if use_residual else 0.0
            lo, hi = conformal_bounds(pool["r_raw"] - ms, GENERIC_ALPHA)
            kind = "generic"
        e = row["expected"] * m
        cols["m_loco"].append(m)
        cols["low_cal"].append(e * math.exp(lo))
        cols["high_cal"].append(e * math.exp(hi))
        cols["range_kind"].append(kind)
    for k, v in cols.items():
        out[k] = v
    out["exp_cal"] = out["expected"] * out["m_loco"]
    return out


def loco_tier2(df: pd.DataFrame) -> pd.DataFrame:
    """LOCO calibrated Tier 2 ranges (columns: model, case, low, expected, high, actual)."""
    out = df.copy()
    out["score"] = [
        tier2_score(a, lo, e, hi)
        for a, lo, e, hi in zip(
            out["actual"], out["low"], out["expected"], out["high"], strict=True
        )
    ]
    qs, kinds = [], []
    for _, row in out.iterrows():
        same = out[out["model"] == row["model"]]
        train = same[same["case"] != row["case"]]
        if same["case"].nunique() >= MIN_CONFIGURATIONS:
            q, kind = conformal_upper(train["score"], ALPHA), "per-operation"
        else:
            q = conformal_upper(out[out["case"] != row["case"]]["score"], GENERIC_ALPHA)
            kind = "generic"
        qs.append(max(q, 1e-3))
        kinds.append(kind)
    out["q_loco"], out["range_kind"] = qs, kinds
    out["low_cal"] = out["expected"] * (out["low"] / out["expected"]) ** out["q_loco"]
    out["high_cal"] = out["expected"] * (out["high"] / out["expected"]) ** out["q_loco"]
    return out


# -- the shipped fit (all configurations) -------------------------------------------------------
def fit_tier01(
    df: pd.DataFrame, use_residual: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Per (tier, model) residual and quantiles on ALL configurations, plus the generic band."""
    d = df.assign(r_raw=np.log(df["actual"] / df["expected"]))
    entries: dict[str, Any] = {}
    generic: dict[str, Any] = {}
    for tier, dt in d.groupby("tier"):
        tier_key = str(int(tier))
        meds = dt.groupby("model")["r_raw"].transform("median") if use_residual else 0.0
        glo, ghi = conformal_bounds(dt["r_raw"] - meds, GENERIC_ALPHA)
        generic[tier_key] = {"q_lo": glo, "q_hi": ghi, "alpha": GENERIC_ALPHA, "n_points": len(dt)}
        entries[tier_key] = {}
        for model, g in dt.groupby("model"):
            m = residual_multiplier(g["r_raw"]) if use_residual else 1.0
            n_cfg = int(g["case"].nunique())
            entry = {
                "residual": m,
                "n_points": len(g),
                "n_configurations": n_cfg,
                "range": "per-operation" if n_cfg >= MIN_CONFIGURATIONS else "generic",
            }
            if n_cfg >= MIN_CONFIGURATIONS:
                lo, hi = conformal_bounds(g["r_raw"] - math.log(m), ALPHA)
                entry.update(q_lo=lo, q_hi=hi, alpha=ALPHA)
            entries[tier_key][model] = entry
    return entries, generic


def _distance(cov: float) -> float:
    lo, hi = TARGET_COVERAGE
    return 0.0 if lo <= cov <= hi else min(abs(cov - lo), abs(cov - hi))


def range_decisions(df: pd.DataFrame, use_residual: bool = True) -> dict[str, dict[str, Any]]:
    """Pre-registered fallback of target (b), decided from LOCO coverage on the given data.

    A model calibrated per operation whose LOCO conformal coverage is outside [88%, 95%] keeps the
    uncalibrated 0.25x .. 4x band around its (residual-corrected) expected time when that band's
    LOCO coverage is closer to the target; otherwise the conformal range is shipped anyway.
    """
    out: dict[str, dict[str, Any]] = {}
    for tier, dt in df.groupby("tier"):
        loco = loco_tier01(dt, use_residual=use_residual)
        out[str(int(tier))] = {}
        for model, g in loco.groupby("model"):
            if g["range_kind"].iloc[0] != "per-operation":
                continue
            a, e = g["actual"], g["exp_cal"]
            conf = float(((g["low_cal"] <= a) & (a <= g["high_cal"])).mean())
            band = float(((UNCALIBRATED_BAND[0] * e <= a) & (a <= UNCALIBRATED_BAND[1] * e)).mean())
            use_band = _distance(conf) > _distance(band)
            out[str(int(tier))][model] = {
                "loco_coverage_conformal": conf,
                "loco_coverage_band": band,
                "range": "band" if use_band else "per-operation",
            }
    return out


def fit_tier2(df: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    d = df.assign(
        score=[
            tier2_score(a, lo, e, hi)
            for a, lo, e, hi in zip(
                df["actual"], df["low"], df["expected"], df["high"], strict=True
            )
        ]
    )
    entries = {}
    for op, g in d.groupby("op"):  # keyed by operation: what the controller passes
        n_cfg = int(g["case"].nunique())
        entry: dict[str, Any] = {"n_points": len(g), "n_configurations": n_cfg}
        if n_cfg >= MIN_CONFIGURATIONS:
            entry.update(q=max(conformal_upper(g["score"], ALPHA), 1e-3), range="per-operation")
        else:
            entry.update(range="generic")
        entries[op] = entry
    generic = {"q": max(conformal_upper(d["score"], GENERIC_ALPHA), 1e-3), "alpha": GENERIC_ALPHA}
    return entries, generic


# -- data --------------------------------------------------------------------------------------
def derived_expected(rows: pd.DataFrame) -> list[float | None]:
    """Recompute each stored prediction's expected time with the current models and profile."""
    from nexus.models.base import NoEstimateError
    from nexus.pipeline import load_builtin_models
    from nexus.registry import default_registry

    load_builtin_models()
    models = {m.name: m for m in default_registry}
    out: list[float | None] = []
    for model, tier, feats in zip(rows["model"], rows["tier"], rows["features"], strict=True):
        try:
            f = json.loads(feats)
            m = models[model]
            try:
                est = m.estimate(f, int(tier))
            except NoEstimateError:
                est = m.estimate(f, 0)
            out.append(float(est.time_expected))
        except Exception:
            out.append(None)
    return out


def load_time_rows(results: Path) -> pd.DataFrame:
    """Dev rows with a valid time actual and a prediction (Tier 0 / 1 / 2), from a results folder."""
    from benchmarks.evaluate import load_joined  # dev only; refuses protected cases

    df = load_joined(results)
    d = df[df["has_estimate"] & (df["time_class"] == "valid")].copy()
    d = d.rename(columns={"time_value": "actual"})
    return d


def data_hash(results: Path) -> str:
    h = hashlib.sha256()
    for name in ("actuals.csv", "predictions.csv"):
        p = results / name
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _fitted_list(
    entries: dict[str, Any], t2: dict[str, Any], t2g: dict[str, Any] | None, use_residual: bool
) -> list[dict[str, str]]:
    """Every fitted parameter of the artifact and what it was fitted on."""
    fitted = []
    for tier_key, models in entries.items():
        for model, e in models.items():
            on = f"{e['n_points']} valid dev time points in {e['n_configurations']} configurations"
            if use_residual:
                fitted.append({"name": f"tier{tier_key}.{model}.residual", "fitted_on": on})
            if e["range"] == "per-operation":
                fitted.append({"name": f"tier{tier_key}.{model}.q_lo/q_hi", "fitted_on": on})
            elif e["range"] == "band":
                fitted.append({"name": f"tier{tier_key}.{model}.range=band (LOCO coverage rule)",
                               "fitted_on": on})  # fmt: skip
        fitted.append(
            {"name": f"tier{tier_key}.generic.q_lo/q_hi", "fitted_on": "all models of the tier"}
        )
    for model, e in t2.items():
        if e["range"] == "per-operation":
            on = f"{e['n_points']} accepted Tier 2 time fits in {e['n_configurations']} configurations"
            fitted.append({"name": f"tier2.{model}.q", "fitted_on": on})
    if t2g is not None:
        fitted.append({"name": "tier2.generic.q", "fitted_on": "all accepted Tier 2 time fits"})
    return fitted


def build_artifact(
    tier01: pd.DataFrame,
    tier2: pd.DataFrame | None,
    *,
    results: Path,
    tier2_results: Path | None,
    use_residual: bool,
    selected: str,
) -> dict[str, Any]:
    """The calibration artifact (JSON-serialisable) with provenance."""
    from nexus.machine import machine

    prof = machine()
    entries, generic = fit_tier01(tier01, use_residual=use_residual)
    decisions = range_decisions(tier01, use_residual=use_residual)
    for tier_key, models in decisions.items():
        for model, dec in models.items():
            entries[tier_key][model].update(dec)
            if dec["range"] == "band":
                entries[tier_key][model]["q_lo"] = float(np.log(UNCALIBRATED_BAND[0]))
                entries[tier_key][model]["q_hi"] = float(np.log(UNCALIBRATED_BAND[1]))
    t2, t2g = fit_tier2(tier2) if tier2 is not None and len(tier2) else ({}, None)
    fitted = _fitted_list(entries, t2, t2g, use_residual)
    pv = pd.__version__.split(".")
    return {
        "format": ARTIFACT_FORMAT,
        "name": "calibration-v1",
        "created": time.strftime("%Y-%m-%d"),
        "git_commit": _git_commit(),
        "selected_candidate": selected,
        "data": {
            "results": str(results).replace("\\", "/"),
            "sha256_16": data_hash(results),
            "tier2_results": str(tier2_results).replace("\\", "/") if tier2_results else None,
            "tier2_sha256_16": data_hash(tier2_results) if tier2_results else None,
            "points_tier01": len(tier01),
            "configurations": int(tier01["case"].nunique()),
            "split": "dev (benchmarks/split.json v6)",
        },
        "machine_profile_id": prof.profile_id,
        "machine_profile_meta": prof.meta,
        "versions": {
            "python": prof.meta.get("python"),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "validated_pandas": [f"{pv[0]}.{pv[1]}"],
        "alpha": ALPHA,
        "generic_alpha": GENERIC_ALPHA,
        "min_configurations": MIN_CONFIGURATIONS,
        "tier01": entries,
        "tier01_generic": generic,
        "tier2": t2,
        "tier2_generic": t2g,
        "fitted_parameters": fitted,
    }


def tier01_frame(rows: pd.DataFrame) -> pd.DataFrame:
    d = rows[rows["tier"].isin([0, 1])].copy()
    d["expected"] = derived_expected(d)
    d = d[d["expected"].notna() & (d["expected"] > 0)]
    return d[["point_id", "model", "op", "tier", "case", "size", "input_bytes", "features",
              "expected", "actual"]].reset_index(drop=True)  # fmt: skip


def tier2_frame(rows: pd.DataFrame) -> pd.DataFrame:
    """Tier 2 rows whose time came from an accepted dry-run fit."""
    d = rows[rows["tier"] == 2].copy()
    ok = []
    for feats in d["features"]:
        try:
            t2 = json.loads(feats).get("tier2") or {}
            fit = t2.get("time") or {}
            ok.append(bool(fit.get("ok")))
        except ValueError:
            ok.append(False)
    d = d[ok]
    d = d.rename(columns={"time_low": "low", "time_expected": "expected", "time_high": "high"})
    return d[["point_id", "model", "op", "case", "size", "input_bytes", "low", "expected", "high",
              "actual"]].reset_index(drop=True)  # fmt: skip


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nexus-calibrate", description=__doc__)
    parser.add_argument("results", type=Path, help="results folder with dev Tier 0/1 predictions")
    parser.add_argument("--tier2-results", type=Path, help="results folder with Tier 2 predictions")
    parser.add_argument("--out", type=Path, help="artifact path (default: the user-local file)")
    parser.add_argument("--no-residual", action="store_true", help="candidate D (no residual)")
    parser.add_argument(
        "--local", action="store_true", help="write the user-local artifact (opt-in, never shipped)"
    )
    args = parser.parse_args(argv)
    from nexus import timecal

    rows = load_time_rows(args.results)
    t01 = tier01_frame(rows)
    t2 = tier2_frame(load_time_rows(args.tier2_results)) if args.tier2_results else None
    art = build_artifact(
        t01, t2, results=args.results, tier2_results=args.tier2_results,
        use_residual=not args.no_residual, selected="D" if args.no_residual else "D+m",
    )  # fmt: skip
    out = args.out or (timecal.local_artifact_path() if args.local else None)
    if out is None:
        parser.error("give --out PATH or --local")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, indent=1, default=str))
    print(f"wrote {out} ({len(art['fitted_parameters'])} fitted parameters)")


if __name__ == "__main__":
    main()
