"""Measure a callable's peak RAM and wall time in a fresh spawned process.

Method: the child builds its inputs (``setup``), garbage-collects, and reports ``ready``. The
parent records the child's resident set size (RSS) as the baseline, sends ``go``, and then polls
the child's RSS every ``poll_interval_s`` until the child reports ``done``. Peak RAM is the
maximum polled RSS minus the baseline ("incremental peak": memory the operation added on top of
what was already resident). Wall time is measured inside the child around ``func`` only.

Known limitations (state them when reporting results):
- Polling can miss spikes shorter than the poll interval, so very short operations have
  unreliable peaks.
- RSS counts pages actually resident: lazily allocated memory (``np.zeros``) is invisible until
  touched, and memory freed by setup that the allocator retained can be reused by the operation
  without raising RSS (under-measurement).
- On Windows RSS is the working set; on Linux/macOS it is the resident set.
"""

from __future__ import annotations

import gc
import multiprocessing
import statistics
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import psutil

OK = "ok"
ERROR = "error"
TIMEOUT = "timeout"
MEMORY_LIMIT = "memory_limit"
DIED = "died"


def rss_bytes(proc: psutil.Process) -> int:
    """Resident memory of ``proc`` in bytes: the one place platform differences are hidden."""
    return int(proc.memory_info().rss)


@dataclass(frozen=True, kw_only=True)
class RunResult:
    """One spawned-process run."""

    status: str
    peak_bytes: int = 0
    baseline_bytes: int = 0
    time_s: float = 0.0
    samples: int = 0
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, kw_only=True)
class Measurement:
    """Aggregate of repeated runs: medians over the successful runs."""

    status: str
    peak_bytes: int = 0
    baseline_bytes: int = 0
    time_s: float = 0.0
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    runs: list[RunResult] = field(default_factory=list)


def _child_main(
    conn: Any,
    func: Callable[[Any], Any],
    setup: Callable[..., Any] | None,
    setup_args: tuple[Any, ...],
    summarize: Callable[[Any], dict[str, Any]] | None,
) -> None:
    try:
        state = setup(*setup_args) if setup is not None else None
        gc.collect()
        conn.send(("ready",))
        if conn.recv() != "go":
            return
        t0 = time.perf_counter()
        result = func(state)
        elapsed = time.perf_counter() - t0
        conn.send(("done", elapsed))
        conn.send(("info", summarize(result) if summarize is not None else {}))
    except BaseException:
        try:
            conn.send(("error", traceback.format_exc()))
        except Exception:
            pass


class _Peak:
    def __init__(self, baseline: int) -> None:
        self.peak = baseline
        self.samples = 0

    def add(self, rss: int) -> None:
        self.samples += 1
        self.peak = max(self.peak, rss)


def _pump(
    conn: Any,
    ps: psutil.Process,
    until: float,
    cap: int | None,
    tracker: _Peak | None,
    poll_s: float,
) -> tuple[str, Any]:
    """Wait for the next child message while sampling RSS; returns (kind, payload)."""
    while True:
        try:
            if conn.poll(poll_s):
                msg = conn.recv()
                return msg[0], (msg[1] if len(msg) > 1 else None)
        except (EOFError, OSError):
            return DIED, None
        try:
            rss = rss_bytes(ps)
        except psutil.Error:
            return DIED, None
        if tracker is not None:
            tracker.add(rss)
        if cap is not None and rss > cap:
            return MEMORY_LIMIT, rss
        if time.monotonic() > until:
            return TIMEOUT, None


def _run_once(
    func: Callable[[Any], Any],
    setup: Callable[..., Any] | None,
    setup_args: tuple[Any, ...],
    summarize: Callable[[Any], dict[str, Any]] | None,
    *,
    setup_timeout_s: float,
    run_timeout_s: float,
    max_rss_bytes: int | None,
    poll_s: float,
) -> RunResult:
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    proc = ctx.Process(
        target=_child_main, args=(child, func, setup, setup_args, summarize), daemon=True
    )
    proc.start()
    child.close()
    try:
        ps = psutil.Process(proc.pid)
        kind, payload = _pump(
            parent, ps, time.monotonic() + setup_timeout_s, max_rss_bytes, None, poll_s
        )
        if kind != "ready":
            return RunResult(
                status=kind, error=str(payload) if payload else f"during setup: {kind}"
            )
        baseline = rss_bytes(ps)
        tracker = _Peak(baseline)
        parent.send("go")
        kind, payload = _pump(
            parent, ps, time.monotonic() + run_timeout_s, max_rss_bytes, tracker, poll_s
        )
        if kind != "done":
            status = kind if kind in (TIMEOUT, MEMORY_LIMIT, DIED) else ERROR
            return RunResult(
                status=status,
                peak_bytes=max(0, tracker.peak - baseline),
                baseline_bytes=baseline,
                samples=tracker.samples,
                error=str(payload) if payload else kind,
            )
        try:
            tracker.add(rss_bytes(ps))
        except psutil.Error:
            pass
        info: dict[str, Any] = {}
        kind2, payload2 = _pump(parent, ps, time.monotonic() + 120, None, None, poll_s)
        if kind2 == "info" and isinstance(payload2, dict):
            info = payload2
        return RunResult(
            status=OK,
            peak_bytes=max(0, tracker.peak - baseline),
            baseline_bytes=baseline,
            time_s=float(payload),
            samples=tracker.samples,
            info=info,
        )
    finally:
        parent.close()
        if proc.is_alive():
            proc.kill()
        proc.join(10)


def measure_call(
    func: Callable[[Any], Any],
    *,
    setup: Callable[..., Any] | None = None,
    setup_args: tuple[Any, ...] = (),
    summarize: Callable[[Any], dict[str, Any]] | None = None,
    repeats: int = 3,
    setup_timeout_s: float = 600.0,
    run_timeout_s: float = 300.0,
    max_rss_bytes: int | None = None,
    poll_interval_s: float = 0.002,
) -> Measurement:
    """Run ``func(setup(*setup_args))`` ``repeats`` times, each in a fresh spawned process.

    ``func``, ``setup`` and ``summarize`` must be picklable (module-level). ``summarize`` turns
    ``func``'s result into a small dict reported after timing stops. A child whose RSS exceeds
    ``max_rss_bytes`` is killed (status ``memory_limit``). Repetition stops at the first failed
    run; the returned status is then that failure and medians cover the successful runs so far.
    """
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    runs: list[RunResult] = []
    for _ in range(repeats):
        run = _run_once(
            func,
            setup,
            setup_args,
            summarize,
            setup_timeout_s=setup_timeout_s,
            run_timeout_s=run_timeout_s,
            max_rss_bytes=max_rss_bytes,
            poll_s=poll_interval_s,
        )
        runs.append(run)
        if run.status != OK:
            break
    ok = [r for r in runs if r.status == OK]
    failure = next((r for r in runs if r.status != OK), None)
    if not ok:
        assert failure is not None
        return Measurement(status=failure.status, error=failure.error, runs=runs)
    return Measurement(
        status=failure.status if failure else OK,
        peak_bytes=int(statistics.median(r.peak_bytes for r in ok)),
        baseline_bytes=int(statistics.median(r.baseline_bytes for r in ok)),
        time_s=float(statistics.median(r.time_s for r in ok)),
        info=ok[0].info,
        error=failure.error if failure else None,
        runs=runs,
    )
