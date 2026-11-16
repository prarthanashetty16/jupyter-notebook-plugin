"""Tier 0 model for ``df["col"].astype(dtype)``."""

from __future__ import annotations

import ast
from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

CATEGORY_CARDINALITY_PRIOR = 0.1  # distinct values / rows when converting to category
PY_STR_BYTES = 60  # assumed bytes per newly created short Python str (header + chars + pointer)


def _column_name(op: DetectedOp) -> str | None:
    """Column from ``df["col"].astype(...)`` read off the call node, if it is a literal."""
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
        return value.slice.value if isinstance(value.slice.value, str) else None
    return None


@register_model
class AstypeModel(OperationModel):
    """Peak RAM and time of converting one column (``df["c"].astype(target)``).

    Hypothesised cost drivers (unverified): the result is a new array of the target dtype, so
    numeric-to-numeric conversion costs ``n * itemsize`` and is fast; conversion to ``str``
    creates one Python string per row (~60 bytes each); conversion to ``category`` hashes every
    value (text hashing is much slower than numeric) and allocates int codes plus the unique
    values, whose count Tier 0 does not know (assumed 10% of rows). Only the single-column
    ``df["c"].astype(...)`` form is modelled; whole-frame astype yields no estimate.
    """

    name = "astype"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "astype"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        column = _column_name(op)
        target = op.args[0] if op.args else op.kwargs.get("dtype")
        if column is None or column not in df.dtypes or not isinstance(target, str):
            raise NoEstimateError("column or target dtype not statically known")
        if target not in ("str", "object", "category"):
            try:
                np.dtype(target)
            except TypeError as exc:
                raise NoEstimateError(f"unsupported target dtype {target!r}") from exc
        return {
            "n_rows": df.shape[0],
            "source_dtype": df.dtypes[column],
            "target": target,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, source, target = features["n_rows"], features["source_dtype"], features["target"]
        source_text = u.is_text(source)
        if target == "category":
            groups = CATEGORY_CARDINALITY_PRIOR * n
            out = 4 * n + groups * (PY_STR_BYTES if source_text else 8)
            temp = 8 * n + 16 * groups
            hash_s = u.machine().text_hash_s if source_text else u.machine().num_hash_s
            seconds = n * hash_s
            why = "hash every value; codes + unique values (count unknown)"
        elif target in ("str", "object"):
            out = n * (8 if source_text else PY_STR_BYTES)
            temp = 0.0
            seconds = 0.0 if source_text else n * u.machine().to_str_s
            why = "one new Python str per row" if not source_text else "no-op for text"
        else:
            itemsize = np.dtype(target).itemsize
            out, temp, seconds = n * itemsize, 0.0, n * u.machine().cast_s
            why = f"new {target} array of {n} elements"
        expected = out + temp
        return u.build(
            (expected * 0.5, expected, expected * 2.5),
            u.time_band(seconds + out / u.machine().copy_bps),
            0.5,
            tier,
            [why],
        )
