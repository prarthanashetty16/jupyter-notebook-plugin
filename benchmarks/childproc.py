"""Spawned helper processes for the benchmark harness: wait with a timeout, record a crash as a HARNESS EVENT.

The prediction / probe children of the harness (not the measured children of ``nexus.measure``, which
handles its own) can die natively (Phase 7a: one 0xC0000005 access violation under CPU contention) or
hang. ``run_child`` waits for the result with a timeout, notices a dead child at once, and enables
``faulthandler`` in the child so a native crash leaves its Python stack in a log file. A crash or
timeout raises ``ChildFailureError`` with the exit code and that log. Callers record it as a harness event
(status ``harness_crash`` / ``harness_timeout``), never as a scored result.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

EXIT_CODES = {3221225477: "0xC0000005 access violation", 3221225725: "0xC00000FD stack overflow",
              -11: "SIGSEGV", -6: "SIGABRT", -9: "SIGKILL"}  # fmt: skip


class ChildFailureError(RuntimeError):
    """A harness child crashed or timed out; ``status`` is ``harness_crash`` or ``harness_timeout``."""

    def __init__(self, status: str, exitcode: int | None, fault_log: str) -> None:
        name = EXIT_CODES.get(exitcode, "") if exitcode is not None else ""
        super().__init__(f"{status}: exit code {exitcode} {name}".strip())
        self.status, self.exitcode, self.fault_log = status, exitcode, fault_log

    def record(self) -> dict[str, Any]:
        """The fields a harness row stores for this event."""
        return {"status": self.status, "exitcode": self.exitcode, "fault": self.fault_log[-2000:]}


def _entry(q: Any, fault_path: str, target: Callable[..., Any], args: tuple[Any, ...]) -> None:
    import faulthandler

    with open(fault_path, "w", encoding="utf-8") as fh:
        faulthandler.enable(file=fh, all_threads=True)
        try:
            q.put(("ok", target(*args)))
        except BaseException:  # a Python error is an ordinary error, not a crash
            import traceback

            q.put(("error", traceback.format_exc()))


def run_child(target: Callable[..., Any], *args: Any, timeout_s: float = 900.0) -> Any:
    """``target(*args)`` in a fresh spawned process (module-level, picklable); its return value."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    fd, fault_path = tempfile.mkstemp(prefix="nexus-child-", suffix=".fault")
    os.close(fd)
    p = ctx.Process(target=_entry, args=(q, fault_path, target, args))
    p.start()
    end = time.monotonic() + timeout_s
    try:
        while True:
            try:
                kind, value = q.get(timeout=min(2.0, max(end - time.monotonic(), 0.01)))
                p.join(timeout=30)
                if kind == "error":
                    raise RuntimeError("harness child raised:\n" + value)
                return value
            except queue.Empty:
                if not p.is_alive():
                    p.join()
                    raise ChildFailureError(
                        "harness_crash", p.exitcode, _read(fault_path)
                    ) from None
                if time.monotonic() >= end:
                    p.kill()
                    p.join()
                    raise ChildFailureError(
                        "harness_timeout", p.exitcode, _read(fault_path)
                    ) from None
    finally:
        Path(fault_path).unlink(missing_ok=True)


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
