"""Conservative models for v4 reset of Series/frame output operations."""

from __future__ import annotations

import ast
from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp, Expr
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import ArrayDescriptor, FrameDescriptor, Inspection, SeriesDescriptor


def _series_or_column(op: DetectedOp, state: Inspection) -> tuple[int, str]:
    desc = state.variables.get(op.receiver) if op.receiver else None
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    col = None
    if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
        col = value.slice.value if isinstance(value.slice.value, str) else None
    if isinstance(desc, SeriesDescriptor) and col is None:
        return desc.shape[0], desc.dtype
    if isinstance(desc, FrameDescriptor) and col in desc.dtypes:
        return desc.shape[0], desc.dtypes[col]
    raise NoEstimateError("map receiver is not a known Series or literal column")


@register_model
class MapModel(OperationModel):
    """Peak RAM of dict/Series and NumPy ufunc mappers; Python functions stay deferred."""

    name = "map"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "map"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if len(op.args) != 1:
            raise NoEstimateError("map mapper is not exactly known")
        mapper = op.args[0]
        if isinstance(mapper, Expr):
            text = str(mapper).strip()
            if text.startswith("{"):
                kind = "dict"
            elif text.startswith(("np.", "numpy.")):
                kind = "ufunc"
            else:
                kind = "series"
        elif isinstance(mapper, np.ufunc):
            kind = "ufunc"
        elif isinstance(mapper, dict):
            kind = "dict"
        else:
            raise NoEstimateError("unsupported map mapper")
        n, dtype = _series_or_column(op, state)
        itemsize = np.dtype(dtype).itemsize if dtype != "str" and dtype != "object" else 8
        return {"n_rows": n, "mapper_kind": kind, "itemsize": itemsize}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n = float(features["n_rows"])
        kind = features["mapper_kind"]
        peak = n * (features["itemsize"] if kind == "ufunc" else 8.0)
        if kind == "series":
            peak *= 2.0
        return u.build(
            (0.85 * peak, peak, 1.15 * peak),
            u.time_band_for_tier(tt.copy_s(peak), tier),
            0.7,
            tier,
            [f"{kind} mapper result and indexer"],
        )


@register_model
class ToNumpyModel(OperationModel):
    """Peak RAM of ``to_numpy``: zero-copy for one dtype, copy for mixed or forced dtype."""

    name = "to_numpy"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "to_numpy"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        desc = state.variables.get(op.receiver) if op.receiver else None
        func = getattr(op.node, "func", None)
        value = getattr(func, "value", None)
        col = None
        if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
            col = value.slice.value if isinstance(value.slice.value, str) else None
        if isinstance(desc, SeriesDescriptor):
            nbytes = desc.nbytes
            dtype = desc.dtype
        elif isinstance(desc, FrameDescriptor):
            nbytes = desc.moved_bytes
            dtype = "mixed" if len(set(desc.dtypes.values())) > 1 else next(iter(desc.dtypes.values()), "unknown")
        else:
            raise NoEstimateError("to_numpy receiver is not known")
        target = op.kwargs.get("dtype")
        copy = op.kwargs.get("copy", False)
        return {"nbytes": nbytes, "dtype": dtype, "target_dtype": target, "copy": copy}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        nbytes = float(features["nbytes"])
        zero_copy = (
            features["dtype"] != "mixed"
            and features["target_dtype"] is None
            and features["copy"] is False
        )
        peak = 0.0 if zero_copy else nbytes
        ram = (0.0, peak, peak * 1.15 if peak else 8.0)
        return u.build(
            ram,
            u.time_band_for_tier(tt.copy_s(peak), tier),
            0.7 if zero_copy else 0.55,
            tier,
            ["zero-copy for compatible ndarray block" if zero_copy else "array/result consolidation copy"],
        )


@register_model
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
