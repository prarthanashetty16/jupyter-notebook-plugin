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
* pandas-3 ``str`` columns (python storage; v4 item (1a), probes ``docs/benchmarks/phase8/probes/p8_text_fillna*``):
  each is its own 1-D block, filled through ``Block.where``. A column holding a missing value is copied (its object
  POINTER array, 8 B/row; the strings are shared) and transiently needs 4 B/row of masks with a string value
  (12 B/row in all, probe 1.000-1.001). A non-string value fails the setitem and coerces the block to object, which
  transiently needs 13 B/row beyond the kept copy (21 B/row in all; second derivation, probe 1.023-1.048).
* Refused (no estimate): ``inplace=True``, ``method`` / ``limit`` / ``axis`` / ``downcast``, a value that
  is not a literal scalar or a literal dict, a receiver that is not a known DataFrame / Series, other extension
  dtypes (category, nullable ints, ``string``), and ``str`` when its default storage is not python (pyarrow).
* v4 item (1d), ``X.copy()`` on receivers the analyser does not see as operations (probe ``p8_copy_receivers``,
  1.000-1.002). The receiver's own cost is the copy's: a boolean mask of comparisons only (``df[...]`` /
  ``df.loc[...]``: comparison temporaries, key, 8 B/row indexer and new index, the row take, then the copy; the
  selected fraction is unknown, so ``high`` takes every row and ``expected = high``); a column list (a view when each
  dtype block's selected columns are one contiguous ascending run, else a take copy, then the copy); an ``iloc`` row
  slice with literal bounds (a view, then the copy). ``head`` / ``tail`` (already copies in pandas 3.1.1), chains and
  masks containing calls are refused (``nexus.deferred`` names the first).
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
STR_DTYPE = "str"
# str column, beyond its kept 8 B/row copy: masks (string value) / coercion to object (non-string value)
STR_TRANSIENT_STR_VALUE = 4
STR_TRANSIENT_OTHER_VALUE = 13


def _python_str_storage() -> bool:
    """The probes measured the python-storage ``str`` array; a pyarrow-backed one takes another path."""
    import pandas as pd

    return getattr(pd.api.types.pandas_dtype("str"), "storage", None) == "python"


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


TEXT_COMPARE_PER_ROW = (
    12  # StringArray._cmp_method: isna, valid, valid pointers (8), op result, result
)
NUM_COMPARE_PER_ROW = 1


def _column_of(node: ast.AST, frame: str | None) -> str | None:
    """``df['c']`` / ``df.c`` on the receiver frame -> ``c``."""
    if (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id == frame
    ):
        sl = node.slice
        return sl.value if isinstance(sl, ast.Constant) and isinstance(sl.value, str) else None
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == frame
    ):
        return node.attr
    return None


def mask_cost(node: ast.AST, frame: str | None, dtypes: dict[str, str]) -> float | None:
    """Bytes per row the mask expression keeps alive at its peak; None unless it is comparisons of the frame's own
    columns with constants combined by ``&`` / ``|`` / ``~`` (a call, e.g. ``isin``, has an unknown cost)."""
    if any(isinstance(n, ast.Call) for n in ast.walk(node)):
        return None
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or not isinstance(node.comparators[0], ast.Constant):
            return None
        col = _column_of(node.left, frame)
        if col is None or col not in dtypes:
            return None
        return float(TEXT_COMPARE_PER_ROW if u.is_text(dtypes[col]) else NUM_COMPARE_PER_ROW)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
        a, b = mask_cost(node.left, frame, dtypes), mask_cost(node.right, frame, dtypes)
        return None if a is None or b is None else a + b + 1.0  # both operands and the result alive
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
        a = mask_cost(node.operand, frame, dtypes)
        return None if a is None else a + 1.0
    return None


def take_copied_bytes(desc: Any, cols: list[str], cb: dict[str, float]) -> tuple[float, float]:
    """(expected, high) bytes ``df[cols]`` copies before the ``.copy()``. Per numpy dtype block (consolidated layout:
    the dtype's columns in frame order), the selected columns are a view when their block positions, in list order,
    are one contiguous ascending run; otherwise ``take_nd`` copies them. Text (extension) columns are viewed. A frame
    not known to be consolidated may have any layout: ``high`` copies every selected numpy column."""
    order: dict[str, list[str]] = {}
    for c, d in desc.dtypes.items():
        if not (u.is_text(d) and d != "object") and _itemsize(d) is not None:
            order.setdefault(d, []).append(c)
    expected = 0.0
    numpy_cols: list[str] = []
    for members in order.values():
        picked = [c for c in cols if c in members]
        numpy_cols += picked
        pos = [members.index(c) for c in picked]
        if pos and pos != list(range(pos[0], pos[0] + len(pos))):
            expected += sum(cb[c] for c in picked)
    high = expected if desc.consolidated is True else float(sum(cb[c] for c in numpy_cols))
    return expected, max(high, expected)


def _receiver_spec(op: DetectedOp) -> tuple[str, Any]:
    """("name", None) | ("columns", [cols]) | ("mask", node) | ("iloc", slice node); NoEstimateError otherwise."""
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    if isinstance(value, ast.Name):
        return "name", None
    if isinstance(value, ast.Subscript):
        base, sl = value.value, value.slice
        if isinstance(base, ast.Name):
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                return "columns", [sl.value]
            if isinstance(sl, ast.List) and all(
                isinstance(e, ast.Constant) and isinstance(e.value, str) for e in sl.elts
            ):
                return "columns", [e.value for e in sl.elts]  # type: ignore[union-attr]
            return "mask", sl
        if isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            if base.attr == "loc" and not isinstance(sl, (ast.Tuple, ast.Slice)):
                return "mask", sl
            if base.attr == "iloc" and isinstance(sl, ast.Slice):
                return "iloc", sl
    raise NoEstimateError("receiver is a computed expression")


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
        deep = op.kwargs.get("deep", op.args[0] if op.args else True)
        if isinstance(deep, Expr) or deep not in (True, False):
            raise NoEstimateError("deep= is not a literal bool")
        kind, arg = _receiver_spec(op)
        if kind in ("mask", "iloc"):
            return _row_receiver_features(op, state, kind, arg, bool(deep))
        desc, sel = _receiver(op, state)
        rows = desc.shape[0]
        cb, dts = column_bytes(desc), _dtypes(desc)
        take = (0.0, 0.0)
        if sel is not None:
            if isinstance(desc, FrameDescriptor) and len(sel) > 1:
                take = take_copied_bytes(desc, sel, cb)
            cb, dts = {c: cb[c] for c in sel}, {c: dts[c] for c in sel}
        return {
            "moved_bytes": float(sum(cb.values())),
            "n_rows": rows,
            "text_cols": sum(1 for d in dts.values() if u.is_text(d) or d == "object"),
            "consolidated": getattr(desc, "consolidated", None),
            "consolidation_bytes": _consolidation_bytes(cb, dts),
            "deep": bool(deep),
            "receiver": "columns" if sel is not None else "name",
            "take_bytes": take,  # (expected, high) copied by df[[...]] before the copy
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        if (
            "row_peak" in features
        ):  # a row-selection receiver: its own cost included (module docstring)
            lo, mid, hi = features["row_peak"]
            return u.build(
                (lo, mid, hi),
                u.time_band_for_tier(tt.copy(features), tier),
                0.5 if features["receiver"] == "mask" else 0.8,
                tier,
                [f"copy of a {features['receiver']} selection, the receiver's own cost included"],
            )
        moved = features["moved_bytes"] if features["deep"] else 0.0
        extra = features.get("consolidation_bytes", 0.0) if features["deep"] else 0.0
        consolidated = features.get("consolidated")
        # BlockManager.copy(deep=True) then _consolidate_inplace: the numpy blocks of a dtype group are
        # stacked into a new block while the copies are alive (probe: 427 MiB = 244 + 183, exact)
        take_mid, take_high = (
            features.get("take_bytes", (0.0, 0.0)) if features["deep"] else (0.0, 0.0)
        )
        expected = moved + (extra if consolidated is False else 0.0) + take_mid
        high = moved + (extra if consolidated is not True else 0.0) + take_high
        moved += take_mid
        return u.build(
            (moved, expected, high),
            u.time_band_for_tier(tt.copy(features), tier),
            0.8 if features["deep"] else 0.9,
            tier,
            ["every block copied (string objects shared, pointers copied)"
             if features["deep"] else "shallow copy: blocks shared (copy-on-write)"],
        )  # fmt: skip


def _row_receiver_features(
    op: DetectedOp, state: Inspection, kind: str, arg: Any, deep: bool
) -> dict[str, Any]:
    """Features of ``df[mask].copy()`` / ``df.loc[mask].copy()`` / ``df.iloc[a:b].copy()`` (module docstring)."""
    desc = state.variables.get(op.receiver) if op.receiver else None
    if not isinstance(desc, FrameDescriptor):
        raise NoEstimateError(f"{op.receiver!r} is not a known DataFrame")
    if not deep:
        raise NoEstimateError("a shallow copy of a row selection is not modelled")
    n = float(desc.shape[0])
    m = float(sum(column_bytes(desc).values()))
    base = {"n_rows": int(n), "deep": True, "receiver": kind, "consolidated": desc.consolidated,
            "text_cols": sum(1 for d in desc.dtypes.values() if u.is_text(d) or d == "object")}  # fmt: skip
    if kind == "iloc":
        bounds: list[int | None] = []
        for b in (arg.lower, arg.upper):
            if b is not None and not (isinstance(b, ast.Constant) and isinstance(b.value, int)):
                raise NoEstimateError("iloc bounds are not literal integers")
            bounds.append(None if b is None else b.value)
        if arg.step is not None:
            raise NoEstimateError("iloc with a step is not modelled")
        rows = len(range(int(n))[slice(*bounds)])
        copied = m * rows / n if n else 0.0
        return {
            **base,
            "moved_bytes": copied,
            "row_peak": (copied, copied, copied),
            "result": (copied,) * 3,
        }
    cost = mask_cost(arg, op.receiver, dict(desc.dtypes))
    if cost is None:
        raise NoEstimateError("the mask is not comparisons of the frame's columns with constants")
    low = max(cost, 1.0) * n  # nothing selected: the comparisons and the key
    high = max(
        cost * n, n + 16.0 * n + m, 8.0 * n + 2.0 * m
    )  # every row selected (fraction unknown)
    return {
        **base,
        "moved_bytes": m,
        "row_peak": (low, high, high),
        "result": (0.0, m + 8.0 * n, m + 8.0 * n),
    }


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
        text = [c for c in nullable if dtypes[c] == STR_DTYPE]
        if text and not _python_str_storage():
            raise NoEstimateError("fillna on a pyarrow-backed str column is not modelled")
        if any(_itemsize(dtypes[c]) is None or u.is_text(dtypes[c]) and dtypes[c] not in ("object", STR_DTYPE)
               for c in nullable):  # fmt: skip
            # other extension arrays (category, nullable ints, ``string``): not derived, refuse
            raise NoEstimateError("fillna on an extension-dtype column is not modelled")
        return {
            "n_rows": desc.shape[0],
            "column_bytes": {c: cols[c] for c in nullable},
            "column_dtypes": {c: dtypes[c] for c in nullable},
            "per_column": per_column,
            "str_value": {
                c: isinstance(value[c] if isinstance(value, dict) else value, str) for c in text
            },
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
        str_value = features.get("str_value", {})
        if features["per_column"]:
            groups = [[c] for c in columns]
        else:  # one block per dtype in a consolidated frame; a str column is a 1-D block of its own
            by_dtype: dict[str, list[str]] = {}
            for c in cb:
                by_dtype.setdefault(c if dt[c] == STR_DTYPE else dt[c], []).append(c)
            groups = [g for g in by_dtype.values() if set(g) & columns]
        data = sum(cb[c] for g in groups for c in g)

        def transient(g: list[str]) -> float:
            if dt[g[0]] == STR_DTYPE:
                per_row = (
                    STR_TRANSIENT_STR_VALUE
                    if str_value.get(g[0], False)
                    else STR_TRANSIENT_OTHER_VALUE
                )
                return float(per_row * n)
            return float(MASK_ARRAYS * n * len(g))

        # the blocks are filled one after another and their copies kept: every copy + the largest transient
        return data + max(transient(g) for g in groups)

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
