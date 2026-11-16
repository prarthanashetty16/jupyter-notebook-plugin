"""Command line: ``python -m benchmarks {small,full,run,evaluate} ...``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from benchmarks.evaluate import write_report
from benchmarks.runner import RunConfig, run_suite

RESULTS = Path(__file__).parent / "results"


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
    ev = sub.add_parser("evaluate", help="(re)write the report for a results directory")
    ev.add_argument("results", type=Path)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if args.command == "evaluate":
        print(write_report(args.results))
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
    run_suite(cfg)
    if not args.no_report:
        print(f"report: {write_report(out)}")


if __name__ == "__main__":
    main()
