"""Phase 7b determinism: samples seeded from the cell, sample size from a predicted cost (not live time)."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from nexus import stats
from nexus.failsafe import Deadline
from nexus.pipeline import Pipeline


def test_same_cell_same_rows_different_cell_different_rows():
    with stats.cell_seed("a = df.drop_duplicates()"):
        a = stats.sample_positions(1_000_000, 1000)
    with stats.cell_seed("a = df.drop_duplicates()"):
        b = stats.sample_positions(1_000_000, 1000)
    with stats.cell_seed("b = df.drop_duplicates()"):
        c = stats.sample_positions(1_000_000, 1000)
    assert (a == b).all() and not (a == c).all()


def test_sample_size_does_not_depend_on_the_time_left():
    values = pd.Series(np.random.default_rng(0).integers(0, 1000, 2_000_000))
    fresh = Deadline(0.2)
    used = Deadline(0.2)
    time.sleep(0.15)  # most of the live budget is gone; the gate uses the fixed budget
    d1 = stats.distinct_count(values, deadline=fresh)
    d2 = stats.distinct_count(values, deadline=used)
    assert d1.sample == d2.sample


def test_gate_fallback_is_visible():
    assert stats.GATE_REASON.startswith("statistics skipped")
    from nexus.render import _FALLBACK_REASONS

    assert "predicted cost" in _FALLBACK_REASONS


def test_repeated_estimates_are_identical():
    df = pd.DataFrame({"k": np.random.default_rng(1).integers(0, 50_000, 300_000), "v": 1.0})
    src = "d = df.drop_duplicates(subset=['k'])"
    exp = {Pipeline(tier=1).run(src, {"df": df}).estimates[0].estimate.ram_expected for _ in range(5)}
    assert len(exp) == 1
