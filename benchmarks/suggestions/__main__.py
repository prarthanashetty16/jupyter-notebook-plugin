"""``python -m benchmarks.suggestions plan | run | evaluate``."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.suggestions import run, split


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.suggestions")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan", help="list the frozen split (counts only)")
    r = sub.add_parser("run", help="measure suggestions (dev by default)")
    r.add_argument("--heldout", action="store_true", help="run the held-out configurations (once!)")
    r.add_argument("--reason", default="")
    r.add_argument(
        "--limit", type=int, default=None, help="at most N cells in this call (resumable)"
    )
    r.add_argument("--base-only", action="store_true", help="dev design check: baselines only")
    r.add_argument("--results", type=Path, default=run.RESULTS)
    e = sub.add_parser("evaluate", help="write the report")
    e.add_argument("--heldout", action="store_true")
    e.add_argument("--reason", default="")
    e.add_argument("--results", type=Path, default=run.RESULTS)
    e.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.cmd == "plan":
        sp = split.load()
        print(
            f"split v{sp.version}: {len(sp.dev)} dev and {len(sp.heldout)} held-out configurations; digest {sp.digest}"
        )
        print(f"dev cells: {len(run._cells(sp.dev))}")
        return 0
    if args.cmd == "run":
        return run.run(
            heldout=args.heldout, reason=args.reason, limit=args.limit, results=args.results
        )
    text = (
        run.evaluate_heldout(args.reason, results=args.results, out=args.out)
        if args.heldout
        else run.evaluate_dev(results=args.results, out=args.out)
    )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
