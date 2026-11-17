"""Tier 0 model for ``pandas.concat`` (row-wise)."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

INDEX_BYTES_PER_ROW = 12  # int64 result index + concatenation transient, measured (docstring)


@register_model
class ConcatModel(OperationModel):
    """Peak RAM and time of ``pd.concat([a, b, ...])`` (row-wise).

    RAM, derived from ``pandas.core.internals.concat.concatenate_managers``: every output block
    is built by one ``np.concatenate`` over the inputs' blocks, so the result holds the sum of the
    inputs' ``moved_bytes``. For object/str columns that is 8-byte POINTERS: the string objects
    are shared with the inputs and are not copied, whether or not they repeat, so
    ``memory_usage(deep=True)`` (which counts the string payload) overstates the copy. The result
    index is an int64 ``Index`` unless ``ignore_index=True`` makes it a ``RangeIndex``; the probes
    measured 12 B/row for it (8 B/row of values plus a 4 B/row transient of the index
    concatenation) and exactly 0 with ``ignore_index``.
    Inputs stay alive, so the increment is exactly that copy; there is no intermediate larger
    than it when dtypes agree.

    Range: ``low`` is the copy alone, ``expected`` adds the int64 index, ``high`` adds a second
    copy of the values for the dtype-unification case (e.g. int + float, or categoricals with
    different categories becoming object), which Tier 0 cannot rule out.

    A frame with pyarrow-backed strings stores the characters inside the array, so its shallow
    bytes already include them and are copied (``moved_bytes`` covers it).

    Verified with isolated allocation probes on synthetic 1.5-2M-row frames (not benchmark
    points): numeric frames of 8..64 B/row peaked at exactly ``moved + 12`` B/row (and ``moved``
    with ``ignore_index``); frames with object/category/datetime columns, shared or unshared
    strings, 2 or 3 inputs, peaked 4-13% above ``moved + index`` (the residual is not explained;
    it stays inside the ``expected``..``high`` range). The peak does not follow the deep size.
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
        return {
            "total_bytes": sum(f.nbytes for f in frames),
            "moved_bytes": sum(f.moved_bytes for f in frames),
            "total_rows": sum(f.shape[0] for f in frames),
            "n_frames": len(frames),
            "ignore_index": op.kwargs.get("ignore_index") is True,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        total = features["total_bytes"]
        moved = features.get("moved_bytes", total)
        index = (
            0
            if features.get("ignore_index")
            else INDEX_BYTES_PER_ROW * features.get("total_rows", 0)
        )
        return u.build(
            (moved, moved + index, 2 * moved + index),
            u.time_band(total / u.machine().copy_bps),
            0.7,
            tier,
            [
                "new frame holding every input row (pointers, not string objects)",
                "possible dtype-unification temporaries",
            ],
        )
