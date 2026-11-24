"""v4 item (1d): ``X.copy()`` on row / column selection receivers (probe docs/benchmarks/phase8/probes/p8_copy_receivers*)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.cellpeak import cell_estimate
from nexus.pipeline import Pipeline

N = 100_000


def _ns() -> dict:
    rng = np.random.default_rng(1)
    cols = {f"f{i}": rng.random(N) for i in range(4)}
    cols["i0"] = rng.integers(0, 1000, N)
    cols["s0"] = pd.array(np.where(rng.random(N) < 0.5, "a", "b"), dtype="str")
    return {"df": pd.DataFrame(cols), "pd": pd}


def _est(src: str):
    rep = Pipeline(tier=1).run(src, _ns())
    return rep.estimates[0].estimate if rep.estimates else None


M = 6 * 8 * N  # four float64, one int64, one str pointer column


@pytest.mark.parametrize(("src", "per_row"), [
    ("y = df[['f0', 'f1']].copy()", 16),  # contiguous run of the float block: view, then the copy
    ("y = df[['f1', 'f0']].copy()", 32),  # reordered: take copies, then the copy
    ("y = df.iloc[:50_000].copy()", 24),  # half the rows of M = 48 B/row
])  # fmt: skip
def test_derivable_receivers_are_exact(src: str, per_row: int):
    e = _est(src)
    assert e.ram_low == e.ram_expected == e.ram_high == per_row * N


@pytest.mark.parametrize(("src", "compare"), [
    ("y = df[df['f0'] > 0.5].copy()", 1),
    ("y = df.loc[df['f0'] > 0.5].copy()", 1),
    ("y = df[(df['f0'] > 0.2) & (df['i0'] < 500)].copy()", 3),
    ("y = df[df['s0'] == 'a'].copy()", 12),
])  # fmt: skip
def test_mask_high_takes_every_row(src: str, compare: int):
    e = _est(src)
    assert e.ram_low == compare * N
    assert e.ram_expected == e.ram_high == max(compare * N, 17 * N + M, 8 * N + 2 * M)


@pytest.mark.parametrize("src", [
    "y = df[df['s0'].isin(['a'])].copy()",  # a call in the mask: unknown cost
    "y = df.head(5).copy()",  # head already copies in pandas 3.1.1
    "y = df.tail(5).copy()",
    "y = df.loc[:5].copy()",
    "y = df.iloc[::2].copy()",  # a step
    "y = df.dropna().copy()",  # a chain
])  # fmt: skip
def test_unmodelled_receivers_are_refused(src: str):
    assert _est(src) is None


def test_the_mask_transients_do_not_stay_in_the_cell():
    src = "y = df[df['f0'] > 0.5].copy()\nz = df.copy()"
    rep = Pipeline(tier=1).run(src, _ns())
    cell, _m, _f = cell_estimate(src, rep.estimates)
    # kept: at most the selected rows (M) + their index (8 B/row); then the second copy's M
    assert cell.ram_high <= max(17 * N + M, 8 * N + 2 * M) + (M + 8 * N) + M
