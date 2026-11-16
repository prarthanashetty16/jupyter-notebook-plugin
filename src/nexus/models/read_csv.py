"""Tier 0 model for ``pandas.read_csv``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection, candidate_paths

EXPANSION_FACTORS = (0.5, 1.5, 5.0)  # in-memory bytes per CSV byte; depends on dtype mix
PARSE_BPS = 80e6  # CSV bytes parsed per second


@register_model
class ReadCsvModel(OperationModel):
    """Peak RAM and time of ``pd.read_csv("path")`` from the file size on disk.

    Hypothesised cost drivers (unverified): the parsed frame is the dominant allocation. Its
    size relative to the file depends on the dtype mix (numbers are about as big in memory as
    in text; short strings carry ~50 bytes of Python object overhead each) and on string
    cardinality (pandas reuses repeated string objects). Tier 0 sees only the file size, so it
    spans 0.5x..5x of it. Time ~ file size / parse throughput.
    """

    name = "read_csv"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "pandas.read_csv"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        paths = [p for p in candidate_paths(op) if p in state.files]
        if not paths:
            raise NoEstimateError("file path unknown or not found on disk")
        return {"file_bytes": state.files[paths[0]].nbytes}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        size = features["file_bytes"]
        lo, mid, hi = (f * size for f in EXPANSION_FACTORS)
        return u.build(
            (lo, mid, hi),
            u.time_band(size / PARSE_BPS),
            0.4,
            tier,
            ["parsed frame size vs file size depends on unknown dtypes/cardinality"],
        )
