"""Tier 1 statistics: estimators, intervals, budgets and the never-mutate guarantee."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus import stats
from nexus.failsafe import Deadline

N = 400_000


@pytest.fixture(scope="module")
def rng():
    return np.random.default_rng(7)


# -- sampling ----------------------------------------------------------------------------------------
def test_sample_positions_are_sorted_distinct_and_deterministic():
    pos = stats.sample_positions(10_000, 500, seed=3)
    assert len(pos) == 500 and (np.diff(pos) > 0).all() and pos.min() >= 0 and pos.max() < 10_000
    assert (pos == stats.sample_positions(10_000, 500, seed=3)).all()
    assert (stats.sample_positions(50, 500) == np.arange(50)).all()  # whole population


def test_sample_positions_stay_distinct_when_the_strata_are_narrow():
    for n, m in (
        (300_000, 200_000),
        (1_000, 600),
        (1_999, 1_000),
        (300_000, 140_000),
        (1_000_003, 333_331),
    ):
        pos = stats.sample_positions(n, m)
        assert len(pos) == m and len(np.unique(pos)) == m  # no row is sampled twice


def test_sample_does_not_alias_with_a_periodic_column():
    col = pd.Series(np.tile(np.arange(100), 5_000))  # period 100
    d = stats.distinct_count(col, rows=1_000)  # a strided sample of step 500 would see 1 value
    assert d.low > 50


# -- distinct counts -----------------------------------------------------------------------------------
@pytest.mark.parametrize("distinct", [12, 400, 20_000, 150_000])
def test_distinct_interval_contains_the_truth_for_uniform_columns(rng, distinct):
    col = pd.Series(rng.integers(0, distinct, N))
    truth = col.nunique()
    d = stats.distinct_count(col, rows=40_000)
    assert d.low <= truth <= d.high
    assert d.sample == 40_000 and 0 <= d.confidence <= 1


def test_distinct_point_estimate_is_close_when_coverage_is_high(rng):
    col = pd.Series(rng.integers(0, 400, N))
    d = stats.distinct_count(col, rows=40_000)
    assert d.value == pytest.approx(400, rel=0.02) and d.method == "seen"


def test_distinct_of_an_all_unique_column_reaches_the_population(rng):
    col = pd.Series(rng.permutation(N))
    d = stats.distinct_count(col, rows=40_000)
    assert d.high == N and d.value > 0.5 * N and d.confidence < 0.5


def test_distinct_is_exact_when_the_sample_is_the_population():
    d = stats.distinct_count(pd.Series([1, 2, 2, 3, 3, 3]), rows=100)
    assert (d.value, d.low, d.high, d.exact) == (3, 3, 3, True)


def test_distinct_interval_contains_a_skewed_column(rng):
    w = 1.0 / np.arange(1, 50_001) ** 1.3
    col = pd.Series(rng.choice(50_000, size=N, p=w / w.sum()))
    d = stats.distinct_count(col, rows=40_000)
    assert d.low <= col.nunique() <= d.high


def test_distinct_rows_counts_combinations_and_treats_nulls_as_equal(rng):
    a = pd.Series(rng.integers(0, 5, 5_000))
    b = pd.Series(np.where(rng.random(5_000) < 0.5, None, "x"), dtype=object)
    truth = len(pd.DataFrame({"a": a, "b": b}).drop_duplicates())
    d = stats.distinct_rows([a, b], rows=100_000)
    assert d.exact and d.value == truth


# -- proportions, nulls, text ---------------------------------------------------------------------------
def test_proportion_wilson_interval():
    p = stats.proportion(50, 1_000, population=1_000_000)
    assert p.low < 0.05 < p.high and p.high - p.low < 0.03
    zero = stats.proportion(0, 1_000)
    assert zero.low == 0.0 and zero.high < 0.01  # a rare property stays possible
    assert stats.proportion(3, 10, population=10).exact


def test_null_profile_scans_float_columns_completely_and_samples_text(rng):
    n = 300_000
    f = rng.random(n)
    f[123_457] = np.nan  # a single null among 300k rows
    df = pd.DataFrame(
        {
            "f_rare": f,
            "f_clean": rng.random(n),
            "i": rng.integers(0, 9, n),
            "s_some": pd.Series(np.where(rng.random(n) < 0.1, None, "x"), dtype=object),
            "s_clean": pd.Series(np.full(n, "y", dtype=object)),
        }
    )
    prof = stats.null_profile(df, list(df.columns), rows=20_000)
    assert prof.certain == ("f_rare", "s_some")  # the single NaN is found by the full scan
    assert prof.possible == ("s_clean",)  # a sample cannot rule out a rare null in text
    assert prof.fraction["i"].exact


def test_text_profile_length_and_sharing():
    vocab = np.array([f"word{i:05d}" for i in range(500)], dtype=object)
    shared = pd.Series(vocab[np.random.default_rng(1).integers(0, 500, 100_000)], dtype=object)
    tp = stats.text_profile(shared)
    assert tp.mean_chars.value == pytest.approx(9.0) and tp.shared_fraction == 1.0
    unshared = pd.Series([str(x) for x in np.random.default_rng(2).integers(0, 50, 20_000)])
    assert stats.text_profile(unshared).shared_fraction == pytest.approx(0.0, abs=0.01)


# -- joins ----------------------------------------------------------------------------------------------
def _pair(n, nr, overlap, fanout, seed=1):
    from benchmarks.datasets import DatasetConfig, make_join_pair

    return make_join_pair(
        DatasetConfig(n_rows=n, seed=seed), nr, overlap=overlap, fanout=fanout, seed=seed + 40
    )


@pytest.mark.parametrize(("overlap", "fanout", "how"), [(0.7, 1.0, "inner"), (0.2, 4.0, "left")])
def test_join_profile_interval_contains_the_true_output_rows(overlap, fanout, how):
    left, right = _pair(200_000, 100_000, overlap, fanout)
    truth = len(left.merge(right, on="k", how=how))
    jp = stats.join_profile(left["k"], right["k"], how, rows=20_000)
    assert jp.out_rows.low <= truth <= jp.out_rows.high
    assert jp.out_rows.value == pytest.approx(truth, rel=0.1)


def test_join_profile_handles_skewed_fanout_with_heavy_keys():
    from benchmarks.datasets import DatasetConfig, make_join_pair

    left, right = make_join_pair(
        DatasetConfig(n_rows=200_000, seed=9), 80_000, overlap=0.5, fanout=3.0, seed=77,
        right_key_dist="zipf",
    )  # fmt: skip
    truth = len(left.merge(right, on="k"))
    jp = stats.join_profile(left["k"], right["k"], "inner", rows=20_000)
    assert jp.heavy_keys > 0
    assert jp.out_rows.low <= truth <= jp.out_rows.high


def test_join_profile_is_exact_when_everything_is_scanned():
    left = pd.Series([1, 2, 3, 3, 4])
    right = pd.Series([3, 3, 4, 5])
    jp = stats.join_profile(left, right, "inner")
    assert jp.out_rows.value == 5 and jp.out_rows.exact  # 3x2 + 4x1... = 2*2 + 1
    assert not jp.right_keys_unique


def test_join_profile_flags_unique_matches_for_copy_elision():
    left = pd.Series(np.arange(5_000))
    right = pd.Series(np.arange(5_000))
    jp = stats.join_profile(left, right, "inner")
    assert jp.left_all_matched_once and jp.right_keys_unique


def test_join_profile_declines_large_text_keys():
    big = pd.Series(["k"] * 450_000)
    with pytest.raises(stats.UnsupportedError):
        stats.join_profile(big, big, "inner")


def test_join_profile_respects_the_deadline():
    keys = pd.Series(np.arange(2_000_000))
    with pytest.raises(TimeoutError):
        stats.join_profile(keys, keys, "inner", deadline=Deadline(0.0))


# -- csv -------------------------------------------------------------------------------------------------
def test_csv_profile_estimates_rows_columns_and_string_uniqueness(tmp_path, rng):
    n = 300_000
    df = pd.DataFrame(
        {
            "i": rng.integers(0, 9, n),
            "f": rng.random(n),
            "s": pd.Series(
                np.array([f"w{k:04d}" for k in range(50)], dtype=object)[rng.integers(0, 50, n)]
            ),
        }
    )
    path = tmp_path / "a.csv"
    df.to_csv(path, index=False)
    cp = stats.csv_profile(str(path), path.stat().st_size)
    assert cp.cols == 3 and cp.text_cols == 1
    assert cp.rows.value == pytest.approx(n, rel=0.01) and cp.rows.low <= n <= cp.rows.high
    assert cp.str_chars == pytest.approx(5.0)
    assert cp.bytes_per_field == pytest.approx(path.stat().st_size / n / 3, rel=0.01)
    assert cp.unique_fraction.value < 0.05  # 50 distinct strings: nearly all shared per chunk
    assert cp.bytes_read <= (1 << 20) + 3 * (256 << 10)  # the byte budget


def test_csv_profile_reads_a_small_file_completely(tmp_path):
    path = tmp_path / "s.csv"
    pd.DataFrame({"a": range(100), "b": list("xy") * 50}).to_csv(path, index=False)
    cp = stats.csv_profile(str(path), path.stat().st_size)
    assert cp.exact and cp.rows.value == 100 and cp.rows.exact


# -- never mutate ------------------------------------------------------------------------------------------
def test_statistics_never_mutate_or_reorder_the_data(rng):
    df = pd.DataFrame(
        {
            "k": rng.integers(0, 1_000, 50_000),
            "s": pd.Series(np.where(rng.random(50_000) < 0.1, None, "v"), dtype=object),
            "f": rng.random(50_000),
        }
    )
    before = df.copy(deep=True)
    stats.distinct_count(df["k"], rows=5_000)
    stats.distinct_rows([df["k"], df["s"]], rows=5_000)
    stats.null_profile(df, ["k", "s", "f"], rows=5_000)
    stats.text_profile(df["s"], rows=5_000)
    stats.join_profile(df["k"], df["k"], "inner", rows=5_000)
    pd.testing.assert_frame_equal(df, before)
    assert df.index.equals(before.index)
