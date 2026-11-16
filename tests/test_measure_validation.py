"""Instrument validation: known allocations must be measured within +/-10% (every platform).

Inputs are *loaded from disk* in the measured process (the production setup path), so the setup
peak stays at the baseline and the operation's peak is observable. The 'garbage in setup' test
documents the one situation where the OS peak counter cannot see an operation: it must then be
reported as censored with an upper bound, never as 0.
"""

from __future__ import annotations

import tracemalloc

import numpy as np
import pandas as pd
import pytest

from benchmarks import store
from nexus.measure import MIB, Measurement, classify, measure_call, read_memory, reset_peak

TOLERANCE = 0.10
SIZE = 100 * MIB


def within(measured: float, expected: float, tol: float = TOLERANCE) -> bool:
    return abs(measured - expected) <= tol * expected


def assert_measured(m: Measurement, expected: float) -> None:
    assert m.status == "ok", m.error
    assert not m.censored, f"unexpectedly censored (bound {m.bound_bytes / MIB:.1f} MiB)"
    assert m.delta_bytes is not None and within(m.delta_bytes, expected), (
        f"measured {m.delta_bytes / MIB:.1f} MiB, expected {expected / MIB:.1f} MiB "
        f"(+/-{TOLERANCE:.0%}); runs={[r.delta_bytes for r in m.runs]}"
    )
    for run in m.runs:  # polling can only under-measure the OS peak
        assert run.poll_delta_bytes <= run.delta_bytes * 1.1 + MIB


# -- module-level (picklable) workloads -----------------------------------------------------------
def alloc_ones(_):
    return np.ones(SIZE // 8)


def alloc_bytes(_):
    return b"x" * SIZE


def alloc_free_loop(_):
    for _i in range(20):
        a = np.ones((SIZE // 2) // 8)
        del a


def load_dir(path):
    return store.load(path)


def load_single_block_frame(path):
    return pd.DataFrame(np.load(path / "block.npy"))


def traced_peak(fn):
    """Independent oracle: tracemalloc sees numpy allocations made by ``fn``."""
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        keep = fn()
        peak = tracemalloc.get_traced_memory()[1] - base
        del keep
        return peak
    finally:
        tracemalloc.stop()


def sort_it(a):
    return np.sort(a)


def copy_frame(df):
    return df.copy()


def leave_garbage_then_nothing():
    garbage = np.ones(2 * SIZE // 8)
    del garbage


def alloc_after_garbage(_):
    return np.ones(SIZE // 8)


# -- known allocations ---------------------------------------------------------------------------
def test_np_ones_known_size():
    assert_measured(measure_call(alloc_ones, repeats=2), SIZE)


def test_bytes_known_size():
    assert_measured(measure_call(alloc_bytes, repeats=2), SIZE)


def test_dataframe_copy_single_block_is_one_copy(tmp_path):
    arr = np.random.default_rng(0).random((SIZE // 8 // 4, 4))
    (tmp_path / "df").mkdir()
    np.save(tmp_path / "df" / "block.npy", arr)
    m = measure_call(
        copy_frame, setup=load_single_block_frame, setup_args=(tmp_path / "df",), repeats=2
    )
    assert_measured(m, SIZE)
    assert within(traced_peak(pd.DataFrame(arr).copy), SIZE)  # oracle agrees with the claim


def test_dataframe_copy_multi_block_matches_tracemalloc_oracle(tmp_path):
    """pandas consolidates separate float blocks on copy: peak is 2x, which tracemalloc confirms."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({f"f{i}": rng.random(SIZE // 8 // 4) for i in range(4)}, copy=False)
    store.save(df, tmp_path / "df")
    expected = traced_peak(df.copy)
    assert within(expected, 2 * SIZE)
    m = measure_call(copy_frame, setup=load_dir, setup_args=(tmp_path / "df",), repeats=2)
    assert_measured(m, expected)


@pytest.mark.parametrize("pattern", ["random", "sorted"])
def test_np_sort_known_size(tmp_path, pattern):
    n = SIZE // 8
    arr = (
        np.arange(n, dtype=np.float64)
        if pattern == "sorted"
        else np.random.default_rng(1).random(n)
    )
    store.save(arr, tmp_path / "a")
    m = measure_call(sort_it, setup=load_dir, setup_args=(tmp_path / "a",), repeats=2)
    assert_measured(m, SIZE)


def test_sorted_vs_random_regression(tmp_path):
    """Phase 3 flaw: sorted and random 500k arrays measured 0.1 MB vs 3.9 MB for the same copy."""
    n = SIZE // 8
    store.save(np.arange(n, dtype=np.float64), tmp_path / "sorted")
    store.save(np.random.default_rng(2).random(n), tmp_path / "random")
    results = {}
    for name in ("sorted", "random"):
        m = measure_call(sort_it, setup=load_dir, setup_args=(tmp_path / name,), repeats=2)
        assert_measured(m, SIZE)
        results[name] = m.delta_bytes
    assert within(results["sorted"], results["random"], 0.10)


def test_repeated_allocate_free_reports_the_peak_not_the_sum():
    assert_measured(measure_call(alloc_free_loop, repeats=2), SIZE // 2)


def test_small_allocation_is_not_reported_as_zero(tmp_path):
    """A 0.8 MB op must read as small-but-nonzero or be flagged; never a silent 0."""
    store.save(np.random.default_rng(3).random(100_000), tmp_path / "a")
    m = measure_call(sort_it, setup=load_dir, setup_args=(tmp_path / "a",), repeats=2)
    assert m.status == "ok"
    assert m.censored or (m.delta_bytes is not None and m.delta_bytes > 0)
    assert classify([r.delta_bytes for r in m.runs], floor=32 * MIB).klass == "censored"


# -- the limitation: garbage left by setup --------------------------------------------------------
def test_garbage_freed_in_setup_is_censored_or_measured_never_zero():
    m = measure_call(alloc_after_garbage, setup=leave_garbage_then_nothing, repeats=2)
    assert m.status == "ok"
    if m.censored:  # Windows/macOS: counter cannot be reset, peak was set by the freed garbage
        assert m.delta_bytes is None
        assert m.bound_bytes >= 0.9 * SIZE
    else:  # Linux: peak counter reset after setup, so the allocation is visible
        assert within(m.delta_bytes, SIZE)


# -- platform layer ------------------------------------------------------------------------------
def test_read_memory_and_reset_are_sane():
    reading = read_memory()
    assert reading.rss > 10 * MIB
    assert reading.peak is None or reading.peak >= reading.rss * 0.99
    assert isinstance(reset_peak(), bool)


def test_peak_counter_is_monotonic_without_reset():
    before = read_memory()
    block = np.ones(20 * MIB // 8)
    during = read_memory()
    del block
    after = read_memory()
    assert during.peak is not None and after.peak is not None and before.peak is not None
    assert after.peak >= during.peak >= before.peak


# -- classification ------------------------------------------------------------------------------
def test_classify_rules():
    floor = 32.0
    assert classify([None, None], floor=floor).klass == "censored"
    assert classify([None, None], floor=floor).value is None
    low = classify([10.0, 11.0, 12.0], floor=floor)
    assert (low.klass, low.reason) == ("censored", "below_floor") and low.value == 11.0
    noisy = classify([40.0, 80.0, 41.0], floor=floor, max_spread=0.3)
    assert (noisy.klass, noisy.reason) == ("excluded", "spread")
    good = classify([100.0, 105.0, 102.0], floor=floor, max_spread=0.3)
    assert good.klass == "valid" and good.value == 102.0 and good.spread == pytest.approx(5 / 102)
    assert classify([100.0], floor=floor).klass == "valid"
    mixed = classify([None, 100.0, 104.0], floor=floor)
    assert mixed.klass == "valid" and mixed.value == 102.0
