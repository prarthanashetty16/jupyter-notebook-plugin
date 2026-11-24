"""Tier 0 model for ``DataFrame.reset_index``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class ResetIndexModel(OperationModel):
    """Peak RAM for inserting or dropping a frame index.

    ``drop=True`` returns a shallow copy and adds no measured copy. ``drop=False`` inserts
    the index as a column: a RangeIndex needs 8 bytes per row for the materialized int64 column;
    an existing materialized index column reuses or copies less. Probe
    ``p8_reset_index.out`` is 122.3 MiB RangeIndex and 61.25 MiB materialized index.
    """

    name = "reset_index"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "reset_index"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        frame = u.frame(state, op.receiver)
        drop = op.kwargs.get("drop", False)
        if drop not in (True, False):
            raise NoEstimateError("reset_index drop is not statically known")
        return {
            "n_rows": frame.shape[0],
            "moved_bytes": frame.moved_bytes,
            "index_nbytes": frame.index_nbytes,
            "index_kind": frame.index_kind,
            "drop": drop,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n = float(features["n_rows"])
        moved = float(features["moved_bytes"])
        if features["drop"]:
            peak = moved * 0.01
        elif features["index_kind"] == "range":
            peak = moved + 8.0 * n
        else:
            peak = moved + float(features["index_nbytes"])
        ram = (0.85 * peak, peak, 1.15 * peak)
        seconds = tt.copy_s(peak)
        return u.build(
            ram,
            u.time_band_for_tier(seconds, tier),
            0.75,
            tier,
            [
                "frame copy or shallow copy",
                "drop=False: index column materialization",
            ],
        )
