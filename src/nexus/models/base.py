"""Plug-in interface for operation cost models.

Adding an operation = one new file with an ``OperationModel`` subclass registered via
``@register_model`` (see ``nexus.registry``). The class docstring must explain the model's
cost drivers (what the peak RAM and time actually depend on) and each claim must be verified
by the benchmark.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from nexus.analyzer import DetectedOp
from nexus.state import Inspection


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

    def __post_init__(self) -> None:
        if not 0 <= self.ram_low <= self.ram_expected <= self.ram_high:
            raise ValueError("ram must satisfy 0 <= low <= expected <= high")
        if not 0 <= self.time_low <= self.time_expected <= self.time_high:
            raise ValueError("time must satisfy 0 <= low <= expected <= high")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if self.tier < 0:
            raise ValueError("tier must be >= 0")


class OperationModel(ABC):
    """Cost model for one kind of operation."""

    name: ClassVar[str]

    @abstractmethod
    def matches(self, op: DetectedOp) -> bool:
        """True if this model can estimate ``op`` (syntactic check only)."""

    @abstractmethod
    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        """Numeric/categorical features of ``op`` given the live state; also logged."""

    @abstractmethod
    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        """Estimate peak RAM and time from ``features`` at the given tier."""
