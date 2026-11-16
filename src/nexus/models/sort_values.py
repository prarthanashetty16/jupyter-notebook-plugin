"""Tier 0 model for ``DataFrame.sort_values``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class SortValuesModel(OperationModel):
    """Peak RAM and time of ``df.sort_values(by)``.

    Hypothesised cost drivers (unverified): pandas computes an int64 sort indexer (8 bytes/row,
    more for multi-key lexsort) and then takes every column through it, so the result is a full
    copy of the frame: peak RAM ~ input bytes + a few int64 arrays per row. Time ~ n*log2(n)
    comparisons (text comparisons are much slower than numeric) plus the copy.
    """

    name = "sort_values"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "sort_values"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        keys = u.literal_columns(u.arg_or_kwarg(op, 0, "by"))
        n_keys, n_text = u.text_count(df, keys)
        return {
            "n_rows": df.shape[0],
            "n_keys": n_keys if keys else 1,
            "n_text_keys": n_text if keys else 0,
            "input_bytes": df.nbytes,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, k, kt, size = (features[x] for x in ("n_rows", "n_keys", "n_text_keys", "input_bytes"))
        ram = (size + 8 * n, size + 16 * n * k, 1.5 * size + 40 * n * k)
        cmp_s = (k - kt) * u.NUM_CMP_S + kt * u.TEXT_CMP_S
        seconds = n * u.log2n(n) * cmp_s + size / u.COPY_BPS
        return u.build(
            ram,
            u.time_band(seconds),
            0.6,
            tier,
            [
                "int64 sort indexer per key",
                "full copy of all columns through the indexer",
                f"{kt} text key column(s): slow comparisons" if kt else "numeric keys only",
            ],
        )
