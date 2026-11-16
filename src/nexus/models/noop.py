"""Test-only dummy model; never registered in the default registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models.base import Estimate, OperationModel
from nexus.state import Inspection


class NoopModel(OperationModel):
    """Proves the pipeline end to end. Its numbers (1-3x input size) are NOT a real estimate."""

    name = "noop"

    def __init__(self, op_names: Iterable[str] = ("drop_duplicates",)) -> None:
        self._op_names = frozenset(op_names)

    def matches(self, op: DetectedOp) -> bool:
        return op.name in self._op_names

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        input_bytes = sum(state.variables[v].nbytes for v in op.variables if v in state.variables)
        return {"op": op.name, "input_bytes": input_bytes}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        size = int(features["input_bytes"])
        return Estimate(
            ram_low=size,
            ram_expected=2 * size,
            ram_high=3 * size,
            time_low=0.0,
            time_expected=0.0,
            time_high=0.0,
            confidence=0.0,
            tier=tier,
            drivers=["noop test model: RAM = 1-3x input bytes"],
        )
