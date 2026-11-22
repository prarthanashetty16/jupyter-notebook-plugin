"""Phase 7b: names bound earlier in the cell shadow the kernel namespace (virtual shapes, Tier 0 only,
or no estimate when the shape is unknown)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.pipeline import Pipeline
from nexus.risk import RiskClass, assess


@pytest.fixture
def csv(tmp_path):
    rng = np.random.default_rng(0)
    p = tmp_path / "x.csv"
    pd.DataFrame({"k": rng.integers(0, 500, 50_000), "v": rng.random(50_000)}).to_csv(p, index=False)
    return repr(str(p))


@pytest.fixture
def ns():
    stale = pd.DataFrame({"k": [1], "v": [1.0]})  # an old `a` left by an earlier cell
    right = pd.DataFrame({"k": np.arange(500), "w": np.ones(500)})
    return {"pd": pd, "right": right, "a": stale, "f": len}


def _by_model(rep):
    return {e.model: e for e in rep.estimates}


def test_operation_on_a_loaded_frame_uses_the_predicted_shape_not_the_stale_object(csv, ns):
    rep = Pipeline(tier=1).run(f"a = pd.read_csv({csv})\nm = a.merge(right, on='k')", ns)
    m = _by_model(rep)["merge"]
    assert m.estimate.tier == 0 and m.features["tier1"]["reason"] == "frame created in this cell"
    assert m.features["n_left"] == pytest.approx(50_000, rel=0.05)  # not the stale 1-row frame


def test_shapes_propagate_through_concat_and_sort(csv, ns):
    src = f"a = pd.read_csv({csv})\nb = pd.read_csv({csv})\nc = pd.concat([a, b])\ns = c.sort_values('v')"
    got = _by_model(Pipeline(tier=1).run(src, ns))
    assert {"concat", "sort_values"} <= set(got)
    assert got["sort_values"].features["n_rows"] == pytest.approx(100_000, rel=0.05)


def test_unknown_producer_gives_no_estimate_and_unknown_names_it(ns):
    rep = Pipeline(tier=1).run("a = f(right)\nm = a.sort_values('k')", ns)
    assert not rep.estimates
    rep = Pipeline(tier=1).run("x = right.sort_values('k')\na = f(right)\nm = a.sort_values('k')", ns)
    assert [e.model for e in rep.estimates] == ["sort_values"]  # only the first
    r = assess(rep)
    assert r.risk in (RiskClass.UNKNOWN, RiskClass.WARN, RiskClass.HIGH_RISK)
    if r.risk is RiskClass.UNKNOWN:
        assert "a.sort_values('k')" in r.reason


def test_merge_results_are_not_propagated_row_count_is_a_range(ns):
    ns = {**ns, "left": pd.DataFrame({"k": np.arange(1000), "v": np.ones(1000)})}
    rep = Pipeline(tier=1).run("a = left.merge(right, on='k')\ns = a.sort_values('k')", ns)
    assert [e.model for e in rep.estimates] == ["merge"]


def test_bindings_inside_if_shadow_conservatively(csv, ns):
    rep = Pipeline(tier=1).run(f"if True:\n    a = pd.read_csv({csv})\nm = a.sort_values('k')", ns)
    assert [e.model for e in rep.estimates] == ["read_csv"]  # `a` bound in an if: shape unknown


def test_no_binding_in_the_cell_keeps_the_namespace_object(ns):
    rep = Pipeline(tier=1).run("m = a.sort_values('k')", ns)
    assert _by_model(rep)["sort_values"].features["n_rows"] == 1
