"""Before/after comparison of two benchmark runs (e.g. v1 polling instrument vs v2 OS-peak).

Reads each run's ``metrics_by_op.csv`` (ALL rows give the pooled figures). v1 results predate the
censored/excluded classes: for v1, ``ram_n``/``time_n`` are the points above the old 1 MiB/10 ms
validity floor and the remainder are shown as *below old floor* in the 'excluded' column.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from benchmarks.evaluate import PCT, md_table


def _pooled(path: Path, total_points: int | None) -> dict[str, Any]:
    df = pd.read_csv(path / "metrics_by_op.csv")
    row = df[(df["op"] == "ALL") & (df["tier"] == 0)].iloc[0]
    out: dict[str, Any] = {"points": int(row["points"])}
    for m in ("ram", "time"):
        n = int(row.get(f"{m}_n", 0) or 0)
        out[f"{m}_valid"] = n
        if f"{m}_valid" in row and not pd.isna(row.get(f"{m}_censored", math.nan)):
            out[f"{m}_censored"] = int(row[f"{m}_censored"])
            out[f"{m}_excluded"] = int(row[f"{m}_excluded"])
        else:
            out[f"{m}_censored"] = "n/a"
            out[f"{m}_excluded"] = int(row["points"]) - n  # v1: below the old validity floor
        for k in ("err_med", "err_p90", "bias", "cov", "width"):
            out[f"{m}_{k}"] = row.get(f"{m}_{k}", math.nan)
    return out


def pooled_table(before: Path, after: Path) -> pd.DataFrame:
    rows = []
    for metric in ("ram", "time"):
        for label, path in (("before", before), ("after", after)):
            p = _pooled(path, None)
            rows.append(
                {
                    "metric": metric.upper(), "run": label, "points": p["points"],
                    "valid": p[f"{metric}_valid"], "censored": p[f"{metric}_censored"],
                    "excluded": p[f"{metric}_excluded"], "median_err": p[f"{metric}_err_med"],
                    "p90_err": p[f"{metric}_err_p90"], "bias": p[f"{metric}_bias"],
                    "coverage": p[f"{metric}_cov"], "width": p[f"{metric}_width"],
                }
            )  # fmt: skip
    return pd.DataFrame(rows)


def per_op_table(before: Path, after: Path, metric: str) -> pd.DataFrame:
    a = pd.read_csv(before / "metrics_by_op.csv")
    b = pd.read_csv(after / "metrics_by_op.csv")
    a, b = a[a["tier"] == 0], b[b["tier"] == 0]
    cols = [f"{metric}_bias", f"{metric}_cov", f"{metric}_n"]
    merged = a[["op", *[c for c in cols if c in a]]].merge(
        b[["op", *[c for c in cols if c in b]]], on="op", how="outer", suffixes=("_v1", "_v2")
    )
    bias1, bias2 = merged.get(f"{metric}_bias_v1"), merged.get(f"{metric}_bias_v2")
    merged["verdict"] = [_verdict(x, y) for x, y in zip(bias1, bias2, strict=False)]
    return merged


def _verdict(before: float, after: float) -> str:
    if pd.isna(after):
        return "no valid v2 points"
    if pd.isna(before):
        return "newly measurable"
    good = lambda b: 0.5 <= b <= 2.0  # noqa: E731  within 2x either way
    if good(before) and good(after):
        return "unchanged (ok)"
    if not good(before) and not good(after):
        return "unchanged (bad)"
    return "now ok" if good(after) else "now bad"


def calibration_table(after: Path, uncalibrated: Path) -> pd.DataFrame:
    """Time accuracy on the SAME v2 measurements with default vs calibrated throughputs."""
    rows = []
    for label, path in (("default constants", uncalibrated), ("calibrated constants", after)):
        df = pd.read_csv(path / "metrics_by_op.csv")
        r = df[(df["op"] == "ALL") & (df["tier"] == 0)].iloc[0]
        rows.append({"time model": label, "valid": int(r["time_n"]), "median_err": r["time_err_med"],
                     "p90_err": r["time_err_p90"], "bias": r["time_bias"], "coverage": r["time_cov"]})  # fmt: skip
    return pd.DataFrame(rows)


def write_comparison(
    before: Path, after: Path, out: Path, uncalibrated: Path | None = None
) -> Path:
    lines = ["# Before/after: measurement instrument v1 (polling) vs v2 (OS peak + disk setup)\n"]
    lines.append("## Pooled Tier 0 accuracy\n")
    lines.append(
        md_table(pooled_table(before, after), ("median_err", "p90_err", "coverage", "width"))
    )
    for metric in ("ram", "time"):
        lines.append(f"\n## Per operation: {metric.upper()} bias (expected/actual) and coverage\n")
        lines.append(
            md_table(per_op_table(before, after, metric), (f"{metric}_cov_v1", f"{metric}_cov_v2"))
        )
    if uncalibrated is not None:
        lines.append("\n## Time: effect of calibration alone (same v2 measurements)\n")
        lines.append(
            md_table(calibration_table(after, uncalibrated), ("median_err", "p90_err", "coverage"))
        )
    lines.append(
        "\nVerdict thresholds: bias within 0.5x-2x counts as ok. v1 numbers came from the "
        "unreliable polling instrument; v2 numbers are the provisional-but-trustworthy ones.\n"
    )
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    if len(sys.argv) not in (4, 5):
        raise SystemExit(
            "usage: python -m benchmarks.compare <before> <after> <out.md> [<uncalibrated>]"
        )
    extra = Path(sys.argv[4]) if len(sys.argv) == 5 else None
    print(write_comparison(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), extra))


if __name__ == "__main__":
    main()
    _ = PCT
