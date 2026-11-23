"""Phase 8a harness: run a COPY of a notebook cell by cell and record NEXUS's estimate vs the actual.

Pre-registration: ``docs/benchmarks/phase8a-preregistration.md``. The "kernel" is a fresh spawned
process hosting an IPython ``InteractiveShell`` (what an ipykernel wraps; ipykernel is not installed).
NEXUS is loaded as an extension with its own hook switched off (logging mode); before each cell the
harness runs the analysis itself, OUTSIDE the measured window:

* primary: ``Pipeline(tier=2)`` (controller; Tier 1 under the 250 ms budget; Tier 2 only if the
  controller triggers and the safety analyzer accepts), risk class, suggestions (default rules);
* secondary: ``Pipeline()`` (Tier 0, what ``%load_ext nexus`` uses today).

Then the cell runs; its output is discarded. Actuals: wall time of the cell; RAM from a parent-side
RSS sampler (~2 ms) and the OS peak counter read before / after in the kernel. The OS counter cannot
be reset on Windows, so a cell's RAM actual is valid only if the cell raised the historical OS peak
(on Linux the counter is reset before each cell when possible); otherwise it is CENSORED (the sampler
value is kept for information, never as an actual). Safety: a watchdog kills the kernel if its RSS
exceeds the cap (default 70% of the free RAM at start); per-cell timeout (default 10 min);
per-notebook budget (default 60 min); stop after N consecutive failing cells (default 5). A kill is a
RAM lower bound. Shell / package cells are never executed. Failing cells: error TYPE only.

Records (JSONL, ``<out>/cells.jsonl``): cell index and hash, operation names, input shapes / dtype
counts, numbers. Never cell code, outputs or data values. Refuses to run unless the freeze guard
passes and the machine is on mains power. ``--allow-battery`` is accepted only with ``--dev`` (a dev run;
``benchmarks.powerguard``): rows record ``battery (user-accepted)``, the summary holds the raw readings, and
the timing figures are battery-throttled (not usable for calibration or timing claims).

    python -m benchmarks.realworld.run_notebook <notebook.ipynb> --out benchmarks/results/realworld/<name>
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import io
import json
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

MIB = 2**20
RAM_FLOOR = 32 * MIB
TIME_FLOOR_S = 0.100
SAMPLE_S = 0.002
SHELL_CELL = re.compile(
    r"^\s*(!|%pip|%conda|%%bash|%%sh|%system|%%script|%%cmd|%%powershell|%sx|%%sx)", re.M
)


@dataclass
class Limits:
    cap_bytes: int | None = None  # watchdog: kernel RSS cap; None = 70% of free RAM at start
    cell_timeout_s: float = 600.0
    notebook_budget_s: float = 3600.0
    max_consecutive_failures: int = 5


@dataclass
class RunSummary:
    notebook: str
    outcome: str = "completed"
    cells: int = 0
    executed: int = 0
    failed: int = 0
    skipped: int = 0
    elapsed_s: float = 0.0
    stop_reason: str = ""
    frozen: dict[str, Any] = field(default_factory=dict)
    power: str = ""
    battery: dict[str, Any] = field(
        default_factory=dict
    )  # raw readings of a user-accepted battery dev run
    profile_id: str | None = None
    cap_bytes: int = 0
    profile_calibrated: bool | None = None


def cell_hash(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]


def read_cells(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for c in raw.get("cells", []):
        if c.get("cell_type") != "code":
            continue
        s = c.get("source", "")
        out.append("".join(s) if isinstance(s, list) else str(s))
    return out


# -- the kernel (child process) ------------------------------------------------------------------
def _describe_inputs(report: Any) -> dict[str, Any]:
    out = {}
    for name, d in getattr(report.inspection, "variables", {}).items():
        shape = getattr(d, "shape", None)
        dtypes = getattr(d, "dtype_counts", None) or (
            {getattr(d, "dtype", "?"): 1} if hasattr(d, "dtype") else {}
        )
        out[cell_hash(name)] = {"kind": getattr(d, "kind", "?"), "shape": list(shape) if shape else None,
                                "dtypes": dtypes, "bytes": int(getattr(d, "nbytes", 0) or 0)}  # fmt: skip
    return out


def _estimate_dict(e: Any) -> dict[str, Any]:
    return {k: getattr(e, k) for k in ("ram_low", "ram_expected", "ram_high", "time_low", "time_expected",
                                        "time_high", "confidence", "tier")} | {
        "flags": list(getattr(e, "flags", ())), "note": bool(e.note)}  # fmt: skip


def _analyse(src: str, ns: dict[str, Any], primary: Any, secondary: Any) -> dict[str, Any]:
    from nexus.cellpeak import cell_estimate
    from nexus.failsafe import Deadline
    from nexus.risk import assess
    from nexus.session import DEFAULT_BUDGET_S
    from nexus.suggestions import suggest

    rec: dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        rep = primary.run(src, ns, Deadline(DEFAULT_BUDGET_S))
        rec["ops"] = [o.name for o in rep.ops]
        rec["estimates"] = [{"model": e.model, "op": e.op.name, **_estimate_dict(e.estimate),
                             "tier1_used": bool((e.features.get("tier1") or {}).get("used", "tier1" in e.features))}
                            for e in rep.estimates]  # fmt: skip
        cell, mode, _flags = cell_estimate(src, rep.estimates)  # the cell-level model (Phase 6c)
        rec["cell_mode"] = mode
        rec["cell"] = _estimate_dict(cell) if cell else None
        rec["uncovered"] = len({id(o) for o in rep.ops} - {id(e.op) for e in rep.estimates})
        rec["inputs"] = _describe_inputs(rep)
        risk = assess(rep)
        rec["risk"] = (
            {"class": risk.risk.value, "reason_kind": risk.reason.split(":")[0][:60], "headroom": risk.headroom}
            if risk else None
        )  # fmt: skip
        if rep.ops:
            sg = suggest(src, ns, rep.inspection, rep.ops)
            rec["suggestions"] = [{"rule": s.rule, "semantics": s.semantics} for s in sg]
        sec = secondary.run(src, ns, Deadline(DEFAULT_BUDGET_S))
        c0, _m0, _f0 = cell_estimate(src, sec.estimates)
        rec["cell_tier0"] = _estimate_dict(c0) if c0 else None
    except Exception as exc:
        rec["analysis_error"] = type(exc).__name__
    rec["analysis_s"] = time.perf_counter() - t0
    return rec


def _kernel_main(conn: Any, workdir: str, tier: int = 2) -> None:  # noqa: C901
    os.chdir(workdir)
    from IPython.core.interactiveshell import InteractiveShell

    from nexus.extension import get_session
    from nexus.measure import read_memory, reset_peak
    from nexus.pipeline import Pipeline

    shell = InteractiveShell.instance()
    shell.run_line_magic("load_ext", "nexus")
    session = get_session(shell)
    if session is not None:
        session.enabled = False  # logging mode: the harness runs the analysis itself
    primary, secondary = Pipeline(tier=tier), Pipeline()
    conn.send(("ready", os.getpid()))
    while True:
        msg = conn.recv()
        if msg[0] == "quit":
            break
        src = msg[1]
        rec = _analyse(src, shell.user_ns, primary, secondary)
        gc.collect()
        reset = reset_peak()
        before = read_memory()
        conn.send(("start", before.rss, before.peak or 0, reset, rec))
        sink = io.StringIO()
        t0 = time.perf_counter()
        err = None
        try:
            with redirect_stdout(sink), redirect_stderr(sink):
                result = shell.run_cell(src, store_history=True)
            exc = result.error_in_exec or result.error_before_exec
            err = type(exc).__name__ if exc is not None else None
        except BaseException as exc:  # never let the kernel die from a cell
            err = type(exc).__name__
        elapsed = time.perf_counter() - t0
        after = read_memory()
        del sink
        conn.send(("done", elapsed, err, after.rss, after.peak or 0))
    conn.close()


# -- the parent ----------------------------------------------------------------------------------
def _ram_actual(
    rss_start: int, peak_before: int, peak_after: int, poll_max: int, reset: bool
) -> dict:
    raised = reset or peak_after > peak_before
    poll_delta = max(0, poll_max - rss_start)
    if not raised:
        return {"ram_class": "censored", "ram_reason": "below the previous historical peak",
                "ram_value": None, "ram_poll": poll_delta}  # fmt: skip
    value = max(0, peak_after - rss_start)
    if value < RAM_FLOOR:
        return {"ram_class": "censored", "ram_reason": "below the floor", "ram_value": None,
                "ram_poll": poll_delta}  # fmt: skip
    return {
        "ram_class": "valid",
        "ram_reason": "os peak",
        "ram_value": value,
        "ram_poll": poll_delta,
    }


def _start_kernel(workdir: Path, tier: int = 2) -> tuple[Any, Any, psutil.Process]:
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe()
    proc = ctx.Process(target=_kernel_main, args=(child, str(workdir), tier), daemon=True)
    os.environ.setdefault("MPLBACKEND", "Agg")
    proc.start()
    if not parent.poll(120):
        proc.kill()
        raise RuntimeError("kernel did not start")
    msg = parent.recv()
    return proc, parent, psutil.Process(msg[1])


def run(  # noqa: C901
    notebook: Path, out: Path, limits: Limits | None = None, *, allow_battery: bool = False,
    path_map: dict[str, str] | None = None, tier: int = 2, dev: bool = False,
) -> RunSummary:  # fmt: skip
    """Run ``notebook`` (a copy is made under ``out``); returns the run summary, writes cells.jsonl."""
    from benchmarks import frozen
    from nexus.machine import machine
    from nexus.power import power_state

    limits = limits or Limits()
    summary = RunSummary(notebook=notebook.stem)
    if dev:  # a DEV run (never held-out): the working tree may differ from the frozen tag
        summary.frozen = {
            "mode": "dev run, NOT the frozen stack",
            "head": frozen._git("rev-parse", "HEAD"),
        }
    else:  # aborts (NotFrozenError) on any frozen-file difference
        from benchmarks.heldout_env import require_profile

        summary.frozen = {**frozen.require_frozen(), "heldout_environment": require_profile(out)}
    from benchmarks.powerguard import BATTERY_NOTE, power_record, recorded

    if allow_battery and not dev:
        raise SystemExit("--allow-battery is refused for held-out runs (only with --dev)")
    if power_state() == "battery" and not allow_battery:
        raise SystemExit(
            "phase 8a harness: on battery power; plug in (recorded power state: battery)"
        )
    rec = power_record(allow_battery, "dev") if allow_battery else {"power": power_state()}
    summary.power = rec["power"]
    if rec["power"] != "mains":
        summary.battery = {**rec, "note": BATTERY_NOTE}
    summary.profile_calibrated = machine().calibrated
    summary.profile_id = machine().profile_id
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    work.mkdir(exist_ok=True)
    copy = work / notebook.name
    shutil.copyfile(notebook, copy)  # the original is never touched
    cells = read_cells(copy)
    summary.cells = len(cells)
    cap = limits.cap_bytes or int(0.70 * psutil.virtual_memory().available)
    summary.cap_bytes = cap
    log = (out / "cells.jsonl").open("w", encoding="utf-8")
    t_nb = time.monotonic()
    proc, conn, kproc = _start_kernel(work, tier)
    consecutive = 0
    try:
        for i, src in enumerate(cells):
            base = {"notebook": notebook.stem, "index": i, "hash": cell_hash(src)}
            if time.monotonic() - t_nb > limits.notebook_budget_s:
                summary.outcome, summary.stop_reason = "stopped", "notebook budget exhausted"
                break
            if not src.strip():
                continue
            if SHELL_CELL.search(src):
                summary.skipped += 1
                log.write(
                    json.dumps({**base, "status": "skipped", "why": "shell/package cell"}) + "\n"
                )
                continue
            for old, new in (path_map or {}).items():
                src = src.replace(old, new)
            avail = psutil.virtual_memory().available
            conn.send(("cell", src))
            msg = None
            while not conn.poll(1.0):  # the analysis (may include a Tier 2 dry run)
                if not proc.is_alive():
                    break
            if proc.is_alive():
                msg = conn.recv()
            if msg is None or msg[0] != "start":
                summary.outcome, summary.stop_reason = "kernel died", "during analysis"
                log.write(json.dumps({**base, "status": "kernel_died"}) + "\n")
                break
            _, rss_start, peak_before, reset, rec = msg
            poll_max, t0, killed = rss_start, time.monotonic(), None
            done = None
            while True:
                if conn.poll(SAMPLE_S):
                    done = conn.recv()
                    break
                try:
                    rss = kproc.memory_info().rss
                except psutil.Error:
                    killed = "kernel died"
                    break
                poll_max = max(poll_max, rss)
                if rss > cap:
                    killed = "watchdog"
                    break
                if time.monotonic() - t0 > limits.cell_timeout_s:
                    killed = "timeout"
                    break
            row = {
                **base,
                **rec,
                "avail_start": avail,
                "rss_start": rss_start,
                "power": recorded(power_state()),
                "profile_id": summary.profile_id,
            }
            if killed:
                proc.kill()
                proc.join(10)
                row.update(status=killed, time_value=None, ram_poll=poll_max - rss_start)
                if killed == "watchdog":  # a lower bound of the incremental peak
                    row.update(ram_class="valid", ram_value=poll_max - rss_start, ram_lower_bound=True,
                               ram_reason="watchdog kill: actual >= observed peak")  # fmt: skip
                else:
                    row.update(ram_class=None)
                log.write(json.dumps(row, default=str) + "\n")
                summary.executed += 1
                summary.outcome, summary.stop_reason = "stopped", f"{killed} at cell {i}"
                break
            _, elapsed, err, rss_end, peak_after = done
            row.update(status="error" if err else "ok", error_type=err, time_value=elapsed,
                       rss_end=rss_end, ram_lower_bound=False,
                       **_ram_actual(rss_start, peak_before, peak_after, poll_max, reset))  # fmt: skip
            row["time_class"] = "valid" if (not err and elapsed >= TIME_FLOOR_S) else "censored"
            if err:
                row["ram_class"] = None
            log.write(json.dumps(row, default=str) + "\n")
            log.flush()
            summary.executed += 1
            if err:
                summary.failed += 1
                consecutive += 1
                if consecutive >= limits.max_consecutive_failures:
                    summary.outcome = "stopped"
                    summary.stop_reason = f"{consecutive} consecutive failing cells (last: {err})"
                    break
            else:
                consecutive = 0
    finally:
        if proc.is_alive():
            try:
                conn.send(("quit",))
            except (OSError, BrokenPipeError):
                pass
            proc.join(10)
            if proc.is_alive():
                proc.kill()
        log.close()
        summary.elapsed_s = time.monotonic() - t_nb
        (out / "summary.json").write_text(json.dumps(summary.__dict__, indent=1, default=str))
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.realworld.run_notebook")
    ap.add_argument("notebook", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cap-mb", type=float, help="watchdog RSS cap (default 70%% of free RAM)")
    ap.add_argument("--cell-timeout-s", type=float, default=600.0)
    ap.add_argument("--budget-s", type=float, default=3600.0)
    ap.add_argument("--max-failures", type=int, default=5)
    ap.add_argument("--path-map", type=Path, help="JSON {literal path in the notebook: local path}")
    ap.add_argument(
        "--allow-battery", action="store_true", help="dev runs only (with --dev; recorded)"
    )
    ap.add_argument(
        "--tier",
        type=int,
        default=2,
        help="primary pipeline tier (Phase 8a: 2; the extension default since Phase 6c: 1)",
    )
    ap.add_argument(
        "--dev",
        action="store_true",
        help="dev run on the working tree (skips the freeze guard; recorded; never for held-out data)",
    )
    args = ap.parse_args(argv)
    limits = Limits(
        cap_bytes=int(args.cap_mb * MIB) if args.cap_mb else None,
        cell_timeout_s=args.cell_timeout_s,
        notebook_budget_s=args.budget_s,
        max_consecutive_failures=args.max_failures,
    )
    pm = json.loads(args.path_map.read_text()) if args.path_map else None
    s = run(
        args.notebook,
        args.out,
        limits,
        allow_battery=args.allow_battery,
        path_map=pm,
        tier=args.tier,
        dev=args.dev,
    )
    print(json.dumps(s.__dict__, indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
