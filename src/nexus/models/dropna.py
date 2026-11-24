"""Tier 0 model for ``DataFrame.dropna``."""

from __future__ import annotations

from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class DropnaModel(OperationModel):
    """Peak RAM and time for ``DataFrame.dropna``.

    The mask stages allocate ``2*K*n`` and ``K*n + 3*n`` bytes, then a partial take copies
    the moved frame bytes for surviving rows plus small indices and masks. A frame with no
    rows removed takes the shallow copy path. The derivation and probe are in
    ``docs/benchmarks/phase8/probes/p8_dropna.*``.
    """

    name = "dropna"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "dropna"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        frame = u.frame(state, op.receiver)
        subset = op.kwargs.get("subset")
        if isinstance(subset, str):
            cols = [subset]
        elif isinstance(subset, (list, tuple)):
            if not all(isinstance(v, str) for v in subset):
                raise NoEstimateError("dropna subset columns are not known")
            cols = list(subset)
        elif subset is None:
            cols = list(frame.dtypes)
        else:
            raise NoEstimateError("dropna subset is not statically known")
        how = op.kwargs.get("how", "any")
        if how not in ("any", "all"):
            raise NoEstimateError("dropna how is not statically known")
        if "thresh" in op.kwargs:
            raise NoEstimateError("dropna thresh is not modelled")
        if any(col not in frame.dtypes for col in cols):
            raise NoEstimateError("dropna subset contains an unknown column")
        return {
            "n_rows": frame.shape[0],
            "n_cols": frame.shape[1],
            "checked_cols": len(cols),
            "moved_bytes": frame.moved_bytes,
            "how": how,
            "subset": cols,
            "surviving_fraction": None,
        }

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        df = ctx.obj(op.receiver)
        cols = features["subset"]
        n = len(df)
        if n < stats.MIN_SAMPLE_ROWS:
            return None
        pos = stats.sample_positions(n, 100_000)
        sample = stats.take(df[cols], pos)
        ctx.deadline.check()
        if features["how"] == "any":
            keep = sample.notna().all(axis=1)
        else:
            keep = sample.notna().any(axis=1)
        fraction = float(keep.mean()) if len(keep) else 1.0
        return {
            "surviving_fraction": fraction,
            "tier1": {"sample": len(sample), "confidence": 0.9, "method": "dropna-null-mask"},
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n = float(features["n_rows"])
        k = float(features["checked_cols"])
        moved = float(features["moved_bytes"])
        fraction = features.get("surviving_fraction")
        notna_phase = 2.0 * k * n
        reduce_phase = k * n + 3.0 * n

        if fraction is None:
            fractions = (0.0, 0.5, 1.0)
        else:
            fractions = (max(0.0, fraction), fraction, min(1.0, fraction))
        peaks = []
        for surviving in fractions:
            phases = [notna_phase, reduce_phase]
            if surviving < 1.0:
                krows = surviving * n
                phases.append(k * n + n + 16.0 * krows + moved * surviving)
            peaks.append(max(phases))
        low, expected, high = sorted(peaks)
        low = float(low)
        high = float(high)
        if fraction is None:
            # If the missing fraction is unknown, span no removals through all rows removed.
            low, expected, high = peaks[2], peaks[1], peaks[0]
            low, expected, high = sorted((low, expected, high))
        seconds = tt.copy_s(expected) * (2.0 if fraction is not None else 3.0)
        return u.build(
            (low, expected, high),
            u.time_band_for_tier(seconds, tier),
            0.65 if fraction is not None else 0.45,
            tier,
            [
                f"{int(k)} checked columns",
                "null mask and block take",
                f"{features['how']} surviving rows",
            ],
        )
