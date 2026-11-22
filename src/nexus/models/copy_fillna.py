"""Tier 0 / Tier 1 models for ``DataFrame.copy()`` and ``DataFrame.fillna(value)`` (Phase 6c).

Derived from pandas 3.1 (copy-on-write) and checked by isolated probes at >= 200 MiB
(``docs/benchmarks/phase6c/probes/p_copy_fillna.py``):

* ``copy()`` / ``copy(deep=True)``: every block is copied (``BlockManager.copy(deep=True)``), so the
  increment is the frame's moved bytes: numeric values and object POINTERS (string objects are shared,
  not copied). A fragmented frame is consolidated by the copy (one block per dtype); whether that needs a
  transient beyond the copy is the probe's question, so ``high`` allows a second copy for a frame that is
  not consolidated. ``copy(deep=False)`` shares every block: no data copy.
* ``fillna(scalar)``: block by block (one block per dtype in a consolidated frame) a block is copied only
  if it holds a missing value; blocks that cannot hold one (int, uint, bool) or hold none are shared under
  copy-on-write. While a block is filled its ``isna`` mask (1 byte per element) is alive.
  ``fillna({col: value})``: only the named columns are copied (each column with its own mask).
* Which blocks hold a missing value is unknown at Tier 0: ``low`` = none, ``expected`` = ``high`` = every
  block that can hold one (the reason to call ``fillna``). Tier 1 reads ``stats.null_profile`` (float and
  datetime columns scanned completely; others from a sample): ``low`` / ``expected`` = blocks with a
  certain null, ``high`` adds the undecided ones.
* Refused (no estimate): ``inplace=True``, ``method`` / ``limit`` / ``axis`` / ``downcast``, a value that
  is not a literal scalar or a literal dict, a receiver that is not a known DataFrame / Series.
"""

from __future__ import annotations

import ast
from typing import Any

import numpy as np

from nexus import stats
from nexus.analyzer import DetectedOp, Expr
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import FrameDescriptor, Inspection, SeriesDescriptor

POINTER_BYTES = 8
# Block.fillna (not inplace) -> Block.where: isna mask, ~mask (cond), ~cond (icond in
# validate_putmask) and ~icond (expressions.where) are alive together: 4 bool bytes per element
MASK_ARRAYS = 4


def _itemsize(dtype: str) -> float | None:
    if u.is_text(dtype) or dtype == "object":
        return float(POINTER_BYTES)
    try:
        return float(np.dtype(dtype).itemsize)
    except TypeError:
        return None  # category / extension dtypes: from the remainder of the moved bytes


def column_bytes(desc: Any) -> dict[str, float]:
    """Moved bytes per column (category / extension columns share the unexplained remainder)."""
    if isinstance(desc, SeriesDescriptor):  # deep nbytes counts string payloads: use the dtype
        size = _itemsize(desc.dtype)
        return {"__series__": size * desc.shape[0] if size is not None else float(desc.nbytes)}
    rows = desc.shape[0]
    out: dict[str, float] = {}
    unknown = []
    for col, dt in desc.dtypes.items():
        size = _itemsize(dt)
        if size is None:
            unknown.append(col)
        else:
            out[col] = size * rows
    rest = max(float(desc.moved_bytes) - sum(out.values()), 0.0)
    for col in unknown:
        out[col] = rest / len(unknown)
    return out


def _selected_columns(op: DetectedOp) -> list[str] | None:
    """Columns of a literal selection receiver (``df["a"]``, ``df[["a", "b"]]``); None for a plain
    name; NoEstimateError for any other computed receiver (its size is unknown)."""
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    if isinstance(value, ast.Name):
        return None
    if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name):
        sl = value.slice
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return [sl.value]
        if isinstance(sl, ast.List) and all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in sl.elts
        ):
            return [e.value for e in sl.elts]  # type: ignore[union-attr]
    raise NoEstimateError("receiver is a computed expression")


def _consolidation_bytes(cols: dict[str, float], dtypes: dict[str, str]) -> float:
    """Bytes of the numpy dtype groups with more than one column: what a consolidating copy stacks
    again (extension dtypes are 1-D blocks and are never consolidated)."""
    groups: dict[str, list[str]] = {}
    for c, d in dtypes.items():
        if _itemsize(d) is not None and not (u.is_text(d) and d != "object"):
            groups.setdefault(d, []).append(c)
    return float(sum(cols[c] for g in groups.values() if len(g) > 1 for c in g))


def _receiver(op: DetectedOp, state: Inspection) -> tuple[Any, list[str] | None]:
    desc = state.variables.get(op.receiver) if op.receiver else None
    if not isinstance(desc, (FrameDescriptor, SeriesDescriptor)):
        raise NoEstimateError(f"{op.receiver!r} is not a known DataFrame / Series")
    cols = _selected_columns(op)
    if cols is not None and (
        isinstance(desc, SeriesDescriptor) or not set(cols) <= set(desc.dtypes)
    ):
        raise NoEstimateError("selected columns are not columns of the frame")
    return desc, cols


def _dtypes(desc: Any) -> dict[str, str]:
    if isinstance(desc, SeriesDescriptor):
        return {"__series__": desc.dtype}
    return dict(desc.dtypes)


@register_model
class CopyModel(OperationModel):
    """Peak RAM and time of ``df.copy()`` (see the module docstring)."""

    name = "copy"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "copy"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        desc, sel = _receiver(op, state)
        deep = op.kwargs.get("deep", op.args[0] if op.args else True)
        if isinstance(deep, Expr) or deep not in (True, False):
            raise NoEstimateError("deep= is not a literal bool")
        rows = desc.shape[0]
        cb, dts = column_bytes(desc), _dtypes(desc)
        if sel is not None:
            cb, dts = {c: cb[c] for c in sel}, {c: dts[c] for c in sel}
        return {
            "moved_bytes": float(sum(cb.values())),
            "n_rows": rows,
            "text_cols": sum(1 for d in dts.values() if u.is_text(d) or d == "object"),
            "consolidated": getattr(desc, "consolidated", None),
            "consolidation_bytes": _consolidation_bytes(cb, dts),
            "deep": bool(deep),
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        moved = features["moved_bytes"] if features["deep"] else 0.0
        extra = features.get("consolidation_bytes", 0.0) if features["deep"] else 0.0
        consolidated = features.get("consolidated")
        # BlockManager.copy(deep=True) then _consolidate_inplace: the numpy blocks of a dtype group are
        # stacked into a new block while the copies are alive (probe: 427 MiB = 244 + 183, exact)
        expected = moved + (extra if consolidated is False else 0.0)
        high = moved + (extra if consolidated is not True else 0.0)
        return u.build(
            (moved, expected, high),
            u.time_band_for_tier(tt.copy(features), tier),
            0.8 if features["deep"] else 0.9,
            tier,
            ["every block copied (string objects shared, pointers copied)"
             if features["deep"] else "shallow copy: blocks shared (copy-on-write)"],
        )  # fmt: skip


_FILLNA_REFUSED = {"method", "limit", "axis", "downcast", "inplace"}


@register_model
class FillnaModel(OperationModel):
    """Peak RAM and time of ``df.fillna(value)`` (see the module docstring)."""

    name = "fillna"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "fillna"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        desc, sel = _receiver(op, state)
        if (_FILLNA_REFUSED - {"inplace"}) & set(op.kwargs) or op.kwargs.get("inplace") not in (
            None,
            False,
        ):
            raise NoEstimateError("fillna options other than value= are not modelled")
        if len(op.args) > 1:
            raise NoEstimateError("positional options are not modelled")
        value = op.kwargs.get("value", op.args[0] if op.args else None)
        if value is None or isinstance(value, Expr):
            raise NoEstimateError("value is not a literal scalar or dict")
        cols = column_bytes(desc)
        dtypes = _dtypes(desc)
        if (
            sel is not None
        ):  # a literal column selection: those columns, one by one (a Series for one)
            cols, dtypes = {c: cols[c] for c in sel}, {c: dtypes[c] for c in sel}
        if isinstance(value, dict):
            if isinstance(desc, SeriesDescriptor) or not set(value) <= set(cols):
                raise NoEstimateError("dict value with unknown columns")
            targets = list(value)
            per_column = True
        else:
            targets = list(cols)
            per_column = sel is not None and len(sel) == 1
        nullable = [c for c in targets if u.can_hold_null(dtypes[c])]
        if any(_itemsize(dtypes[c]) is None or u.is_text(dtypes[c]) and dtypes[c] != "object"
               for c in nullable):  # fmt: skip
            # extension arrays (pandas 3 ``str``, category, nullable ints) fill through
            # ExtensionArray.fillna: a probe measured 2.45x the column bytes, not derived: refuse
            raise NoEstimateError("fillna on an extension-dtype column is not modelled")
        return {
            "n_rows": desc.shape[0],
            "column_bytes": {c: cols[c] for c in nullable},
            "column_dtypes": {c: dtypes[c] for c in nullable},
            "per_column": per_column,
            "null_columns": None,  # Tier 1: (certain, possible)
        }

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        obj = ctx.obj(op.receiver)
        cols = [c for c in features["column_bytes"] if c != "__series__"]
        if not cols and "__series__" not in features["column_bytes"]:
            return {
                "null_columns": ([], []),
                "tier1": {"used": True, "method": "no nullable column"},
            }
        frame = obj.to_frame("__series__") if "__series__" in features["column_bytes"] else obj
        prof = stats.null_profile(frame, cols or ["__series__"], deadline=ctx.deadline)
        return {
            "null_columns": (list(prof.certain), list(prof.possible)),
            "tier1": {"used": True, "method": "null_profile", "rows": prof.scanned_rows},
        }

    @staticmethod
    def copied(features: dict[str, Any], columns: set[str]) -> float:
        """Bytes copied + the largest mask when the given columns hold a missing value."""
        cb, dt, n = features["column_bytes"], features["column_dtypes"], features["n_rows"]
        if not columns:
            return 0.0
        if features["per_column"]:
            groups = [[c] for c in columns]
        else:  # one block per dtype in a consolidated frame: the whole block is copied
            by_dtype: dict[str, list[str]] = {}
            for c in cb:
                by_dtype.setdefault(dt[c], []).append(c)
            groups = [g for g in by_dtype.values() if set(g) & columns]
        data = sum(cb[c] for g in groups for c in g)
        mask = MASK_ARRAYS * max(n * len(g) for g in groups)
        return data + mask

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        every = set(features["column_bytes"])
        known = features.get("null_columns")
        if known is None:  # Tier 0
            low, mid, high = 0.0, self.copied(features, every), self.copied(features, every)
        else:
            certain, possible = set(known[0]), set(known[1])
            low = mid = self.copied(features, certain)
            high = self.copied(features, certain | possible)
        return u.build(
            (low, mid, high),
            u.time_band_for_tier(tt.fillna(features, mid), tier),
            0.7 if known is not None else 0.5,
            tier,
            [
                "blocks holding a missing value are copied (+ an isna mask); others shared (copy-on-write)"
            ],
        )
