"""Run the benchmark: measure actual peak RAM/time and record NEXUS's predictions.

Per grid point, in separate spawned processes: (1) ``measure_call`` of the operation, (2) one
NEXUS analysis per tier. Runs are sequential on purpose (parallel runs distort memory). Results
are appended to CSV files as soon as they exist, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import csv
import functools
import json
import logging
import multiprocessing
import platform
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

from benchmarks import workers
from benchmarks.suite import CsvInput, GridPoint, build_grid
from nexus.measure import OK, measure_call

log = logging.getLogger("benchmarks")

ACTUAL_FIELDS = [
    "point_id", "suite", "case", "op", "size", "source", "status", "error", "repeats_ok",
    "peak_bytes", "baseline_bytes", "time_s", "peak_bytes_all", "time_s_all", "input_bytes",
    "out_rows", "out_bytes", "est_footprint_bytes", "cap_bytes", "meta",
]  # fmt: skip
PREDICTION_FIELDS = [
    "point_id", "tier", "status", "error", "has_estimate", "model", "ram_low", "ram_expected",
    "ram_high", "time_low", "time_expected", "time_high", "confidence", "drivers", "features",
    "overhead_cold_s", "overhead_warm_s", "analysis_peak_bytes", "inspected_bytes", "skipped",
    "other_ops",
]  # fmt: skip
SKIPPED_CAP = "skipped_cap"


class ResultStore:
    """Append-only CSV with an in-memory index of finished keys."""

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

    def drop(self, **key: Any) -> None:
        """Forget a row (used to retry failures); the stale line is superseded on load."""
        self.done.pop(tuple(str(key[k]) for k in self.key), None)


def default_mem_limit_bytes() -> int:
    """40% of currently available RAM, at most 8 GiB: the machine must never be exhausted."""
    return int(min(0.4 * psutil.virtual_memory().available, 8 * 2**30))


def machine_info(cap_bytes: int, suite: str) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except Exception:
        commit = ""
    return {
        "suite": suite,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "cpu_count": psutil.cpu_count(logical=True),
        "total_ram": psutil.virtual_memory().total,
        "available_ram_at_start": psutil.virtual_memory().available,
        "cap_bytes": cap_bytes,
        "git_commit": commit,
    }


def _prepare_csv(point: GridPoint, cache_dir: Path) -> str | None:
    """Create the CSV for a read_csv point (in a spawned process) and return its path."""
    for spec in point.inputs:
        if isinstance(spec, CsvInput):
            path = spec.file_path(str(cache_dir))
            if not Path(path).exists():
                ctx = multiprocessing.get_context("spawn")
                proc = ctx.Process(target=workers.write_csv_file, args=(spec.cfg, path))
                proc.start()
                proc.join()
                if proc.exitcode != 0 or not Path(path).exists():
                    raise RuntimeError(f"failed to write {path}")
            return path
    return None


def _payload(point: GridPoint, source: str, cache_dir: Path) -> dict[str, Any]:
    return {"inputs": list(point.inputs), "source": source, "cache_dir": str(cache_dir)}


def _actual_row(point: GridPoint, suite: str, source: str, cap: int, **kw: Any) -> dict[str, Any]:
    return {
        "point_id": point.id, "suite": suite, "case": point.case, "op": point.op,
        "size": point.size, "source": source, "est_footprint_bytes": point.est_footprint_bytes(),
        "cap_bytes": cap, "meta": point.describe(), **kw,
    }  # fmt: skip


def run_actual(
    point: GridPoint, suite: str, source: str, cache_dir: Path, cap: int
) -> dict[str, Any]:
    m = measure_call(
        workers.run_op,
        setup=workers.build_state,
        setup_args=(_payload(point, source, cache_dir),),
        summarize=workers.summarize_result,
        repeats=point.repeats,
        max_rss_bytes=cap,
    )
    ok_runs = [r for r in m.runs if r.status == OK]
    return _actual_row(
        point, suite, source, cap,
        status=m.status, error=(m.error or "")[:500], repeats_ok=len(ok_runs),
        peak_bytes=m.peak_bytes, baseline_bytes=m.baseline_bytes, time_s=m.time_s,
        peak_bytes_all=json.dumps([r.peak_bytes for r in ok_runs]),
        time_s_all=json.dumps([round(r.time_s, 6) for r in ok_runs]),
        input_bytes=m.info.get("input_bytes", ""), out_rows=m.info.get("out_rows", ""),
        out_bytes=m.info.get("out_bytes", ""),
    )  # fmt: skip


def run_prediction(
    point: GridPoint, tier: int, source: str, cache_dir: Path, cap: int
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
                           "error": (m.error or "")[:500], "has_estimate": False}  # fmt: skip
    if m.status != OK:
        return row
    info = m.info
    row.update(
        overhead_cold_s=info["overhead_cold_s"], overhead_warm_s=info["overhead_warm_s"],
        analysis_peak_bytes=m.peak_bytes, inspected_bytes=info["inspected_bytes"],
        skipped=json.dumps(info["skipped"]),
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
    (out / "meta.json").write_text(json.dumps(machine_info(cap, cfg.suite), indent=2))
    log.info("suite=%s points=%d memory cap=%.0f MB -> %s", cfg.suite, len(grid), cap / 2**20, out)

    t_start = time.monotonic()
    for i, point in enumerate(grid, 1):
        prefix = f"[{i}/{len(grid)}] {point.id}"
        previous = actuals.has(point_id=point.id)
        retry = cfg.retry_failed and previous is not None and previous["status"] == "error"
        if previous is not None and not retry:
            log.info("%s: already done (%s)", prefix, previous["status"])
            continue
        try:
            path = _prepare_csv(point, cache_dir)
            source = point.source.format(csv=path) if "{csv" in point.source else point.source
            if point.est_footprint_bytes() > cap:
                row = _actual_row(point, cfg.suite, source, cap, status=SKIPPED_CAP,
                                  error=f"estimated footprint {point.est_footprint_bytes()} B > cap")  # fmt: skip
                actuals.add(row)
                log.info("%s: skipped (estimated footprint above memory cap)", prefix)
                continue
            row = run_actual(point, cfg.suite, source, cache_dir, cap)
            actuals.add(row)
            line = f"{prefix}: {row['status']} peak={int(row['peak_bytes']) / 2**20:.1f} MB t={float(row['time_s']):.3f} s"
            for tier in cfg.tiers:
                if preds.has(point_id=point.id, tier=tier) and not retry:
                    continue
                prow = run_prediction(point, tier, source, cache_dir, cap)
                preds.add(prow)
                if prow["has_estimate"]:
                    line += f" | tier{tier} pred={int(prow['ram_expected']) / 2**20:.1f} MB t={float(prow['time_expected']):.3f} s"
                else:
                    line += f" | tier{tier} no estimate ({prow['status']})"
            log.info("%s  [%.0fs elapsed]", line, time.monotonic() - t_start)
        except Exception:
            log.exception("%s: harness error (point skipped, will retry on resume)", prefix)
    return actuals.path, preds.path
