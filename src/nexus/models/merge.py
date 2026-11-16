"""Tier 0 model for ``DataFrame.merge`` / ``pandas.merge``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

OUTPUT_ROWS_FACTORS = (0.1, 1.0, 4.0)  # x max(n_left, n_right); join fan-out is unknown


@register_model
class MergeModel(OperationModel):
    """Peak RAM and time of a two-frame merge.

    Hypothesised cost drivers (unverified): pandas factorizes both key columns jointly (hash
    table + int64 codes), builds two int64 row-indexers of the OUTPUT length M, then takes rows
    from both frames into the result, so peak RAM ~ 16*M + M*(row_bytes_left + row_bytes_right)
    plus hashing state. M depends on key overlap and fan-out, which Tier 0 cannot see; it assumes
    M ~ max(n_left, n_right) and spans 0.1x..4x of that. Time ~ hashing both key columns plus
    the output copy.
    """

    name = "merge"

    def matches(self, op: DetectedOp) -> bool:
        return op.name in ("merge", "pandas.merge")

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if len(op.variables) < 2:
            raise NoEstimateError("merge needs two known frames")
        left, right = u.frame(state, op.variables[0]), u.frame(state, op.variables[1])
        keys = u.literal_columns(op.kwargs.get("on"))
        key_text = bool(keys) and any(u.is_text(left.dtypes.get(c, "")) for c in keys)
        return {
            "n_left": left.shape[0],
            "n_right": right.shape[0],
            "bytes_left": left.nbytes,
            "bytes_right": right.nbytes,
            "key_text": key_text,
            "how": op.kwargs.get("how", "inner"),
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        nl, nr = features["n_left"], features["n_right"]
        row_l = features["bytes_left"] / max(nl, 1)
        row_r = features["bytes_right"] / max(nr, 1)
        base = max(nl, nr)
        hashing = 8 * (nl + nr) + 24 * min(nl, nr)  # key codes + hash table over the smaller side

        def ram_at(factor: float) -> float:
            m = factor * base
            return hashing + 16 * m + m * (row_l + row_r)

        hash_s = u.machine().text_hash_s if features["key_text"] else u.machine().num_hash_s
        seconds = (nl + nr) * hash_s + base * (row_l + row_r) / u.machine().copy_bps
        lo, mid, hi = OUTPUT_ROWS_FACTORS
        return u.build(
            (ram_at(lo), ram_at(mid), ram_at(hi)),
            u.time_band(seconds),
            0.3,
            tier,
            [
                "hash table + codes over both key columns",
                "two int64 indexers of output length",
                "output rows copied from both frames",
                "output length depends on unknown key overlap / fan-out",
            ],
        )
