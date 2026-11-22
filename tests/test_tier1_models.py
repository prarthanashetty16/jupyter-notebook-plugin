"""Tier 1: model behaviour with data statistics (wiring, fallbacks, narrowing, no data mutation)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nexus import stats
from nexus.models import _util as u
from nexus.models.groupby import _aggregated_columns
from nexus.pipeline import Pipeline

N = 300_000


@pytest.fixture(autouse=True)
def _native_tier1_range(monkeypatch):
    """These tests are about the models' own Tier 1 ranges, not the global range policy."""
    from nexus import ranges

    monkeypatch.setattr(ranges, "UPPER_IS_TIER0_HIGH", False)


@pytest.fixture(scope="module")
def df():
    rng = np.random.default_rng(11)
    vocab = np.array([f"key_{i:06d}" for i in range(300)], dtype=object)
    f0 = rng.random(N)
    f0[rng.integers(0, N, 20_000)] = np.nan
    return pd.DataFrame(
        {
            "s": pd.Series(vocab[rng.integers(0, 300, N)], dtype=object),
            "i": rng.integers(0, 3_000_000, N),
            "k": rng.integers(0, 40, N),
            "f0": f0,
            "f1": rng.random(N),
        }
    )


def run(source, ns, tier, **kw):
    report = Pipeline(tier=tier, **kw).run(source, {"pd": pd, "np": np, **ns})
    (item,) = report.estimates
    return item


def per_row(item, n=N):
    e = item.estimate
    return [round(x / n, 1) for x in (e.ram_low, e.ram_expected, e.ram_high)]


# -- fallbacks and wiring ---------------------------------------------------------------------------
def test_tier1_off_keeps_tier0_estimates(df):
    item = run('df["s"].astype("category")', {"df": df}, 0)
    assert item.estimate.tier == 0 and "tier1" not in item.features


def test_tier1_budget_exhausted_falls_back_to_tier0(df):
    item = run('df["s"].astype("category")', {"df": df}, 1, tier1_budget_s=0.0)
    assert item.estimate.tier == 0
    assert item.features["tier1"]["used"] is False and "budget" in item.features["tier1"]["reason"]


def test_tier1_never_changes_the_users_frame(df):
    before = df.copy(deep=True)
    for source in (
        'df["s"].astype("category")',
        'df.groupby("s")["f0"].sum()',
        "df.drop_duplicates()",
        'df["i"].astype(str)',
    ):
        run(source, {"df": df}, 1)
    pd.testing.assert_frame_equal(df, before)


def test_time_ranges_come_from_the_calibration_per_tier(df):
    """Phase 6: each tier's range is its own calibrated (conformal) range, around its own expected."""
    from nexus import timecal

    t0 = run('df.groupby("s")["f0"].sum()', {"df": df}, 0).estimate
    t1 = run('df.groupby("s")["f0"].sum()', {"df": df}, 1).estimate
    assert t1.tier == 1
    art = timecal.artifact()
    for est, tier in ((t0, "0"), (t1, "1")):
        entry = art["tier01"][tier]["groupby"]
        assert entry["range"] == "per-operation"
        widen = 3.0  # tests run on an uncalibrated machine (generic profile)
        assert est.time_low / est.time_expected == pytest.approx(math.exp(entry["q_lo"]) / widen)
        assert est.time_high / est.time_expected == pytest.approx(math.exp(entry["q_hi"]) * widen)


def test_stats_overhead_stays_inside_the_budget(df):
    item = run('df.groupby("s")["f0"].sum()', {"df": df}, 1)
    assert item.features["tier1"]["stats_s"] < 0.25


# -- astype ---------------------------------------------------------------------------------------------------
def test_astype_category_tier1_narrows_the_range_around_the_cardinality(df):
    t0 = per_row(run('df["s"].astype("category")', {"df": df}, 0))
    t1 = per_row(run('df["s"].astype("category")', {"df": df}, 1))
    assert t1[2] - t1[0] < 0.5 * (t0[2] - t0[0])
    sc = stats.hash_scatter(df["s"], text=True).value  # the fixture's keys are sequential strings
    assert t1[0] <= u.factorize_peak_bytes("text", N, 300, sc) / N <= t1[2]  # 300 distinct of 300k


def test_astype_int_to_str_tier1_gives_the_probe_value(df):
    item = run('df["k"].astype(str)', {"df": df}, 1)  # 0..39: 1-2 digit strings, small cached ints
    low, exp, high = per_row(item)
    assert exp < 80 and low <= exp <= high  # ints below 257 are cached: no 32-byte int temporary
    big = run('df["i"].astype(str)', {"df": df}, 1)  # up to 7 digits, 32-byte int objects
    assert per_row(big)[1] == pytest.approx(96, abs=2)


# -- groupby ----------------------------------------------------------------------------------------------------
def test_groupby_tier1_estimates_groups_and_narrows(df):
    t0 = per_row(run('df.groupby("s")["f0"].sum()', {"df": df}, 0))
    item = run('df.groupby("s")["f0"].sum()', {"df": df}, 1)
    low, exp, high = per_row(item)
    assert high - low < 0.5 * (t0[2] - t0[0])
    sc = stats.hash_scatter(df["s"], text=True).value
    assert exp == pytest.approx(u.factorize_peak_bytes("text", N, 300, sc) / N, abs=1.5)
    assert item.features["groups_fraction"][1] == pytest.approx(300 / N, rel=0.1)


def test_groupby_reads_the_aggregated_columns_from_the_cell(df):
    import ast

    from nexus.analyzer import analyze_cell

    for source, expected in (
        ('df.groupby("s")["f0"].sum()', ["f0"]),
        ('df.groupby("s")[["f0", "f1"]].mean()', ["f0", "f1"]),
        ('df.groupby("s").sum(numeric_only=True)', ["i", "k", "f0", "f1"]),
    ):
        ast.parse(source)
        (op,) = [o for o in analyze_cell(source, {"df": df}) if o.name == "groupby"]
        assert _aggregated_columns(source, op, df, ["s"]) == expected


def test_groupby_high_group_count_is_charged_for_the_result_frame():
    n = 200_000
    rng = np.random.default_rng(3)
    wide = pd.DataFrame({"g": rng.permutation(n), **{f"v{j}": rng.random(n) for j in range(10)}})
    one = per_row(run('wide.groupby("g")[["v0"]].sum()', {"wide": wide}, 1), n)
    ten = per_row(run('wide.groupby("g").sum()', {"wide": wide}, 1), n)
    assert ten[1] > one[1] + 40  # probe: +8 B/row per extra aggregated column when G = n


# -- merge --------------------------------------------------------------------------------------------------------
def _frames():
    rng = np.random.default_rng(5)
    n = 200_000
    left = pd.DataFrame({"k": rng.permutation(n), "a": rng.random(n), "b": rng.integers(0, 9, n)})
    right = pd.DataFrame({"k": rng.permutation(n)[: n // 2], "c": rng.random(n // 2)})
    return left, right


def test_merge_tier1_supplies_output_rows_and_copy_elision():
    left, right = _frames()
    item = run('left.merge(right, on="k", how="left")', {"left": left, "right": right}, 1)
    f = item.features
    assert f["out_rows_source"] == "tier1" and f["left_elided"] and f["right_unique"]
    lo, mid, hi = f["out_rows"]
    assert lo <= len(left) <= hi and mid == pytest.approx(len(left), rel=0.01)
    inner = run('left.merge(right, on="k")', {"left": left, "right": right}, 1)
    assert inner.features["out_rows"][1] == pytest.approx(len(right), rel=0.02)
    assert not inner.features["left_elided"]  # half of the left rows have no match


def test_merge_outer_and_right_have_their_own_terms():
    from nexus.models.merge import MergeModel

    f = {"n_left": 10, "n_right": 10, "bytes_left": 80, "bytes_right": 80, "moved_left": 80,
         "moved_right": 80}  # fmt: skip
    inner = MergeModel.ram_at({**f, "how": "inner"}, 1_000_000)
    outer = MergeModel.ram_at({**f, "how": "outer"}, 1_000_000)
    assert outer - inner == pytest.approx(24 * 1_000_000, rel=0.01)
    big = {**f, "n_left": 3_000_000, "n_right": 1_000_000, "bytes_left": 8 * 3_000_000,
           "moved_left": 8 * 3_000_000, "bytes_right": 8_000_000, "moved_right": 8_000_000}  # fmt: skip
    left_join = MergeModel.ram_at({**big, "how": "left"}, 10)
    right_join = MergeModel.ram_at({**big, "how": "right"}, 10)
    assert right_join > left_join  # engine over the 3M left keys instead of the 1M right keys


def test_merge_without_a_single_literal_key_stays_at_tier0():
    left, right = _frames()
    item = run('left.merge(right, left_on="k", right_on="k")', {"left": left, "right": right}, 1)
    assert item.estimate.tier == 0


# -- drop_duplicates -----------------------------------------------------------------------------------------------
def test_drop_duplicates_tier1_counts_certain_null_columns_and_survivors(df):
    item = run("df.drop_duplicates()", {"df": df}, 1)
    info = item.features["tier1"]
    assert (
        info["null_certain"] == 1
    )  # f0 has NaNs (found by a full scan); the sample sees none in s
    lo, mid, hi = item.features["distinct_rows_range"]
    assert lo <= 1.0 <= hi + 1e-9 and mid > 0.5  # nearly every row of this frame is distinct
    t0 = item.estimate
    assert t0.ram_low <= t0.ram_expected <= t0.ram_high


def test_drop_duplicates_subset_uses_only_the_subset_columns(df):
    item = run('df.drop_duplicates(subset=["k"])', {"df": df}, 1)
    assert item.features["distinct_rows_range"][1] == pytest.approx(40 / N, abs=2e-4)
    assert item.features["null_range"] == (0, 0, 0)


# -- read_csv ------------------------------------------------------------------------------------------------------------
def test_read_csv_tier1_stops_overpredicting_float_heavy_files(tmp_path):
    rng = np.random.default_rng(2)
    n = 120_000
    path = tmp_path / "f.csv"
    pd.DataFrame({f"f{j}": rng.random(n) for j in range(10)}).to_csv(path, index=False)
    size = path.stat().st_size
    ns = {"pd": pd}
    t0 = Pipeline(tier=0).run(f"pd.read_csv({str(path)!r})", ns).estimates[0].estimate
    t1 = Pipeline(tier=1).run(f"pd.read_csv({str(path)!r})", ns).estimates[0].estimate
    assert t1.tier == 1 and t0.ram_expected / size > 4  # the Tier 0 prior assumes narrow fields
    assert t1.ram_expected / size < 3.2  # float-heavy: probes measured ~2.2-2.4 x the file
    assert t1.ram_high - t1.ram_low < 0.5 * (t0.ram_high - t0.ram_low)


def test_read_csv_options_tier1_only_when_understood(tmp_path):
    """Phase 6c: one-character sep / delimiter and header 0 / None get Tier 1 (the probe showed the
    same cost as the default read). Phase 7b: usecols, nrows, numeric dtype targets and na_values too
    (reader-path model); text dtype targets, parse_dates and anything else stay at Tier 0."""
    frame = pd.DataFrame({"a": range(5_000), "b": range(5_000)})
    path, tsv = tmp_path / "x.csv", tmp_path / "x.tsv"
    frame.to_csv(path, index=False)
    frame.to_csv(tsv, index=False, sep=chr(9))
    p, t, tab = repr(str(path)), repr(str(tsv)), repr(chr(9))
    understood = (
        f"pd.read_csv({p}, sep=',')", f"pd.read_csv({t}, sep={tab})",
        f"pd.read_csv({t}, delimiter={tab})", f"pd.read_csv({p}, header=0)",
        f"pd.read_csv({p}, usecols=['a'])", f"pd.read_csv({p}, dtype={{'a': 'float32'}})",
        f"pd.read_csv({p}, nrows=100)", f"pd.read_csv({p}, na_values=['NA'])",
        f"pd.read_csv({p}, dtype='float64')",
    )  # fmt: skip
    refused = (
        f"pd.read_csv({p}, dtype={{'a': 'str'}})", f"pd.read_csv({p}, parse_dates=['a'])",
        f"pd.read_csv({p}, low_memory=False)", f"pd.read_csv({p}, sep='::')",
        f"pd.read_csv({p}, names=['x', 'y'])", f"pd.read_csv({p}, chunksize=100)",
        f"pd.read_csv({p}, sep=sep)",
    )  # fmt: skip
    for call in understood:
        report = Pipeline(tier=1).run(call, {"pd": pd, "sep": ","})
        assert report.estimates and report.estimates[0].estimate.tier == 1, call
    for call in refused:
        report = Pipeline(tier=1).run(call, {"pd": pd, "sep": ","})
        assert report.estimates and report.estimates[0].estimate.tier == 0, call
    a = Pipeline(tier=1).run(f"pd.read_csv({p})", {"pd": pd}).estimates[0].estimate
    b = Pipeline(tier=1).run(f"pd.read_csv({t}, sep={tab})", {"pd": pd}).estimates[0].estimate
    assert a.ram_expected == pytest.approx(b.ram_expected, rel=0.05)  # same rows / fields
