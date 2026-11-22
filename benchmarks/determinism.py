"""Phase 6d determinism check (information only; nothing changes): Tier 1 repeated on the same inputs.

Tier 1 statistics sample rows under a 250 ms budget, so the sample size (and, near the budget, whether
Tier 1 runs at all) can depend on how fast the CPU is at that moment. This runs the benchmark's own
prediction worker (a fresh process, inputs loaded from the dataset cache) REPEATS times on POINTS stored
dev points and reports, per operation, the spread of the expected and high RAM and of the expected time,
and how often the Tier 0 fallback differs between repeats of the same point. Mains power required.

    python -m benchmarks.determinism --out docs/benchmarks/phase6d/determinism.md
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

OPS = ("astype", "drop_duplicates", "groupby", "merge", "pandas.read_csv", "pandas.concat")
PER_OP = 5
REPEATS = 10
MAX_ROWS = 3_000_000


def pick_points() -> list:
    from benchmarks.split import DEV
    from benchmarks.suite import build_grid

    grid = [p for p in build_grid("full", max_size=MAX_ROWS) if p.split == DEV and p.op in OPS]
    out, by = [], defaultdict(list)
    for p in sorted(grid, key=lambda q: (q.op, q.id)):
        by[p.op].append(p)
    for op in OPS:
        pts = by[op]
        step = max(1, len(pts) // PER_OP)
        out += pts[::step][:PER_OP]
    return out


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    from benchmarks.runner import _prepare, default_mem_limit_bytes, env_info, run_prediction
    from nexus.power import power_state

    ap = argparse.ArgumentParser(prog="python -m benchmarks.determinism")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=REPEATS)
    args = ap.parse_args(argv)
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    cache = Path("benchmarks/.cache")
    env, cap = env_info(), default_mem_limit_bytes()
    rows = []
    points = pick_points()
    for i, point in enumerate(points, 1):
        path = _prepare(point, cache)
        source = point.source.format(csv=path) if "{csv" in point.source else point.source
        for rep in range(args.repeats):
            r = run_prediction(point, 1, source, cache, cap, env)
            t1 = (
                (json.loads(r.get("features") or "{}").get("tier1") or {})
                if r.get("has_estimate")
                else {}
            )
            rows.append({"point": point.id, "op": point.op, "rep": rep, "status": r["status"],
                         "ram_expected": r.get("ram_expected"), "ram_high": r.get("ram_high"),
                         "time_expected": r.get("time_expected"),
                         "tier1_used": bool(t1.get("used", bool(t1))), "reason": t1.get("reason"),
                         "sample": t1.get("sample"), "stats_s": t1.get("stats_s"), "power": power_state()})  # fmt: skip
        print(f"[{i}/{len(points)}] {point.id}", flush=True)
    df = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out.with_suffix(".csv"), index=False)
    per_point = []
    for (op, pid), g in df[df["status"] == "ok"].groupby(["op", "point"]):
        rec = {"op": op, "point": pid, "n": len(g), "fallback_differs": g["tier1_used"].nunique() > 1,
               "tier1_runs": int(g["tier1_used"].sum())}  # fmt: skip
        for col in ("ram_expected", "ram_high", "time_expected", "sample"):
            v = pd.to_numeric(g[col], errors="coerce").dropna()
            if len(v) and v.median():
                rec[f"{col}_spread"] = float((v.max() - v.min()) / v.median())
                rec[f"{col}_cv"] = float(v.std(ddof=0) / v.mean())
        per_point.append(rec)
    pp = pd.DataFrame(per_point)
    lines = [
        "# Tier 1 determinism (Phase 6d; information only, nothing changed)",
        "",
        f"{len(points)} stored dev points (<= {MAX_ROWS:,} rows; {PER_OP} per operation with Tier 1 statistics), "
        f"{args.repeats} repeats each, each a fresh prediction process (the benchmark's worker), mains power "
        f"(power seen: {sorted(df['power'].unique())}). Spread = (max - min) / median over the repeats of one point; "
        "CV = std / mean. Raw rows: `determinism.csv`.",
        "",
        "| op | points | points whose fallback differs | median spread expected | max spread expected | "
        "median spread high | max spread high | median spread time | max spread time | median spread sample |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for op, g in pp.groupby("op"):

        def f(c: str, fn: str, g: pd.DataFrame = g) -> str:
            if c not in g:
                return "-"
            v = getattr(g[c], fn)()
            return "-" if pd.isna(v) else f"{v:.2%}"

        lines.append(
            f"| {op} | {len(g)} | {int(g['fallback_differs'].sum())} | {f('ram_expected_spread', 'median')} | "
            f"{f('ram_expected_spread', 'max')} | {f('ram_high_spread', 'median')} | {f('ram_high_spread', 'max')} | "
            f"{f('time_expected_spread', 'median')} | {f('time_expected_spread', 'max')} | {f('sample_spread', 'median')} |"
        )
    flips = pp[pp["fallback_differs"]]
    lines += ["", f"Points whose Tier 0 fallback differs between repeats: {len(flips)} of {len(pp)}"
              + ("".join(f"\n- {r.point}: Tier 1 in {r.tier1_runs} of {r.n} runs" for r in flips.itertuples()) if len(flips) else ""),
              "", "## Proposal for v3 (not implemented)", "",
              "Seed the statistics sampler from the cell hash and fix the sample size per operation (independent of the "
              "time budget; the budget would only decide between that sample and no statistics). Repeated analyses of "
              "the same cell on the same data would then give identical estimates; the remaining variation would be "
              "the budget decision itself. This changes frozen files (`stats.py`, the models' Tier 1 code): a v3 freeze "
              "and a fresh evaluation are needed."]  # fmt: skip
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
