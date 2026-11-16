"""Benchmark dataset generators and suite declarations."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from benchmarks.datasets import (
    DatasetConfig,
    estimate_frame_bytes,
    make_frame,
    make_join_pair,
)
from benchmarks.suite import CASES, SUITES, build_grid


def test_reproducible_and_seed_sensitive():
    cfg = DatasetConfig(n_rows=2000, dup_rate=0.3, null_rate=0.1)
    assert make_frame(cfg).equals(make_frame(cfg))
    assert not make_frame(cfg).equals(make_frame(cfg.with_(seed=1)))


def test_columns_and_dtypes():
    df = make_frame(DatasetConfig(n_rows=500, n_int=2, n_float=1, n_object=2, n_category=1))
    assert list(df.columns) == ["k", "i0", "i1", "f0", "s0", "s1", "c0", "d0"]
    assert df["i0"].dtype == np.int64 and df["f0"].dtype == np.float64
    assert df["s0"].dtype == object and isinstance(df["c0"].dtype, pd.CategoricalDtype)
    assert str(df["d0"].dtype).startswith("datetime64")
    assert len(df) == 500


@pytest.mark.parametrize("dup_rate", [0.0, 0.25, 0.5, 0.9])
def test_duplicate_rate_is_exact(dup_rate):
    df = make_frame(DatasetConfig(n_rows=4000, dup_rate=dup_rate))
    assert df.duplicated().mean() == pytest.approx(dup_rate, abs=0.001)


@pytest.mark.parametrize("card", [0.01, 50, 0.5])
def test_cardinality(card):
    cfg = DatasetConfig(n_rows=5000, cardinality=card)
    df = make_frame(cfg)
    assert df["i0"].nunique() <= cfg.card
    assert df["s0"].nunique() <= cfg.card
    assert df["s0"].nunique() > cfg.card * 0.8


def test_string_length_and_null_rate():
    df = make_frame(DatasetConfig(n_rows=20_000, str_len=17, null_rate=0.2))
    assert df["s0"].dropna().str.len().eq(17).all()
    assert df["s0"].isna().mean() == pytest.approx(0.2, abs=0.02)
    assert df["f0"].isna().mean() == pytest.approx(0.2, abs=0.02)
    assert df["d0"].isna().mean() == pytest.approx(0.2, abs=0.02)
    assert df["i0"].isna().sum() == 0


def test_string_sharing_option():
    shared = make_frame(DatasetConfig(n_rows=1000, cardinality=0.01))
    distinct = make_frame(DatasetConfig(n_rows=1000, cardinality=0.01, share_strings=False))
    assert len({id(x) for x in shared["s0"]}) == 10
    assert len({id(x) for x in distinct["s0"]}) == 1000
    assert (shared["s0"] == distinct["s0"]).all()


def test_real_like_distribution_is_skewed():
    uniform = make_frame(DatasetConfig(n_rows=50_000, cardinality=100))
    skewed = make_frame(DatasetConfig(n_rows=50_000, cardinality=100, distribution="real_like"))
    top_u = uniform["s0"].value_counts(normalize=True).iloc[0]
    top_s = skewed["s0"].value_counts(normalize=True).iloc[0]
    assert top_s > 5 * top_u
    assert skewed["f0"].skew() > uniform["f0"].skew() + 1


def test_invalid_configs():
    with pytest.raises(ValueError):
        DatasetConfig(n_rows=0)
    with pytest.raises(ValueError):
        DatasetConfig(n_rows=10, dup_rate=1.0)
    with pytest.raises(ValueError):
        DatasetConfig(n_rows=10, distribution="nope")
    with pytest.raises(ValueError):
        make_frame(DatasetConfig(n_rows=10_000, cardinality=10_000, str_len=2))


@pytest.mark.parametrize(("overlap", "fanout"), [(1.0, 1.0), (0.2, 1.0), (1.0, 4.0), (0.5, 2.0)])
def test_join_overlap_and_fanout(overlap, fanout):
    left, right = make_join_pair(DatasetConfig(n_rows=4000), 2000, overlap=overlap, fanout=fanout)
    assert len(right) == 2000
    rows_per_key = right["k"].value_counts()
    assert rows_per_key.mean() == pytest.approx(fanout, rel=0.05)
    matched = right["k"].isin(left["k"]).mean()
    assert matched == pytest.approx(overlap, abs=0.05)
    assert len(left.merge(right, on="k")) == pytest.approx(2000 * overlap, rel=0.06)


def test_join_many_to_many_blows_up_output():
    left, right = make_join_pair(DatasetConfig(n_rows=4000, dup_rate=0.5), 2000, fanout=3.0)
    assert len(left.merge(right, on="k")) > 1.5 * 2000


def test_estimate_frame_bytes_is_positive_and_scales():
    small, large = DatasetConfig(n_rows=1000), DatasetConfig(n_rows=100_000)
    assert 0 < estimate_frame_bytes(small) < estimate_frame_bytes(large)


def test_suite_grid_is_well_formed():
    for suite, spec in SUITES.items():
        grid = build_grid(suite)
        ids = [p.id for p in grid]
        assert len(ids) == len(set(ids))
        assert {p.case for p in grid} == {c.name for c in CASES}
        sizes = {p.size for p in grid if p.case.startswith(("drop_duplicates", "sort_values"))}
        assert sizes == set(spec.row_sizes)
    assert max(p.size for p in build_grid("full")) == 10_000_000
    assert min(p.size for p in build_grid("full") if "drop_dup" in p.case) == 10_000


def test_suite_filters_and_footprint_cap_inputs():
    grid = build_grid("small", ops={"merge"})
    assert grid and {p.op for p in grid} == {"merge"}
    big = [p for p in build_grid("full") if p.case == "merge/inner_1to1" and p.size == 10_000_000]
    assert big[0].est_footprint_bytes() > 2**30
    assert max(p.size for p in build_grid("full") if p.case.startswith("read_csv")) <= 3_000_000
