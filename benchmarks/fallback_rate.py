"""How often Tier 1 statistics fall back to Tier 0 on the time budget when CPU is scarce (Phase 6b).

Information only: no model, budget or threshold changes. The prediction runner (Tier 1 only, the
operations that have Tier 1 statistics) is re-run on the stored dev points under a CPU condition;
its spawned workers inherit the process affinity:

* ``cores2``: the runner and its workers pinned to 2 logical CPUs;
* ``cores2_contended``: the same 2 CPUs plus 2 busy-loop processes pinned to them at normal
  priority, so the workers get about half of each core (an artificially slowed CPU without changing
  any system setting; the busy loops are terminated at the end).

    python -m benchmarks.fallback_rate run cores2 --out benchmarks/results/fallback-cores2
    python -m benchmarks.fallback_rate run cores2_contended --out benchmarks/results/fallback-contended
    python -m benchmarks.fallback_rate report --baseline benchmarks/results/phase6-dev-mains \\
        --run cores2=benchmarks/results/fallback-cores2 --run cores2_contended=benchmarks/results/fallback-contended \\
        --out docs/benchmarks/phase6b/fallback_rate.md

Refuses to run on battery power (the result would measure the throttling, not the condition).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from nexus.power import power_state

OPS = "astype,drop_duplicates,groupby,merge,pandas.read_csv,pandas.concat"
CORES = [0, 1]
BASE_ACTUALS = Path("benchmarks/results/tier2-dev-b/actuals.csv")


def _busy(cores: list[int]) -> None:
    psutil.Process().cpu_affinity(cores)
    x = 0
    while True:
        x = (x * 1103515245 + 12345) % 2147483648


def run(condition: str, out: Path, allow_battery: bool = False) -> None:
    if power_state() == "battery" and not allow_battery:
        raise SystemExit(
            "on battery power: plug in first (the CPU would be throttled), or pass --allow-battery "
            "(the report then marks the run as confounded by battery throttling)"
        )
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "actuals.csv").exists():
        shutil.copy(BASE_ACTUALS, out / "actuals.csv")
    psutil.Process().cpu_affinity(CORES)
    hogs = []
    if condition == "cores2_contended":
        ctx = mp.get_context("spawn")
        hogs = [ctx.Process(target=_busy, args=(CORES,), daemon=True) for _ in CORES]
        for h in hogs:
            h.start()
    elif condition != "cores2":
        raise SystemExit(f"unknown condition {condition!r}")
    meta = {"condition": condition, "affinity": CORES, "busy_loops": len(hogs),
            "power": power_state(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}  # fmt: skip
    (out / "condition.json").write_text(json.dumps(meta, indent=1))
    from benchmarks.__main__ import main as bench_main

    argv = ["full", "--out", str(out), "--tiers", "1", "--ops", OPS, "--mem-limit-gb", "2.5",
            "--max-size", "10000000", "--no-report"]  # fmt: skip
    old = sys.argv
    try:
        sys.argv = ["benchmarks", *argv]
        bench_main()
    finally:
        sys.argv = old
        for h in hogs:
            h.terminate()
        meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        meta["power_end"] = power_state()
        (out / "condition.json").write_text(json.dumps(meta, indent=1))


def _tier1_status(results: Path) -> pd.DataFrame:
    p = pd.read_csv(results / "predictions.csv", dtype=str, keep_default_na=False)
    p = p[p["tier"] == "1"].drop_duplicates("point_id", keep="last")
    a = pd.read_csv(results / "actuals.csv", dtype=str, keep_default_na=False)[["point_id", "op"]]
    p = p.merge(a, on="point_id", how="left")

    def why(row: pd.Series) -> str:
        if row["status"] != "ok":
            return f"prediction {row['status']}"
        t1 = (json.loads(row["features"] or "{}").get("tier1")) or {}
        if t1.get("used", bool(t1)):
            return "tier1"
        return t1.get("reason") or "no statistics"

    p["outcome"] = p.apply(why, axis=1)
    return p[["point_id", "op", "outcome"]]


def _dev_errors(baseline: Path, docs: Path) -> pd.DataFrame:
    """Per operation on dev: what Tier 0 instead of Tier 1 means (RAM from the stored policy-B rows,
    time from the Phase 6 LOCO calibrated predictions)."""
    from benchmarks.evaluate import load_joined

    d = load_joined(baseline)
    d = d[d["has_estimate"] & (d["ram_class"] == "valid") & d["tier"].isin([0, 1])]
    rows = []
    for (op, tier), g in d.groupby(["op", "tier"]):
        a = g["ram_value"]
        rows.append({"op": op, "tier": int(tier),
                     "ram_err_med": float(((g["ram_expected"] - a).abs() / a).median()),
                     "ram_width": float(((g["ram_high"] - g["ram_low"]) / g["ram_expected"]).mean())})  # fmt: skip
    ram = pd.DataFrame(rows)
    trows = []
    for tier in (0, 1):
        loco = pd.read_csv(docs / f"tier{tier}_loco.csv")
        for op, g in loco.groupby("op"):
            a = g["actual"]
            trows.append({"op": op, "tier": tier,
                          "time_err_med": float(((g["exp_cal"] - a).abs() / a).median()),
                          "time_width": float(((g["high_cal"] - g["low_cal"]) / g["exp_cal"]).mean())})  # fmt: skip
    return ram.merge(pd.DataFrame(trows), on=["op", "tier"], how="outer")


def _condition_notes(runs: list[tuple[str, Path]]) -> list[str]:
    """What each run's condition was, flagging runs made on battery (throttling confounded)."""
    lines = []
    for name, path in runs:
        cond = path / "condition.json"
        if not cond.exists():
            continue
        info = json.loads(cond.read_text())
        if "battery" in (info.get("power"), info.get("power_end")):
            lines.append(
                f"\n**`{name}` was measured ON BATTERY** (power at start: {info.get('power')}, "
                f"at end: {info.get('power_end')}): battery throttling and the CPU condition are "
                "confounded; the 16-core baseline was measured on mains."
            )
        lines.append(f"\n`{name}`: `{json.dumps(info)}`")
    return lines


def report(baseline: Path, runs: list[tuple[str, Path]], out: Path, docs: Path) -> None:
    ops = OPS.split(",")
    tables = {"16 cores (baseline, phase6-dev-mains)": _tier1_status(baseline)}
    for name, path in runs:
        tables[name] = _tier1_status(path)
    base_ids = set(tables[next(iter(tables))]["point_id"])
    lines = [
        "# Tier 1 fallback rate under scarce CPU (Phase 6b; information only, no model change)",
        "",
        "Tier 1 statistics run inside the 250 ms analysis budget; when it runs out, the estimate falls back to "
        "Tier 0 (`tier1.reason = 'time budget'`). Same stored dev points and code as the frozen stack "
        "`models-frozen-v1`, prediction only. Conditions: `benchmarks/fallback_rate.py` (affinity to 2 logical "
        "CPUs; plus 2 busy loops on the same CPUs for the contended run). The baseline is on mains; see the power notes of each run below.",
        "",
        "## Fallback to Tier 0 on the time budget, per operation",
        "",
        "| op | points | " + " | ".join(tables) + " |",
        "|---|---|" + "---|" * len(tables),
    ]
    for op in [*ops, "ALL"]:
        cells = []
        n = None
        for _, t in tables.items():
            t = t[t["point_id"].isin(base_ids)]
            g = t if op == "ALL" else t[t["op"] == op]
            g = g[g["op"].isin(ops)]
            n = len(g)
            k = int((g["outcome"] == "time budget").sum())
            other = int(g["outcome"].str.startswith("prediction").sum())
            cells.append(
                f"{k} ({k / max(n, 1):.0%})" + (f", {other} prediction errors" if other else "")
            )
        lines.append(f"| {op} | {n} | " + " | ".join(cells) + " |")
    lines += _condition_notes(runs)
    err = _dev_errors(baseline, docs)
    lines += [
        "",
        "## What a fallback means for the user (dev, per operation: Tier 0 vs Tier 1)",
        "",
        "RAM: median |expected - actual| / actual and mean width (high - low) / expected of the stored policy-B rows; "
        "time: the same for the calibrated LOCO predictions of Phase 6 (`docs/benchmarks/phase6/tier*_loco.csv`).",
        "",
        "| op | RAM error T1 -> T0 | RAM width T1 -> T0 | time error T1 -> T0 | time width T1 -> T0 |",
        "|---|---|---|---|---|",
    ]
    for op in ops:
        e = err[err["op"] == op].set_index("tier")
        if not {0, 1} <= set(e.index):
            continue

        def f(col: str, pct: bool, e: pd.DataFrame = e) -> str:
            a, b = e.loc[1, col], e.loc[0, col]
            if np.isnan(a) or np.isnan(b):
                return "n/a"
            return f"{a:.0%} -> {b:.0%}" if pct else f"{a:.2f} -> {b:.2f}"

        lines.append(f"| {op} | {f('ram_err_med', True)} | {f('ram_width', False)} | "
                     f"{f('time_err_med', True)} | {f('time_width', False)} |")  # fmt: skip
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m benchmarks.fallback_rate")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("condition", choices=("cores2", "cores2_contended"))
    r.add_argument("--out", type=Path, required=True)
    r.add_argument(
        "--allow-battery", action="store_true", help="run on battery (recorded, flagged)"
    )
    rep = sub.add_parser("report")
    rep.add_argument("--baseline", type=Path, required=True)
    rep.add_argument("--run", action="append", default=[], help="name=results_dir")
    rep.add_argument("--out", type=Path, required=True)
    rep.add_argument("--phase6-docs", type=Path, default=Path("docs/benchmarks/phase6"))
    args = p.parse_args(argv)
    if args.cmd == "run":
        run(args.condition, args.out, allow_battery=args.allow_battery)
    else:
        runs = [(s.split("=", 1)[0], Path(s.split("=", 1)[1])) for s in args.run]
        report(args.baseline, runs, args.out, args.phase6_docs)


if __name__ == "__main__":
    main()
