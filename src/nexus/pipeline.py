"""Per-cell pipeline: analyze -> inspect state -> run matching models."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from nexus.analyzer import DetectedOp, analyze_cell
from nexus.failsafe import Deadline
from nexus.models.base import Estimate
from nexus.registry import ModelRegistry, default_registry
from nexus.state import Inspection, ResourceProbe, ResourceSnapshot, StateInspector, candidate_paths

log = logging.getLogger("nexus")


@dataclass(frozen=True, kw_only=True)
class OpEstimate:
    op: DetectedOp
    model: str
    estimate: Estimate


@dataclass(frozen=True, kw_only=True)
class CellReport:
    ops: list[DetectedOp] = field(default_factory=list)
    inspection: Inspection = field(default_factory=Inspection)
    estimates: list[OpEstimate] = field(default_factory=list)
    resources: ResourceSnapshot | None = None
    elapsed_s: float = 0.0


class Pipeline:
    """Runs one cell's source through analysis, state inspection and the model registry."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        inspector: StateInspector | None = None,
        probe: ResourceProbe | None = None,
        tier: int = 0,
    ) -> None:
        self.registry = default_registry if registry is None else registry
        self._inspector = inspector or StateInspector()
        self._probe = probe or ResourceProbe()
        self._tier = tier

    def run(
        self, source: str, namespace: Mapping[str, Any], deadline: Deadline | None = None
    ) -> CellReport:
        """Analyze ``source``. Raises TimeoutError if ``deadline`` expires; a model that raises
        is skipped without affecting the others."""
        t0 = time.perf_counter()
        ops = analyze_cell(source, namespace, deadline)
        if not ops:
            return CellReport(elapsed_s=time.perf_counter() - t0)
        names = [v for op in ops for v in op.variables]
        paths = [p for op in ops for p in candidate_paths(op)]
        inspection = self._inspector.inspect(names, namespace, paths=paths, deadline=deadline)
        estimates: list[OpEstimate] = []
        for op in ops:
            if deadline is not None:
                deadline.check()
            for model in self.registry.find(op):
                try:
                    estimate = model.estimate(model.features(op, inspection), self._tier)
                    if not isinstance(estimate, Estimate):
                        raise TypeError(f"{model.name} returned {type(estimate).__name__}")
                except Exception:
                    log.debug("nexus: model %s failed on %s", model.name, op.name, exc_info=True)
                    continue
                estimates.append(OpEstimate(op=op, model=model.name, estimate=estimate))
        try:
            resources = self._probe.snapshot()
        except Exception:
            log.debug("nexus: resource probe failed", exc_info=True)
            resources = None
        return CellReport(
            ops=ops,
            inspection=inspection,
            estimates=estimates,
            resources=resources,
            elapsed_s=time.perf_counter() - t0,
        )
