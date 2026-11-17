"""Shared helpers and first-draft constants for the Tier 0 models.

Hardware throughputs come from ``machine()`` (per-machine microbenchmarks, ``nexus.machine``).
The remaining constants (priors, bands, expansion factors) are initial guesses chosen BEFORE any
benchmark data was seen; none is calibrated (Phase 6).
RAM figures are *incremental peak*: extra resident memory above what was resident before the
operation ran (the inputs themselves are not counted).
"""

from __future__ import annotations

import math
from typing import Any

from nexus.analyzer import DetectedOp, Expr
from nexus.machine import machine  # noqa: F401  (re-exported for models)
from nexus.models.base import Estimate, NoEstimateError
from nexus.state import ArrayDescriptor, FrameDescriptor, Inspection

RAM_BAND_TIME = (0.25, 4.0)  # default low/high multipliers around the expected time

TEXT_DTYPES = ("object", "str", "string")


def is_text(dtype: str) -> bool:
    return dtype in TEXT_DTYPES or dtype.startswith("string")


def can_hold_null(dtype: str) -> bool:
    """False for NumPy int/uint/bool columns, which cannot contain a null; True otherwise."""
    return not (dtype.startswith(("int", "uint")) or dtype == "bool")


def frame(state: Inspection, name: str | None) -> FrameDescriptor:
    desc = state.variables.get(name) if name else None
    if not isinstance(desc, FrameDescriptor):
        raise NoEstimateError(f"{name!r} is not a known DataFrame")
    return desc


def array(state: Inspection, name: str | None) -> ArrayDescriptor:
    desc = state.variables.get(name) if name else None
    if not isinstance(desc, ArrayDescriptor):
        raise NoEstimateError(f"{name!r} is not a known ndarray")
    return desc


def literal_columns(value: Any) -> list[str] | None:
    """Column names from a literal str / list of str; None if absent or not a literal."""
    if isinstance(value, Expr) or value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def arg_or_kwarg(op: DetectedOp, index: int, name: str) -> Any:
    if name in op.kwargs:
        return op.kwargs[name]
    return op.args[index] if len(op.args) > index else None


def text_count(df: FrameDescriptor, columns: list[str] | None) -> tuple[int, int]:
    """(number of key columns, how many of them are text) for ``columns`` (None = all)."""
    if columns is None:
        k = df.shape[1]
        return k, df.text_columns
    return len(columns), sum(1 for c in columns if is_text(df.dtypes.get(c, "")))


# -- khash tables (pandas hash tables: factorize, duplicated, merge) --------------------------
KHASH_MAX_LOAD = 0.77  # khash grows a table when it is more than 77% full
KHASH_BUCKET_BYTES = 16  # 8-byte key + 8-byte value slot of the factorize hash tables
KHASH_FLAG_BYTES = 0.25  # 2 flag bits per bucket
KHASH_RESIZE_OVERLAP = 1.5  # old and new table alive together while growing (upper bound)


INT64_MAX = 2**63


def group_ids_overflow(k: int, distinct_per_key: float) -> bool:
    """True if fusing ``k`` key columns into one int64 id needs the compress step."""
    return k > 1 and (max(distinct_per_key, 1.0) + 1) ** k >= INT64_MAX


def khash_table_bytes(distinct: float, *, key_only: bool = False) -> float:
    """Bytes of a khash table holding ``distinct`` entries (power-of-two bucket count)."""
    if distinct <= 0:
        return 0.0
    buckets = 2 ** math.ceil(math.log2(max(distinct / KHASH_MAX_LOAD, 4)))
    slot = KHASH_BUCKET_BYTES / 2 if key_only else KHASH_BUCKET_BYTES
    return buckets * (slot + KHASH_FLAG_BYTES)


SIZE_HINT_LIMIT = (1 << 20) + 7  # pandas caps the initial hash-table size hint at this many entries


def khash_presized_bytes(distinct: float, size_hint: float, *, key_only: bool = False) -> float:
    """Bytes of a pandas hash table built with ``size_hint`` that ends up holding ``distinct`` keys.

    The table is allocated for ``min(size_hint, SIZE_HINT_LIMIT)`` entries up front, whatever the
    real distinct count; only if more distinct keys arrive does it grow, with the old and the new
    table alive together during the resize (``KHASH_RESIZE_OVERLAP``).
    """
    presized = min(size_hint, SIZE_HINT_LIMIT)
    grows = distinct > presized
    size = khash_table_bytes(max(distinct, presized), key_only=key_only)
    return size * (KHASH_RESIZE_OVERLAP if grows else 1.0)


# -- factorizing one key column (``astype("category")``, one ``groupby`` key) ------------------
# Derived from the pandas hash tables and validated with isolated probes (docs/benchmarks/
# val-v3-diagnosis/probes/pb1..pb10). The peak is the larger of two phases:
#
#     factorize:  FACTORIZE_BASE * n  +  resident pages of the hash table  +  UNIQUE_BYTES * distinct
#     copy:       FACTORIZE_FLOOR * n          (numeric keys only: 2 int64 arrays, independent of U)
#
# * The table is allocated for ``min(n, 2**20 + 7)`` entries up front (``hash_buckets``) and grows
#   only when the distinct count exceeds its 77% load limit. Allocated pages are NOT resident until
#   a key lands in them: ``distinct`` keys hashed to random buckets touch a fraction
#   ``1 - exp(-distinct / pages)`` of each array (``table_touch``). Phase 4a measured its curve on
#   sequential keys (``value_000000123``, ints 0..U-1) whose hashes cluster into few pages, which
#   hid this term; random strings and random ids touch the whole table (+38 MiB at 2M rows, U = 12k).
#   Clustered keys fill pages more slowly as U grows (``CLUSTER_FILL``, from three dense-int probes).
# * ``TABLE_STRIDES``: bytes per bucket of the arrays whose pages get touched: text tables
#   (``StringHashTable``) 16 + 8, numeric ones 8 + 8 (plus 2 flag bits per bucket, always resident).
# * A table that had to grow was rehashed completely: fully resident.
FACTORIZE_BASE = {"text": 24.1, "numeric": 8.65}  # B/row (codes, vectors, remap)
FACTORIZE_FLOOR = {"text": 0.0, "numeric": 16.3}  # B/row of the copy phase (numeric keys)
UNIQUE_BYTES = {"text": 8.0, "numeric": 16.0}  # B per distinct value (uniques; numeric: + sort)
TABLE_STRIDES = {"text": (16, 8), "numeric": (8, 8)}
PAGE_BYTES = 4096
CLUSTER_FILL = 0.1  # clustered keys fill a table as 1 - exp(-U / (CLUSTER_FILL * buckets))


def hash_buckets(entries: float) -> int:
    """khash bucket count for ``entries`` keys (power of two, 77% maximum load)."""
    return int(2 ** math.ceil(math.log2(max(entries / KHASH_MAX_LOAD, 4))))


def table_touch(distinct: float, buckets: int, stride: int) -> float:
    """Expected share of an array's pages touched by ``distinct`` keys hashed to random buckets."""
    pages = max(buckets * stride / PAGE_BYTES, 1.0)
    return 1.0 - math.exp(-max(distinct, 0.0) / pages)


def factorize_parts(
    kind: str, n: float, distinct: float, scatter: float = 1.0
) -> tuple[float, float]:
    """(factorize-phase peak, copy-phase peak) bytes of factorizing a ``kind`` column.

    ``scatter`` in [0, 1] is how uniformly the keys hash over the table (1: random keys, the usual
    case; ~0.05: sequential strings; ~0.7: dense integers). A table that grew is fully resident.
    """
    distinct = min(max(distinct, 0.0), n)
    presized = hash_buckets(min(n, SIZE_HINT_LIMIT))
    buckets = max(presized, hash_buckets(distinct))
    grown = buckets > presized
    fill = 1.0 - math.exp(-distinct / (CLUSTER_FILL * buckets))
    resident = KHASH_FLAG_BYTES * buckets
    for stride in TABLE_STRIDES[kind]:
        random_share = table_touch(distinct, buckets, stride)
        # clustered keys still occupy at least ``distinct`` slots: the floor is the load factor
        share = (
            1.0
            if grown
            else max(scatter * random_share + (1.0 - scatter) * fill, distinct / buckets)
        )
        resident += min(share, 1.0) * buckets * stride
    factorize = FACTORIZE_BASE[kind] * n + resident + UNIQUE_BYTES[kind] * distinct
    return factorize, FACTORIZE_FLOOR[kind] * n


def factorize_peak_bytes(kind: str, n: float, distinct: float, scatter: float = 1.0) -> float:
    """Peak bytes of factorizing a ``kind`` ("text" / "numeric") column of ``n`` rows."""
    return max(factorize_parts(kind, n, distinct, scatter))


def factorize_peak_per_row(kind: str, distinct_fraction: float, n: float = 2_000_000) -> float:
    """``factorize_peak_bytes`` per row at a distinct fraction (random keys)."""
    return factorize_peak_bytes(kind, n, distinct_fraction * n) / n


def log2n(n: float) -> float:
    return math.log2(max(n, 2.0))


def build(
    ram: tuple[float, float, float],
    time: tuple[float, float, float],
    confidence: float,
    tier: int,
    drivers: list[str],
) -> Estimate:
    r = sorted(max(0.0, x) for x in ram)
    t = sorted(max(0.0, x) for x in time)
    return Estimate(
        ram_low=int(r[0]),
        ram_expected=int(r[1]),
        ram_high=int(r[2]),
        time_low=t[0],
        time_expected=t[1],
        time_high=t[2],
        confidence=confidence,
        tier=tier,
        drivers=drivers,
    )


def time_band_for_tier(expected: float, tier: int) -> tuple[float, float, float]:
    """Time range at a tier. Statistics do NOT narrow it.

    A Tier 1 band of (0.5x, 2x) was tried first, chosen a priori from the ~40% session-to-session
    variance of the same point; on the development split it cut time coverage from 94% to 69% and
    put 13% of the actuals above ``high``, because the first-draft time formulas are biased by
    0.4x-2.8x (more than the variance). Until the time models are calibrated (Phase 6) the Tier 0
    band (0.25x .. 4x, far wider than the measured variance) stays at every tier.
    """
    del tier
    return time_band(expected)


def time_band(expected: float) -> tuple[float, float, float]:
    return (expected * RAM_BAND_TIME[0], expected, expected * RAM_BAND_TIME[1])


def require_tier0(tier: int) -> None:
    if tier != 0:
        raise NoEstimateError(f"tier {tier} not implemented for this model")


def require_tier(tier: int, highest: int = 1) -> None:
    """Models answer at Tier 0 and (with statistics) Tier 1."""
    if not 0 <= tier <= highest:
        raise NoEstimateError(f"tier {tier} not implemented for this model")
