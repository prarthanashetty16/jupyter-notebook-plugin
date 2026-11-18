"""Re-estimate a cell on a virtual modification with the FROZEN operation models.

Both the "before" and the "after" figures come from the same code path (the operation's model at
Tier 0 on a virtual ``Inspection``), so their difference is the model's own opinion of the change
and not a mix of tiers. Nothing is executed and the namespace is never touched. The modified cell
also pays for what it materialises (``VirtualChange.temp_bytes``), added to every bound.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from nexus.analyzer import DetectedOp
from nexus.models.base import Estimate, NoEstimateError
from nexus.models.builtin import load_builtin_models
from nexus.registry import ModelRegistry, default_registry
from nexus.state import Inspection
from nexus.suggestions.base import VirtualChange

log = logging.getLogger("nexus")


def virtual_inspection(state: Inspection, change: VirtualChange) -> Inspection:
    return Inspection(
        variables={**state.variables, **change.frames},
        files={**state.files, **change.files},
        skipped=state.skipped,
    )


def _tier0(op: DetectedOp, state: Inspection, registry: ModelRegistry) -> Estimate | None:
    for model in registry.find(op):
        try:
            return model.estimate(model.features(op, state), 0)
        except NoEstimateError:
            continue
        except Exception:
            log.debug("nexus: re-estimate failed for %s", model.name, exc_info=True)
    return None


def reestimate(
    op: DetectedOp,
    state: Inspection,
    change: VirtualChange,
    registry: ModelRegistry | None = None,
) -> tuple[Estimate, Estimate] | None:
    """(before, after) Tier 0 estimates of ``op``, or None if the frozen model has no estimate."""
    if registry is None:
        load_builtin_models()
        registry = default_registry
    before = _tier0(op, state, registry)
    after = _tier0(op, virtual_inspection(state, change), registry)
    if before is None or after is None:
        return None
    extra, trans = change.temp_bytes, change.transient
    after = replace(
        after,
        ram_low=after.ram_low + extra,
        ram_expected=after.ram_expected + extra,
        ram_high=after.ram_high + extra + trans,
        note=(after.note or "")
        + ("; " if after.note else "")
        + "re-estimated at Tier 0 on a virtual state",
    )
    return before, after
