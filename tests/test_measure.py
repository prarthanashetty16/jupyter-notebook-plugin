"""measure_call: spawned-process peak RAM / time measurement."""

from __future__ import annotations

import time

import numpy as np
import pytest

from nexus.measure import MEMORY_LIMIT, OK, TIMEOUT, Measurement, measure_call

MB = 2**20


def alloc_40mb(_state):
    return np.ones(5 * 2**20)  # 40 MB, every page written


def alloc_many(_state):
    keep = [np.ones(6 * 2**20) for _ in range(20)]  # up to ~960 MB in 48 MB steps
    return len(keep)


def sleep_a_bit(_state):
    time.sleep(0.3)


def sleep_long(_state):
    time.sleep(30)


def boom(_state):
    raise ValueError("kaput")


def make_state(n):
    return np.zeros(n)


def use_state(state):
    return state.shape[0]


def summarize(result):
    return {"out": result}


def test_peak_ram_is_incremental():
    m = measure_call(alloc_40mb, repeats=2)
    assert m.status == OK and len(m.runs) == 2
    assert m.delta_bytes is not None and 30 * MB <= m.delta_bytes <= 90 * MB, m.delta_bytes
    assert m.baseline_bytes > 20 * MB
    assert m.runs[0].samples >= 0  # very short ops may get no polls; the OS counter is the value


def test_inputs_built_in_setup_are_not_counted():
    m = measure_call(use_state, setup=make_state, setup_args=(10_000_000,), repeats=1)
    assert m.status == OK
    # np.zeros is lazy: censored (None) or tiny, never a fake exact value
    assert m.censored or m.delta_bytes < 20 * MB


def test_time_is_measured_around_func_only():
    m = measure_call(sleep_a_bit, repeats=1)
    assert 0.28 <= m.time_s < 1.0


def test_summarize_info_returned():
    m = measure_call(use_state, setup=make_state, setup_args=(7,), summarize=summarize, repeats=1)
    assert m.info == {"out": 7}


def test_error_is_reported_not_raised():
    m = measure_call(boom, repeats=3)
    assert m.status == "error" and "kaput" in (m.error or "")
    assert len(m.runs) == 1


def test_timeout_kills_child():
    t0 = time.monotonic()
    m = measure_call(sleep_long, repeats=1, run_timeout_s=0.5)
    assert m.status == TIMEOUT
    assert time.monotonic() - t0 < 20


def test_memory_limit_kills_child():
    m = measure_call(alloc_many, repeats=1, max_rss_bytes=400 * MB)
    assert m.status == MEMORY_LIMIT


def test_invalid_repeats():
    with pytest.raises(ValueError):
        measure_call(alloc_40mb, repeats=0)


def test_measurement_type():
    assert isinstance(measure_call(sleep_a_bit, repeats=1), Measurement)
