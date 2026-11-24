"""Tier 0 baseline models: wiring, unknown inputs, tier handling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.analyzer import analyze_cell
from nexus.models.builtin import load_builtin_models
from nexus.pipeline import Pipeline
from nexus.registry import default_registry


@pytest.fixture(scope="module")
def pipeline():
    return Pipeline(tier=0)


def estimates(pipeline, source, ns):
    report = pipeline.run(source, {"pd": pd, "np": np, **ns})
    return {e.op.name: e for e in report.estimates}


def frame(n=2000):
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "k": np.arange(n),
            "i0": rng.integers(0, 50, n),
            "f0": rng.random(n),
            "s0": [f"v{i % 40}" for i in range(n)],
        }
    )


def test_all_builtin_models_registered_once():
    load_builtin_models()
    load_builtin_models()
    names = {m.name for m in default_registry}
    assert {
        "drop_duplicates",
        "merge",
        "groupby",
        "sort_values",
        "read_csv",
        "astype",
        "concat",
        "matmul",
        "np_sort",
    } <= names


@pytest.mark.parametrize(
    ("source", "op"),
    [
        ("df.drop_duplicates()", "drop_duplicates"),
        ('df.drop_duplicates(subset=["s0"])', "drop_duplicates"),
        ('df.merge(df2, on="k")', "merge"),
        ('pd.merge(df, df2, on="k", how="left")', "pandas.merge"),
        ('df.groupby("s0")["f0"].sum()', "groupby"),
        ('df.sort_values("s0")', "sort_values"),
        ('df["s0"].astype("category")', "astype"),
        ('df["i0"].astype("float32")', "astype"),
        ('df["i0"].astype(str)', "astype"),
        ("pd.concat([df, df2])", "pandas.concat"),
        ("a @ b", "operator.matmul"),
        ("np.sort(v)", "numpy.sort"),
    ],
)
def test_estimate_is_a_valid_range(pipeline, source, op):
    ns = {
        "df": frame(),
        "df2": frame(),
        "a": np.ones((20, 30)),
        "b": np.ones((30, 10)),
        "v": np.ones(500),
    }
    est = estimates(pipeline, source, ns)[op].estimate
    assert 0 < est.ram_low <= est.ram_expected <= est.ram_high
    assert 0 < est.time_low <= est.time_expected <= est.time_high
    assert 0 <= est.confidence <= 1 and est.tier == 0 and est.drivers


def test_read_csv_uses_file_size(pipeline, tmp_path):
    path = tmp_path / "d.csv"
    frame().to_csv(path, index=False)
    est = estimates(pipeline, f"pd.read_csv({str(path)!r})", {})["pandas.read_csv"]
    size = path.stat().st_size
    assert est.estimate.ram_low < est.estimate.ram_expected < est.estimate.ram_high
    # Phase 4a: the parse holds tokens and chunks, so the peak is several times the file, and the
    # estimate scales linearly with it (the first draft pinned 1.5x, which under-predicted).
    assert est.estimate.ram_expected == pytest.approx(4.41 * size, rel=0.02)


def test_ram_grows_with_input_size(pipeline):
    small = estimates(pipeline, "df.drop_duplicates()", {"df": frame(1000)})["drop_duplicates"]
    large = estimates(pipeline, "df.drop_duplicates()", {"df": frame(10_000)})["drop_duplicates"]
    assert large.estimate.ram_expected > 5 * small.estimate.ram_expected
    assert large.estimate.time_expected > 5 * small.estimate.time_expected


def test_dropna_estimate(pipeline):
    df = frame(10_000)
    df["f0"] = np.linspace(0.0, 1.0, len(df))
    df.loc[df.index[:1000], "f0"] = np.nan
    estimate = estimates(pipeline, "df.dropna(subset=['f0'])", {"df": df})["dropna"]
    assert estimate.estimate.ram_low > 0
    assert estimate.estimate.ram_low <= estimate.estimate.ram_expected
    assert estimate.estimate.ram_expected <= estimate.estimate.ram_high


def test_reset_index_estimate(pipeline):
    df = frame(10_000)
    dropped = estimates(pipeline, "df.reset_index(drop=True)", {"df": df})["reset_index"]
    retained = estimates(pipeline, "df.reset_index()", {"df": df})["reset_index"]
    assert dropped.estimate.ram_expected < retained.estimate.ram_expected


def test_v4_output_and_easy_estimates(pipeline):
    df = frame(10_000)
    assert "map" in estimates(pipeline, "df['s0'].map({'v0': 1})", {"df": df})
    assert "to_numpy" in estimates(pipeline, "df.to_numpy()", {"df": df})
    assert "sample" in estimates(pipeline, "df.sample(n=100)", {"df": df})
    assert "describe" in estimates(pipeline, "df.describe()", {"df": df})
    assert "numpy.zeros" in estimates(pipeline, "np.zeros((100, 100))", {"np": np})
    assert "numpy.linspace" in estimates(pipeline, "np.linspace(0, 1, 100)", {"np": np})


@pytest.mark.parametrize(
    ("source", "ns"),
    [
        ("df.drop_duplicates()", {}),  # unknown variable
        ("df.drop_duplicates()", {"df": [1, 2, 3]}),  # not a DataFrame
        ('df.merge(other, on="k")', {"df": frame()}),  # right side unknown
        ('df.astype("float32")', {"df": frame()}),  # whole-frame astype not modelled
        ('df["nope"].astype("float32")', {"df": frame()}),  # unknown column
        ("pd.concat([df, df2], axis=1)", {"df": frame(), "df2": frame()}),
        ("a @ b", {"a": np.ones((3, 4)), "b": np.ones((5, 6))}),  # non-conforming
        ("a @ b", {"a": np.ones(4), "b": np.ones(4)}),  # 1-D
        ('pd.read_csv("definitely_missing.csv")', {}),
    ],
)
def test_unknown_inputs_give_no_estimate(pipeline, source, ns):
    assert estimates(pipeline, source, ns) == {}


def test_tier1_falls_back_to_tier0_when_the_sample_is_too_small():
    report = Pipeline(tier=1).run("df.drop_duplicates()", {"df": frame(500)})  # < 1000 rows
    (item,) = report.estimates
    assert item.estimate.tier == 0
    assert item.features["tier1"] == {"used": False, "reason": "no statistics"}


def test_tier1_on_a_small_complete_frame_is_exact_not_sampled():
    report = Pipeline(tier=1).run("df.drop_duplicates()", {"df": frame(2000)})
    (item,) = report.estimates
    assert item.estimate.tier == 1
    assert item.features["tier1"]["used"] and item.features["tier1"]["method"] == "complete"


def test_tiers_above_two_are_not_implemented():
    report = Pipeline(tier=3).run("df.drop_duplicates()", {"df": frame()})
    assert report.ops and report.estimates == []


def test_tier_2_on_a_small_frame_keeps_the_tier_1_estimate():
    report = Pipeline(tier=2).run("df.drop_duplicates()", {"df": frame()})
    assert report.estimates and report.estimates[0].estimate.tier <= 1


def test_features_are_logged_with_estimate(pipeline):
    item = estimates(pipeline, "df.drop_duplicates()", {"df": frame()})["drop_duplicates"]
    assert item.features["n_rows"] == 2000 and item.features["n_text_keys"] == 1


def test_analyzer_still_sees_ops_for_model_inputs():
    assert [o.name for o in analyze_cell('df["s0"].astype("category")')] == ["astype"]
