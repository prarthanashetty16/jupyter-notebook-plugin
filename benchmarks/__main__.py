"""Command line: ``python -m benchmarks {small,full,run,plan,status,evaluate} ...``.

Typical full run (resumable; re-run the same command after any interruption):

    python -m benchmarks plan   --suite full --mem-limit-gb 4
    python -m benchmarks full   --mem-limit-gb 4 --max-size 10000000
    python -m benchmarks status benchmarks/results/full          # from a second terminal
    python -m benchmarks evaluate benchmarks/results/full        # dev split only
    python -m benchmarks evaluate benchmarks/results/full --final --reason "..."  # test, logged
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import Floors, write_final_report, write_report
from benchmarks.runner import RunConfig, default_mem_limit_bytes, run_suite
from benchmarks.split import GROUPS, SEALED_DIR
from benchmarks.suite import SUITES, build_grid
from nexus.machine import ENV_VAR

RESULTS = Path(__file__).parent / "results"


def _floor_args(p: argparse.ArgumentParser) -> None:
    d = Floors()
    p.add_argument("--ram-floor-mib", type=float, default=d.ram_bytes / 2**20)
    p.add_argument("--time-floor-ms", type=float, default=d.time_s * 1e3)
    p.add_argument("--max-spread", type=float, default=d.max_spread)


def _floors(args: argparse.Namespace) -> Floors:
    return Floors(args.ram_floor_mib * 2**20, args.time_floor_ms / 1e3, args.max_spread)


def _select_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--mem-limit-gb",
        type=float,
        help="kill any child above this RSS and skip points whose estimated footprint exceeds "
        "it (default: 40%% of available RAM, at most 8)",
    )
    p.add_argument("--ops", help="comma-separated operation or case-group names")
    p.add_argument(
        "--splits",
        default="dev,exposed-v1",
        help="comma list of dev, exposed-v1, test-v2. The sealed test-v2 group is measured only "
        "when named here; its log lines show id, status and elapsed time only",
    )
    p.add_argument("--max-size", type=int, help="skip points with size above this")
    p.add_argument("--max-points", type=int)


def _splits(args: argparse.Namespace) -> tuple[str, ...]:
    chosen = tuple(s.strip() for s in args.splits.split(",") if s.strip())
    unknown = [s for s in chosen if s not in GROUPS]
    if unknown:
        raise SystemExit(f"unknown split(s) {unknown}; choose from {list(GROUPS)}")
    return chosen


def _cap(args: argparse.Namespace) -> int:
    return int(args.mem_limit_gb * 2**30) if args.mem_limit_gb else default_mem_limit_bytes()


def cmd_plan(args: argparse.Namespace) -> None:
    cap = _cap(args)
    ops = set(args.ops.split(",")) if args.ops else None
    splits = _splits(args)
    grid = build_grid(args.suite, ops=ops, splits=splits, max_size=args.max_size)
    print(f"suite={args.suite}  memory cap={cap / 2**30:.1f} GiB  points={len(grid)}")
    for split in GROUPS:
        pts = [p for p in grid if p.split == split]
        run = [p for p in pts if p.est_footprint_bytes() <= cap]
        procs = sum(p.repeats + 2 for p in run)  # repeats + prep + prediction
        print(
            f"  {split:4s}: {len(pts):3d} points, {len(run):3d} would run, "
            f"{len(pts) - len(run):3d} skipped (above cap), ~{procs} child processes"
        )
    big = sorted(
        (p for p in grid if p.est_footprint_bytes() <= cap), key=lambda p: -p.est_footprint_bytes()
    )
    print("largest runnable points (estimated worst-case footprint):")
    for p in big[:8]:
        print(f"  {p.est_footprint_bytes() / 2**30:5.2f} GiB  {p.id}")
    skipped = [p for p in grid if p.est_footprint_bytes() > cap]
    if skipped:
        print(
            f"first skipped: {skipped[0].id} ({skipped[0].est_footprint_bytes() / 2**30:.1f} GiB); "
            "raise --mem-limit-gb to include more"
        )


def cmd_status(args: argparse.Namespace) -> None:
    out: Path = args.results
    progress = out / "progress.json"
    if progress.exists():
        s = json.loads(progress.read_text())
        eta = f"{s['eta_s'] / 60:.0f} min" if s.get("eta_s") is not None else "n/a"
        print(
            f"state={s['state']}  point {s['index']}/{s['total']} ({s['runnable']} runnable)  "
            f"elapsed={s['elapsed_s'] / 60:.0f} min  eta~{eta}  updated {s['updated']}"
        )
        print(f"current: {s.get('current')}   counts: {s['counts']}")
    else:
        print(f"no progress.json in {out} (run not started?)")
    for label, path in (
        ("dev", out / "actuals.csv"),
        ("test-v2 (count only)", out / SEALED_DIR / "actuals.csv"),
    ):
        if path.exists():
            rows = pd.read_csv(path, dtype=str, keep_default_na=False)
            rows = rows.drop_duplicates("point_id", keep="last")
            print(f"{label:22s}: {len(rows)} points  {dict(Counter(rows['status']))}")
    log = out / "run.log"
    if log.exists():
        print("last log lines:")
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]:
            print("  " + line)


def main() -> None:  # noqa: C901
    parser = argparse.ArgumentParser(
        prog="python -m benchmarks",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("small", "full", "run"):
        p = sub.add_parser(name, help="run (or resume) a suite, then write the dev report")
        if name == "run":
            p.add_argument("--suite", choices=tuple(SUITES), default="small")
        p.add_argument(
            "--out", type=Path, help="results directory (default benchmarks/results/<suite>)"
        )
        _select_args(p)
        p.add_argument("--retry-failed", action="store_true", help="re-run points that errored")
        p.add_argument("--no-report", action="store_true")
        p.add_argument(
            "--no-calibrate",
            action="store_true",
            help="ablation: use the uncalibrated default throughputs",
        )
        _floor_args(p)
    pl = sub.add_parser("plan", help="dry run: what would run under the memory cap")
    pl.add_argument("--suite", choices=tuple(SUITES), default="full")
    _select_args(pl)
    st = sub.add_parser("status", help="progress of a (possibly running) suite")
    st.add_argument("results", type=Path)
    ev = sub.add_parser("evaluate", help="(re)write the report for a results directory")
    ev.add_argument("results", type=Path)
    ev.add_argument("--final", action="store_true", help="evaluate the sealed TEST split (logged)")
    ev.add_argument("--reason", help="required with --final; recorded in docs/PROGRESS.md")
    _floor_args(ev)
    args = parser.parse_args()

    if args.command == "plan":
        cmd_plan(args)
        return
    if args.command == "status":
        cmd_status(args)
        return
    if args.command == "evaluate":
        if args.final:
            if not args.reason:
                parser.error("--final requires --reason")
            cmd = "python -m benchmarks " + " ".join(sys.argv[1:])
            print(write_final_report(args.results, args.reason, command=cmd, floors=_floors(args)))
        else:
            print(write_report(args.results, floors=_floors(args)))
        return

    suite = args.suite if args.command == "run" else args.command
    out = args.out or RESULTS / suite
    out.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(out / "run.log", encoding="utf-8")]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    cfg = RunConfig(
        suite=suite,
        out_dir=out,
        mem_limit_bytes=_cap(args) if args.mem_limit_gb else None,
        ops=set(args.ops.split(",")) if args.ops else None,
        retry_failed=args.retry_failed,
        max_points=args.max_points,
        max_size=args.max_size,
        splits=_splits(args),
    )
    if args.no_calibrate:
        os.environ[ENV_VAR] = str(out / "no_profile.json")  # nonexistent: models use defaults
        cfg.calibrate = False
    try:
        run_suite(cfg)
    except KeyboardInterrupt:
        print("\ninterrupted; re-run the same command to resume", file=sys.stderr)
        raise SystemExit(130) from None
    if not args.no_report:
        print(f"report: {write_report(out, floors=_floors(args))}")


if __name__ == "__main__":
    main()
