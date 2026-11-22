"""Phase 7b determinism: samples seeded from the cell. (The deterministic cost gate failed its pre-registered
rule and was not adopted: the v2 timed gate stays, so near the budget the tier can still differ.)"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nexus import stats
from nexus.pipeline import Pipeline


def test_same_cell_same_rows_different_cell_different_rows():
    with stats.cell_seed("a = df.drop_duplicates()"):
        a = stats.sample_positions(1_000_000, 1000)
    with stats.cell_seed("a = df.drop_duplicates()"):
        b = stats.sample_positions(1_000_000, 1000)
    with stats.cell_seed("b = df.drop_duplicates()"):
        c = stats.sample_positions(1_000_000, 1000)
    assert (a == b).all() and not (a == c).all()


def test_repeated_estimates_are_identical():
    df = pd.DataFrame({"k": np.random.default_rng(1).integers(0, 50_000, 300_000), "v": 1.0})
    src = "d = df.drop_duplicates(subset=['k'])"
    exp = {
        Pipeline(tier=1).run(src, {"df": df}).estimates[0].estimate.ram_expected for _ in range(5)
    }
    assert len(exp) == 1
