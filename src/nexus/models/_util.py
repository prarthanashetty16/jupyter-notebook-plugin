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
