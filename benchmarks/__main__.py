"""Command line: ``python -m benchmarks {small,full,run,evaluate} ...``."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from benchmarks.evaluate import Floors, write_report
from benchmarks.runner import RunConfig, run_suite
from nexus.machine import ENV_VAR

RESULTS = Path(__file__).parent / "results"


def _floor_args(p: argparse.ArgumentParser) -> None:
    d = Floors()
    p.add_argument("--ram-floor-mib", type=float, default=d.ram_bytes / 2**20)
    p.add_argument("--time-floor-ms", type=float, default=d.time_s * 1e3)
    p.add_argument("--max-spread", type=float, default=d.max_spread)


def _floors(args: argparse.Namespace) -> Floors:
    return Floors(args.ram_floor_mib * 2**20, args.time_floor_ms / 1e3, args.max_spread)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m benchmarks", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("small", "full", "run"):
        p = sub.add_parser(name, help="run (or resume) a suite, then write the report")
        if name == "run":
            p.add_argument("--suite", choices=("small", "full"), default="small")
        p.add_argument(
            "--out", type=Path, help="results directory (default benchmarks/results/<suite>)"
        )
        p.add_argument("--mem-limit-gb", type=float, help="kill any child above this RSS")
        p.add_argument("--ops", help="comma-separated operation or case-group names to run")
        p.add_argument("--max-points", type=int)
        p.add_argument("--retry-failed", action="store_true", help="re-run points that errored")
        p.add_argument("--no-report", action="store_true")
        p.add_argument(
            "--no-calibrate",
            action="store_true",
            help="ablation: use the uncalibrated default throughputs",
        )
        _floor_args(p)
    ev = sub.add_parser("evaluate", help="(re)write the report for a results directory")
    ev.add_argument("results", type=Path)
    _floor_args(ev)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.command == "evaluate":
        print(write_report(args.results, floors=_floors(args)))
        return
    suite = args.suite if args.command == "run" else args.command
    out = args.out or RESULTS / suite
    cfg = RunConfig(
        suite=suite,
        out_dir=out,
        mem_limit_bytes=int(args.mem_limit_gb * 2**30) if args.mem_limit_gb else None,
        ops=set(args.ops.split(",")) if args.ops else None,
        retry_failed=args.retry_failed,
        max_points=args.max_points,
    )
    if args.no_calibrate:
        os.environ[ENV_VAR] = str(out / "no_profile.json")  # nonexistent: models use defaults
        cfg.calibrate = False
    run_suite(cfg)
    if not args.no_report:
        print(f"report: {write_report(out, floors=_floors(args))}")


if __name__ == "__main__":
    main()
