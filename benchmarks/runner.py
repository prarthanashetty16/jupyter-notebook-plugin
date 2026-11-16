"""Run the benchmark: measure actual peak RAM/time and record NEXUS's predictions.

Per grid point, in separate spawned processes: (0) inputs are generated once and cached to disk,
(1) ``measure_call`` of the operation on inputs *loaded from disk*, (2) one NEXUS analysis per
tier. Runs are sequential on purpose (parallel runs distort memory). Results are appended to CSV
files as soon as they exist, so an interrupted run resumes where it stopped. The machine profile
(``nexus-calibrate-machine``) is measured/loaded once before any point and never on points.
"""

from __future__ import annotations

import csv
import functools
import json
import logging
import multiprocessing
import platform
import subprocess
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

from benchmarks import workers
from benchmarks.suite import CsvInput, GridPoint, build_grid
from nexus.calibrate import ensure_profile
from nexus.machine import MachineProfile
from nexus.measure import (
    DEFAULT_RAM_FLOOR_BYTES,
    DEFAULT_TIME_FLOOR_S,
    OK,
    Measurement,
    classify,
    measure_call,
)

log = logging.getLogger("benchmarks")

INSTRUMENT = "os-peak-v2"
ENV_FIELDS = [
    "instrument", "python", "pandas", "numpy", "pyarrow", "pandas_str_default", "text_dtype",
    "os", "cpu", "cpu_count", "cpu_max_mhz", "total_ram", "git_commit",
]  # fmt: skip
ACTUAL_FIELDS = [
    "point_id", "suite", "case", "op", "size", "source", "status", "error", "repeats_ok",
    "ram_delta_all", "ram_bound_bytes", "ram_censored_runs", "peak_reset", "poll_delta_all",
    "time_s_all", "baseline_bytes", "setup_peak_bytes", "input_bytes", "input_resident_bytes",
    "out_rows", "out_bytes", "est_footprint_bytes", "cap_bytes", "meta", *ENV_FIELDS,
]  # fmt: skip
PREDICTION_FIELDS = [
    "point_id", "tier", "status", "error", "has_estimate", "model", "ram_low", "ram_expected",
    "ram_high", "time_low", "time_expected", "time_high", "confidence", "drivers", "features",
    "overhead_cold_s", "overhead_warm_s", "analysis_peak_bytes", "inspected_bytes", "skipped",
    "other_ops", *ENV_FIELDS,
]  # fmt: skip
SKIPPED_CAP = "skipped_cap"


def env_info() -> dict[str, Any]:
    """Library versions, string dtype and hardware, recorded in every result row."""
    try:
        import pyarrow

        pyarrow_version = pyarrow.__version__
    except ImportError:
        pyarrow_version = "none"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        commit = ""
    freq = psutil.cpu_freq()
    return {
        "instrument": INSTRUMENT,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "pyarrow": pyarrow_version,
        "pandas_str_default": str(pd.Series(["a"]).dtype),
        "text_dtype": "object",  # dtype of text columns the generators emit (str_dtype default)
        "os": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_max_mhz": round(freq.max) if freq else "",
        "total_ram": psutil.virtual_memory().total,
        "git_commit": commit,
    }


class ResultStore:
    """Append-only CSV with an in-memory index of finished keys (last row wins)."""

    def __init__(self, path: Path, fields: list[str], key: tuple[str, ...]) -> None:
        self.path, self.fields, self.key = path, fields, key
        self.rows: list[dict[str, Any]] = []
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                self.rows = list(csv.DictReader(fh))
        self.done = {self._key(r): r for r in self.rows}

    def _key(self, row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(row[k]) for k in self.key)

    def has(self, **key: Any) -> dict[str, Any] | None:
        return self.done.get(tuple(str(key[k]) for k in self.key))

    def add(self, row: dict[str, Any]) -> None:
        new_file = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=self.fields)
            if new_file:
                writer.writeheader()
            writer.writerow({f: row.get(f, "") for f in self.fields})
        self.done[self._key(row)] = row


def default_mem_limit_bytes() -> int:
    """40% of currently available RAM, at most 8 GiB: the machine must never be exhausted."""
    return int(min(0.4 * psutil.virtual_memory().available, 8 * 2**30))


def _prepare(point: GridPoint, cache_dir: Path) -> str | None:
    """Generate/cache the point's inputs in a spawned process; return the CSV path if any."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=workers.prepare_inputs, args=(list(point.inputs), str(cache_dir)))
    proc.start()
    proc.join()
    if proc.exitcode != 0:
        raise RuntimeError(f"input preparation failed for {point.id}")
    for spec in point.inputs:
        if isinstance(spec, CsvInput):
            return spec.file_path(str(cache_dir))
    return None


def _payload(point: GridPoint, source: str, cache_dir: Path) -> dict[str, Any]:
    return {"inputs": list(point.inputs), "source": source, "cache_dir": str(cache_dir)}


def _actual_row(
    point: GridPoint, suite: str, source: str, cap: int, env: dict[str, Any], **kw: Any
) -> dict[str, Any]:
    return {
        "point_id": point.id, "suite": suite, "case": point.case, "op": point.op,
        "size": point.size, "source": source, "est_footprint_bytes": point.est_footprint_bytes(),
        "cap_bytes": cap, "meta": point.describe(), **env, **kw,
    }  # fmt: skip


def run_actual(
    point: GridPoint, suite: str, source: str, cache_dir: Path, cap: int, env: dict[str, Any]
) -> tuple[dict[str, Any], Measurement]:
    m = measure_call(
        workers.run_op,
        setup=workers.build_state,
        setup_args=(_payload(point, source, cache_dir),),
        summarize=workers.summarize_result,
        repeats=point.repeats,
        max_rss_bytes=cap,
    )
    ok_runs = [r for r in m.runs if r.status == OK]
    row = _actual_row(
        point, suite, source, cap, env,
        status=m.status, error=(m.error or "")[:500], repeats_ok=len(ok_runs),
        ram_delta_all=json.dumps([r.delta_bytes for r in ok_runs]),
        ram_bound_bytes=m.bound_bytes,
        ram_censored_runs=sum(r.censored for r in ok_runs),
        peak_reset=bool(ok_runs and ok_runs[0].peak_reset),
        poll_delta_all=json.dumps([r.poll_delta_bytes for r in ok_runs]),
        time_s_all=json.dumps([round(r.time_s, 6) for r in ok_runs]),
        baseline_bytes=m.baseline_bytes,
        setup_peak_bytes=ok_runs[0].setup_peak_bytes if ok_runs else "",
        input_bytes=m.info.get("input_bytes", ""),
        input_resident_bytes=m.info.get("input_resident_bytes", ""),
        out_rows=m.info.get("out_rows", ""), out_bytes=m.info.get("out_bytes", ""),
    )  # fmt: skip
    return row, m


def run_prediction(
    point: GridPoint, tier: int, source: str, cache_dir: Path, cap: int, env: dict[str, Any]
) -> dict[str, Any]:
    m = measure_call(
        functools.partial(workers.predict, tier=tier),
        setup=workers.build_state,
        setup_args=(_payload(point, source, cache_dir),),
        summarize=workers.as_info,
        repeats=1,
        max_rss_bytes=cap,
    )
    row: dict[str, Any] = {"point_id": point.id, "tier": tier, "status": m.status,
                           "error": (m.error or "")[:500], "has_estimate": False, **env}  # fmt: skip
    if m.status != OK:
        return row
    info = m.info
    row.update(
        overhead_cold_s=info["overhead_cold_s"], overhead_warm_s=info["overhead_warm_s"],
        analysis_peak_bytes=m.delta_bytes if m.delta_bytes is not None else "",
        inspected_bytes=info["inspected_bytes"], skipped=json.dumps(info["skipped"]),
    )  # fmt: skip
    matching = [e for e in info["estimates"] if e["op"] == point.op]
    row["other_ops"] = json.dumps([o for o in info["ops"] if o != point.op])
    if matching:
        e = matching[0]
        row.update(has_estimate=True, model=e["model"], drivers=json.dumps(e["drivers"]),
                   features=json.dumps(e["features"], default=str))  # fmt: skip
        for key in ("ram_low", "ram_expected", "ram_high", "time_low", "time_expected",
                    "time_high", "confidence"):  # fmt: skip
            row[key] = e[key]
    return row


@dataclass
class RunConfig:
    suite: str
    out_dir: Path
    tiers: tuple[int, ...] = (0,)
    mem_limit_bytes: int | None = None
    ops: set[str] | None = None
    retry_failed: bool = False
    max_points: int | None = None
    calibrate: bool = True  # False: use the uncalibrated default throughputs (ablation)


def _summary(m: Measurement) -> str:
    ram = classify([r.delta_bytes for r in m.runs if r.status == OK],
                   floor=DEFAULT_RAM_FLOOR_BYTES)  # fmt: skip
    t = classify([r.time_s for r in m.runs if r.status == OK], floor=DEFAULT_TIME_FLOOR_S)
    ram_txt = "n/a" if ram.value is None else f"{ram.value / 2**20:.1f} MB"
    if ram.klass != "valid":
        ram_txt += f" [{ram.klass}:{ram.reason}]"
    time_txt = f"{t.value:.3f} s" + ("" if t.klass == "valid" else f" [{t.klass}:{t.reason}]")
    return f"ram={ram_txt} t={time_txt}"


def run_suite(cfg: RunConfig, points: Iterable[GridPoint] | None = None) -> tuple[Path, Path]:
    """Run (or resume) a suite; returns the paths of actuals.csv and predictions.csv."""
    out = cfg.out_dir
    cache_dir = out.parent.parent / ".cache"
    out.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cap = cfg.mem_limit_bytes or default_mem_limit_bytes()
    grid = list(points) if points is not None else build_grid(cfg.suite, ops=cfg.ops)
    if cfg.max_points:
        grid = grid[: cfg.max_points]
    actuals = ResultStore(out / "actuals.csv", ACTUAL_FIELDS, ("point_id",))
    preds = ResultStore(out / "predictions.csv", PREDICTION_FIELDS, ("point_id", "tier"))

    profile = ensure_profile() if cfg.calibrate else MachineProfile()
    env = env_info()
    (out / "meta.json").write_text(
        json.dumps(
            {
                **env,
                "suite": cfg.suite,
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                "cap_bytes": cap,
                "machine_profile": asdict(profile),
            },
            indent=2,
            default=str,
        )  # fmt: skip
    )
    log.info("suite=%s points=%d memory cap=%.0f MB -> %s", cfg.suite, len(grid), cap / 2**20, out)
    log.info("machine profile calibrated=%s", profile.calibrated)

    t_start = time.monotonic()
    for i, point in enumerate(grid, 1):
        prefix = f"[{i}/{len(grid)}] {point.id}"
        previous = actuals.has(point_id=point.id)
        retry = cfg.retry_failed and previous is not None and previous["status"] == "error"
        missing = [t for t in cfg.tiers if preds.has(point_id=point.id, tier=t) is None or retry]
        if (
            previous is not None
            and not retry
            and (not missing or previous["status"] == SKIPPED_CAP)
        ):
            log.info("%s: already done (%s)", prefix, previous["status"])
            continue
        try:
            if previous is None or retry:
                if point.est_footprint_bytes() > cap:
                    row = _actual_row(point, cfg.suite, point.source, cap, env, status=SKIPPED_CAP,
                                      error=f"estimated footprint {point.est_footprint_bytes()} B > cap")  # fmt: skip
                    actuals.add(row)
                    log.info("%s: skipped (estimated footprint above memory cap)", prefix)
                    continue
                path = _prepare(point, cache_dir)
                source = point.source.format(csv=path) if "{csv" in point.source else point.source
                row, m = run_actual(point, cfg.suite, source, cache_dir, cap, env)
                actuals.add(row)
                line = f"{prefix}: {row['status']} {_summary(m)}"
            else:  # actual already measured: only the missing predictions run
                _prepare(point, cache_dir)
                source = previous["source"]
                line = f"{prefix}: actual kept ({previous['status']})"
            for tier in missing:
                prow = run_prediction(point, tier, source, cache_dir, cap, env)
                preds.add(prow)
                if prow["has_estimate"]:
                    line += f" | tier{tier} pred={int(prow['ram_expected']) / 2**20:.1f} MB t={float(prow['time_expected']):.3f} s"
                else:
                    line += f" | tier{tier} no estimate ({prow['status']})"
            log.info("%s  [%.0fs elapsed]", line, time.monotonic() - t_start)
        except Exception:
            log.exception("%s: harness error (point skipped, will retry on resume)", prefix)
    return actuals.path, preds.path
