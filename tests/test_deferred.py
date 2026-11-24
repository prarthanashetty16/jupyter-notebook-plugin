"""v4 item (4): every deferred operation's UNKNOWN message names it and the reason (nexus.deferred)."""

from __future__ import annotations

import pandas as pd
import pytest

from nexus.deferred import DEFERRED
from nexus.pipeline import Pipeline
from nexus.risk import RiskClass, assess


def _assess(src: str):
    df = pd.DataFrame({"a": range(1000), "b": [1.5] * 1000})
    return assess(Pipeline(tier=1).run(src, {"df": df, "pd": pd}))


@pytest.mark.parametrize(("src", "name"), [
    ("z = df['a'].value_counts()", "value_counts"),
    ("c = df.corr()", "corr"),
    ("d = pd.get_dummies(df)", "pandas.get_dummies"),
    ("df.to_csv('x.csv')", "to_csv"),
])  # fmt: skip
def test_deferred_operation_is_named_with_its_reason(src: str, name: str):
    r = _assess(src)
    assert r is not None and r.risk is RiskClass.UNKNOWN
    assert f"`{src.split(' = ')[-1]}`" in r.reason and DEFERRED[name] in r.reason


def test_value_counts_reason_names_the_key_values():
    assert "exact key values" in DEFERRED["value_counts"]


def test_copy_of_head_or_tail_names_the_copying_receiver():
    for src in ("y = df.head(5).copy()", "y = df.tail(5).copy()"):
        r = _assess(src)
        assert r is not None and r.risk is RiskClass.UNKNOWN and "head() / tail()" in r.reason
