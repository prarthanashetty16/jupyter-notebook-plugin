"""Fail-safe primitives: NEXUS must never break or block the user's cell."""

from __future__ import annotations

import functools
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

log = logging.getLogger("nexus")

T = TypeVar("T")


class Deadline:
    """Cooperative time budget; long-running stages poll it and give up when expired."""

    def __init__(self, budget_s: float) -> None:
        self._end = time.perf_counter() + budget_s

    def remaining(self) -> float:
        return max(0.0, self._end - time.perf_counter())

    def expired(self) -> bool:
        return time.perf_counter() >= self._end

    def check(self) -> None:
        """Raise TimeoutError if the budget is exhausted."""
        if self.expired():
            raise TimeoutError("nexus time budget exhausted")


def swallow(func: Callable[..., T]) -> Callable[..., T | None]:
    """Run ``func``; on any ``Exception`` log at debug level and return None."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T | None:
        try:
            return func(*args, **kwargs)
        except Exception:
            log.debug("nexus: swallowed exception in %s", func.__qualname__, exc_info=True)
            return None

    return wrapper


def run_with_timeout(func: Callable[[], T], timeout_s: float) -> T:
    """Run ``func`` in a daemon thread and wait at most ``timeout_s`` seconds.

    Raises TimeoutError if it does not finish (the thread is abandoned; callers should also
    pass a ``Deadline`` into ``func`` so the thread stops soon after). Exceptions raised by
    ``func`` are re-raised in the caller.
    """
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = func()
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=target, name="nexus-analysis", daemon=True)
    thread.start()
    thread.join(timeout_s)
    if thread.is_alive():
        raise TimeoutError(f"nexus analysis exceeded {timeout_s:.3f}s")
    if "error" in box:
        raise box["error"]
    return box["value"]
