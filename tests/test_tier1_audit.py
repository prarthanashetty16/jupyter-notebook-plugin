"""Audit of every Tier 1 path for zero, negative, NaN or infinite results, plus the sanity guard.

Root cause that prompted it (val-v4): in pandas 3 ``astype(str)`` keeps a null as a null, so the
sampled string lengths of a float / datetime column with nulls were NaN, the mean was NaN and
``max(0.0, nan)`` turned the estimate into a silent 0.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nexus import guard
from nexus.models import _util as u
from nexus.models.base import Estimate
from nexus.pipeline import Pipeline

N = 60_000


def _frames():
    rng = np.random.default_rng(7)
    f = rng.random(N)
    f[rng.integers(0, N, 2_400)] = np.nan
    dt = pd.Series(pd.date_range("2021-01-01", periods=N, freq="min")).where(rng.random(N) > 0.04)
    words = np.array([f"w{i:05d}" for i in range(500)], dtype=object)
    txt = pd.Series(words[rng.integers(0, 500, N)], dtype=object).where(rng.random(N) > 0.1)
    return {
        "nulls": pd.DataFrame(
            {
                "f": f,
                "d": dt,
                "s": txt,
                "i": rng.integers(0, 50_000, N),
                "b": rng.random(N) > 0.5,
                "c": pd.Categorical(words[rng.integers(0, 30, N)]),
                "k": rng.integers(0, 40, N),
            }
        ),  # fmt: skip
        "all_null": pd.DataFrame(
            {
                "f": np.full(N, np.nan),
                "d": pd.Series([pd.NaT] * N),
                "s": pd.Series([None] * N, dtype=object),
                "k": rng.integers(0, 40, N),
            }
        ),  # fmt: skip
        "constant": pd.DataFrame(
            {"f": np.full(N, 1.5), "s": ["same"] * N, "i": np.full(N, 7), "k": np.zeros(N, int)}
        ),
        "mixed_len": pd.DataFrame(
            {
                "s": pd.Series(
                    ["" if i % 3 == 0 else "x" * (i % 40) for i in range(N)], dtype=object
                ),
                "f": rng.random(N) * 1e12,
                "i": rng.integers(-5, 300, N),
                "k": rng.integers(0, 3, N),
            }
        ),  # fmt: skip
    }


FRAMES = _frames()
CELLS = [
    ("nulls", 'df["f"].astype(str)'), ("nulls", 'df["d"].astype(str)'), ("nulls", 'df["i"].astype(str)'),
    ("nulls", 'df["b"].astype(str)'), ("nulls", 'df["s"].astype("category")'),
    ("nulls", 'df["f"].astype("category")'), ("nulls", 'df["c"].astype("category")'),
    ("nulls", 'df["i"].astype("int32")'),
    ("all_null", 'df["f"].astype(str)'), ("all_null", 'df["d"].astype(str)'),
    ("all_null", 'df["s"].astype("category")'), ("all_null", 'df["f"].astype("category")'),
    ("constant", 'df["f"].astype(str)'), ("constant", 'df["s"].astype("category")'),
    ("constant", 'df["i"].astype(str)'), ("mixed_len", 'df["i"].astype(str)'),
    ("mixed_len", 'df["f"].astype(str)'), ("mixed_len", 'df["s"].astype("category")'),
    ("nulls", 'df.groupby("s")["f"].sum()'), ("nulls", 'df.groupby(["k", "s"])["f"].sum()'),
    ("nulls", 'df.groupby("d")["f"].mean()'), ("all_null", 'df.groupby("f")["k"].sum()'),
    ("all_null", 'df.groupby(["s", "d"])["k"].sum()'), ("constant", 'df.groupby("k")["f"].sum()'),
    ("nulls", 'df.groupby("c")["f"].sum()'),
    ("nulls", "df.drop_duplicates()"), ("nulls", 'df.drop_duplicates(subset=["f", "s"])'),
    ("all_null", "df.drop_duplicates()"), ("all_null", 'df.drop_duplicates(subset=["d"])'),
    ("constant", "df.drop_duplicates()"), ("mixed_len", "df.drop_duplicates()"),
    ("nulls", 'df.sort_values("f")'), ("all_null", 'df.sort_values("s")'),
]  # fmt: skip


def _check(item):
    e = item.estimate
    figures = (e.ram_low, e.ram_expected, e.ram_high, e.time_low, e.time_expected, e.time_high)
    assert all(math.isfinite(x) for x in figures), item.op.name
    assert e.ram_expected > 0 and e.time_expected > 0, (item.op.name, figures)
    assert 0 <= e.ram_low <= e.ram_expected <= e.ram_high


@pytest.mark.parametrize(("frame", "cell"), CELLS)
def test_tier1_never_returns_zero_negative_nan_or_infinite(frame, cell):
    df = FRAMES[frame]
    report = Pipeline(tier=1).run(cell, {"df": df, "pd": pd, "np": np})
    assert report.estimates, cell
    for item in report.estimates:
        _check(item)


@pytest.mark.parametrize("col", ["f", "d"])
def test_astype_str_with_nulls_charges_no_string_object_for_a_null(col):
    """Regression for the val-v4 zero estimate (float and datetime sources with nulls)."""
    df = FRAMES["nulls"]
    item = Pipeline(tier=1).run(f'df["{col}"].astype(str)', {"df": df}).estimates[0]
    assert item.estimate.tier == 1 and item.estimate.note is None
    per_row = item.estimate.ram_expected / N
    null_share = float(df[col].isna().mean())
    assert 0.02 < null_share < 0.06
    obj = item.features["str_obj_bytes"]
    assert per_row == pytest.approx(8 + (1 - null_share) * obj, rel=0.03)  # pointer + str objects
    assert per_row > 40  # not ~0


def test_astype_str_of_an_all_null_column_falls_back_to_tier_0():
    item = Pipeline(tier=1).run('df["f"].astype(str)', {"df": FRAMES["all_null"]}).estimates[0]
    assert item.estimate.tier == 0 and item.estimate.ram_expected > 0
    assert item.features["tier1"]["used"] is False


def test_build_refuses_non_finite_figures_instead_of_clamping_them_to_zero():
    with pytest.raises(ValueError, match="non-finite"):
        u.build((float("nan"), 1.0, 2.0), (0.1, 0.2, 0.4), 0.5, 1, [])
    with pytest.raises(ValueError, match="non-finite"):
        u.build((1.0, 2.0, 3.0), (0.1, float("inf"), 0.4), 0.5, 1, [])


# -- the guard ---------------------------------------------------------------------------------------
def _est(low, exp, high, t=1.0, tier=1):
    return Estimate(ram_low=low, ram_expected=exp, ram_high=high, time_low=t / 4, time_expected=t,
                    time_high=t * 4, confidence=0.5, tier=tier)  # fmt: skip


def test_guard_rejects_non_positive_and_wildly_inconsistent_estimates():
    t0 = _est(100, 200, 400, tier=0)
    assert guard.tier1_problem(_est(120, 220, 300), t0) is None
    assert guard.tier1_problem(_est(0, 0, 0), t0) == "non-positive expected value"
    assert guard.tier1_problem(_est(1, 2, 3, t=0.0), t0) == "non-positive expected value"
    assert "far outside" in guard.tier1_problem(_est(10_000, 20_000, 40_000), t0)
    assert "far outside" in guard.tier1_problem(_est(1, 2, 3), t0)
    assert guard.tier1_problem(_est(1, 2, 3), None) is None  # no Tier 0 to compare with


def test_guard_keeps_a_correct_estimate_that_sits_just_outside_tier_0():
    """Tier 0 does not know about nulls: 69 B/row (4% nulls) is just under its 70.5 B/row low."""
    t0 = _est(70_500, 79_000, 88_000, tier=0)
    assert guard.tier1_problem(_est(66_000, 69_000, 72_000), t0) is None


def test_a_rejected_tier_1_estimate_falls_back_to_tier_0_with_the_reason(monkeypatch):
    from nexus.models.astype import AstypeModel

    real = AstypeModel.estimate

    def broken(self, features, tier):
        if tier == 1:
            return _est(0, 0, 0)
        return real(self, features, tier)

    monkeypatch.setattr(AstypeModel, "estimate", broken)
    item = Pipeline(tier=1).run('df["f"].astype(str)', {"df": FRAMES["nulls"]}).estimates[0]
    assert item.estimate.tier == 0 and "non-positive" in item.estimate.note
    assert item.features["tier1"] == {"used": False, "reason": "non-positive expected value"}
    assert item.estimate.ram_expected > 0
