"""Prediction-only re-run of the stored DEV points (no measurement), for before/after comparisons.

    python -m benchmarks.repredict --from benchmarks/results/phase6c-dev --out benchmarks/results/phase7b-dev

Copies ``<from>/actuals.csv`` (the dev actuals only: never ``sealed/`` or ``validation/``) and runs the
predictions (tiers 0 and 1) for exactly the dev points that have a stored actual, so nothing is measured.
Refuses on battery power unless ``--allow-battery`` (dev only; ``benchmarks.powerguard``): the rows then record
``battery (user-accepted)``, ``<out>/power.json`` holds the raw readings, and the timing figures of the run
(time predictions use live Tier 1 budgets) are battery-throttled and not usable for calibration or timing claims.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from benchmarks.powerguard import BATTERY_NOTE, power_record
from benchmarks.runner import RunConfig, run_suite
from benchmarks.suite import build_grid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.repredict")
    ap.add_argument("--from", dest="src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tiers", default="0,1")
    ap.add_argument(
        "--allow-battery", action="store_true", help="dev only: run on battery (recorded)"
    )
    args = ap.parse_args(argv)
    rec = power_record(args.allow_battery, "dev")
    args.out.mkdir(parents=True, exist_ok=True)
    if rec["power"] != "mains":
        (args.out / "power.json").write_text(
            json.dumps({**rec, "note": BATTERY_NOTE}, indent=1, default=str)
        )
    if not (args.out / "actuals.csv").exists():
        shutil.copy(args.src / "actuals.csv", args.out / "actuals.csv")
    stored = set(pd.read_csv(args.out / "actuals.csv", usecols=["point_id"])["point_id"])
    grid = [p for p in build_grid("full", splits=("dev",)) if p.id in stored]
    missing = stored - {p.id for p in grid}
    if missing:
        print(
            f"{len(missing)} stored dev actuals have no grid point (not re-predicted): {sorted(missing)[:5]}"
        )
    cfg = RunConfig(suite="full", out_dir=args.out, tiers=tuple(int(t) for t in args.tiers.split(",")),
                    splits=("dev",), plan_with_model=False)  # fmt: skip
    run_suite(cfg, points=grid)
    print(f"re-predicted {len(grid)} dev points into {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
