"""Run / evaluate the multi-statement benchmark (Phase 6c pre-registration A).

    python -m benchmarks.multicell.run run                       # dev part (mains power required)
    python -m benchmarks.multicell.run evaluate --out docs/benchmarks/phase6c
    python -m benchmarks.multicell.run run --heldout --reason "..."       # held-out: ONCE, frozen stack
    python -m benchmarks.multicell.run evaluate --heldout --reason "..." --out <dir>

``--version 2`` selects the Phase 7 group (``cases_v2``, ``split_v2.json``; results in
``benchmarks/results/multicell_v2``, access log ``docs/benchmarks/phase7-heldout-access-log.md``), the
held-out check of freeze v3; v1 (the default) is the Phase 6c group, all dev since 2026-11-22.

Each cell: the prediction (``Pipeline(tier=1)`` on the cell with its inputs loaded; the cell-level
model ``nexus.cellpeak`` and, for comparison, the v1 aggregation ``nexus.risk.combine``) in a fresh
process, then the measurement with the validated instrument (``nexus.measure.measure_call``: fresh
processes, inputs from disk, median of 3 runs, incremental OS peak). Held-out runs require the frozen
stack (``benchmarks.frozen.require_frozen``), mains power and a reason; their console output is id /
status / time only, their results go to ``<results>/heldout/`` and every access is logged.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import psutil

from benchmarks.multicell import cases, cases_v2, cases_v3
from benchmarks.multicell import split as split_mod

RESULTS = Path("benchmarks/results/multicell")
CACHE = Path("benchmarks/.cache/multicell")
HELDOUT_LOG = Path("docs/benchmarks/phase6c-heldout-access-log.md")
# v2 (Phase 7): its own results, cache and held-out access log; same rules
SUITES = {
    1: (cases, RESULTS, CACHE, HELDOUT_LOG),
    2: (cases_v2, Path("benchmarks/results/multicell_v2"), Path("benchmarks/.cache/multicell_v2"),
        Path("docs/benchmarks/phase7-heldout-access-log.md")),
    3: (cases_v3, Path("benchmarks/results/multicell_v3"), Path("benchmarks/.cache/multicell_v3"),
        Path("docs/benchmarks/phase7-heldout-access-log.md")),
}  # fmt: skip
# simulated headrooms (MiB) at which the prediction child records the risk class (the uncovered-operation rule)
HEADROOMS_MIB = (64, 128, 256, 512, 1024, 2048, 4096, 8192)
MIB = 2**20
ABOVE_HIGH_CELL, ABOVE_HIGH_CONFIG = 0.03, 0.05


# -- child-process functions (module level: spawn-picklable) ------------------------------------------
def load_inputs(paths: dict[str, str], src: str) -> dict[str, Any]:
    import numpy as np

    ns = {"pd": pd, "np": np, "df": pd.read_pickle(paths["df"]), "df2": pd.read_pickle(paths["df2"]),
          "right": pd.read_pickle(paths["right"]), "__src__": src}  # fmt: skip
    gc.collect()
    return ns


def exec_cell(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (generated benchmark cells only)
    return 0


def _est(e: Any) -> dict[str, Any] | None:
    if e is None:
        return None
    return {
        k: getattr(e, k) for k in ("ram_low", "ram_expected", "ram_high", "time_expected", "tier")
    }


def _predict_child(paths: dict[str, str], src: str) -> dict[str, Any]:
    from nexus.cellpeak import cell_estimate
    from nexus.pipeline import Pipeline
    from nexus.risk import combine

    ns = load_inputs(paths, src)
    rep = Pipeline(tier=1).run(src, ns)
    new, mode, flags = cell_estimate(src, rep.estimates)
    v1 = combine([e.estimate for e in rep.estimates])
    classes = _classes(rep, src, new)
    return {
        "ops": [o.name for o in rep.ops],
        "estimates": [{"model": e.model, "tier": e.estimate.tier} for e in rep.estimates],
        "uncovered": len({id(o) for o in rep.ops} - {id(e.op) for e in rep.estimates}),
        "new": _est(new), "v1": _est(v1), "mode": mode, "flags": flags, "classes": classes,
    }  # fmt: skip


def _classes(rep: Any, src: str, cell: Any) -> dict[str, str] | None:
    """Risk class per simulated headroom (MiB), the same call ``risk.assess`` makes; None without estimates."""
    from dataclasses import replace

    from nexus.cellpeak import cell_estimate
    from nexus.risk import classify, describe_uncovered, warn_high_estimate

    if not rep.estimates or cell is None:
        return None
    covered = {id(e.op) for e in rep.estimates}
    missing = [o for o in rep.ops if id(o) not in covered]
    warn, _, _ = cell_estimate(
        src, [replace(e, estimate=warn_high_estimate(e)) for e in rep.estimates]
    )
    out = {}
    for h in HEADROOMS_MIB:
        r = classify([e.estimate for e in rep.estimates], None, headroom=h * MIB, uncovered=len(missing),
                     drivers_from=rep.estimates or None, cell=cell, warn_high=warn.ram_high,
                     uncovered_ops=describe_uncovered(missing) if missing else None)  # fmt: skip
        out[str(h)] = r.risk.value
    return out


def predict(paths: dict[str, str], src: str) -> dict[str, Any]:
    """The prediction in a fresh process. A native crash or a hang is a HARNESS EVENT: returned as
    ``{"harness": {...}}`` with no estimate, so the cell is never scored (``metrics`` needs ``new``)."""
    from benchmarks.childproc import ChildFailureError, run_child

    try:
        return run_child(_predict_child, paths, src, timeout_s=600)
    except ChildFailureError as fail:
        return {"harness": fail.record(), "new": None, "v1": None}


# -- running -----------------------------------------------------------------------------------------
def _log_access(line: str, log: Path = HELDOUT_LOG) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"- {time.strftime('%Y-%m-%d %H:%M:%S')} | {line}\n")


def run(
    *,
    heldout: bool = False,
    reason: str = "",
    results: Path | None = None,
    limit: int | None = None,
    version: int = 1,
) -> Path:
    from benchmarks.heldout_env import profile_record
    from nexus.measure import measure_call
    from nexus.power import power_state

    mod, default_results, cache, log = SUITES[version]
    results = results or default_results
    sp = split_mod.load(version=version)
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    if heldout:
        if not reason:
            raise SystemExit("--heldout needs --reason")
        from benchmarks.frozen import require_frozen

        frozen = require_frozen()
        from benchmarks.heldout_env import require_profile

    keys = set(sp.heldout if heldout else sp.dev)
    out_dir = results / ("heldout" if heldout else "dev")
    if heldout:
        env = require_profile(out_dir)  # pins the profile on the first run, requires it on resume
        _log_access(
            f"RUN held-out multicell v{version} | frozen {frozen} | profile {env} | reason: {reason}",
            log,
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "results.jsonl"
    done = (
        {json.loads(line)["id"] for line in out.open(encoding="utf-8")} if out.exists() else set()
    )
    cells = [c for c in mod.all_cells(keys) if c.id not in done][:limit]
    for i, cell in enumerate(cells, 1):
        t0 = time.monotonic()
        paths = mod.prepare(cache, cell.config.shape, cell.rows)
        src = mod.source(cell, paths)
        pred = predict(paths, src)
        if "harness" in pred:  # not measured either: a harness event, listed by the report
            with out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"id": cell.id, "config": cell.config.key, "template": cell.config.template,
                                     "status": pred["harness"]["status"], "harness": pred["harness"],
                                     "power": power_state()}) + chr(10))  # fmt: skip
            print(f"[{i}/{len(cells)}] {cell.id}: {pred['harness']['status']}", flush=True)
            continue
        cap = int(0.7 * psutil.virtual_memory().available)
        m = measure_call(exec_cell, setup=load_inputs, setup_args=(paths, src), repeats=3,
                         max_rss_bytes=cap)  # fmt: skip
        row = {"id": cell.id, "config": cell.config.key, "template": cell.config.template,
               "shape": cell.config.shape, "rows": cell.rows, "status": m.status,
               "actual": m.delta_bytes, "censored": m.censored, "bound": m.bound_bytes,
               "spread": m.ram_spread, "time_s": m.time_s, **profile_record(),
               "power": power_state(), **pred}  # fmt: skip
        with out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        took = time.monotonic() - t0
        if heldout:
            print(f"[{i}/{len(cells)}] {cell.id}: {m.status} ({took:.0f} s)", flush=True)
        else:
            a = "censored" if m.delta_bytes is None else f"{m.delta_bytes / MIB:.0f} MiB"
            n = pred["new"]["ram_expected"] / MIB if pred["new"] else float("nan")
            print(
                f"[{i}/{len(cells)}] {cell.id}: {m.status} actual {a} | new exp {n:.0f} MiB ({took:.0f} s)",
                flush=True,
            )
    return out


# -- evaluation --------------------------------------------------------------------------------------
def metrics(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    pts = [r for r in rows if r.get("actual") and r.get(key)]
    if not pts:
        return {"n": 0}
    a = pd.Series([float(r["actual"]) for r in pts])
    lo = pd.Series([r[key]["ram_low"] for r in pts])
    e = pd.Series([r[key]["ram_expected"] for r in pts], dtype=float)
    hi = pd.Series([r[key]["ram_high"] for r in pts])
    rel = (e - a).abs() / a
    above = a > hi
    cfg_above = pd.Series([r["config"] for r in pts])[above.values].nunique()
    return {
        "n": len(pts), "configs": len({r["config"] for r in pts}),
        "bias": float((e / a).median()), "err_med": float(rel.median()), "err_p90": float(rel.quantile(0.9)),
        "coverage": float(((lo <= a) & (a <= hi)).mean()), "above_high": float(above.mean()),
        "above_high_n": int(above.sum()), "configs_above_high": int(cfg_above),
        "below_low": float((a < lo).mean()), "width": float(((hi - lo) / e.where(e > 0)).mean()),
    }  # fmt: skip


RATIO_COLS = (
    "bias",
    "width",
    "v1_bias",
    "v2_bias",
    "v3_bias",
)  # ratios (x); every other float column is a share (%)


def _fmt(v: Any, col: str) -> str:
    if isinstance(v, float):
        if math.isnan(v):
            return "-"
        return f"{v:.2f}" if col in RATIO_COLS else f"{v:.1%}"
    return str(v)


def _table(rows: list[dict[str, Any]]) -> list[str]:
    cols = list(rows[0])
    return ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols),
            *["| " + " | ".join(_fmt(r.get(c), c) for c in cols) + " |" for r in rows]]  # fmt: skip


def report(rows: list[dict[str, Any]], title: str) -> str:
    lines = [f"# {title}", ""]
    measured = [r for r in rows if r.get("actual")]
    events = [r for r in rows if r.get("harness")]
    rows = [r for r in rows if not r.get("harness")]
    if events:
        lines += [
            f"**Harness events (not scored):** {[(r['id'], r['status']) for r in events]}",
            "",
        ]
    lines.append(f"{len(rows)} cells run; {len(measured)} with a measured peak (others censored / killed: "
                 f"{[r['id'] for r in rows if not r.get('actual')]}).")  # fmt: skip
    lines += ["", "## All cells", ""]
    lines += _table(
        [
            {"model": "new (cellpeak)", **metrics(rows, "new")},
            {"model": "v1 (combine)", **metrics(rows, "v1")},
        ]
    )
    new = metrics(rows, "new")
    if new.get("n"):
        cell_ok = new["above_high"] <= ABOVE_HIGH_CELL
        cfg_ok = new["configs_above_high"] / max(new["configs"], 1) <= ABOVE_HIGH_CONFIG
        lines += ["", f"* **above_high <= 3% of cells:** {new['above_high']:.1%} -> {'MET' if cell_ok else 'FAILED'}",
                  f"* **above_high <= 5% of configurations:** {new['configs_above_high']} of {new['configs']} -> "
                  f"{'MET' if cfg_ok else 'FAILED'}"]  # fmt: skip
    covered = [r for r in rows if r.get("uncovered") == 0]
    lines += ["", "## Cells whose every operation has an estimate (descriptive)", ""]
    lines += _table(
        [{"model": "new", **metrics(covered, "new")}, {"model": "v1", **metrics(covered, "v1")}]
    )
    lines += ["", "## Per template (new model)", ""]
    per = []
    for t in sorted({r["template"] for r in rows}):
        g = [r for r in rows if r["template"] == t]
        per.append({"template": t, **metrics(g, "new"), "v1_bias": metrics(g, "v1").get("bias", float("nan")),
                    "uncovered_ops": sum(r.get("uncovered", 0) for r in g)})  # fmt: skip
    lines += _table(per)
    lines += ["", "## Uncovered-operation rule (amendment 1): a cell with an uncovered operation must never be OK", "",
              "at a simulated headroom its ACTUAL exceeds (UNKNOWN, WARN and HIGH_RISK are acceptable).", ""]  # fmt: skip
    unc = [r for r in rows if r.get("uncovered") and r.get("classes") and r.get("actual")]
    viol = [
        (r["id"], h)
        for r in unc
        for h, c in r["classes"].items()
        if c == "OK" and r["actual"] > int(h) * MIB
    ]
    lines.append(f"Cells with an uncovered operation: {len(unc)}; violations (OK while actual > headroom): "
                 f"{len(viol)} -> {'MET' if not viol else 'FAILED'}" + (f": {viol}" if viol else ""))  # fmt: skip
    lines += ["", "## Every cell (MiB)", ""]
    cells = []
    for r in rows:
        n, v = r.get("new") or {}, r.get("v1") or {}
        actual = f"{r['actual'] / MIB:.0f}" if r.get("actual") else "-"
        cells.append({"cell": r["id"], "actual": actual,
                      "new low/exp/high": f"{n.get('ram_low', 0) / MIB:.0f} / {n.get('ram_expected', 0) / MIB:.0f} / {n.get('ram_high', 0) / MIB:.0f}",
                      "v1 exp/high": f"{v.get('ram_expected', 0) / MIB:.0f} / {v.get('ram_high', 0) / MIB:.0f}",
                      "mode": r.get("mode"), "uncovered": r.get("uncovered")})  # fmt: skip
    lines += _table(cells)
    return "\n".join(lines) + "\n"


def evaluate(
    *,
    heldout: bool = False,
    reason: str = "",
    results: Path | None = None,
    out: Path,
    version: int = 1,
) -> Path:
    _, default_results, _, log = SUITES[version]
    results = results or default_results
    part = "heldout" if heldout else "dev"
    if heldout:
        if not reason:
            raise SystemExit("--heldout needs --reason")
        tag = "" if version == 1 else f" v{version}"
        _log_access(f"EVALUATE held-out multicell{tag} | reason: {reason}", log)
    path = results / part / "results.jsonl"
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    out.mkdir(parents=True, exist_ok=True)
    target = out / (f"multicell_{part}.md" if version == 1 else f"multicell_v{version}_{part}.md")
    phase = "Phase 6c" if version == 1 else f"v{version}, Phase 7"
    title = (f"Multi-statement cells ({phase}): HELD-OUT part (read once)" if heldout
             else f"Multi-statement cells ({phase}): DEV part (not validation)")  # fmt: skip
    target.write_text(report(rows, title), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m benchmarks.multicell.run")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "evaluate"):
        s = sub.add_parser(name)
        s.add_argument("--heldout", action="store_true")
        s.add_argument("--reason", default="")
        s.add_argument("--results", type=Path, default=None)
        s.add_argument("--version", type=int, choices=sorted(SUITES), default=1)
        if name == "run":
            s.add_argument("--limit", type=int)
        else:
            s.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.cmd == "run":
        print(run(heldout=args.heldout, reason=args.reason, results=args.results, limit=args.limit,
                  version=args.version))  # fmt: skip
    else:
        print(evaluate(heldout=args.heldout, reason=args.reason, results=args.results, out=args.out,
                       version=args.version))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
