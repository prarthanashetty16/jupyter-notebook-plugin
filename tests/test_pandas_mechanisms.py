"""Probe checks of the pandas internals the RAM and time models depend on.

Each test states one mechanism a model term assumes (with the model that assumes it). A failure on
some pandas version means that term is not valid there: the calibration artifact marks only the
versions it was fitted on as validated (``nexus.timecal``), and the CI matrix runs this file over
several pandas versions to show which ones keep the mechanisms. Results are claimed only for the
versions that were actually run.
"""

from __future__ import annotations

import os
import statistics
import tempfile
import time

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.pandas_mechanisms


def _median_time(fn, reps: int = 3) -> float:
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return statistics.median(out)


def _frames(n: int, card: int, unique_right: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(0)
    left = pd.DataFrame({"k": rng.integers(0, card, n), "v": rng.random(n), "p": rng.random(n)})
    keys = np.arange(card) if unique_right else np.repeat(np.arange(card), 2)
    right = pd.DataFrame({"k": keys, "w": rng.random(len(keys))})
    return left, right


# -- merge: the left copy is skipped when the left indexer is a range (MergeModel, Tier 1) ---------
def test_merge_skips_the_left_copy_when_every_left_row_matches_once():
    left, right = _frames(200_000, 1_000)
    out = left.merge(right, on="k")
    assert np.shares_memory(out["v"].to_numpy(), left["v"].to_numpy())
    out = left.merge(right, on="k", how="left")
    assert np.shares_memory(out["p"].to_numpy(), left["p"].to_numpy())


def test_merge_copies_the_left_rows_when_keys_fan_out():
    left, right = _frames(200_000, 1_000, unique_right=False)
    out = left.merge(right, on="k")
    assert len(out) == 2 * len(left)
    assert not np.shares_memory(out["v"].to_numpy(), left["v"].to_numpy())


# -- concat of categoricals (ConcatModel time; the RAM gap of differing categories) --------------
def test_concat_keeps_category_codes_only_when_categories_agree():
    a = pd.DataFrame({"c": pd.Categorical(["x", "y"] * 1000)})
    b = pd.DataFrame({"c": pd.Categorical(["y", "x"] * 1000, categories=["x", "y"])})
    assert str(pd.concat([a, b], ignore_index=True)["c"].dtype) == "category"
    c = pd.DataFrame({"c": pd.Categorical(["x", "z"] * 1000)})
    out = pd.concat([a, c], ignore_index=True)["c"]
    assert str(out.dtype) != "category"  # values are materialised as Python objects
    assert out.dtype == object or str(out.dtype) in ("str", "string")


# -- groupby / astype("category") sort the uniques (_time.groupby / _time.astype) ---------------
def test_groupby_sorts_the_groups_by_default():
    df = pd.DataFrame({"k": ["b", "c", "a"] * 100, "v": 1.0})
    assert df.groupby("k")["v"].sum().index.is_monotonic_increasing


def test_astype_category_sorts_the_categories():
    s = pd.Series(["b", "c", "a"] * 100)
    assert s.astype("category").cat.categories.is_monotonic_increasing


# -- read_csv reads dates as text by default (_time.read_csv charges them as text fields) ---------
def test_read_csv_does_not_parse_dates_by_default():
    df = pd.DataFrame({"d": pd.date_range("2020-01-01", periods=100, freq="h"), "x": range(100)})
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "d.csv")
        df.to_csv(path, index=False)
        back = pd.read_csv(path)
    assert not str(back["d"].dtype).startswith("datetime")
    assert str(back["x"].dtype).startswith("int")


# -- hash-table cost follows the working set (machine curves num/text_factorize_s) ----------------
def test_factorize_cost_per_row_grows_with_the_distinct_count():
    rng = np.random.default_rng(1)
    n = 2_000_000
    few = rng.integers(0, 100, n)
    many = rng.permutation(n).astype(np.int64)
    t_few = _median_time(lambda: pd.factorize(few))
    t_many = _median_time(lambda: pd.factorize(many))
    assert t_many > 2.0 * t_few, (t_few, t_many)


def test_factorize_presized_table_pages_are_not_all_resident_for_few_keys():
    """Few distinct keys touch few pages of the table presized for min(n, 2**20 + 7) entries
    (``_util.khash_presized_bytes`` / ``table_touch``): the allocation stays mostly virtual."""
    from nexus.measure import measure_call

    m = measure_call(_factorize_few, setup=_setup_ints, setup_args=(4_000_000,), repeats=1)
    if m.delta_bytes is None:
        pytest.skip("peak not resolved by the OS counter on this platform (censored)")
    codes = 8 * 4_000_000
    presized_table = (2**20 + 7) / 0.77 * 16  # khash buckets at the max load, 16 B each
    assert m.delta_bytes - codes < 0.5 * presized_table, (m.delta_bytes, codes)


def _setup_ints(n: int) -> np.ndarray:
    return np.random.default_rng(2).integers(0, 50, n)


def _factorize_few(values: np.ndarray) -> int:
    codes, _ = pd.factorize(values)
    return int(codes[0])


# -- object take: incref cost follows the distinct objects touched (object_take_s) ---------------
def test_object_take_cost_grows_with_the_distinct_objects():
    rng = np.random.default_rng(3)
    n = 2_000_000
    few = np.array([f"w{i:012d}" for i in range(1_000)], dtype=object)
    many = np.array([f"w{i:012d}" for i in range(2_000_000)], dtype=object)
    i_few, i_many = rng.integers(0, len(few), n), rng.integers(0, len(many), n)
    t_few = _median_time(lambda: few.take(i_few))
    t_many = _median_time(lambda: many.take(i_many))
    assert t_many > 2.0 * t_few, (t_few, t_many)
