"""Models for easy NumPy allocation/sequence operations and pandas describe."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp, Expr
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import ArrayDescriptor, Inspection


def _shape(value: Any) -> tuple[int, ...] | None:
    if isinstance(value, int):
        return (value,)
    if isinstance(value, tuple) and all(isinstance(v, int) for v in value):
        return value
    if isinstance(value, list) and all(isinstance(v, int) for v in value):
        return tuple(value)
    return None


class NumpyZerosModel(OperationModel):
    """Peak RAM of ``np.zeros`` with a literal shape."""

    name = "numpy.zeros"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "numpy.zeros"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:  # noqa: C901
        try:
            dtype = np.dtype(op.kwargs.get("dtype", "float64"))
        except (TypeError, ValueError):
            raise NoEstimateError("NumPy dtype is not statically known") from None
        if op.name == "numpy.array":
            obj = op.args[0] if op.args else None
            if not isinstance(obj, Expr):
                raise NoEstimateError("np.array literal inputs are not validated")
            source = state.variables.get(str(obj))
            if not isinstance(source, ArrayDescriptor):
                raise NoEstimateError("np.array source is not a known ndarray")
            if op.kwargs.get("copy", True) is False:
                raise NoEstimateError("np.array(copy=False) may be zero-copy")
            target = op.kwargs.get("dtype")
            if target is not None and not isinstance(target, str):
                raise NoEstimateError("np.array target dtype is not literal")
            try:
                itemsize = np.dtype(target or source.dtype).itemsize
            except (TypeError, ValueError):
                raise NoEstimateError("np.array target dtype is unsupported") from None
            nbytes = math.prod(source.shape) * itemsize
            kind = "copy"
        elif op.name == "numpy.linspace":
            num = op.args[2] if len(op.args) >= 3 else op.kwargs.get("num")
            if not isinstance(num, int):
                raise NoEstimateError("np.linspace num is not literal")
            nbytes = num * dtype.itemsize
            kind = "sequence"
        else:
            shape = _shape(op.args[0]) if op.args else None
            if shape is None:
                raise NoEstimateError("NumPy allocation shape is not literal")
            nbytes = math.prod(shape) * dtype.itemsize
            kind = "zeros" if op.name == "numpy.zeros" else "empty"
        return {"nbytes": nbytes, "kind": kind}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        nbytes = float(features["nbytes"])
        if features["kind"] == "zeros":
            low, expected, high = 0.0, nbytes * 0.5, nbytes
        elif features["kind"] == "empty":
            low, expected, high = nbytes * 0.7, nbytes, nbytes
        else:
            low, expected, high = nbytes * 0.85, nbytes, nbytes * 1.15
        return u.build(
            (low, expected, high),
            u.time_band_for_tier(tt.copy_s(nbytes), tier),
            0.65,
            tier,
            ["shape x itemsize", features["kind"]],
        )


class NumpyEmptyModel(NumpyZerosModel):
    """Peak RAM of ``np.empty`` with a literal shape."""

    name = "numpy.empty"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "numpy.empty"


class NumpyLinspaceModel(NumpyZerosModel):
    """Peak RAM of ``np.linspace`` with a literal count."""

    name = "numpy.linspace"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "numpy.linspace"


@register_model
class NumpyArrayModel(NumpyZerosModel):
    """Peak RAM of ``np.array`` from a literal iterable."""

    name = "numpy.array"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "numpy.array"


