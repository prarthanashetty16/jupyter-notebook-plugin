"""Measure a callable's peak RAM and wall time in a fresh spawned process.

Method
------
The child builds its inputs (``setup``, normally by *loading from disk*), garbage-collects, and
reports ``ready`` with its own memory reading: current RSS (the **baseline**) and the OS-tracked
**peak** counter at that moment. The parent sends ``go``; the child runs ``func``, times it, and
reads the OS peak counter again. The operation's peak is ``peak_after - baseline``.

The OS peak counter (Windows peak working set, Linux ``VmHWM``, macOS ``ru_maxrss``) is exact
but monotonic and, except on Linux, cannot be reset. If the operation never exceeded the peak
reached during setup, the counter says nothing about it: the run is reported as **censored**
(upper bound ``setup_peak - baseline``) and its delta is ``None``, never 0. On Linux the counter
is reset after setup (``/proc/self/clear_refs``) so runs are never censored for that reason.

The parent additionally polls the child's RSS (also used to enforce a memory cap) as an
independent cross-check; disagreements are logged and recorded, not used as the value.

Memory-pressure evidence is recorded per run: available system RAM at the start and its minimum
during the window, page faults of the child (all, and major ones where the OS reports them),
and the rise of swap/pagefile use. Windows has no per-process hard-fault counter in psutil, so
there only the system-wide signals (available RAM, pagefile use) can flag paging.

Limitations: RSS counts resident pages (lazily allocated, untouched memory is invisible);
Windows reports the working set; time is measured around the single call without warm-up.
"""

from __future__ import annotations

import gc
import logging
import multiprocessing
import statistics
import sys
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import psutil

log = logging.getLogger("nexus.measure")

OK = "ok"
ERROR = "error"
TIMEOUT = "timeout"
MEMORY_LIMIT = "memory_limit"
DIED = "died"

MIB = 2**20
DEFAULT_RAM_FLOOR_BYTES = 32 * MIB
DEFAULT_TIME_FLOOR_S = 0.100
DEFAULT_MAX_SPREAD = 0.30


# -- platform layer: the only place that knows about OS-specific counters ----------------------
@dataclass(frozen=True)
class MemoryReading:
    rss: int  # current resident set (Windows: working set)
    peak: int | None  # OS-tracked peak of the same quantity; None if unavailable


def read_memory(pid: int | None = None) -> MemoryReading:
    """Current and peak resident memory of ``pid`` (default: this process).

    Windows: ``psutil`` working set and ``peak_wset``. Linux: ``VmRSS``/``VmHWM`` from /proc.
    macOS/other Unix: psutil RSS and ``ru_maxrss`` (own process only; ``peak`` is None for others).
    """
    if sys.platform == "win32":
        m = psutil.Process(pid).memory_info()
        return MemoryReading(int(m.rss), int(m.peak_wset))
    if sys.platform.startswith("linux"):
        try:
            fields: dict[str, int] = {}
            with open(f"/proc/{pid or 'self'}/status", encoding="ascii") as fh:
                for line in fh:
                    key, _, rest = line.partition(":")
                    if key in ("VmRSS", "VmHWM"):
                        fields[key] = int(rest.split()[0]) * 1024
            if "VmRSS" in fields and "VmHWM" in fields:
                return MemoryReading(fields["VmRSS"], fields["VmHWM"])
        except (OSError, ValueError):
            pass
    rss = int(psutil.Process(pid).memory_info().rss)
    if pid is None or pid == psutil.Process().pid:
        import resource

        scale = 1 if sys.platform == "darwin" else 1024
        return MemoryReading(rss, int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * scale)
    return MemoryReading(rss, None)


def read_faults() -> tuple[int, int | None]:
    """(all page faults, major faults or None) of this process since it started.

    Windows: ``num_page_faults`` (soft + hard, no split). Unix: ``ru_minflt + ru_majflt`` and
    ``ru_majflt``.
    """
    if sys.platform == "win32":
        return int(psutil.Process().memory_info().num_page_faults), None
    import resource

    ru = resource.getrusage(resource.RUSAGE_SELF)
    return int(ru.ru_minflt + ru.ru_majflt), int(ru.ru_majflt)


def reset_peak() -> bool:
    """Reset this process's peak counter to its current value; True if supported (Linux only)."""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/clear_refs", "w", encoding="ascii") as fh:
                fh.write("5")
            return True
        except OSError:
            return False
    return False


# -- results -----------------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class RunResult:
    """One spawned-process run. ``delta_bytes`` is None when the run is censored."""

    status: str
    baseline_bytes: int = 0
    setup_peak_bytes: int = 0
    peak_bytes: int = 0  # absolute OS peak after the operation
    delta_bytes: int | None = None  # peak above baseline; None if censored
    bound_bytes: int = 0  # when censored: upper bound on the operation's increment
    censored: bool = False
    peak_reset: bool = False
    peak_source: str = "os"  # "os" counter or "poll" fallback when no counter exists
    poll_delta_bytes: int = 0  # max polled RSS minus baseline (cross-check only)
    time_s: float = 0.0
    samples: int = 0
    avail_start_bytes: int = 0  # system available RAM when the operation started
    avail_min_bytes: int = 0  # lowest available RAM seen while it ran (polled)
    page_faults: int | None = None  # child page faults during the operation
    major_faults: int | None = None  # of which major (None where the OS does not report)
    swap_rise_bytes: int = 0  # max rise of swap/pagefile use during the operation (polled)
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, kw_only=True)
class Measurement:
    """Aggregate of repeated runs."""

    status: str
    delta_bytes: int | None = None  # median over uncensored runs; None if all censored
    bound_bytes: int = 0
    censored: bool = False
    ram_spread: float | None = None  # (max - min) / median over uncensored runs
    baseline_bytes: int = 0
    time_s: float = 0.0
    time_spread: float | None = None
    info: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    runs: list[RunResult] = field(default_factory=list)


@dataclass(frozen=True)
class Classification:
    """Floor/spread classification of one metric over repeats."""

    klass: str  # "valid" | "censored" | "excluded"
    value: float | None
    spread: float | None
    reason: str = ""


def relative_spread(values: Sequence[float]) -> float | None:
    """(max - min) / median; None for fewer than two values or a zero median."""
    if len(values) < 2:
        return None
    med = statistics.median(values)
    return (max(values) - min(values)) / med if med > 0 else None


def classify(
    values: Sequence[float | None], *, floor: float, max_spread: float = DEFAULT_MAX_SPREAD
) -> Classification:
    """Classify repeats of one metric (None = censored run).

    censored: no uncensored run, or the median is below ``floor`` (value is then not trusted);
    excluded: relative spread above ``max_spread``; valid otherwise.
    """
    measured = [v for v in values if v is not None]
    if not measured:
        return Classification("censored", None, None, "below_setup_peak")
    med = float(statistics.median(measured))
    spread = relative_spread(measured)
    if med < floor:
        return Classification("censored", med, spread, "below_floor")
    if spread is not None and spread > max_spread:
        return Classification("excluded", med, spread, "spread")
    return Classification("valid", med, spread)


# -- child / parent ----------------------------------------------------------------------------
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
        reset = reset_peak()
        before = read_memory()
        faults0 = read_faults()
        avail0 = int(psutil.virtual_memory().available)
        conn.send(
            (
                "ready",
                {"rss": before.rss, "peak": before.peak, "reset": reset, "avail": avail0},
            )
        )
        if conn.recv() != "go":
            return
        t0 = time.perf_counter()
        result = func(state)
        elapsed = time.perf_counter() - t0
        after = read_memory()
        faults1 = read_faults()
        major = None if faults1[1] is None or faults0[1] is None else faults1[1] - faults0[1]
        conn.send(
            (
                "done",
                {
                    "elapsed": elapsed,
                    "rss": after.rss,
                    "peak": after.peak,
                    "faults": faults1[0] - faults0[0],
                    "major": major,
                },
            )
        )
        conn.send(("info", summarize(result) if summarize is not None else {}))
    except BaseException:
        try:
            conn.send(("error", traceback.format_exc()))
        except Exception:
            pass


class _Poll:
    """Polled RSS peak plus system-wide pressure signals (sampled at most every 20 ms)."""

    def __init__(self, baseline: int, avail: int = 0) -> None:
        self.peak = baseline
        self.samples = 0
        self.avail_min = avail
        self.swap0 = self._swap_used()
        self.swap_rise = 0
        self._next = 0.0

    @staticmethod
    def _swap_used() -> int:
        try:
            return int(psutil.swap_memory().used)
        except Exception:
            return 0

    def add(self, rss: int) -> None:
        self.samples += 1
        self.peak = max(self.peak, rss)
        now = time.monotonic()
        if now >= self._next:
            self._next = now + 0.02
            self.avail_min = min(self.avail_min or 2**62, int(psutil.virtual_memory().available))
            self.swap_rise = max(self.swap_rise, self._swap_used() - self.swap0)


def _pump(
    conn: Any, ps: psutil.Process, until: float, cap: int | None, poll: _Poll | None, poll_s: float
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
            rss = int(ps.memory_info().rss)
        except psutil.Error:
            return DIED, None
        if poll is not None:
            poll.add(rss)
        if cap is not None and rss > cap:
            return MEMORY_LIMIT, rss
        if time.monotonic() > until:
            return TIMEOUT, None


def _evaluate_run(ready: dict[str, Any], done: dict[str, Any], poll: _Poll) -> dict[str, Any]:
    baseline = int(ready["rss"])
    poll_delta = max(0, poll.peak - baseline)
    out: dict[str, Any] = {
        "baseline_bytes": baseline,
        "poll_delta_bytes": poll_delta,
        "peak_reset": bool(ready["reset"]),
        "time_s": float(done["elapsed"]),
        "samples": poll.samples,
        "avail_start_bytes": int(ready.get("avail", 0)),
        "avail_min_bytes": int(poll.avail_min),
        "page_faults": done.get("faults"),
        "major_faults": done.get("major"),
        "swap_rise_bytes": int(poll.swap_rise),
    }
    if done["peak"] is None or ready["peak"] is None:
        return {**out, "peak_source": "poll", "delta_bytes": poll_delta, "censored": False}
    out.update(setup_peak_bytes=int(ready["peak"]), peak_bytes=int(done["peak"]))
    if ready["reset"] or done["peak"] > ready["peak"]:
        delta = max(0, int(done["peak"]) - baseline)
        if poll_delta > delta * 1.1 + MIB:
            log.warning(
                "instrument disagreement: polled RSS rose %.1f MiB but OS peak says %.1f MiB",
                poll_delta / MIB,
                delta / MIB,
            )
        elif delta >= DEFAULT_RAM_FLOOR_BYTES and poll_delta < 0.5 * delta:
            log.info(
                "polling missed spike: OS peak %.1f MiB vs polled %.1f MiB",
                delta / MIB,
                poll_delta / MIB,
            )
        return {**out, "delta_bytes": delta, "censored": False}
    bound = max(0, int(ready["peak"]) - baseline)
    return {**out, "delta_bytes": None, "censored": True, "bound_bytes": bound}


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
        kind, ready = _pump(
            parent, ps, time.monotonic() + setup_timeout_s, max_rss_bytes, None, poll_s
        )
        if kind != "ready":
            return RunResult(status=kind, error=str(ready) if ready else f"during setup: {kind}")
        poll = _Poll(int(ready["rss"]), int(ready.get("avail", 0)))
        parent.send("go")
        kind, done = _pump(
            parent, ps, time.monotonic() + run_timeout_s, max_rss_bytes, poll, poll_s
        )
        if kind != "done":
            status = kind if kind in (TIMEOUT, MEMORY_LIMIT, DIED) else ERROR
            return RunResult(
                status=status,
                baseline_bytes=int(ready["rss"]),
                poll_delta_bytes=max(0, poll.peak - int(ready["rss"])),
                error=str(done) if done else kind,
            )
        info: dict[str, Any] = {}
        kind2, payload2 = _pump(parent, ps, time.monotonic() + 120, None, None, poll_s)
        if kind2 == "info" and isinstance(payload2, dict):
            info = payload2
        return RunResult(status=OK, info=info, **_evaluate_run(ready, done, poll))
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
    ``func``'s result into a small dict reported after the measurement window closes. A child
    whose RSS exceeds ``max_rss_bytes`` is killed (status ``memory_limit``). Repetition stops at
    the first failed run. Floors and spread thresholds are applied later by ``classify``.
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
    deltas = [r.delta_bytes for r in ok if r.delta_bytes is not None]
    times = [r.time_s for r in ok]
    return Measurement(
        status=failure.status if failure else OK,
        delta_bytes=int(statistics.median(deltas)) if deltas else None,
        bound_bytes=max(r.bound_bytes for r in ok),
        censored=not deltas,
        ram_spread=relative_spread([float(d) for d in deltas]),
        baseline_bytes=int(statistics.median(r.baseline_bytes for r in ok)),
        time_s=float(statistics.median(times)),
        time_spread=relative_spread(times),
        info=ok[0].info,
        error=failure.error if failure else None,
        runs=runs,
    )
