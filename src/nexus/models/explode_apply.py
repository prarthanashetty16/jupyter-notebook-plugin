"""Model for ``Series.apply(<numpy ufunc>)`` (Phase 7b).

Derived from pandas 3.1.1 source BEFORE its probes ran; it passed the pre-registered bar (every probe
variant within +-15% of the derived peak; ``docs/benchmarks/phase7a/probes/p1d_coverage.out`` and
``docs/benchmarks/phase7b/probes/p7b_changes.out`` section F: 1.000, 1.000, 1.001).

``Series.explode`` was derived the same way (below, kept for the record) but FAILED the Phase 7b grid
(section E: 1.341 at mean length 2, 1.274 with 30% empty lists, 1.605 with string elements; only
mean 12 passed). It is NOT modelled and stays uncovered:

* ``s.explode()`` / ``df["c"].explode()`` (``Series.explode`` -> ``reshape.explode``): a per-row counts
  array (8 B x n) and the object result (8 B x E pointers; the elements are the existing objects, not
  copies) plus ``index.repeat(counts)`` (8 B x E): **peak = 8n + 16E**, E = elements after exploding (an
  empty list or a scalar counts as one). E is unknowable from the descriptor, so there is NO Tier 0
  estimate: Tier 1 samples the list lengths, and without it the operation stays uncovered (UNKNOWN).
  ``ignore_index=True`` and ``DataFrame.explode`` (contradicted: 1.33) are refused.
* ``s.apply(np.<ufunc>)`` (``SeriesApply`` calls a ufunc on the array): the result array, **peak =
  n x itemsize(result dtype)**; the result dtype is the ufunc's own on the column dtype (computed on a
  one-element array). Python functions (element-wise: 2.19, row-wise: 1.25 against their derivations)
  and ``DataFrame.apply`` are refused.

The range is the adoption band (``BAND``): the model is claimed only to that accuracy.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp, Expr
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import FrameDescriptor, Inspection, SeriesDescriptor

BAND = (0.85, 1.15)  # the pre-registered adoption bar, used as the model's stated accuracy
UFUNC_EXPR = re.compile(r"^(np|numpy)\.([A-Za-z_][A-Za-z0-9_]*)$")


def _column(op: DetectedOp) -> str | None:
    import ast

    value = getattr(getattr(op.node, "func", None), "value", None)
    if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
        return value.slice.value if isinstance(value.slice.value, str) else None
    return None


def series_shape(op: DetectedOp, state: Inspection) -> tuple[int, str]:
    """(rows, dtype) of the Series the method is called on: a Series variable or ``df["col"]``."""
    desc = state.variables.get(op.receiver) if op.receiver else None
    col = _column(op)
    if isinstance(desc, SeriesDescriptor) and col is None:
        return desc.shape[0], desc.dtype
    if isinstance(desc, FrameDescriptor) and col is not None and col in desc.dtypes:
        return desc.shape[0], desc.dtypes[col]
    raise NoEstimateError("receiver is not a known Series or literal column of a known frame")


@register_model
class ApplyUfuncModel(OperationModel):
    """Peak RAM of ``Series.apply(np.<ufunc>)`` (module docstring)."""

    name = "apply_ufunc"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "apply"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        func = op.args[0] if op.args else op.kwargs.get("func")
        if len(op.args) > 1 or set(op.kwargs) - {"func"}:
            raise NoEstimateError("only s.apply(np.<ufunc>) is modelled")
        m = UFUNC_EXPR.match(str(func)) if isinstance(func, Expr) else None
        ufunc = getattr(np, m.group(2), None) if m else None
        if not isinstance(ufunc, np.ufunc) or ufunc.nin != 1 or ufunc.nout != 1:
            raise NoEstimateError("apply with a Python function or a non-unary ufunc: not modelled")
        rows, dtype = series_shape(op, state)
        try:
            with np.errstate(all="ignore"):
                out = ufunc(np.zeros(1, dtype=np.dtype(dtype))).dtype
        except TypeError as exc:
            raise NoEstimateError(f"ufunc does not apply to {dtype}") from exc
        return {
            "n_rows": rows,
            "in_dtype": dtype,
            "out_itemsize": int(out.itemsize),
            "ufunc": m.group(2),
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        out = float(features["n_rows"]) * features["out_itemsize"]
        seconds = tt.copy_s(out) * 2.0  # read the column + write the result: two array passes
        return u.build(
            (out * BAND[0], out, out * BAND[1]),
            u.time_band_for_tier(seconds, tier),
            0.8,
            tier,
            [f"the {features['ufunc']} result array ({features['out_itemsize']} B/row)"],
        )
