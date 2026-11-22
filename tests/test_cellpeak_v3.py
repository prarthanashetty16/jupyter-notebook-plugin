"""Phase 7b: rebinding releases the old result only when no other reference can exist (aliasing tests)."""

from __future__ import annotations

import pandas as pd

from nexus import cellpeak
from nexus.analyzer import analyze_cell
from nexus.pipeline import OpEstimate
from tests.test_phase6c import MIB, _est

PEAKS3 = [(10, 100, 100), (10, 50, 50), (10, 30, 30)]


def _exp(src: str, peaks=PEAKS3) -> float:
    """Cell expected (MiB): the statements' sort_values get ``peaks`` in order (output = whole peak);
    any other detected operation (the alias forms) gets a zero estimate."""
    ops = analyze_cell(src, {"pd": pd, "df": pd.DataFrame({"a": [1]}), "m": pd.DataFrame({"a": [1]})})
    sorts = [o for o in ops if o.name == "sort_values" and o.receiver == "df"]
    assert len(sorts) == len(peaks), [(o.name, o.receiver) for o in ops]
    it = iter(peaks)
    est = [OpEstimate(op=o, model="unknown", estimate=_est(*(next(it) if o in sorts else (0, 0, 0))),
                      features={}) for o in ops]  # fmt: skip
    cell, mode, _ = cellpeak.cell_estimate(src, est)
    assert mode == "statements"
    return cell.ram_expected / MIB


def test_plain_rebinding_releases_after_the_new_value_exists():
    src = "m = df.sort_values('a')\nm = df.sort_values('a')\nc = df.sort_values('a')"
    # m (100) is freed once m is rebound: the third statement sees 50 retained, not 150
    assert _exp(src) == max(100, 100 + 50, 50 + 30)
    src2 = "m = df.sort_values('a')\nm = m.sort_values('a')\nc = df.sort_values('a')"
    # the read of m goes into sort_values (new memory): m is released after the rebinding; that sort has
    # a zero estimate here, so the third statement sees nothing retained
    assert _exp(src2, [(10, 100, 100), (10, 30, 30)]) == 100


def test_aliases_keep_the_conservative_rule():
    keep = 100 + 50 + 30  # nothing released
    for alias in (
        "y = m\n",                    # a second name
        "lst = [m]\n",                # a container
        "print(m)\n",                 # a call argument
        "h = m.head()\n",             # head() shares memory under copy-on-write
        "g = m.groupby('a')\n",       # a GroupBy object keeps the frame
        "s = m.copy(deep=False)\n",   # a shallow copy shares the blocks
    ):  # fmt: skip
        src = "m = df.sort_values('a')\n" + alias + "m = df.sort_values('a')\nc = df.sort_values('a')"
        assert _exp(src) == keep, alias


def test_bindings_inside_if_are_not_released():
    src = "if True:\n    m = df.sort_values('a')\nm = df.sort_values('a')\nc = df.sort_values('a')"
    assert _exp(src) == 180
    src = "m = df.sort_values('a')\nif True:\n    m = df.sort_values('a')\nc = df.sort_values('a')"
    assert _exp(src) == 180


def test_tuple_targets_and_attribute_stores_are_not_released():
    src = "m = df.sort_values('a')\nm, z = df.sort_values('a'), 1\nc = df.sort_values('a')"
    assert _exp(src) == 180
