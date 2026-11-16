"""Tier 0 model for ``pandas.concat`` (row-wise)."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class ConcatModel(OperationModel):
    """Peak RAM and time of ``pd.concat([a, b, ...])``.

    Hypothesised cost drivers (unverified): the result is a new frame holding all rows, so peak
    RAM ~ the sum of the input bytes (inputs stay alive); dtype unification (e.g. int + float,
    category mismatch) can add temporaries. Time ~ one copy of all bytes. Row-wise concat only:
    ``axis`` other than 0 yields no estimate.
    """

    name = "concat"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "pandas.concat"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if op.kwargs.get("axis", 0) not in (0, "index"):
            raise NoEstimateError("only axis=0 is modelled")
        if len(op.variables) < 2:
            raise NoEstimateError("need at least two known frames")
        frames = [u.frame(state, v) for v in op.variables]
        return {"total_bytes": sum(f.nbytes for f in frames), "n_frames": len(frames)}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        total = features["total_bytes"]
        return u.build(
            (0.9 * total, total, 1.6 * total),
            u.time_band(total / u.COPY_BPS),
            0.7,
            tier,
            ["new frame holding every input row", "possible dtype-unification temporaries"],
        )
