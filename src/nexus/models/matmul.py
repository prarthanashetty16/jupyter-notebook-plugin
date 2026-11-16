"""Tier 0 model for the ``@`` operator on 2-D numpy arrays."""

from __future__ import annotations

from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

BLAS_BUFFER_BYTES = 8 * 2**20  # typical packing-buffer overhead, per call


@register_model
class MatmulModel(OperationModel):
    """Peak RAM and time of ``a @ b`` for 2-D arrays.

    Hypothesised cost drivers (unverified): peak RAM is the result array (m*p*itemsize) plus
    small BLAS packing buffers; no input copy for matching float dtypes. Time ~ 2*m*k*p flops at
    an effective BLAS rate that depends on core count and BLAS library, which Tier 0 does not
    know (hence a wide time band). Integer inputs use a much slower non-BLAS path (not modelled
    differently here).
    """

    name = "matmul"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "operator.matmul"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if len(op.variables) != 2:
            raise NoEstimateError("need two known arrays")
        a, b = u.array(state, op.variables[0]), u.array(state, op.variables[1])
        if len(a.shape) != 2 or len(b.shape) != 2 or a.shape[1] != b.shape[0]:
            raise NoEstimateError("only conforming 2-D arrays are modelled")
        out_dtype = np.result_type(np.dtype(a.dtype), np.dtype(b.dtype))
        return {
            "m": a.shape[0],
            "k": a.shape[1],
            "p": b.shape[1],
            "itemsize": out_dtype.itemsize,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        m, k, p, item = (features[x] for x in ("m", "k", "p", "itemsize"))
        out = m * p * item
        return u.build(
            (out, out + BLAS_BUFFER_BYTES, 1.5 * out + 8 * BLAS_BUFFER_BYTES),
            (
                2 * m * k * p / u.machine().blas_flops * 0.2,
                2 * m * k * p / u.machine().blas_flops,
                2 * m * k * p / u.machine().blas_flops * 5,
            ),
            0.7,
            tier,
            [
                "result array m*p*itemsize",
                "BLAS packing buffers",
                "2*m*k*p flops at unknown BLAS rate",
            ],
        )
