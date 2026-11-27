"""Pre-freeze check of deterministic Tier 1 selection and hard-deadline firing rates.

Runs the benchmark's prediction worker in a fresh process with a fixed 250 ms hard deadline.
Deadline firings are unestimated and listed. For all other runs it compares the estimate signature
across repeats. Mains power required.

    python -m benchmarks.determinism --point-ids docs/benchmarks/phase7b/determinism_final_cores2.csv --repeats 3 --condition cores2_contended --out <md>
    python -m benchmarks.determinism --point-ids docs/benchmarks/phase7b/determinism_final_cores2.csv --repeats 3 --condition all --out <md>

Phase 7b: ``--max-rows`` (points spread over the sizes, the largest included), ``--condition`` (``all`` CPUs
or ``cores2_contended``: the process and its workers pinned to 2 CPUs with 2 busy loops on them), and the
power state checked before every point (the run stops on battery unless ``--allow-battery``, dev only:
rows then record ``battery (user-accepted)`` and the report carries ``powerguard.BATTERY_NOTE``).
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
HARD_DEADLINE_S = 0.25


def pick_points(
    max_rows: int = MAX_ROWS, spread_sizes: bool = False, point_ids: list[str] | None = None
) -> list:
    from benchmarks.split import DEV
    from benchmarks.suite import build_grid

    grid = [p for p in build_grid("full", max_size=max_rows) if p.split == DEV and p.op in OPS]
    if point_ids is not None:
        by_id = {p.id: p for p in grid}
        missing = [pid for pid in point_ids if pid not in by_id]
        if missing:
            raise ValueError(f"unknown dev point ids: {missing}")
        return [by_id[pid] for pid in point_ids]
    out, by = [], defaultdict(list)
    key = (lambda q: (q.op, q.size, q.id)) if spread_sizes else (lambda q: (q.op, q.id))
    for p in sorted(grid, key=key):
        by[p.op].append(p)
    for op in OPS:
        pts = by[op]
        if spread_sizes and len(pts) > PER_OP:  # evenly over the sizes, the largest included
            idx = sorted({round(i * (len(pts) - 1) / (PER_OP - 1)) for i in range(PER_OP)})
            out += [pts[i] for i in idx]
            continue
        step = max(1, len(pts) // PER_OP)
        out += pts[::step][:PER_OP]
    return out


def _busy(cores: list[int]) -> None:
    import psutil

    psutil.Process().cpu_affinity(cores)
    x = 0
    while True:
        x = (x * 1103515245 + 12345) % 2147483648


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    from benchmarks.runner import _prepare, default_mem_limit_bytes, env_info, run_prediction
    from nexus.power import power_state

    ap = argparse.ArgumentParser(prog="python -m benchmarks.determinism")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--max-rows", type=int, default=MAX_ROWS)
    ap.add_argument("--condition", choices=("all", "cores2_contended"), default="all")
    ap.add_argument(
        "--allow-battery", action="store_true", help="dev only: run on battery (recorded)"
    )
    ap.add_argument("--title", default="Tier 1 determinism (v4 pre-freeze dev check)")
    ap.add_argument("--point-ids", type=Path, help="CSV with a `point` column listing inputs")
    ap.add_argument(
        "--report-existing", type=Path, help="summarize an existing raw CSV without rerunning"
    )
    args = ap.parse_args(argv)
    from benchmarks.powerguard import power_record

    args.power_rec = power_record(args.allow_battery, "dev")
    if args.report_existing is not None:
        df = pd.read_csv(args.report_existing)
        point_ids = list(dict.fromkeys(df["point"].astype(str)))
        points = pick_points(
            args.max_rows, spread_sizes=args.max_rows != MAX_ROWS, point_ids=point_ids
        )
        _write_report(args, df, points, write_csv=False)
        return
    import multiprocessing as mp

    import psutil

    hogs = []
    if args.condition == "cores2_contended":
        psutil.Process().cpu_affinity([0, 1])
        ctx = mp.get_context("spawn")
        hogs = [ctx.Process(target=_busy, args=([0, 1],), daemon=True) for _ in range(2)]
        for h in hogs:
            h.start()
    try:
        _run(args, power_state, env_info, default_mem_limit_bytes, _prepare, run_prediction)
    finally:
        for h in hogs:
            h.terminate()


def _run(args, power_state, env_info, default_mem_limit_bytes, _prepare, run_prediction) -> None:  # noqa: ANN001, C901
    from benchmarks.powerguard import recorded

    cache = Path("benchmarks/.cache")
    env, cap = env_info(), default_mem_limit_bytes()
    rows = []
    point_ids = None
    if args.point_ids is not None:
        historical = pd.read_csv(args.point_ids, usecols=["point", "status"])
        historical = historical[historical["status"] == "ok"]
        point_ids = list(dict.fromkeys(historical["point"].astype(str)))
    points = pick_points(args.max_rows, spread_sizes=args.max_rows != MAX_ROWS, point_ids=point_ids)
    for i, point in enumerate(points, 1):
        if power_state() == "battery" and not args.allow_battery:
            raise SystemExit(f"on battery power at point {i}: stopped (no partial report)")
        path = _prepare(point, cache)
        source = point.source.format(csv=path) if "{csv" in point.source else point.source
        for rep in range(args.repeats):
            r = run_prediction(point, 1, source, cache, cap, env, hard_deadline_s=HARD_DEADLINE_S)
            t1 = (
                (json.loads(r.get("features") or "{}").get("tier1") or {})
                if r.get("has_estimate")
                else {}
            )
            rows.append({"point": point.id, "op": point.op, "rep": rep, "status": r["status"],
                         "ram_low": r.get("ram_low"), "ram_expected": r.get("ram_expected"),
                         "ram_high": r.get("ram_high"), "time_low": r.get("time_low"),
                         "time_expected": r.get("time_expected"), "time_high": r.get("time_high"),
                         "tier1_used": bool(t1.get("used", bool(t1))), "reason": t1.get("reason"),
                         "sample": t1.get("sample"), "stats_s": t1.get("stats_s"),
                         "estimate_tier": r.get("estimate_tier"), "has_estimate": r.get("has_estimate"),
                         "hard_deadline_fired": bool(r.get("hard_deadline_fired")),
                         "power": recorded(power_state())})  # fmt: skip
        print(f"[{i}/{len(points)}] {point.id}", flush=True)
    df = pd.DataFrame(rows)
    _write_report(args, df, points, write_csv=True)


def _write_report(args, df: pd.DataFrame, points: list, *, write_csv: bool) -> None:  # noqa: ANN001, C901
    from benchmarks.powerguard import BATTERY_NOTE

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if write_csv:
        df.to_csv(args.out.with_suffix(".csv"), index=False)
    per_point = []
    for (op, pid), g in df.groupby(["op", "point"]):
        non_fired = g[(g["status"] == "ok") & ~g["hard_deadline_fired"]]
        signatures = non_fired[
            [
                "has_estimate",
                "estimate_tier",
                "ram_low",
                "ram_expected",
                "ram_high",
                "time_low",
                "time_expected",
                "time_high",
            ]
        ]
        rec = {"op": op, "point": pid, "n": len(g),
               "status_failures": int((g["status"] != "ok").sum()),
               "deadline_firings": int(g["hard_deadline_fired"].sum()),
               "estimate_differs": len(signatures.drop_duplicates()) > 1,
               "fallback_differs": non_fired["tier1_used"].nunique() > 1,
               "tier1_runs": int(g["tier1_used"].sum())}  # fmt: skip
        for col in ("ram_expected", "ram_high", "time_expected", "sample"):
            v = pd.to_numeric(g[col], errors="coerce").dropna()
            if len(v) and v.median():
                rec[f"{col}_spread"] = float((v.max() - v.min()) / v.median())
                rec[f"{col}_cv"] = float(v.std(ddof=0) / v.mean())
        per_point.append(rec)
    pp = pd.DataFrame(per_point)
    firing_count = int(df["hard_deadline_fired"].sum())
    firing_rate = firing_count / (len(points) * args.repeats)
    firing_bar = 0.05 if args.condition == "cores2_contended" else 0.0
    criteria = "MET" if firing_rate <= firing_bar else "FAILED"
    unstable = pp[pp["estimate_differs"]]
    comparable = 0
    for _, g in df.groupby("point"):
        valid = g[(g["status"] == "ok") & ~g["hard_deadline_fired"]]
        if len(valid) >= 2:
            comparable += 1
    signature_firings = int(((df["status"] == "ok") & ~df["hard_deadline_fired"]).sum())
    failures = df[df["status"] != "ok"]
    lines = [
        f"# {args.title}",
        "",
        *(
            [
                BATTERY_NOTE,
                "",
                f"Power at the start: `{json.dumps(args.power_rec, default=str)}`",
                "",
            ]
            if args.power_rec.get("power") != "mains"
            else []
        ),
        f"Condition: {args.condition}. {len(points)} stored dev points (<= {args.max_rows:,} rows), "
        f"{args.repeats} repeats each, each a fresh prediction process with a "
        f"{HARD_DEADLINE_S * 1000:.0f} ms hard deadline, mains power "
        f"(power seen: {sorted(df['power'].unique())}). Spread = (max - min) / median over the repeats of one point; "
        f"CV = std / mean. Every hard-deadline firing is NOT ESTIMATED. "
        f"Raw rows: `{args.out.with_suffix('.csv').name}`.",
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
    lines += ["", f"Points whose Tier 1/Tier 0 selection differs between non-firing repeats: {len(flips)} of {len(pp)}"
              + ("".join(f"\n- {r.point}: Tier 1 in {r.tier1_runs} of {r.n} runs" for r in flips.itertuples()) if len(flips) else ""),
              f"Points with non-identical estimate signatures among non-firing repeats: {len(unstable)} of {comparable} comparable points "
              + ("".join(f"\n- {r.point}" for r in unstable.itertuples()) if len(unstable) else ""),
              f"Successful non-firing analyses: {signature_firings}/{len(points) * args.repeats}; "
              "each is an estimate or a deterministic model-level no-estimate.",
              f"Hard-deadline firings: {firing_count}/{len(points) * args.repeats} = {firing_rate:.2%}; "
              f"pre-registered bar <= {firing_bar:.0%}: **{criteria}**.",
              "Firing inputs:" +
              ("".join(f"\n- {r.point}, repeat {r.rep}" for r in df[df["hard_deadline_fired"]].itertuples())
               if firing_count else " none."),
              f"Non-deadline worker failures (also unestimated): {len(failures)}."
              + ("".join(f"\n- {r.point}, repeat {r.rep}: {r.status}" for r in failures.itertuples())
                 if len(failures) else ""),
              ]  # fmt: skip
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
