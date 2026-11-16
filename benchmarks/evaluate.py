"""Score predictions against measurements; write CSVs, a markdown report and figures.

Definitions (all restated in the report):
- RAM = *incremental peak* resident memory during the operation, from the OS-tracked peak counter
  (see ``nexus.measure``); time = wall clock around the call. Median over repeats.
- Every point is classified per metric, from the raw repeats, by configurable ``Floors``:
  **censored** (all repeats below the setup peak, or median below the floor: the value is not
  trusted), **excluded** (relative spread (max-min)/median above the threshold), else **valid**.
  Only valid points enter the accuracy metrics; censored and excluded counts are reported apart.
- relative error = |expected - actual| / actual; bias = median(expected / actual) (> 1 over-predicts);
  coverage = share of valid points whose actual lies inside the predicted [low, high];
  width = mean (high - low) / expected.
- OOM warning: for a simulated available-memory limit L a point is *positive* if
  input_bytes + RAM > L (a censored point uses its upper bound); NEXUS *warns* if inspected input
  bytes + predicted RAM (``high`` or ``expected``) > L. Points killed by the harness memory cap are
  positive for L <= cap. Excluded points and points without an estimate never count.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.measure import (
    DEFAULT_MAX_SPREAD,
    DEFAULT_RAM_FLOOR_BYTES,
    DEFAULT_TIME_FLOOR_S,
    MIB,
    classify,
)

OOM_LIMITS_MB = (64, 128, 256, 512, 1024, 2048, 4096)
BUDGET_S = 0.25


@dataclass(frozen=True)
class Floors:
    ram_bytes: float = DEFAULT_RAM_FLOOR_BYTES
    time_s: float = DEFAULT_TIME_FLOOR_S
    max_spread: float = DEFAULT_MAX_SPREAD


def _read_last(path: Path, key: list[str]) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    return df.drop_duplicates(subset=key, keep="last").reset_index(drop=True)


def _json_list(cell: Any) -> list[Any]:
    try:
        value = json.loads(cell) if isinstance(cell, str) and cell else []
        return value if isinstance(value, list) else []
    except ValueError:
        return []


def classify_points(df: pd.DataFrame, floors: Floors) -> pd.DataFrame:
    """Add ram_/time_ ``class``, ``value``, ``spread``, ``reason`` (and ram_bound) columns."""
    cols: dict[str, list[Any]] = {
        k: [] for k in ("ram_class", "ram_value", "ram_spread", "ram_reason",
                        "time_class", "time_value", "time_spread", "time_reason")
    }  # fmt: skip
    for _, row in df.iterrows():
        if row["status"] != "ok":
            for k in cols:
                cols[k].append(None)
            continue
        ram = classify(_json_list(row.get("ram_delta_all")), floor=floors.ram_bytes,
                       max_spread=floors.max_spread)  # fmt: skip
        tim = classify(_json_list(row.get("time_s_all")), floor=floors.time_s,
                       max_spread=floors.max_spread)  # fmt: skip
        for name, c in (("ram", ram), ("time", tim)):
            cols[f"{name}_class"].append(c.klass)
            cols[f"{name}_value"].append(c.value)
            cols[f"{name}_spread"].append(c.spread)
            cols[f"{name}_reason"].append(c.reason)
    out = df.copy()
    for k, v in cols.items():
        out[k] = v
    for k in ("ram_value", "time_value", "ram_spread", "time_spread"):
        out[k] = pd.to_numeric(out[k], errors="coerce")
    return out


def load_joined(results_dir: Path, floors: Floors | None = None) -> pd.DataFrame:
    """One row per (grid point, tier); points with no prediction run have tier NaN."""
    floors = floors or Floors()
    actuals = _read_last(results_dir / "actuals.csv", ["point_id"])
    preds_path = results_dir / "predictions.csv"
    preds = (
        _read_last(preds_path, ["point_id", "tier"])
        if preds_path.exists()
        else pd.DataFrame(columns=["point_id", "tier"])
    )
    env_cols = [
        c
        for c in preds.columns
        if c in actuals.columns and c not in ("point_id", "status", "error")
    ]
    preds = preds.drop(columns=env_cols).rename(
        columns={"status": "pred_status", "error": "pred_error"}
    )
    df = actuals.merge(preds, on="point_id", how="left")
    numeric = [
        "size", "baseline_bytes", "setup_peak_bytes", "input_bytes", "input_resident_bytes",
        "out_rows", "out_bytes", "cap_bytes", "tier", "ram_low", "ram_expected", "ram_high",
        "time_low", "time_expected", "time_high", "confidence", "overhead_cold_s",
        "overhead_warm_s", "analysis_peak_bytes", "inspected_bytes", "repeats_ok",
        "ram_bound_bytes",
    ]  # fmt: skip
    for col in numeric:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["has_estimate"] = df["has_estimate"].fillna("False").astype(str).eq("True")
    return classify_points(df, floors)


def _accuracy(g: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"points": len(g), "estimated": int(g["has_estimate"].sum())}
    for name, ex, lo, hi in (("ram", "ram_expected", "ram_low", "ram_high"),
                             ("time", "time_expected", "time_low", "time_high")):  # fmt: skip
        for klass in ("valid", "censored", "excluded"):
            out[f"{name}_{klass}"] = int((g[f"{name}_class"] == klass).sum())
        sub = g[g["has_estimate"] & (g[f"{name}_class"] == "valid")]
        if sub.empty:
            continue
        a = sub[f"{name}_value"]
        err = (sub[ex] - a).abs() / a
        out[f"{name}_n"] = len(sub)
        out[f"{name}_err_med"] = err.median()
        out[f"{name}_err_p90"] = err.quantile(0.9)
        out[f"{name}_bias"] = (sub[ex] / a).median()
        out[f"{name}_cov"] = ((sub[lo] <= a) & (a <= sub[hi])).mean()
        out[f"{name}_above_high"] = (a > sub[hi]).mean()
        out[f"{name}_below_low"] = (a < sub[lo]).mean()
        out[f"{name}_width"] = ((sub[hi] - sub[lo]) / sub[ex].where(sub[ex] > 0)).mean()
    return out


def accuracy_table(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Accuracy metrics per group of ok-status points that had a prediction run."""
    ok = df[(df["status"] == "ok") & df["tier"].notna()]
    rows = []
    for key, g in ok.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(by, key, strict=True)), **_accuracy(g)})
    return pd.DataFrame(rows)


def oom_table(
    df: pd.DataFrame, tier: int, limits_mb: tuple[int, ...] = OOM_LIMITS_MB
) -> pd.DataFrame:
    d = df[(df["tier"] == tier) & (df["pred_status"] == "ok")]
    killed_all = d["status"] == "memory_limit"
    d = d[(d["status"] == "ok") & (d["ram_class"] != "excluded") | killed_all]
    rows = []
    for limit_mb in limits_mb:
        limit = limit_mb * 2**20
        killed = d["status"] == "memory_limit"
        valid = d[(~killed) | (d["cap_bytes"] >= limit)]
        killed_v = valid["status"] == "memory_limit"
        ram = valid["ram_value"].fillna(valid["ram_bound_bytes"]).fillna(0)
        footprint = valid["input_bytes"].fillna(valid["inspected_bytes"]) + ram
        positive = killed_v | (footprint > limit)
        for rule, col in (("high", "ram_high"), ("expected", "ram_expected")):
            warn = valid["has_estimate"] & ((valid["inspected_bytes"] + valid[col]) > limit)
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
        cold = pd.to_numeric(g["overhead_cold_s"], errors="coerce")
        warm = pd.to_numeric(g["overhead_warm_s"], errors="coerce")
        rows.append(
            {
                "op": op, "n": len(g),
                "cold_med_ms": cold.median() * 1e3, "cold_p90_ms": cold.quantile(0.9) * 1e3,
                "warm_med_ms": warm.median() * 1e3, "warm_max_ms": warm.max() * 1e3,
                "over_budget": int((cold > BUDGET_S).sum()),
            }
        )  # fmt: skip
    return pd.DataFrame(rows)


def instrument_crosscheck(df: pd.DataFrame) -> pd.DataFrame:
    """OS peak vs polled RSS per op: polling can only under-measure, so poll > OS is a bug."""
    rows = []
    ok = df[(df["status"] == "ok")].drop_duplicates("point_id")
    for op, g in list(ok.groupby("op")) + [("ALL", ok)]:
        ratios, bad, missed, runs = [], 0, 0, 0
        for _, r in g.iterrows():
            os_d, poll_d = _json_list(r.get("ram_delta_all")), _json_list(r.get("poll_delta_all"))
            for a, b in zip(os_d, poll_d, strict=False):
                if a is None:
                    continue
                runs += 1
                if b > a * 1.1 + MIB:
                    bad += 1
                if a >= DEFAULT_RAM_FLOOR_BYTES:
                    ratios.append(b / a)
                    missed += b < 0.5 * a
        rows.append(
            {
                "op": op, "uncensored_runs": runs, "poll_over_os": bad,
                "poll_missed_half": int(missed),
                "median_poll_ratio": float(np.median(ratios)) if ratios else math.nan,
            }
        )  # fmt: skip
    return pd.DataFrame(rows)


def censor_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    ok = df[df["status"] == "ok"].drop_duplicates("point_id")
    rows = []
    for op, g in list(ok.groupby("op")) + [("ALL", ok)]:
        row: dict[str, Any] = {"op": op, "points": len(g)}
        for name in ("ram", "time"):
            c = g[f"{name}_class"]
            reason = g[f"{name}_reason"]
            row[f"{name}_valid"] = int((c == "valid").sum())
            row[f"{name}_cens_setup_peak"] = int(
                ((c == "censored") & (reason == "below_setup_peak")).sum()
            )
            row[f"{name}_cens_floor"] = int(((c == "censored") & (reason == "below_floor")).sum())
            row[f"{name}_excluded"] = int((c == "excluded").sum())
        rows.append(row)
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
    d = df[(df["tier"] == tier) & df["has_estimate"]]
    written = []
    for name, lo, ex, hi, unit in (
        ("ram", "ram_low", "ram_expected", "ram_high", "bytes"),
        ("time", "time_low", "time_expected", "time_high", "seconds"),
    ):
        sub = d[d[f"{name}_class"] == "valid"]
        actual = f"{name}_value"
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
    for ax, name, ex in ((axes[0], "ram", "ram_expected"), (axes[1], "time", "time_expected")):
        sub = d[(d[f"{name}_class"] == "valid") & (d[ex] > 0)]
        groups = [(op, np.log10(g[ex] / g[f"{name}_value"])) for op, g in sub.groupby("op")]
        if groups:
            ax.boxplot([x[1] for x in groups], tick_labels=[x[0] for x in groups])
        ax.axhline(0, color="k", lw=0.8)
        ax.set_ylabel("log10(predicted / actual)   (+1 = 10x too high)")
        ax.set_title(f"Tier {tier}: {name.upper()} error by operation")
        ax.tick_params(axis="x", rotation=60)
    fig.tight_layout()
    fname = f"fig_error_by_op_tier{tier}.png"
    fig.savefig(out_dir / fname, dpi=130)
    plt.close(fig)
    written.append(fname)

    acc = accuracy_table(df, ["tier", "op"])
    acc = acc[(acc["tier"] == tier) & acc.get("ram_cov", pd.Series(dtype=float)).notna()]
    if not acc.empty:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        x = np.arange(len(acc))
        ax.bar(x - 0.2, acc["ram_cov"].fillna(0), 0.4, label="RAM")
        ax.bar(x + 0.2, acc["time_cov"].fillna(0) if "time_cov" in acc else 0, 0.4, label="time")
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
- RAM is *incremental peak resident memory* from the OS peak counter (Windows peak working set,
  Linux VmHWM, macOS ru_maxrss), read inside the measured process before and after the operation.
  On Windows/macOS the counter cannot be reset, so an operation whose peak stays below the peak
  reached while *loading* its inputs is **censored** (reported with an upper bound), not zero.
- RSS counts resident pages only: lazily allocated memory is invisible until touched. Windows
  reports the working set.
- Time is wall-clock around the single call inside a fresh process (no warm-up; first-touch
  effects of freshly loaded data are included). Median of the repeats; raw repeats are in
  `actuals.csv`.
- Polled RSS from the parent is a cross-check only (see the instrument cross-check table).
- Datasets are synthetic (see `benchmarks/datasets.py`); real-world value distributions, dtype
  mixes and file layouts will differ. Phase 8 covers real data.
- Tier 0 RAM models and priors were fixed before any result was seen; the hardware throughputs
  come from the per-machine calibration (`nexus-calibrate-machine`), measured on dedicated
  microbenchmarks. Nothing has been tuned against benchmark results.
"""


def write_report(
    results_dir: Path, tiers: list[int] | None = None, floors: Floors | None = None
) -> Path:
    floors = floors or Floors()
    df = load_joined(results_dir, floors)
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
    breakdown = censor_breakdown(df)
    breakdown.to_csv(results_dir / "classification_by_op.csv", index=False)

    status = df.drop_duplicates("point_id")["status"].value_counts().to_dict()
    lines = [f"# NEXUS benchmark report: `{meta.get('suite', results_dir.name)}`\n"]
    lines.append(
        f"Instrument `{meta.get('instrument', '?')}`. {meta.get('os', '?')}, Python "
        f"{meta.get('python', '?')}, pandas {meta.get('pandas', '?')} (default string dtype "
        f"`{meta.get('pandas_str_default', '?')}`, generated text columns `{meta.get('text_dtype', '?')}`), "
        f"numpy {meta.get('numpy', '?')}, pyarrow {meta.get('pyarrow', '?')}, CPU "
        f"{meta.get('cpu', '?')} ({meta.get('cpu_count', '?')} logical, max "
        f"{meta.get('cpu_max_mhz', '?')} MHz), git `{meta.get('git_commit', '?')}`. Memory cap per "
        f"child process: {float(meta.get('cap_bytes', 0)) / 2**20:.0f} MB. Machine profile calibrated: "
        f"{meta.get('machine_profile', {}).get('calibrated', '?')}.\n"
    )
    lines.append(f"Grid points by outcome: {status}.\n")
    lines.append(
        f"Floors: RAM >= {floors.ram_bytes / MIB:.0f} MiB above baseline, time >= "
        f"{floors.time_s * 1e3:.0f} ms, relative spread <= {floors.max_spread:.0%}. Points below a floor "
        "are *censored*; points above the spread threshold are *excluded*; accuracy covers *valid* "
        "points only.\n"
    )
    lines.append("## Classification of measurements (all points that ran)\n")
    lines.append(md_table(breakdown))
    lines.append(
        "`cens_setup_peak` = operation never exceeded the peak reached while loading inputs; "
        "`cens_floor` = measured but below the floor.\n"
    )
    lines.append("## Instrument cross-check (OS peak vs polled RSS)\n")
    lines.append(md_table(instrument_crosscheck(df)))
    lines.append(
        "`poll_over_os` should be 0 (polling can only under-measure). `poll_missed_half` = runs "
        "where polling saw less than half of the OS peak.\n"
    )
    for tier in tiers:
        lines.append(f"\n## Tier {tier}\n")
        t = acc_op_all[acc_op_all["tier"] == tier]
        lines.append("### Estimate availability and sample sizes\n")
        lines.append(md_table(_select(t, ["op", "points", "estimated", "ram_valid", "ram_censored",
                                          "ram_excluded", "time_valid", "time_censored",
                                          "time_excluded"])))  # fmt: skip
        lines.append("### RAM accuracy (valid points)\n")
        lines.append(md_table(_select(t, ["op", "ram_n", "ram_err_med", "ram_err_p90", "ram_bias",
                                          "ram_cov", "ram_above_high", "ram_below_low",
                                          "ram_width"]), PCT))  # fmt: skip
        lines.append("### Time accuracy (valid points)\n")
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
        worst = df[(df["tier"] == tier) & df["has_estimate"] & (df["ram_class"] == "valid")].copy()
        worst["dev"] = np.abs(np.log(worst["ram_expected"] / worst["ram_value"]))
        worst = worst.sort_values("dev", ascending=False).head(10)
        lines.append("### Ten worst RAM predictions (valid points)\n")
        lines.append(md_table(worst.assign(actual_MB=worst["ram_value"] / 2**20,
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
