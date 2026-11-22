"""Frames created earlier in the same cell (Phase 7b): shape / dtype propagation, conservative fallback.

Before v3 the pipeline inspected the KERNEL's objects for every name an operation touches, so in

    a = pd.read_csv(path)
    m = a.merge(right, on="k")

the merge either had no estimate (``a`` not defined yet) or, worse, was estimated on a STALE ``a`` left
in the kernel by an earlier cell. Now a name bound by an earlier statement of the cell SHADOWS the
namespace:

* if that statement is a top-level ``name = <modelled operation>`` whose result shape is deterministic,
  the name gets a VIRTUAL descriptor built from the producer's prediction (``output_descriptor``):
  ``read_csv`` with Tier 1 statistics (rows, kept columns, dtypes from the call's own sample), ``concat``
  of frames with equal dtypes, deep ``copy``, ``sort_values``, ``fillna`` on frames without text columns;
* any other binding (merge / groupby / drop_duplicates results, whose row count is a range; unmodelled
  code; bindings inside ``if`` / loops / ``with``; ``del``) leaves the shape unknown, and the operation gets
  NO estimate. ``risk.assess`` then names it in the UNKNOWN message;
* an operation on a virtual frame runs at Tier 0 only: Tier 1 statistics would read the stale kernel
  object. The fallback is shown ("frame created in this cell").

Phase 7a probe 1c (docs/benchmarks/phase7a/probes/p1c_cell_frames.out): shapes / dtypes are enough for
concat (1.00), copy and sort, and bound fillna; merge and groupby on shapes alone are wide but contain
the measured peak (Tier 0). Column statistics are NOT carried in v3.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from nexus.state import Descriptor, FrameDescriptor, Inspection

CELL_FRAME_REASON = "frame created in this cell"
RANGE_INDEX_BYTES = 132


@dataclass
class CellBindings:
    """Which top-level statement binds which names, and which op produced the value."""

    spans: list[tuple[int, int]] = field(
        default_factory=list
    )  # (first line, last line) per statement
    binds: dict[str, list[tuple[int, int | None]]] = field(
        default_factory=dict
    )  # name -> (stmt, op id)

    def stmt_of(self, lineno: int) -> int | None:
        for i, (lo, hi) in enumerate(self.spans):
            if lo <= lineno <= hi:
                return i
        return None

    def last_binding(self, name: str, before_stmt: int) -> tuple[int, int | None] | None:
        """The latest binding of ``name`` in a statement before ``before_stmt`` (None: not bound in the cell)."""
        hits = [b for b in self.binds.get(name, []) if b[0] < before_stmt]
        return hits[-1] if hits else None


def _store_names(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.append(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out.extend((a.asname or a.name).split(".")[0] for a in n.names)
    return out


def bindings(tree: ast.Module, ops: list[Any]) -> CellBindings:
    """Bindings per top-level statement; the producer is set only for ``name = <op call>`` (top level)."""

    def key(n: ast.AST) -> tuple[Any, ...]:  # the analyzer parsed its own tree: match by position
        return tuple(
            getattr(n, a, None) for a in ("lineno", "col_offset", "end_lineno", "end_col_offset")
        )

    by_node = {key(op.node): id(op) for op in ops}
    cb = CellBindings()
    for i, st in enumerate(tree.body):
        cb.spans.append((st.lineno, getattr(st, "end_lineno", st.lineno) or st.lineno))
        producer = None
        if (
            isinstance(st, ast.Assign)
            and len(st.targets) == 1
            and isinstance(st.targets[0], ast.Name)
            and isinstance(st.value, ast.Call)
        ):
            producer = by_node.get(key(st.value))
        for name in dict.fromkeys(_store_names(st)):
            cb.binds.setdefault(name, []).append((i, producer))
    return cb


def _frame(name: str, rows: int, dtypes: dict[str, str], value_bytes: float, text_bytes: float,
           index_kind: str, index_nbytes: int, consolidated: bool | None) -> FrameDescriptor:  # fmt: skip
    text_cols = sum(
        1 for d in dtypes.values() if d in ("object", "str", "string") or d.startswith("string")
    )
    return FrameDescriptor(
        name=name, kind="DataFrame", nbytes=int(value_bytes + text_bytes + index_nbytes),
        shape=(int(rows), len(dtypes)), dtypes=dict(dtypes), dtype_counts=dict(Counter(dtypes.values())),
        index_kind=index_kind, index_nbytes=int(index_nbytes), text_columns=text_cols, n_blocks=None,
        consolidated=consolidated, shallow_bytes=int(value_bytes),
    )  # fmt: skip


def output_descriptor(  # noqa: C901
    name: str, model: str, features: dict[str, Any], estimate: Any, inputs: list[Descriptor]
) -> Descriptor | None:
    """The predicted result of a producer operation as a descriptor, or None when its shape is not
    deterministic (the consumer then gets no estimate)."""
    if model == "read_csv":
        f = features
        if not (f.get("tier1") or {}).get("used") or not f.get("n_rows") or not f.get("dtypes"):
            return None
        from nexus.models.read_csv import string_object_bytes

        rows = float(f["n_rows"])
        dts = dict(f["dtypes"])
        text = (f.get("text_cols") or 0) * rows * (f.get("unique_fraction") or 1.0)
        return _frame(name, int(rows), dts, rows * float(f.get("value_bytes_per_row") or 8.0 * len(dts)),
                      text * string_object_bytes(f.get("str_chars") or 12.0), "RangeIndex",
                      RANGE_INDEX_BYTES, f.get("reader_path") in ("parallel",))  # fmt: skip
    frames = [d for d in inputs if isinstance(d, FrameDescriptor)]
    if model == "concat":
        if not frames or len(frames) != len(inputs) or features.get("axis", 0) not in (0, "index"):
            return None
        if any(d.dtypes != frames[0].dtypes for d in frames):
            return None  # mixed dtypes are cast: not propagated
        rows = sum(d.shape[0] for d in frames)
        shallow = sum(d.moved_bytes for d in frames)
        rest = sum(d.nbytes - d.moved_bytes - d.index_nbytes for d in frames)
        return _frame(name, rows, frames[0].dtypes, shallow, max(rest, 0), "Index", 8 * rows, True)
    if len(frames) != 1:
        return None
    src = frames[0]
    if model == "copy":
        if not features.get("deep", True):
            return None
        return replace(src, name=name, consolidated=True if src.consolidated is not None else None)
    if model == "sort_values":
        return replace(src, name=name, index_kind="Index", index_nbytes=8 * src.shape[0],
                       nbytes=src.nbytes - src.index_nbytes + 8 * src.shape[0])  # fmt: skip
    if model == "fillna":
        if src.text_columns:
            return None  # an incompatible value coerces text columns to object
        return replace(src, name=name)
    return None


def cell_bindings(source: str, ops: list[Any]) -> CellBindings | None:
    """The cell's bindings, or None if it does not parse (then nothing is shadowed: v2 behaviour)."""
    from nexus.analyzer import strip_magics

    try:
        return bindings(ast.parse(strip_magics(source)), ops)
    except SyntaxError:
        return None


def _names(op: Any) -> list[str]:
    names = list(op.variables)
    if op.receiver and op.receiver not in names:
        names.append(op.receiver)
    return names


def state_for(
    op: Any, cb: CellBindings | None, produced: dict[int, Descriptor], inspection: Inspection
) -> tuple[Inspection | None, bool]:
    """(the state the op's models see, True if it touches a frame created in this cell). None: the op
    touches a name bound earlier in the cell whose shape is unknown, so it gets no estimate."""
    if cb is None:
        return inspection, False
    si = cb.stmt_of(op.lineno)
    if si is None:
        return inspection, False
    override: dict[str, Descriptor] = {}
    for name in _names(op):
        b = cb.last_binding(name, si)
        if b is None:
            continue
        desc = produced.get(b[1]) if b[1] is not None else None
        if desc is None:
            return None, True
        override[name] = replace(desc, name=name)
    if not override:
        return inspection, False
    return replace(inspection, variables={**inspection.variables, **override}), True


def record(
    op: Any, model: str, features: dict[str, Any], estimate: Any, state: Inspection,
    cb: CellBindings | None, produced: dict[int, Descriptor],
) -> None:  # fmt: skip
    """Remember the op's predicted result if a top-level ``name = <this op>`` binds it."""
    if cb is None or not any(p == id(op) for bs in cb.binds.values() for _, p in bs):
        return
    inputs = [state.variables[n] for n in _names(op) if n in state.variables]
    desc = output_descriptor("result", model, features, estimate, inputs)
    if desc is not None:
        produced[id(op)] = desc
