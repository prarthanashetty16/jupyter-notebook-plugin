"""Per-cell pipeline: analyze -> inspect state -> run matching models."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from nexus import cellframes, dryrun, guard, ranges, stats, timecal, upperbound
from nexus.analyzer import DetectedOp, analyze_cell
from nexus.controller import Controller
from nexus.failsafe import Deadline
from nexus.models.base import Estimate, NoEstimateError, Tier1Context
from nexus.models.builtin import load_builtin_models
from nexus.registry import ModelRegistry, default_registry
from nexus.state import Inspection, ResourceProbe, ResourceSnapshot, StateInspector, candidate_paths

log = logging.getLogger("nexus")


@dataclass(frozen=True, kw_only=True)
class OpEstimate:
    op: DetectedOp
    model: str
    estimate: Estimate
    features: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class CellReport:
    ops: list[DetectedOp] = field(default_factory=list)
    inspection: Inspection = field(default_factory=Inspection)
    estimates: list[OpEstimate] = field(default_factory=list)
    resources: ResourceSnapshot | None = None
    elapsed_s: float = 0.0
    source: str = ""  # the analysed cell (the cell-level peak model needs its statements)


def _stats_summary(extra: dict[str, Any]) -> dict[str, Any]:
    return dict(extra.get("tier1", {}))


class Pipeline:
    """Runs one cell's source through analysis, state inspection and the model registry."""

    def __init__(
        self,
        registry: ModelRegistry | None = None,
        inspector: StateInspector | None = None,
        probe: ResourceProbe | None = None,
        tier: int = 0,
        tier1_budget_s: float = 0.2,
        tier2_budget_s: float = 40.0,
        tier2_escalate: str = "controller",
        controller: Controller | None = None,
    ) -> None:
        if registry is None:
            load_builtin_models()
            registry = default_registry
        self.registry = registry
        self._inspector = inspector or StateInspector()
        self._probe = probe or ResourceProbe()
        self._tier = tier
        self._tier1_budget_s = tier1_budget_s
        self._tier2_budget_s = tier2_budget_s
        self._tier2_escalate = (
            tier2_escalate  # "controller" (pre-registered rules) or "always" (Phase 4c evaluation)
        )
        self._controller = controller or Controller()

    def run(  # noqa: C901
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
        dry: dict[str, Any] = {}  # one dry run per cell, shared by its ops
        cb = cellframes.cell_bindings(source, ops)
        produced: dict[int, Any] = {}  # id(op) -> predicted result descriptor (nexus.cellframes)
        for op in ops:
            if deadline is not None:
                deadline.check()
            state, cell_frame = cellframes.state_for(op, cb, produced, inspection)
            if state is None:  # touches a frame made earlier in this cell whose shape is unknown
                continue
            for model in self.registry.find(op):
                try:
                    if self._tier > 2:
                        raise NoEstimateError(f"tier {self._tier} not implemented")
                    features = model.features(op, state)
                    tier0_features = features
                    tier0 = None
                    used = 0
                    if cell_frame:  # statistics would read the stale kernel object: Tier 0 only
                        features = {
                            **features,
                            "tier1": {"used": False, "reason": cellframes.CELL_FRAME_REASON},
                        }
                    elif self._tier >= 1:
                        features, used = self._tier1(model, op, features, namespace, source, t0)
                    estimate = None
                    if used >= 1:
                        tier0 = self._tier0_estimate(model, tier0_features)
                        try:
                            estimate = model.estimate(features, used)
                            problem = guard.tier1_problem(estimate, tier0)
                        except NoEstimateError:
                            raise
                        except Exception as exc:
                            problem = f"estimate failed ({type(exc).__name__})"
                        if problem is None:
                            # risk v2 (C3) WARNs on this for read_csv / merge; the display keeps policy B
                            features = {**features, "tier1_own_ram_high": int(estimate.ram_high)}
                            estimate = ranges.apply(model.name, estimate, tier0)
                            estimate = upperbound.apply(model.name, estimate)
                        elif tier0 is not None:  # keep Tier 0 and say why
                            estimate = replace(tier0, note=f"Tier 1 rejected: {problem}")
                            features = {**features, "tier1": {"used": False, "reason": problem}}
                            log.debug("nexus: tier 1 rejected for %s: %s", model.name, problem)
                        else:
                            raise NoEstimateError(f"tier 1 rejected ({problem}) and no Tier 0")
                    else:
                        estimate = tier0 = model.estimate(features, used)
                    if isinstance(estimate, Estimate):  # time: residual + conformal range
                        estimate = timecal.calibrate(model.name, estimate)
                    if self._tier >= 2 and isinstance(estimate, Estimate) and not cell_frame:
                        estimate, features = self._tier2(
                            op, estimate, features, source, namespace, dry, tier0, inspection
                        )
                    if not isinstance(estimate, Estimate):
                        raise TypeError(f"{model.name} returned {type(estimate).__name__}")
                except NoEstimateError as why:
                    log.debug("nexus: no estimate from %s for %s: %s", model.name, op.name, why)
                    continue
                except Exception:
                    log.debug("nexus: model %s failed on %s", model.name, op.name, exc_info=True)
                    continue
                estimates.append(
                    OpEstimate(op=op, model=model.name, estimate=estimate, features=features)
                )
                cellframes.record(op, model.name, features, estimate, state, cb, produced)
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
            source=source,
        )

    def _tier2(
        self, op: DetectedOp, estimate: Estimate, features: dict[str, Any], source: str,
        namespace: Mapping[str, Any], dry: dict[str, Any], tier0: Estimate | None, inspection: Inspection,
    ) -> tuple[Estimate, dict[str, Any]]:  # fmt: skip
        """Refine with the adaptive controller (or, for the Phase 4c evaluation, always); never raises."""
        try:
            if self._tier2_escalate != "always":
                names = list(dict.fromkeys(op.variables))
                descs = [inspection.variables[n] for n in names if n in inspection.variables]
                size = float(
                    sum(d.nbytes for d in descs) + sum(f.nbytes for f in inspection.files.values())
                )
                rows = (
                    max((float(d.shape[0]) for d in descs if getattr(d, "shape", ())), default=0.0)
                    or None
                )
                refined, info = self._controller.refine(
                    op.name,
                    estimate,
                    tier0,
                    features,
                    source,
                    namespace,
                    self._available_bytes(),
                    size,
                    rows,
                )
                return refined, {**features, "controller": info}
            if "verdict" not in dry:
                dry["verdict"] = dryrun.analyze_safety(source, namespace)
            verdict = dry["verdict"]
            if (
                not verdict.safe
                or verdict.recipe is None
                or not dryrun.matching_op(verdict.recipe.kind, op.name)
            ):
                return estimate, features
            if "result" not in dry:
                dry["result"] = dryrun.run_dryrun(source, namespace, budget_s=self._tier2_budget_s)
            result = dry["result"]
            refined = dryrun.tier2_estimate(result, estimate)
            return (refined or estimate), {**features, "tier2": result.diagnostics()}
        except Exception:
            log.debug("nexus: tier 2 failed", exc_info=True)
            return estimate, features

    def _available_bytes(self) -> float | None:
        try:
            snap = self._probe.snapshot()
            return float(snap.effective_available)
        except Exception:
            return None

    @staticmethod
    def _tier0_estimate(model: Any, features: dict[str, Any]) -> Estimate | None:
        """The Tier 0 estimate of the same op (its ``high`` can serve as a ceiling); None if absent."""
        try:
            return model.estimate(features, 0)
        except Exception:
            return None

    def _tier1(
        self,
        model: Any,
        op: DetectedOp,
        features: dict[str, Any],
        namespace: Mapping[str, Any],
        source: str,
        t0: float,
    ) -> tuple[dict[str, Any], int]:
        """Add Tier 1 statistics to ``features``; (features, tier actually used).

        Any failure (no statistics for this model, too small a sample, budget exhausted, an
        unexpected exception) keeps the Tier 0 features: Tier 1 may only refine, never break.
        """
        left = self._tier1_budget_s - (time.perf_counter() - t0)
        started = time.perf_counter()
        try:
            if left <= 0:
                raise TimeoutError("tier 1 budget used up by earlier stages")
            ctx = Tier1Context(namespace, source, Deadline(left))
            with stats.cell_seed(source):
                extra = model.tier1_features(op, features, ctx)
        except NoEstimateError as why:
            log.debug("nexus: tier 1 unavailable for %s: %s", model.name, why)
            return {**features, "tier1": {"used": False, "reason": str(why)}}, 0
        except TimeoutError:
            return {**features, "tier1": {"used": False, "reason": "time budget"}}, 0
        except Exception as exc:
            log.debug("nexus: tier 1 failed for %s", model.name, exc_info=True)
            return {**features, "tier1": {"used": False, "reason": type(exc).__name__}}, 0
        if not extra:
            return {**features, "tier1": {"used": False, "reason": "no statistics"}}, 0
        info = {**_stats_summary(extra), "used": True, "stats_s": time.perf_counter() - started}
        return {**features, **extra, "tier1": info}, 1
