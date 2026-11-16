"""Tier 0 model for ``DataFrame.groupby`` (the grouping plus a following aggregation)."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

GROUP_FRACTION_PRIOR = 0.1  # distinct groups as a share of rows; unknown at Tier 0
VALUE_COPY_FRACTIONS = (0.0, 0.3, 1.0)  # share of input bytes copied for aggregation


@register_model
class GroupByModel(OperationModel):
    """Peak RAM and time of ``df.groupby(keys)`` followed by an aggregation.

    Hypothesised cost drivers (unverified): the key columns are factorized into int64 codes
    (8 bytes/row/key), text keys add a hash table over the distinct values, aggregation reads
    the value columns (possibly copying some of them) and allocates a result of one row per
    group. The analyzer reports only the ``groupby`` call, not the aggregation after it, so
    Tier 0 does not know which value columns are aggregated and spans 0..100% of the input
    bytes. The number of groups is unknown and assumed to be 10% of the rows.
    """

    name = "groupby"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "groupby"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        keys = u.literal_columns(u.arg_or_kwarg(op, 0, "by"))
        n_keys, n_text = u.text_count(df, keys)
        return {
            "n_rows": df.shape[0],
            "n_cols": df.shape[1],
            "n_keys": n_keys if keys else 1,
            "n_text_keys": n_text if keys else 0,
            "input_bytes": df.nbytes,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, cols, k, kt, size = (
            features[x] for x in ("n_rows", "n_cols", "n_keys", "n_text_keys", "input_bytes")
        )
        codes = 8 * n * k
        result = GROUP_FRACTION_PRIOR * n * 8 * cols
        _, mid_v, hi_v = (f * size for f in VALUE_COPY_FRACTIONS)
        text_tables = 8 * n * kt
        ram = (
            codes,
            codes + text_tables + result + mid_v,
            codes + 2 * text_tables + n * 8 * cols + hi_v,
        )
        seconds = n * ((k - kt) * u.NUM_HASH_S + kt * u.TEXT_HASH_S) + n * cols * 5e-9
        return u.build(
            ram,
            u.time_band(seconds),
            0.4,
            tier,
            [
                "factorize key columns into int64 codes",
                f"{kt} text key column(s) hashed" if kt else "numeric keys only",
                "aggregated columns and group count unknown at Tier 0",
            ],
        )
