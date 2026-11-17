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


def time_band(expected: float) -> tuple[float, float, float]:
    return (expected * RAM_BAND_TIME[0], expected, expected * RAM_BAND_TIME[1])


def require_tier0(tier: int) -> None:
    if tier != 0:
        raise NoEstimateError(f"tier {tier} not implemented for this model")
