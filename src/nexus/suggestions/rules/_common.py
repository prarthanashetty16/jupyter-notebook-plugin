"""Helpers shared by suggestion rules."""

from __future__ import annotations

import ast
from typing import Any

import pandas as pd

from nexus.analyzer import DetectedOp, Expr
from nexus.state import FrameDescriptor
from nexus.suggestions.base import Context
from nexus.suggestions.liveness import parents


def call_receiver(op: DetectedOp) -> ast.Name | None:
    """The ``Name`` node of ``df`` in ``df.method(...)``, if the receiver is a plain name."""
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    return value if isinstance(value, ast.Name) and value.id == op.receiver else None


def merge_operands(op: DetectedOp) -> tuple[ast.Name, ast.Name] | None:
    """Name nodes of the left and right frame of ``left.merge(right, ...)`` / ``pd.merge(l, r)``."""
    node = op.node
    if not isinstance(node, ast.Call):
        return None
    if op.name == "merge":
        left = call_receiver(op)
        right = (
            node.args[0]
            if node.args
            else next((k.value for k in node.keywords if k.arg == "right"), None)
        )
    else:
        if len(node.args) < 2:
            return None
        left, right = node.args[0], node.args[1]
    if isinstance(left, ast.Name) and isinstance(right, ast.Name) and left.id != right.id:
        return left, right
    return None


def literal_cols(value: Any) -> list[str] | None:
    if value is None or isinstance(value, Expr):
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple) and value and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def live_frame(ctx: Context, name: str) -> tuple[pd.DataFrame, FrameDescriptor] | None:
    """The live DataFrame and its descriptor, only for a frame with unique column labels."""
    obj = ctx.namespace.get(name)
    desc = ctx.inspection.variables.get(name)
    if not isinstance(obj, pd.DataFrame) or not isinstance(desc, FrameDescriptor):
        return None
    if not obj.columns.is_unique or obj.shape[0] != desc.shape[0]:
        return None
    return obj, desc


def _str_list(node: ast.AST) -> frozenset[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({node.value})
    if isinstance(node, ast.List) and node.elts:
        if all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            return frozenset(e.value for e in node.elts)  # type: ignore[attr-defined]
    return None


def result_use(ctx: Context, call: ast.Call) -> tuple[str, Any]:
    """How the cell consumes the call's value.

    ('chain', columns): a literal subscript of the value itself; ('bound', name): ``name = call``;
    ('bare', None): an expression statement (displayed whole); ('other', None): anything else.
    """
    parent = parents(ctx.tree).get(call)
    if isinstance(parent, ast.Subscript) and parent.value is call:
        cols = _str_list(parent.slice) if isinstance(parent.ctx, ast.Load) else None
        return ("chain", cols) if cols else ("other", None)
    if (
        isinstance(parent, ast.Assign)
        and len(parent.targets) == 1
        and isinstance(parent.targets[0], ast.Name)
    ):
        return "bound", parent.targets[0].id
    if isinstance(parent, ast.Expr):
        return "bare", None
    return "other", None


def quote_list(items: list[str]) -> str:
    return "[" + ", ".join(repr(i) for i in items) + "]"


def bound_target(ctx: Context, call: ast.Call) -> frozenset[ast.AST]:
    """The ``name`` node of ``name = call``, to be ignored by the liveness check of ``name``."""
    parent = parents(ctx.tree).get(call)
    if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
        return frozenset({parent.targets[0]})
    return frozenset()
