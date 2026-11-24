"""Conservative models for v4 reset of Series/frame output operations."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.state import Inspection


class SampleModel(OperationModel):
    """Peak RAM of a row take: selected bytes, or the full frame for sampling with replacement."""

    name = "sample"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "sample"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        frame = u.frame(state, op.receiver)
        replace = op.kwargs.get("replace", False)
        n = op.kwargs.get("n")
        frac = op.kwargs.get("frac")
        if not isinstance(n, (int, float)) and not isinstance(frac, (int, float)):
            raise NoEstimateError("sample n/frac is not statically known")
        selected = int(n) if isinstance(n, (int, float)) else int(frame.shape[0] * float(frac))
        return {
            "n_rows": frame.shape[0],
            "selected": max(0, min(selected, frame.shape[0] if not replace else selected)),
            "moved_bytes": frame.moved_bytes,
            "replace": bool(replace),
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n = float(features["n_rows"])
        selected = float(features["selected"])
        moved = float(features["moved_bytes"])
        peak = moved * (selected / n if n else 0.0)
        if features["replace"]:
            peak = moved * max(1.0, selected / n)
        return u.build(
            (0.85 * peak, peak, 1.15 * peak),
            u.time_band_for_tier(tt.copy_s(peak), tier),
            0.65,
            tier,
            ["selected-row block take", "replacement may select every row repeatedly"],
        )
