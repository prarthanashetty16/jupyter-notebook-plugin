"""The harness child helper returns results, re-raises Python errors and reports a dead child as a
harness event (not a result)."""

from __future__ import annotations

import os

import pytest

from benchmarks.childproc import ChildFailureError, run_child


def _ok(x: int) -> int:
    return x * 2


def _raise() -> None:
    raise ValueError("boom")


def _die() -> None:
    os._exit(7)


def _hang() -> None:
    import time

    time.sleep(60)


def test_result_error_crash_and_timeout_are_distinguished():
    assert run_child(_ok, 21) == 42
    with pytest.raises(RuntimeError, match="boom"):
        run_child(_raise)
    with pytest.raises(ChildFailureError) as crash:
        run_child(_die)
    assert crash.value.status == "harness_crash" and crash.value.exitcode == 7
    assert crash.value.record()["status"] == "harness_crash"
    with pytest.raises(ChildFailureError) as slow:
        run_child(_hang, timeout_s=3)
    assert slow.value.status == "harness_timeout"
