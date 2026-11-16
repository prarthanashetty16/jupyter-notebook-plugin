"""Score predictions against measurements; write CSVs, a markdown report and figures.

Definitions (all stated again in the report):
- RAM = *incremental* peak resident memory during the operation (see ``nexus.measure``).
- relative error = |expected - actual| / actual (median and p90 over valid points).
- bias = median(expected / actual); > 1 over-predicts, < 1 under-predicts.
- coverage = share of points whose actual value lies inside the predicted [low, high].
- width = mean (high - low) / expected.
- validity filters (measurement reliability, not tuning): RAM needs actual >= MIN_RAM_BYTES and
  time needs actual >= MIN_TIME_S, because polled RSS and timer noise dominate below that.
  Excluded counts are reported.
- OOM warning: for a simulated available-memory limit L, a point is *positive* if
  input_bytes + actual peak > L; NEXUS *warns* if inspected input bytes + predicted RAM (the
  ``high`` or ``expected`` value) > L. Points killed by the harness memory cap count as positive
  for L <= cap. Points without an estimate never warn.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

MIN_RAM_BYTES = 2**20
MIN_TIME_S = 0.01
OOM_LIMITS_MB = (64, 128, 256, 512, 1024, 2048, 4096)
BUDGET_S = 0.25


def _read_last(path: Path, key: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.drop_duplicates(subset=key, keep="last").reset_index(drop=True)


def load_joined(results_dir: Path) -> pd.DataFrame:
    """One row per (grid point, tier); points with no prediction run have tier NaN."""
    actuals = _read_last(results_dir / "actuals.csv", ["point_id"])
    preds_path = results_dir / "predictions.csv"
    preds = (
        _read_last(preds_path, ["point_id", "tier"])
        if preds_path.exists()
        else pd.DataFrame(columns=["point_id", "tier"])
    )
    preds = preds.rename(columns={"status": "pred_status", "error": "pred_error"})
    df = actuals.merge(preds, on="point_id", how="left")
    numeric = [
        "size", "peak_bytes", "baseline_bytes", "time_s", "input_bytes", "out_rows", "out_bytes",
        "cap_bytes", "tier", "ram_low", "ram_expected", "ram_high", "time_low", "time_expected",
        "time_high", "confidence", "overhead_cold_s", "overhead_warm_s", "analysis_peak_bytes",
        "inspected_bytes", "repeats_ok",
    ]  # fmt: skip
    for col in numeric:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["has_estimate"] = df["has_estimate"].fillna("False").astype(str).eq("True")
    return df


def _accuracy(g: pd.DataFrame, min_ram: float, min_time: float) -> dict[str, Any]:
    est = g[g["has_estimate"]]
    out: dict[str, Any] = {"points": len(g), "estimated": len(est)}
    specs = (
        (
            "ram",
            est[est["peak_bytes"] >= min_ram],
            "peak_bytes",
            "ram_low",
            "ram_expected",
            "ram_high",
        ),
        (
            "time",
            est[est["time_s"] >= min_time],
            "time_s",
            "time_low",
            "time_expected",
            "time_high",
        ),
    )
    for name, sub, actual, lo, ex, hi in specs:
        out[f"{name}_n"] = len(sub)
        if len(sub) == 0:
            continue
        a = sub[actual]
        err = (sub[ex] - a).abs() / a
        out[f"{name}_err_med"] = err.median()
        out[f"{name}_err_p90"] = err.quantile(0.9)
        out[f"{name}_bias"] = (sub[ex] / a).median()
        out[f"{name}_cov"] = ((sub[lo] <= a) & (a <= sub[hi])).mean()
        out[f"{name}_above_high"] = (a > sub[hi]).mean()
        out[f"{name}_below_low"] = (a < sub[lo]).mean()
        out[f"{name}_width"] = ((sub[hi] - sub[lo]) / sub[ex].where(sub[ex] > 0)).mean()
    return out


def accuracy_table(
    df: pd.DataFrame, by: list[str], min_ram: float = MIN_RAM_BYTES, min_time: float = MIN_TIME_S
) -> pd.DataFrame:
    """Accuracy metrics per group of ok-actual points that had a prediction run."""
    ok = df[(df["status"] == "ok") & df["tier"].notna()]
    rows = []
    for key, g in ok.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key, strict=True)), **_accuracy(g, min_ram, min_time)})
    return pd.DataFrame(rows)


def oom_table(
    df: pd.DataFrame, tier: int, limits_mb: tuple[int, ...] = OOM_LIMITS_MB
) -> pd.DataFrame:
    d = df[(df["tier"] == tier) & (df["pred_status"] == "ok")]
    d = d[d["status"].isin(["ok", "memory_limit"])]
    rows = []
    for limit_mb in limits_mb:
        limit = limit_mb * 2**20
        killed = d["status"] == "memory_limit"
        valid = d[(~killed) | (d["cap_bytes"] >= limit)]
        killed_v = valid["status"] == "memory_limit"
        footprint = valid["input_bytes"].fillna(valid["inspected_bytes"]) + valid["peak_bytes"]
        positive = killed_v | (footprint > limit)
        for rule, col in (("high", "ram_high"), ("expected", "ram_expected")):
            pred = valid["inspected_bytes"] + valid[col]
            warn = valid["has_estimate"] & (pred > limit)
            tp = int((warn & positive).sum())
            fp = int((warn & ~positive).sum())
            fn = int((~warn & positive).sum())
            tn = int((~warn & ~positive).sum())
            rows.append(
                {
                    "limit_mb": limit_mb, "rule": rule, "positives": tp + fn, "tp": tp, "fp": fp,
                    "fn": fn, "tn": tn,
                    "precision": tp / (tp + fp) if tp + fp else math.nan,
                    "recall": tp / (tp + fn) if tp + fn else math.nan,
                }
            )  # fmt: skip
    return pd.DataFrame(rows)


def overhead_table(df: pd.DataFrame, tier: int) -> pd.DataFrame:
    d = df[(df["tier"] == tier) & (df["pred_status"] == "ok")]
    rows = []
    for op, g in list(d.groupby("op")) + [("ALL", d)]:
        rows.append(
            {
                "op": op, "n": len(g),
                "cold_med_ms": g["overhead_cold_s"].median() * 1e3,
                "cold_p90_ms": g["overhead_cold_s"].quantile(0.9) * 1e3,
                "warm_med_ms": g["overhead_warm_s"].median() * 1e3,
                "warm_max_ms": g["overhead_warm_s"].max() * 1e3,
                "over_budget": int((g["overhead_cold_s"] > BUDGET_S).sum()),
                "analysis_peak_MB_med": g["analysis_peak_bytes"].median() / 2**20,
            }
        )  # fmt: skip
    return pd.DataFrame(rows)


def _fmt(v: Any, pct: bool = False) -> str:
    if isinstance(v, (float, np.floating)):
        if math.isnan(v):
            return "–"
        if pct:
            return f"{v * 100:.0f}%"
        return f"{v:.2f}" if abs(v) < 100 else f"{v:.0f}"
    return str(v)


def md_table(df: pd.DataFrame, pct: tuple[str, ...] = ()) -> str:
    if df.empty:
        return "_no data_\n"
    head = "| " + " | ".join(df.columns) + " |\n|" + "|".join("---" for _ in df.columns) + "|\n"
    body = ""
    for _, row in df.iterrows():
        body += "| " + " | ".join(_fmt(row[c], c in pct) for c in df.columns) + " |\n"
    return head + body


PCT = ("ram_err_med", "ram_err_p90", "time_err_med", "time_err_p90", "ram_cov", "time_cov",
       "ram_above_high", "ram_below_low", "time_above_high", "time_below_low", "ram_width",
       "time_width", "precision", "recall")  # fmt: skip


def _select(t: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return t[[c for c in cols if c in t.columns]]


def make_figures(df: pd.DataFrame, out_dir: Path, tier: int) -> list[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    d = df[(df["status"] == "ok") & (df["tier"] == tier) & df["has_estimate"]]
    written = []
    for name, actual, lo, ex, hi, floor, unit in (
        ("ram", "peak_bytes", "ram_low", "ram_expected", "ram_high", MIN_RAM_BYTES, "bytes"),
        ("time", "time_s", "time_low", "time_expected", "time_high", MIN_TIME_S, "seconds"),
    ):
        sub = d[d[actual] >= floor]
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(7, 6))
        for op, g in sub.groupby("op"):
            yerr = np.array([(g[ex] - g[lo]).clip(lower=0), (g[hi] - g[ex]).clip(lower=0)])
            ax.errorbar(g[actual], g[ex], yerr=yerr, fmt="o", ms=3.5, lw=0.5, alpha=0.7, label=op)
        lims = [sub[actual].min() * 0.5, sub[actual].max() * 2]
        ax.plot(lims, lims, "k-", lw=0.8)
        ax.plot(lims, [x * 2 for x in lims], "k:", lw=0.6)
        ax.plot(lims, [x / 2 for x in lims], "k:", lw=0.6)
        ax.set(xscale="log", yscale="log", xlabel=f"actual ({unit})", ylabel=f"predicted ({unit})")
        ax.set_title(f"Tier {tier}: predicted vs actual {name} (bars = [low, high]; dotted = 2x)")
        ax.legend(fontsize=7)
        fig.tight_layout()
        fname = f"fig_pred_vs_actual_{name}_tier{tier}.png"
        fig.savefig(out_dir / fname, dpi=130)
        plt.close(fig)
        written.append(fname)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for ax, name, actual, ex, floor in (
        (axes[0], "RAM", "peak_bytes", "ram_expected", MIN_RAM_BYTES),
        (axes[1], "time", "time_s", "time_expected", MIN_TIME_S),
    ):
        sub = d[(d[actual] >= floor) & (d[ex] > 0)]
        groups = [(op, np.log10(g[ex] / g[actual])) for op, g in sub.groupby("op")]
        if groups:
            ax.boxplot([x[1] for x in groups], tick_labels=[x[0] for x in groups])
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylabel("log10(predicted / actual)   (+1 = 10x too high)")
        ax.set_title(f"Tier {tier}: {name} error by operation")
        ax.tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fname = f"fig_error_by_op_tier{tier}.png"
    fig.savefig(out_dir / fname, dpi=130)
    plt.close(fig)
    written.append(fname)

    acc = accuracy_table(df, ["tier", "op"])
    acc = acc[acc["tier"] == tier]
    if not acc.empty:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        x = np.arange(len(acc))
        ax.bar(x - 0.2, acc["ram_cov"].fillna(0), 0.4, label="RAM")
        ax.bar(x + 0.2, acc["time_cov"].fillna(0), 0.4, label="time")
        ax.set_xticks(x, acc["op"], rotation=60, ha="right")
        ax.set(ylim=(0, 1.05), ylabel="coverage of [low, high]", title=f"Tier {tier}: coverage")
        ax.axhline(0.9, color="gray", ls=":", lw=0.8)
        ax.legend()
        fig.tight_layout()
        fname = f"fig_coverage_by_op_tier{tier}.png"
        fig.savefig(out_dir / fname, dpi=130)
        plt.close(fig)
        written.append(fname)
    return written


CAVEATS = """\
- RAM is *incremental peak RSS* polled every ~2 ms from the parent process. Spikes shorter than
  that can be missed; below 1 MiB the number is allocator/page noise and is excluded.
- RSS counts resident pages only: lazily allocated memory is invisible until touched, and memory
  freed during dataset construction that the allocator kept can be reused by the operation without
  raising RSS (under-measurement). Windows reports working set.
- Time is wall-clock around the single call inside a fresh process (cold caches for first-touch
  data are included; no warm-up). Median of the repeats; the raw repeats are in `actuals.csv`.
- Datasets are synthetic (see `benchmarks/datasets.py`); real-world value distributions, dtype
  mixes and file layouts will differ. Phase 8 covers real data.
- The Tier 0 constants were fixed before any result was seen; nothing has been tuned.
"""


def write_report(results_dir: Path, tiers: list[int] | None = None) -> Path:
    df = load_joined(results_dir)
    meta_path = results_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    tiers = tiers or sorted(int(t) for t in df["tier"].dropna().unique())
    acc_op = accuracy_table(df, ["tier", "op"])
    acc_all = accuracy_table(df.assign(op="ALL"), ["tier", "op"])
    acc_case = accuracy_table(df, ["tier", "op", "case"])
    acc_op_all = pd.concat([acc_op, acc_all], ignore_index=True)
    acc_op_all.to_csv(results_dir / "metrics_by_op.csv", index=False)
    acc_case.to_csv(results_dir / "metrics_by_case.csv", index=False)
    df.to_csv(results_dir / "points_joined.csv", index=False)

    status = df.drop_duplicates("point_id")["status"].value_counts().to_dict()
    lines = [f"# NEXUS benchmark report: `{meta.get('suite', results_dir.name)}`\n"]
    lines.append(
        f"Platform {meta.get('platform', '?')}, Python {meta.get('python', '?')}, pandas "
        f"{meta.get('pandas', '?')}, numpy {meta.get('numpy', '?')}, {meta.get('cpu_count', '?')} "
        f"logical CPUs, git `{meta.get('git_commit', '?')}`. Memory cap per child process: "
        f"{meta.get('cap_bytes', 0) / 2**20:.0f} MB.\n"
    )
    lines.append(f"Grid points by outcome: {status}.\n")
    lines.append(
        f"Validity filters: RAM points need actual >= {MIN_RAM_BYTES / 2**20:.0f} MiB, time "
        f"points need actual >= {MIN_TIME_S * 1e3:.0f} ms. Percentages below are of valid points.\n"
    )
    for tier in tiers:
        lines.append(f"\n## Tier {tier}\n")
        t = acc_op_all[acc_op_all["tier"] == tier]
        lines.append("### Estimate availability and sample sizes\n")
        lines.append(md_table(_select(t, ["op", "points", "estimated", "ram_n", "time_n"])))
        lines.append("### RAM accuracy\n")
        lines.append(md_table(_select(t, ["op", "ram_n", "ram_err_med", "ram_err_p90", "ram_bias",
                                          "ram_cov", "ram_above_high", "ram_below_low",
                                          "ram_width"]), PCT))  # fmt: skip
        lines.append("### Time accuracy\n")
        lines.append(md_table(_select(t, ["op", "time_n", "time_err_med", "time_err_p90",
                                          "time_bias", "time_cov", "time_above_high",
                                          "time_below_low", "time_width"]), PCT))  # fmt: skip
        lines.append(
            "`above_high` = actual exceeded the predicted high (under-prediction beyond the "
            "range); `below_low` = actual fell under the predicted low. bias = median(expected / actual).\n"
        )
        lines.append("### Per case (variant) detail\n")
        c = acc_case[acc_case["tier"] == tier]
        lines.append(md_table(_select(c, ["case", "ram_n", "ram_bias", "ram_cov", "time_n",
                                          "time_bias", "time_cov"]), PCT))  # fmt: skip
        lines.append("### OOM warnings (simulated memory limits)\n")
        oom = oom_table(df, tier)
        oom.to_csv(results_dir / f"oom_tier{tier}.csv", index=False)
        lines.append(md_table(oom, PCT))
        lines.append("### Analysis overhead (budget 250 ms)\n")
        lines.append(md_table(overhead_table(df, tier)))
        figs = make_figures(df, results_dir, tier)
        if figs:
            lines.append("### Figures\n")
            lines += [f"![{f}]({f})\n" for f in figs]
        worst = df[(df["tier"] == tier) & df["has_estimate"] & (df["status"] == "ok")].copy()
        worst = worst[worst["peak_bytes"] >= MIN_RAM_BYTES]
        worst["ram_ratio"] = worst["ram_expected"] / worst["peak_bytes"]
        worst["dev"] = np.abs(np.log(worst["ram_ratio"]))
        worst = worst.sort_values("dev", ascending=False).head(10)
        lines.append("### Ten worst RAM predictions\n")
        lines.append(md_table(worst.assign(actual_MB=worst["peak_bytes"] / 2**20,
                                           expected_MB=worst["ram_expected"] / 2**20,
                                           low_MB=worst["ram_low"] / 2**20,
                                           high_MB=worst["ram_high"] / 2**20)
                              [["point_id", "actual_MB", "expected_MB", "low_MB", "high_MB"]]))  # fmt: skip
    failed = df.drop_duplicates("point_id")
    failed = failed[failed["status"] != "ok"][["point_id", "status", "error"]]
    lines.append("\n## Points that did not produce a measurement\n")
    lines.append(md_table(failed))
    lines.append("\n## Measurement caveats\n")
    lines.append(CAVEATS)
    report = results_dir / "report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: python -m benchmarks.evaluate <results_dir>")
    print(write_report(Path(args[0])))


if __name__ == "__main__":
    main()
