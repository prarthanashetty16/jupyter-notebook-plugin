"""Generator knobs added for test-v2, and the guarantee that older configs did not change."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from benchmarks.datasets import DatasetConfig, make_frame, make_join_pair
from benchmarks.suite import ArrayInput, JoinInput


def fingerprint(df: pd.DataFrame) -> str:
    """Portable content hash (numpy bytes / strings; datetimes normalised to seconds)."""
    h = hashlib.sha256(",".join(map(str, df.columns)).encode())
    for name in df.columns:
        col = df[name]
        if str(col.dtype).startswith("datetime64"):
            h.update(col.to_numpy().astype("datetime64[s]").astype("int64").tobytes())
        elif (
            col.dtype == object
            or isinstance(col.dtype, pd.CategoricalDtype)
            or str(col.dtype) == "str"
        ):
            h.update("|".join(map(str, col.astype(object).tolist())).encode())
        else:
            h.update(np.ascontiguousarray(col.to_numpy()).tobytes())
    return h.hexdigest()[:16]


# -- defaults reproduce the earlier datasets exactly ----------------------------------------------
@pytest.mark.parametrize(
    ("cfg", "expected"),
    [
        (
            DatasetConfig(n_rows=3000, null_rate=0.1, dup_rate=0.3, cardinality=0.05),
            "eb974b63daa00a53",
        ),
        (
            DatasetConfig(n_rows=2000, distribution="real_like", null_rate=0.05, str_len=20),
            "bbdd50272164648b",
        ),
        (
            DatasetConfig(n_rows=1500, n_object=0, n_category=0, n_datetime=0, n_int=3, n_float=3),
            "f15f62a7bc418283",
        ),
    ],
)
def test_existing_configs_are_bit_identical(cfg, expected):
    assert fingerprint(make_frame(cfg)) == expected


def test_existing_join_is_bit_identical():
    left, right = make_join_pair(DatasetConfig(n_rows=2000), 900, overlap=0.4, fanout=2.0)
    assert (fingerprint(left), fingerprint(right)) == ("9a73d80c011775ce", "be95a14cf61e0ca5")


def test_default_repr_is_unchanged_but_new_knobs_change_the_cache_key():
    base = DatasetConfig(n_rows=100)
    assert "zipf_exponent" not in repr(base) and "ordering" not in repr(base)
    for change in ({"zipf_exponent": 1.8}, {"null_pattern": "clustered"},
                   {"str_len_dist": "variable"}, {"ordering": "block_sorted"}):  # fmt: skip
        assert repr(base.with_(**change)) != repr(base)
    plain = JoinInput(base, 50)
    assert "right_key_dist" not in repr(plain) and "right_seed" not in repr(plain)
    assert repr(JoinInput(base, 50, right_key_dist="zipf")) != repr(plain)
    assert repr(JoinInput(base, 50, right_seed=9)) != repr(plain)


# -- new knobs ------------------------------------------------------------------------------------
def test_variable_string_lengths():
    df = make_frame(
        DatasetConfig(n_rows=20_000, str_len=12, str_len_dist="variable", cardinality=0.2, seed=5)
    )
    lengths = df["s0"].dropna().str.len()
    assert lengths.nunique() > 8 and lengths.min() >= 3 and lengths.max() <= 48
    assert 6 < lengths.median() < 20
    assert df["s0"].nunique() <= DatasetConfig(n_rows=20_000, cardinality=0.2).card
    fixed = make_frame(DatasetConfig(n_rows=20_000, str_len=12, cardinality=0.2, seed=5))
    assert fixed["s0"].dropna().str.len().nunique() == 1


def test_variable_vocabulary_strings_stay_distinct():
    df = make_frame(DatasetConfig(n_rows=5000, n_category=1, cardinality=0.9, str_len=6,
                                  str_len_dist="variable", seed=7))  # fmt: skip
    assert df["c0"].cat.categories.is_unique


def test_clustered_nulls_come_in_runs_at_about_the_requested_rate():
    cfg = DatasetConfig(n_rows=40_000, null_rate=0.1, null_pattern="clustered", seed=11)
    nulls = make_frame(cfg)["f0"].isna().to_numpy()
    assert 0.03 < nulls.mean() < 0.15
    run_starts = np.flatnonzero(nulls & ~np.r_[False, nulls[:-1]])
    assert len(run_starts) < nulls.sum() / 20  # long runs, unlike independent nulls
    uniform = make_frame(cfg.with_(null_pattern="uniform"))["f0"].isna().to_numpy()
    assert (uniform & ~np.r_[False, uniform[:-1]]).sum() > 10 * len(run_starts)


def test_zipf_exponent_controls_skew():
    mild = make_frame(
        DatasetConfig(
            n_rows=60_000, cardinality=500, distribution="real_like", zipf_exponent=1.1, seed=3
        )
    )
    heavy = make_frame(
        DatasetConfig(
            n_rows=60_000, cardinality=500, distribution="real_like", zipf_exponent=2.0, seed=3
        )
    )
    top = lambda df: df["i0"].value_counts(normalize=True).iloc[0]  # noqa: E731
    assert top(heavy) > 2 * top(mild)


def test_block_sorted_ordering_is_sorted_within_blocks_only():
    df = make_frame(DatasetConfig(n_rows=20_000, cardinality=0.5, ordering="block_sorted", seed=9))
    key = df["i0"].to_numpy()
    in_block = [np.all(np.diff(key[s : s + 4096]) >= 0) for s in range(0, len(key), 4096)]
    assert all(in_block) and not np.all(np.diff(key) >= 0)
    random = make_frame(DatasetConfig(n_rows=20_000, cardinality=0.5, seed=9))["i0"].to_numpy()
    assert not np.all(np.diff(random[:4096]) >= 0)


def test_new_knobs_are_deterministic_and_validated():
    cfg = DatasetConfig(n_rows=3000, null_rate=0.1, null_pattern="clustered", str_len_dist="variable",
                        zipf_exponent=1.6, distribution="real_like", ordering="block_sorted", seed=21)  # fmt: skip
    assert fingerprint(make_frame(cfg)) == fingerprint(make_frame(cfg))
    for bad in (
        {"null_pattern": "x"},
        {"str_len_dist": "x"},
        {"ordering": "x"},
        {"zipf_exponent": 0},
    ):
        with pytest.raises(ValueError):
            DatasetConfig(n_rows=10, **bad)


def test_zipf_right_keys_skew_the_join_fanout():
    left = DatasetConfig(n_rows=6000, seed=31)
    _, even = make_join_pair(left, 3000, overlap=1.0, fanout=3.0, seed=32)
    _, skew = make_join_pair(left, 3000, overlap=1.0, fanout=3.0, seed=32, right_key_dist="zipf")
    assert skew["k"].value_counts().iloc[0] > 10 * even["k"].value_counts().iloc[0]
    assert len(skew) == len(even) == 3000


@pytest.mark.parametrize("pattern", ["nearly_sorted", "few_unique"])
def test_new_array_patterns(pattern):
    dtype = "int64" if pattern == "few_unique" else "float64"
    arr = ArrayInput((20_000,), pattern=pattern, dtype=dtype, seed=41).generate()["a"]
    assert arr.dtype == np.dtype(dtype) and arr.shape == (20_000,)
    if pattern == "nearly_sorted":
        inversions = (np.diff(arr) < 0).mean()
        assert 0 < inversions < 0.05
        assert (arr[:200] == np.arange(200)).mean() > 0.9
    else:
        assert len(np.unique(arr)) <= 1000 and len(np.unique(arr)) > 900
