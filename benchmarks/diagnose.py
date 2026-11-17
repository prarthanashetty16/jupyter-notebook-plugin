"""Diagnose Tier 0 accuracy from DEVELOPMENT results (groups dev and exposed-v1 only).

    python -m benchmarks.diagnose <results_dir> --out docs/benchmarks/full-v3

Reads results through ``evaluate.load_joined``, which never touches the sealed test-v2 files, and
writes ``findings.md`` plus the CSVs behind each table. Nothing here changes a model.

Definitions
- fold = predicted / actual when >= 1 (over-prediction, shown +x), else -(actual / predicted)
  (under-prediction, shown -x). Only *valid* measurements (above the floors, stable spread) count.
- slope = log-log slope of actual (or predicted) value versus the point's size n (rows, or the
  matrix side for matmul, where cubic time gives 3). 1 is linear, > 1.15 is flagged superlinear.
  Time points under 20 ms and RAM points under 1 MiB are left out of slope fits (timer / page noise).
- Error structure per operation and metric (thresholds below):
    bias        = median of log10(fold-ratio) over valid points (shared, constant-factor part)
    data_spread = std over scenarios of the per-scenario median log10 ratio (how much the error
                  changes with the dataset configuration at the same operation)
    trend       = median over scenarios of the slope of log10 ratio vs log10 n (scaling mismatch)
  no dominant error: |bias| < log10(1.5) and data_spread < log10(1.5);
  data-dependent:    data_spread >= max(|bias|, log10(2));
  structural:        otherwise (scaling exponent if |trend| >= 0.10, else constant factor).
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.evaluate import Floors, load_joined, md_table
from benchmarks.split import DEV, EXPOSED

NO_ERROR = math.log10(1.5)
DATA_DEPENDENT = math.log10(2.0)
TREND = 0.10
SUPERLINEAR = 1.15
MIN_TIME_FOR_SLOPE = 0.02
MIN_RAM_FOR_SLOPE = 2**20
MB = 2**20


def fold(pred: pd.Series, actual: pd.Series) -> pd.Series:
    r = pred / actual
    out = np.where(r >= 1, r, -1.0 / r)
    return pd.Series(np.where((pred > 0) & (actual > 0), out, np.nan), index=pred.index)


def build_points(df: pd.DataFrame, tier: int = 0) -> pd.DataFrame:
    """One row per grid point with actual/predicted RAM and time and signed fold errors."""
    d = df[(df["tier"] == tier) & df["has_estimate"] & (df["status"] == "ok")].copy()
    out = pd.DataFrame(
        {
            "op": d["op"], "scenario": d["case"], "split": d["origin"] if "origin" in d else d["split"], "size": d["size"],
            "ram_actual_MB": d["ram_value"] / MB, "ram_pred_MB": d["ram_expected"] / MB,
            "ram_class": d["ram_class"], "time_actual_s": d["time_value"],
            "time_pred_s": d["time_expected"], "time_class": d["time_class"],
        }
    )  # fmt: skip
    out["ram_fold"] = fold(d["ram_expected"], d["ram_value"]).where(d["ram_class"] == "valid")
    out["time_fold"] = fold(d["time_expected"], d["time_value"]).where(d["time_class"] == "valid")
    out["worst_fold"] = out[["ram_fold", "time_fold"]].abs().max(axis=1)
    return out.sort_values("worst_fold", ascending=False, na_position="last").reset_index(drop=True)


def _loglog(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """(slope, R^2) of log10 y on log10 x; NaN if fewer than two points or no x range."""
    if len(x) < 2 or np.ptp(x) == 0:
        return math.nan, math.nan
    lx, ly = np.log10(x), np.log10(y)
    slope, icpt = np.polyfit(lx, ly, 1)
    ss_tot = float(((ly - ly.mean()) ** 2).sum())
    ss_res = float(((ly - (slope * lx + icpt)) ** 2).sum())
    return float(slope), (1 - ss_res / ss_tot) if ss_tot > 0 else math.nan


def scaling_table(pts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (op, scen), g in pts.groupby(["op", "scenario"]):
        row: dict[str, Any] = {"op": op, "scenario": scen, "points": len(g),
                               "sizes": f"{int(g['size'].min()):,}..{int(g['size'].max()):,}"}  # fmt: skip
        t = g[(g["time_actual_s"] >= MIN_TIME_FOR_SLOPE) & (g["time_pred_s"] > 0)]
        r = g[(g["ram_actual_MB"] * MB >= MIN_RAM_FOR_SLOPE) & (g["ram_pred_MB"] > 0)]
        row["time_pts"], row["ram_pts"] = len(t), len(r)
        row["time_slope_actual"], row["time_r2"] = _loglog(
            t["size"].to_numpy(float), t["time_actual_s"].to_numpy()
        )
        row["time_slope_pred"], _ = _loglog(t["size"].to_numpy(float), t["time_pred_s"].to_numpy())
        row["ram_slope_actual"], row["ram_r2"] = _loglog(
            r["size"].to_numpy(float), r["ram_actual_MB"].to_numpy()
        )
        row["ram_slope_pred"], _ = _loglog(r["size"].to_numpy(float), r["ram_pred_MB"].to_numpy())
        rows.append(row)
    return pd.DataFrame(rows)


def op_slopes(sc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for op, g in sc.groupby("op"):
        row = {"op": op, "scenarios": len(g)}
        for col in ("time_slope_actual", "time_slope_pred", "ram_slope_actual", "ram_slope_pred"):
            row[col] = g[col].median()
        limit = 3.0 * SUPERLINEAR if op == "operator.matmul" else SUPERLINEAR
        row["superlinear_time"] = bool(row["time_slope_actual"] > limit)
        rows.append(row)
    return pd.DataFrame(rows)


def error_structure(pts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for op, g in pts.groupby("op"):
        for metric in ("ram", "time"):
            v = g[g[f"{metric}_fold"].notna()].copy()
            if v.empty:
                continue
            v["lr"] = np.log10(
                np.where(v[f"{metric}_fold"] > 0, v[f"{metric}_fold"], 1 / -v[f"{metric}_fold"])
            )
            case_med = v.groupby("scenario")["lr"].median()
            bias = float(v["lr"].median())
            spread = float(case_med.std(ddof=0)) if len(case_med) >= 3 else math.nan
            trends = []
            for _, s in v.groupby("scenario"):
                if len(s) >= 3 and s["size"].nunique() >= 3:
                    trends.append(np.polyfit(np.log10(s["size"].astype(float)), s["lr"], 1)[0])
            trend = float(np.median(trends)) if trends else math.nan
            same = float((np.sign(case_med) == np.sign(bias)).mean()) if bias != 0 else math.nan
            origin = v["origin"] if "origin" in v else v["split"]
            dev = v[origin == DEV]["lr"]
            exp = v[origin == EXPOSED]["lr"]
            label, why = _classify(bias, spread, trend)
            rows.append(
                {"op": op, "metric": metric.upper(), "points": len(v), "scenarios": len(case_med),
                 "bias_fold": 10 ** abs(bias) * (1 if bias >= 0 else -1), "data_spread_log10": spread,
                 "trend_per_decade": trend, "sign_consistency": same,
                 "dev_bias_fold": _signed(dev.median()) if len(dev) else math.nan,
                 "exposed_bias_fold": _signed(exp.median()) if len(exp) else math.nan,
                 "classification": label, "evidence": why}
            )  # fmt: skip
    return pd.DataFrame(rows)


def _signed(log_ratio: float) -> float:
    return math.nan if pd.isna(log_ratio) else 10 ** abs(log_ratio) * (1 if log_ratio >= 0 else -1)


def _classify(bias: float, spread: float, trend: float) -> tuple[str, str]:
    mag = abs(bias)
    sp = 0.0 if math.isnan(spread) else spread
    bias_txt = f"median fold {_signed(bias):+.2f}"
    spread_txt = (
        "n/a (<3 scenarios)" if math.isnan(spread) else f"scenario spread x{10**spread:.2f}"
    )
    trend_txt = "" if math.isnan(trend) else f", size trend {trend:+.2f}/decade"
    why = f"{bias_txt}; {spread_txt}{trend_txt}"
    if mag < NO_ERROR and sp < NO_ERROR:
        return "no dominant error", why
    if sp >= max(mag, DATA_DEPENDENT):
        return "data-dependent", why
    if not math.isnan(trend) and abs(trend) >= TREND:
        return "structural (scaling exponent)", why
    return "structural (constant factor)", why


def read_csv_throughput(df: pd.DataFrame) -> pd.DataFrame:
    """Parse throughput per read_csv scenario and size (needs the cached CSV files on disk)."""
    rows = []
    d = df[(df["op"] == "pandas.read_csv") & (df["status"] == "ok") & df["time_value"].notna()]
    for _, r in d.drop_duplicates("point_id").iterrows():
        src = str(r.get("source", ""))
        if "'" not in src:
            continue
        path = src[src.index("'") + 1 : src.rindex("'")].replace("\\\\", "\\")
        if not os.path.exists(path):
            continue
        size = os.path.getsize(path)
        rows.append({"scenario": r["case"], "rows": int(r["size"]), "file_MB": size / 1e6,
                     "time_s": r["time_value"], "MB_per_s": size / r["time_value"] / 1e6})  # fmt: skip
    return pd.DataFrame(rows)


def _engine_line(df: pd.DataFrame) -> str:
    if "read_csv_engine" in df and df["read_csv_engine"].astype(str).str.len().gt(0).any():
        eng = sorted(set(df["read_csv_engine"].dropna().astype(str)) - {""})
        dt = sorted(set(df["read_csv_text_dtype"].dropna().astype(str)) - {""})
        return f"read_csv parser recorded in the result rows: {eng}, text dtype produced: {dt}"
    return "read_csv parser not recorded in these rows (run predates Phase 3d); verified separately"


def write_findings(
    results_dir: Path, out_dir: Path, floors: Floors | None = None, top: int = 25
) -> Path:
    floors = floors or Floors()
    df = load_joined(results_dir, floors)
    pts = build_points(df)
    scaling = scaling_table(pts)
    ops = op_slopes(scaling)
    struct = error_structure(pts)
    csv_tp = read_csv_throughput(df)
    out_dir.mkdir(parents=True, exist_ok=True)
    pts.to_csv(out_dir / "points_ratio.csv", index=False)
    scaling.to_csv(out_dir / "scaling_slopes.csv", index=False)
    struct.to_csv(out_dir / "error_structure.csv", index=False)
    csv_tp.to_csv(out_dir / "read_csv_throughput.csv", index=False)

    meta_path = results_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    n_by = (
        df.drop_duplicates("point_id")["origin" if "origin" in df else "split"]
        .value_counts()
        .to_dict()
    )
    lines = ["# Tier 0 diagnosis from development results\n"]
    lines.append(
        f"Source: `{results_dir.as_posix()}` (suite `{meta.get('suite', '?')}`, git "
        f"`{meta.get('git_commit', '?')}`). Groups used: dev and exposed-v1 only; the sealed test-v2 "
        f"split is never read. Points by group: {n_by}. Floors: RAM >= {floors.ram_bytes / MB:.0f} MiB, "
        f"time >= {floors.time_s * 1e3:.0f} ms, spread <= {floors.max_spread:.0%}. {_engine_line(df)}.\n"
    )
    lines.append("fold = predicted/actual, shown **+x** for over-prediction and **-x** for "
                 "under-prediction (x times too low). Only valid measurements get a fold.\n")  # fmt: skip

    lines.append("## 1. Error structure per operation (structural vs data-dependent)\n")
    lines.append(
        f"Rule: no dominant error if |bias| and scenario spread are both below x1.5; data-dependent if "
        f"scenario spread >= max(|bias|, x2); otherwise structural (scaling exponent if the log-ratio "
        f"size trend is >= {TREND}/decade, else a constant factor).\n"
    )
    cols = ["op", "metric", "points", "scenarios", "bias_fold", "data_spread_log10", "trend_per_decade",
            "dev_bias_fold", "exposed_bias_fold", "classification", "evidence"]  # fmt: skip
    lines.append(md_table(struct[[c for c in cols if c in struct]]))

    lines.append("## 2. Scaling: log-log slope of actual time and RAM versus n\n")
    lines.append(
        f"Per operation (median over scenarios); linear = 1, matmul n is the matrix side so cubic = 3. "
        f"`superlinear_time` = actual time slope above {SUPERLINEAR} (x3 for matmul).\n"
    )
    lines.append(md_table(ops))
    lines.append("Per scenario:\n")
    lines.append(md_table(scaling))

    lines.append("## 3. Largest errors, both directions\n")
    under = pts[(pts["ram_fold"] < 0) | (pts["time_fold"] < 0)].copy()
    under["worst_under"] = under[["ram_fold", "time_fold"]].min(axis=1)
    under = under.sort_values("worst_under").head(top)
    lines.append(f"### 3a. Under-predictions (actual above predicted), worst {top}\n")
    lines.append(md_table(under[["op", "scenario", "split", "size", "ram_actual_MB", "ram_pred_MB",
                                 "ram_fold", "time_actual_s", "time_pred_s", "time_fold"]]))  # fmt: skip
    lines.append("### 3b. Every valid point, sorted by worst error in either direction "
                 "(rows with a negative fold are under-predictions)\n")  # fmt: skip
    full = pts[pts["worst_fold"].notna()].copy()
    full["under"] = np.where((full["ram_fold"] < 0) | (full["time_fold"] < 0), "UNDER", "")
    lines.append(md_table(full[["op", "scenario", "split", "size", "ram_actual_MB", "ram_pred_MB",
                                "ram_fold", "time_actual_s", "time_pred_s", "time_fold", "under"]]))  # fmt: skip

    lines.append("## 4. read_csv parse throughput (plausibility check)\n")
    lines.append(
        md_table(csv_tp) if len(csv_tp) else "_CSV files not on disk; throughput not computed._\n"
    )
    path = out_dir / "findings.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.diagnose", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)  # fmt: skip
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(write_findings(args.results, args.out))


if __name__ == "__main__":
    main()
