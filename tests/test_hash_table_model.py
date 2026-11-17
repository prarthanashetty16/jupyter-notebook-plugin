"""Hash-table residency model (factorize / merge indexers): regression tests pinned to isolated probes.

The reference numbers are measurements from docs/benchmarks/val-v3-diagnosis/probes (project
instrument, random keys unless stated), NOT benchmark points.
"""

from __future__ import annotations

import string

import numpy as np
import pandas as pd
import pytest

from nexus import stats
from nexus.models import _util as u
from nexus.models.groupby import GroupByModel
from nexus.models.merge import MergeModel

MIB = 2**20


# (kind, n, distinct, measured MiB): probes pb1 / pb9, random keys
FACTORIZE_PROBES = [
    ("text", 300_000, 12_000, 19.2),
    ("text", 1_000_000, 12_000, 63.2),
    ("text", 2_000_000, 12_000, 85.9),
    ("text", 4_000_000, 12_000, 131.9),
    ("text", 2_000_000, 5_000, 72.0),
    ("text", 1_500_000, 3_000, 52.6),
    ("text", 3_000_000, 600_000, 121.7),
    ("text", 2_000_000, 2_000_000, 157.5),
    ("text", 4_000_000, 12, 92.0),
    ("numeric", 2_000_000, 100, 31.1),
    ("numeric", 1_000_000, 30_000, 40.4),
    ("numeric", 3_000_000, 400_000, 59.7),
    ("numeric", 2_000_000, 2_000_000, 110.4),
]


@pytest.mark.parametrize(("kind", "n", "distinct", "measured"), FACTORIZE_PROBES)
def test_factorize_model_matches_the_probes(kind, n, distinct, measured):
    model = u.factorize_peak_bytes(kind, n, distinct) / MIB
    assert model == pytest.approx(measured, rel=0.07)  # worst probe: +6% (over-predicts)


def test_the_val_v3_failures_are_a_table_residency_effect_not_a_fixed_offset():
    """12k random strings in 1M rows: 63 MiB, not the 26 MiB of the sequential-key curve."""
    random_keys = u.factorize_peak_bytes("text", 1_000_000, 12_000, scatter=1.0)
    clustered = u.factorize_peak_bytes("text", 1_000_000, 12_000, scatter=0.05)
    assert random_keys / MIB > 55 and clustered / MIB < 30
    # no fixed offset: the extra bytes follow the presized table (cap at ~1M entries), not a constant
    extra = [
        u.factorize_peak_bytes("text", n, 12_000) - u.factorize_peak_bytes("text", n, 12_000, 0.0)
        for n in (300_000, 1_000_000, 4_000_000)
    ]
    assert extra[1] == pytest.approx(extra[2], rel=0.05)  # saturated once n reaches the presize cap
    assert extra[0] < extra[1] / 2  # smaller tables below the cap


def test_factorize_peak_is_monotone_in_distinct_count_and_in_scatter():
    for kind in ("text", "numeric"):
        peaks = [u.factorize_peak_bytes(kind, 2_000_000, d) for d in (10, 1e3, 1e4, 1e5, 1e6, 2e6)]
        assert peaks == sorted(peaks)
        assert u.factorize_peak_bytes(kind, 2_000_000, 5e4, 0.1) <= u.factorize_peak_bytes(
            kind, 2_000_000, 5e4, 1.0
        )


def _random_strings(count, rng, width=12):
    chars = np.array(list(string.ascii_lowercase))
    return np.array(
        ["".join(r) for r in chars[rng.integers(0, 26, size=(count, width))]], dtype=object
    )


def test_hash_scatter_tells_random_from_clustered_keys():
    rng = np.random.default_rng(3)
    u_count, n = 12_000, 100_000
    rows = rng.integers(0, u_count, n)
    seq = pd.Series(np.array([f"value_{i:09d}" for i in range(u_count)], dtype=object)[rows])
    rnd = pd.Series(_random_strings(u_count, rng)[rows])
    assert (
        stats.hash_scatter(seq, text=True).value < 0.15
    )  # X31 puts sequential keys in a few pages
    assert stats.hash_scatter(rnd, text=True).value > 0.9
    dense = pd.Series(rng.integers(0, 5_000, n))
    ids = pd.Series(rng.choice(2**62, 5_000)[rng.integers(0, 5_000, n)])
    assert (
        0.5 < stats.hash_scatter(dense, text=False).value < 0.9
    )  # dense ints: ~0.7 (replica, pb7)
    assert stats.hash_scatter(ids, text=False).value > 0.9
    few = pd.Series(rng.integers(0, 50, n))
    assert stats.hash_scatter(few, text=False).value == 1.0  # tiny tables: assume the safe side


def test_hash_scatter_never_changes_the_column():
    rng = np.random.default_rng(4)
    col = pd.Series(_random_strings(5_000, rng)[rng.integers(0, 5_000, 50_000)])
    before = col.copy(deep=True)
    stats.hash_scatter(col, text=True)
    pd.testing.assert_series_equal(col, before)


# -- merge: the sort-based path hashes the UNION of the keys of both sides ----------------------------
def _merge_features(nl, nr):
    return {"n_left": nl, "n_right": nr, "bytes_left": 68.8 * nl, "bytes_right": 32.0 * nr,
            "moved_left": 68.8 * nl, "moved_right": 32.0 * nr, "how": "inner"}  # fmt: skip


@pytest.mark.parametrize(
    ("nl", "nr", "m", "right_distinct", "overlap", "measured"),
    [  # probes pc3 (unique left keys, non-unique right keys): measured MiB of the full merge
        (1_000_000, 350_000, 87_504, 58_334, 0.25, 71.4),
        (1_000_000, 100_000, 25_002, 16_667, 0.25, 48.8),
        (1_000_000, 1_000_000, 900_000, 166_667, 0.9, 93.2),
        (2_000_000, 700_000, 175_002, 116_667, 0.25, 134.9),
        (3_000_000, 1_050_000, 262_500, 175_000, 0.25, 181.1),  # pc2, 3M
    ],
)
def test_nonunique_right_merge_model_matches_the_probes(
    nl, nr, m, right_distinct, overlap, measured
):
    model = (
        MergeModel.ram_at(
            _merge_features(nl, nr), m, left_elided=False, right_distinct=right_distinct,
            right_unique=False, left_distinct=nl, overlap=overlap,
        )
        / MIB
    )  # fmt: skip
    assert model == pytest.approx(measured, rel=0.20)  # probe grid: measured/formula 0.83-1.17


def test_merge_charges_the_left_keys_table_only_for_the_sort_based_path():
    f = _merge_features(3_000_000, 1_050_000)
    unique = MergeModel.ram_at(f, 262_500, right_distinct=175_000, right_unique=True)
    nonunique = MergeModel.ram_at(
        f,
        262_500,
        right_distinct=175_000,
        right_unique=False,
        left_distinct=3_000_000,
        overlap=0.25,
    )
    assert nonunique > 1.5 * unique  # val-v3 overlap25_fanout6 at 3M: measured 181 MiB vs 90 before


# -- groupby: two keys ---------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("card", "groups", "measured"),  # probes pb8: n = 1M, int + random-string key, MiB
    [(60, 3_600, 55.9), (800, 505_945, 80.4), (6_000, 986_253, 101.5), (40_000, 999_705, 101.9)],
)
def test_two_key_groupby_range_brackets_the_probes(card, groups, measured):
    n = 1_000_000
    f = {"n_rows": n, "key_kinds": ["numeric", "text"]}
    frac = [(card / n,) * 3, (card / n,) * 3]
    g = groups / n
    low = GroupByModel.ram_at(f, [x[0] for x in frac], g, 1, 0, [0.72, 0.0]) / MIB
    mid = GroupByModel.ram_at(f, [x[1] for x in frac], g, 1, 1, [0.72, 1.0]) / MIB
    high = GroupByModel.ram_at(f, [x[2] for x in frac], g, 1, 2, [1.0, 1.0]) / MIB
    assert low <= measured * 1.05 and measured <= high * 1.05
    assert mid == pytest.approx(measured, rel=0.25)
