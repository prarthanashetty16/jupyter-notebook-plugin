"""Plug-in interface for operation cost models.

Adding an operation = one new file with an ``OperationModel`` subclass registered via
``@register_model`` (see ``nexus.registry``). The class docstring must explain the model's
cost drivers (what the peak RAM and time actually depend on) and each claim must be verified
by the benchmark.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from nexus.analyzer import DetectedOp
from nexus.failsafe import Deadline
from nexus.state import Inspection


class NoEstimateError(Exception):
    """A model cannot responsibly estimate this op (unknown inputs, unsupported tier...)."""


@dataclass(frozen=True, kw_only=True)
class Estimate:
    """Peak RAM (bytes) and wall time (seconds) as a range, with confidence in [0, 1]."""

    ram_low: int
    ram_expected: int
    ram_high: int
    time_low: float
    time_expected: float
    time_high: float
    confidence: float
    tier: int
    drivers: list[str] = field(default_factory=list)
    note: str | None = None  # e.g. why a Tier 1 estimate was rejected and Tier 0 kept
    diagnostics: dict[str, Any] | None = None  # Tier 2: sample sizes, measurements, fit quality
    # e.g. "uncalibrated machine", "generic time range", "unvalidated pandas version" (nexus.timecal)
    flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.ram_low <= self.ram_expected <= self.ram_high:
            raise ValueError("ram must satisfy 0 <= low <= expected <= high")
        if not 0 <= self.time_low <= self.time_expected <= self.time_high:
            raise ValueError("time must satisfy 0 <= low <= expected <= high")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.tier < 0:
            raise ValueError("tier must be >= 0")


@dataclass
class Tier1Context:
    """What a model may read to compute Tier 1 statistics: live objects (read-only), the cell
    source and the time budget left for this cell. Models must never mutate ``namespace``."""

    namespace: Mapping[str, Any]
    source: str
    deadline: Deadline

    def obj(self, name: str | None) -> Any:
        """The live object bound to ``name`` or NoEstimateError."""
        if name is None or name not in self.namespace:
            raise NoEstimateError(f"{name!r} is not in the namespace")
        return self.namespace[name]


class OperationModel(ABC):
    """Cost model for one kind of operation."""

    name: ClassVar[str]

    @abstractmethod
    def matches(self, op: DetectedOp) -> bool:
        """True if this model can estimate ``op`` (syntactic check only)."""

    @abstractmethod
    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        """Numeric/categorical features of ``op`` given the live state; also logged."""

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Extra features from cheap data statistics, or None to stay at Tier 0.

        Called only at tier >= 1. Must be read-only, respect ``ctx.deadline`` (raising
        TimeoutError is fine) and report its sample sizes and confidence in the returned dict
        under ``"tier1"``. Raising NoEstimateError / returning None means "Tier 0".
        """
        return None

    @abstractmethod
    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        """Estimate peak RAM and time from ``features`` at the given tier."""
