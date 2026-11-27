"""v4 item (1b): statistics carried through a deep copy of a kernel frame (nexus.cellframes.stats_namespace)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.cellpeak import cell_estimate
from nexus.pipeline import Pipeline

N = 200_000


def _ns() -> dict:
    f0 = np.random.default_rng(0).random(N)
    f0[::40] = np.nan
    s0 = pd.array(np.where(np.arange(N) % 20 == 0, None, "abc"), dtype="str")
    return {"df": pd.DataFrame({"k": np.arange(N), "f0": f0, "s0": s0}), "pd": pd}


def _run(src: str):
    ns = _ns()
    rep = Pipeline(tier=1).run(src, ns)
    cell, _m, _f = cell_estimate(src, rep.estimates)
    return {e.model: e for e in rep.estimates}, cell


@pytest.mark.parametrize(
    "src", ["x = df.copy()\ny = x.fillna(0)", "x = df.copy()\nz = x.copy()\ny = z.fillna(0)"]
)
def test_fillna_on_a_copy_of_a_kernel_frame_runs_tier1_like_the_original(src: str):
    ops, cell = _run(src)
    direct = Pipeline(tier=1).run("y = df.fillna(0)", _ns()).estimates[0].estimate
    assert ops["fillna"].estimate.tier == 1 and cell.tier == 1
    assert ops["fillna"].estimate.ram_expected == direct.ram_expected
    assert ops["fillna"].estimate.ram_high == direct.ram_high


@pytest.mark.parametrize("src", [
    "df['k'] = 1\nx = df.copy()\ny = x.fillna(0)",  # the kernel frame may have changed before the copy
    "x = df[['k', 'f0']].copy()\ny = x.fillna(0)",  # a column selection, not the whole frame
    "x = df.copy(deep=False)\ny = x.fillna(0)",  # shallow: not a produced frame
    "x = df.sort_values('k')\ny = x.fillna(0)",  # not a copy
])  # fmt: skip
def test_no_statistics_without_a_provable_alias(src: str):
    ops, _cell = _run(src)
    if "fillna" in ops:
        assert ops["fillna"].estimate.tier == 0
