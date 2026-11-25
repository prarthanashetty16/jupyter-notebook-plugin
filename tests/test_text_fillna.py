"""v4 item (1a): fillna on pandas-3 ``str`` columns (probes docs/benchmarks/phase8/probes/p8_text_fillna*)."""

from __future__ import annotations

import pandas as pd
import pytest

from nexus.models.base import Estimate
from nexus.pipeline import Pipeline

N = 100_000


def _ns() -> dict:
    with_na = pd.array(["a", None] * (N // 2), dtype="str")
    return {
        "t": pd.DataFrame({"s": with_na, "u": pd.array(["b"] * N, dtype="str")}),
        "one": pd.DataFrame({"s": with_na}),
        "cat": pd.DataFrame({"c": pd.Categorical(["a", None] * (N // 2))}),
        "pd": pd,
    }


def _est(src: str, tier: int = 1) -> Estimate | None:
    rep = Pipeline(tier=tier).run(src, _ns())
    return rep.estimates[0].estimate if rep.estimates else None


@pytest.mark.parametrize(("src", "per_row"), [
    ("one.fillna(0)", 21),  # non-string value: coercion to object (second derivation)
    ("one.fillna(-1.5)", 21),
    ("one.fillna('z')", 12),  # string value: pointer copy + 4 masks
    ("one.fillna({'s': 'z'})", 12),
    ("one['s'].fillna('z')", 12),
])  # fmt: skip
def test_one_str_column_with_a_missing_value(src: str, per_row: int):
    e = _est(src)
    assert e.tier == 1 and e.ram_low == e.ram_expected == per_row * N
    assert e.ram_high >= e.ram_expected


def test_columns_kept_then_the_largest_transient():
    e = _est(
        "t.fillna(0)"
    )  # s certain (NA in the sample), u possible (no NA seen): only the high adds u
    assert e.ram_expected == 21 * N and e.ram_high == (8 + 8 + 13) * N


def test_tier0_does_not_know_which_column_holds_a_missing_value():
    e = _est("t.fillna(0)", tier=0)
    assert e.ram_low == 0 and e.ram_expected == e.ram_high == (8 + 8 + 13) * N


def test_other_extension_dtypes_and_pyarrow_storage_are_refused(monkeypatch: pytest.MonkeyPatch):
    assert _est("cat.fillna('a')") is None
    from nexus.models import copy_fillna

    monkeypatch.setattr(copy_fillna, "_python_str_storage", lambda: False)
    assert _est("one.fillna(0)") is None
