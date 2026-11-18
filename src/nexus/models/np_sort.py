"""Tier 0 model for ``numpy.sort``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class NpSortModel(OperationModel):
    """Peak RAM and time of ``np.sort(a)``.

    Hypothesised cost drivers (unverified): ``np.sort`` copies the array and sorts the copy in
    place, so peak RAM ~ the array's nbytes; time ~ n*log2(n) comparisons. Input order (already
    sorted data is much faster) is invisible at Tier 0, hence a wide time band.
    """

    name = "np_sort"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "numpy.sort"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if len(op.variables) < 1:
            raise NoEstimateError("need a known array")
        a = u.array(state, op.variables[0])
        size = 1
        for dim in a.shape:
            size *= dim
        return {"nbytes": a.nbytes, "size": size}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        nbytes = features["nbytes"]
        seconds = tt.np_sort(features)
        return u.build(
            (0.9 * nbytes, nbytes, 1.3 * nbytes),
            (seconds * 0.1, seconds, seconds * 4),
            0.7,
            tier,
            ["one full copy of the array, sorted in place", "n*log2(n) comparisons"],
        )
