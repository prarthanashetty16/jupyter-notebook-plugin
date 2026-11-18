"""Which cells may be dry-run: side-effect free AND fully understood. Unknown means unsafe.

The check is an allowlist over the syntax tree, not a denylist: a cell qualifies only if it is ONE
statement (an expression, or an assignment to a plain name) whose value is exactly one of the
supported operations with literal arguments and operands that are plain user variables:

    left.merge(right, on=..., how=...)      pd.merge(left, right, ...)
    df.groupby(keys)[cols].<aggregation>()  df.sort_values(...)   df.drop_duplicates(...)
    df["col"].astype(target)                pd.concat([a, b, ...], ...)
    pd.read_csv("local/file.csv", ...)       np.sort(a)   a @ b   np.matmul(a, b)   np.dot(a, b)

Everything else is rejected with a reason: other statements (import, del, global, with, loops,
functions, augmented or subscript / attribute assignment, walrus), lambdas and comprehensions, calls
that are not in the table, chains of operations, ``inplace=True`` or any keyword outside the
operation's allowlist, relevant random state (``sample``, ``np.random``), file / network writes,
URLs, names that do not resolve to the real ``pandas`` / ``numpy`` modules, operands that are not
EXACTLY a DataFrame / ndarray (subclasses could override the method), and frames with unknown
object columns, duplicate or non-string column names.

The verdict also carries the ``Recipe``: a JSON-serialisable description of the call. The sandbox
child executes the recipe, never the source text, so the cell's code is not evaluated anywhere.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from nexus.analyzer import strip_magics

AGGREGATIONS = frozenset(
    {
        "sum",
        "mean",
        "min",
        "max",
        "count",
        "size",
        "first",
        "last",
        "std",
        "var",
        "median",
        "nunique",
        "prod",
    }  # fmt: skip
)
# keyword allowlists per operation: value kinds are checked separately (constants only)
KWARGS: dict[str, frozenset[str]] = {
    "merge": frozenset({"on", "how", "suffixes", "sort"}),
    "groupby": frozenset({"sort", "dropna", "observed", "as_index"}),
    "agg": frozenset({"numeric_only", "min_count"}),
    "astype": frozenset(),
    "concat": frozenset({"ignore_index", "axis", "join", "sort"}),
    "sort_values": frozenset({"by", "ascending", "na_position", "ignore_index", "kind"}),
    "drop_duplicates": frozenset({"subset", "keep", "ignore_index"}),
    "np_sort": frozenset({"axis", "kind"}),
    "read_csv": frozenset({"sep", "header", "usecols", "delimiter"}),
}
BUILTIN_TYPES = {"str": "str", "int": "int64", "float": "float64", "bool": "bool"}
SAFE_DTYPES = frozenset({"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
                         "float32", "float64", "bool", "category", "str", "object", "datetime64[ns]"})  # fmt: skip
_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_SHELL_OR_MAGIC = re.compile(r"^\s*(?:!|%(?!%?(?:time|timeit)\b))", re.M)


class UnsafeCellError(Exception):
    """Internal: the cell (or part of it) is not understood or not side-effect free."""


@dataclass(frozen=True)
class Recipe:
    """JSON-serialisable description of the one supported operation in a cell."""

    kind: str  # merge, groupby_agg, astype, concat, sort_values, drop_duplicates, np_sort, matmul, read_csv
    operands: tuple[str, ...] = ()  # user variable names, in call order
    kwargs: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(
        default_factory=dict
    )  # groupby: by / agg / cols; astype: column / target ...
    target: str | None = None  # name assigned to, if any (informational)

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "operands": list(self.operands),
            "kwargs": self.kwargs,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class SafetyVerdict:
    safe: bool
    reasons: tuple[str, ...] = ()
    recipe: Recipe | None = None


def analyze_safety(source: str, namespace: Mapping[str, Any]) -> SafetyVerdict:
    """Decide whether ``source`` may be dry-run; ``safe`` implies a ``recipe``."""
    try:
        return SafetyVerdict(True, (), _translate_cell(source, namespace))
    except UnsafeCellError as why:
        return SafetyVerdict(False, (str(why),))
    except Exception as exc:  # anything unexpected is "not understood"
        return SafetyVerdict(False, (f"not understood ({type(exc).__name__})",))


# -- statement level ---------------------------------------------------------------------------------
def _translate_cell(source: str, ns: Mapping[str, Any]) -> Recipe:
    if not isinstance(source, str) or len(source) > 20_000:
        raise UnsafeCellError("no source or too long")
    if _SHELL_OR_MAGIC.search(source):
        raise UnsafeCellError("shell command or non-timing magic")
    tree = ast.parse(strip_magics(source))
    body = [s for s in tree.body if not (isinstance(s, ast.Pass))]
    if len(body) != 1:
        raise UnsafeCellError(f"{len(body)} statements (exactly one is required)")
    stmt = body[0]
    target = None
    if isinstance(stmt, ast.Expr):
        value = stmt.value
    elif isinstance(stmt, ast.Assign):
        if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
            raise UnsafeCellError(
                "assignment target is not a plain name (subscript / attribute / unpacking)"
            )
        target, value = stmt.targets[0].id, stmt.value
    elif isinstance(stmt, ast.AnnAssign):
        if not isinstance(stmt.target, ast.Name) or stmt.value is None:
            raise UnsafeCellError("annotated assignment without a plain name or value")
        target, value = stmt.target.id, stmt.value
    else:
        raise UnsafeCellError(f"statement type {type(stmt).__name__} is not allowed")
    recipe = _translate_value(value, ns)
    return Recipe(recipe.kind, recipe.operands, recipe.kwargs, recipe.extra, target)


def _translate_value(node: ast.expr, ns: Mapping[str, Any]) -> Recipe:
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, ast.MatMult):
            raise UnsafeCellError("binary operator other than @")
        return _matmul(_array_name(node.left, ns), _array_name(node.right, ns), ns)
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        raise UnsafeCellError("not a supported call")
    func = node.func
    attr, base = func.attr, func.value
    if attr in AGGREGATIONS and _is_groupby_part(base):
        return _groupby(node, ns)
    module = _module_name(base, ns)
    if module == "pandas":
        return _pandas_function(attr, node, ns)
    if module == "numpy":
        return _numpy_function(attr, node, ns)
    return _method(attr, node, ns)


def _matmul(a: str, b: str, ns: Mapping[str, Any]) -> Recipe:
    if ns[a].ndim != 2 or ns[b].ndim != 2 or ns[a].shape[1] != ns[b].shape[0]:
        raise UnsafeCellError("matmul of anything but conforming 2-D arrays")
    return Recipe("matmul", (a, b))


# -- operands ----------------------------------------------------------------------------------------
def _module_name(node: ast.expr, ns: Mapping[str, Any]) -> str | None:
    if not isinstance(node, ast.Name) or node.id not in ns:
        return None
    import numpy
    import pandas

    obj = ns[node.id]
    return "pandas" if obj is pandas else "numpy" if obj is numpy else None


def _frame_name(node: ast.expr, ns: Mapping[str, Any]) -> str:
    import pandas as pd

    if not isinstance(node, ast.Name) or node.id not in ns:
        raise UnsafeCellError("operand is not a plain variable that exists")
    obj = ns[node.id]
    if type(obj) is not pd.DataFrame:
        raise UnsafeCellError(f"{node.id!r} is not exactly a DataFrame (subclass or other type)")
    _check_frame(node.id, obj)
    return node.id


def _check_frame(name: str, df: Any) -> None:
    import pandas as pd

    cols = list(df.columns)
    if isinstance(df.columns, pd.MultiIndex) or len(set(cols)) != len(cols):
        raise UnsafeCellError(f"{name!r} has MultiIndex or duplicate column names")
    if not all(isinstance(c, str) for c in cols):
        raise UnsafeCellError(f"{name!r} has non-string column names")
    for c in cols:
        dtype = str(df[c].dtype)
        if dtype not in SAFE_DTYPES and not dtype.startswith("datetime64"):
            raise UnsafeCellError(f"{name!r}[{c!r}] has dtype {dtype} (not supported)")
        if dtype == "object":
            head = df[c].iloc[:2000]
            if not all(v is None or isinstance(v, (str, float)) for v in head):
                raise UnsafeCellError(f"{name!r}[{c!r}] holds objects other than strings")


def _array_name(node: ast.expr, ns: Mapping[str, Any]) -> str:
    import numpy as np

    if not isinstance(node, ast.Name) or node.id not in ns:
        raise UnsafeCellError("operand is not a plain variable that exists")
    obj = ns[node.id]
    if type(obj) is not np.ndarray or obj.dtype.kind not in "iuf" or obj.ndim not in (1, 2):
        raise UnsafeCellError(f"{node.id!r} is not a numeric 1-D / 2-D ndarray")
    return node.id


def _const(node: ast.expr) -> Any:
    """A literal: str / int / float / bool / None, or a list / tuple of those; nothing else."""
    if isinstance(node, ast.Constant) and (
        node.value is None or isinstance(node.value, (str, int, float, bool))
    ):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
    ):
        if isinstance(node.operand.value, (int, float)) and not isinstance(
            node.operand.value, bool
        ):
            return -node.operand.value
    if isinstance(node, (ast.List, ast.Tuple)):
        items = [_const(e) for e in node.elts]
        if any(isinstance(i, (list, tuple)) for i in items):
            raise UnsafeCellError("nested containers are not supported")
        return items
    raise UnsafeCellError(f"argument is not a literal ({type(node).__name__})")


def _kwargs(op: str, node: ast.Call, ns: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kw in node.keywords:
        if kw.arg is None:
            raise UnsafeCellError("**kwargs")
        if kw.arg == "inplace":
            raise UnsafeCellError("inplace is never dry-run")
        if kw.arg not in KWARGS[op]:
            raise UnsafeCellError(f"keyword {kw.arg!r} is not in the {op} allowlist")
        out[kw.arg] = _const(kw.value)
    _check_values(op, out)
    return out


def _check_values(op: str, kw: dict[str, Any]) -> None:
    if kw.get("axis") not in (None, 0, -1):
        raise UnsafeCellError("axis other than 0 / -1")
    if kw.get("join") not in (None, "outer", "inner"):
        raise UnsafeCellError("unsupported join")
    if kw.get("how") not in (None, "inner", "left", "right", "outer"):
        raise UnsafeCellError("unsupported how")
    if isinstance(kw.get("sep"), str) and len(kw["sep"]) > 8:
        raise UnsafeCellError("odd separator")


# -- operations --------------------------------------------------------------------------------------
def _method(attr: str, node: ast.Call, ns: Mapping[str, Any]) -> Recipe:  # noqa: C901
    base = node.func.value  # type: ignore[attr-defined]
    if attr == "astype":
        return _astype(node, base, ns)
    if attr == "groupby":
        raise UnsafeCellError("groupby without an aggregation is lazy: nothing to estimate")
    if not isinstance(base, ast.Name):
        raise UnsafeCellError("method chain or computed receiver")
    df = _frame_name(base, ns)
    if attr == "merge":
        if len(node.args) != 1:
            raise UnsafeCellError("merge needs exactly one positional operand")
        right = _frame_name(node.args[0], ns)
        kw = _kwargs("merge", node, ns)
        _need_keys(kw, ns, df, right)
        return Recipe("merge", (df, right), kw)
    if attr == "sort_values":
        kw = _kwargs("sort_values", node, ns)
        if node.args:
            if len(node.args) != 1:
                raise UnsafeCellError("sort_values takes one positional argument")
            kw["by"] = _const(node.args[0])
        if "by" not in kw:
            raise UnsafeCellError("sort_values without literal columns")
        _need_columns(ns[df], _as_list(kw["by"]))
        return Recipe("sort_values", (df,), kw)
    if attr == "drop_duplicates":
        kw = _kwargs("drop_duplicates", node, ns)
        if node.args:
            if len(node.args) != 1:
                raise UnsafeCellError("drop_duplicates takes one positional argument")
            kw["subset"] = _const(node.args[0])
        if kw.get("subset") is not None:
            _need_columns(ns[df], _as_list(kw["subset"]))
        return Recipe("drop_duplicates", (df,), kw)
    raise UnsafeCellError(f"method {attr!r} is not in the allowlist")


def _as_list(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    if not all(isinstance(i, str) for i in items):
        raise UnsafeCellError("column names must be strings")
    return items


def _need_columns(df: Any, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise UnsafeCellError(f"columns {missing} not in the frame")


def _need_keys(kw: dict[str, Any], ns: Mapping[str, Any], left: str, right: str) -> None:
    if "on" not in kw:
        raise UnsafeCellError("merge without a literal on=")
    keys = _as_list(kw["on"])
    _need_columns(ns[left], keys)
    _need_columns(ns[right], keys)


def _astype(node: ast.Call, base: ast.expr, ns: Mapping[str, Any]) -> Recipe:
    if not (isinstance(base, ast.Subscript) and isinstance(base.value, ast.Name)):
        raise UnsafeCellError("astype only on df['column']")
    col_node = base.slice
    if not (isinstance(col_node, ast.Constant) and isinstance(col_node.value, str)):
        raise UnsafeCellError("column is not a string literal")
    df = _frame_name(base.value, ns)
    column = col_node.value
    _need_columns(ns[df], [column])
    if len(node.args) != 1 or node.keywords:
        raise UnsafeCellError("astype takes exactly one positional argument")
    arg = node.args[0]
    if isinstance(arg, ast.Name) and arg.id in BUILTIN_TYPES:
        if ns.get(arg.id, {"str": str, "int": int, "float": float, "bool": bool}[arg.id]) is not {
            "str": str, "int": int, "float": float, "bool": bool}[arg.id]:  # fmt: skip
            raise UnsafeCellError(f"{arg.id!r} is shadowed")
        target = BUILTIN_TYPES[arg.id]
    else:
        target = _const(arg)
        if not isinstance(target, str) or target not in SAFE_DTYPES:
            raise UnsafeCellError("astype target is not a supported dtype literal")
    return Recipe("astype", (df,), {}, {"column": column, "target": target})


def _is_groupby_part(node: ast.expr) -> bool:
    if isinstance(node, ast.Subscript):
        node = node.value
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "groupby"
    )


def _groupby(node: ast.Call, ns: Mapping[str, Any]) -> Recipe:
    agg = node.func.attr  # type: ignore[attr-defined]
    if node.args:
        raise UnsafeCellError("aggregation with arguments")
    agg_kw = _kwargs("agg", node, ns)
    base = node.func.value  # type: ignore[attr-defined]
    cols: list[str] | None = None
    if isinstance(base, ast.Subscript):
        cols = _as_list(_const(base.slice))
        base = base.value
    gb = base
    assert isinstance(gb, ast.Call) and isinstance(gb.func, ast.Attribute)
    if not isinstance(gb.func.value, ast.Name):
        raise UnsafeCellError("groupby on a computed receiver")
    df = _frame_name(gb.func.value, ns)
    if len(gb.args) != 1:
        raise UnsafeCellError("groupby needs literal key columns as its one positional argument")
    keys = _as_list(_const(gb.args[0]))
    gb_kw = _kwargs("groupby", gb, ns)
    _need_columns(ns[df], keys + (cols or []))
    return Recipe(
        "groupby_agg",
        (df,),
        {"groupby": gb_kw, "agg": agg_kw},
        {"by": keys, "cols": cols, "agg": agg},
    )


def _pandas_function(attr: str, node: ast.Call, ns: Mapping[str, Any]) -> Recipe:
    if attr == "merge":
        if len(node.args) != 2:
            raise UnsafeCellError("pd.merge needs two positional operands")
        left, right = _frame_name(node.args[0], ns), _frame_name(node.args[1], ns)
        kw = _kwargs("merge", node, ns)
        _need_keys(kw, ns, left, right)
        return Recipe("merge", (left, right), kw)
    if attr == "concat":
        if len(node.args) != 1 or not isinstance(node.args[0], (ast.List, ast.Tuple)):
            raise UnsafeCellError("pd.concat needs one literal list of variables")
        names = tuple(_frame_name(e, ns) for e in node.args[0].elts)
        if len(names) < 2:
            raise UnsafeCellError("pd.concat of fewer than two frames")
        kw = _kwargs("concat", node, ns)
        return Recipe("concat", names, kw)
    if attr == "read_csv":
        if len(node.args) != 1:
            raise UnsafeCellError("read_csv needs one literal path")
        path = _const(node.args[0])
        if not isinstance(path, str) or _URL.match(path) or not os.path.isfile(path):
            raise UnsafeCellError("read_csv path is not an existing local file literal")
        kw = _kwargs("read_csv", node, ns)
        if kw.get("header") not in (None, 0, "infer"):
            raise UnsafeCellError("read_csv header other than the first line")
        return Recipe("read_csv", (), kw, {"path": os.path.abspath(path)})
    raise UnsafeCellError(f"pandas function {attr!r} is not in the allowlist")


def _numpy_function(attr: str, node: ast.Call, ns: Mapping[str, Any]) -> Recipe:
    if attr == "sort":
        if len(node.args) != 1:
            raise UnsafeCellError("np.sort needs one positional array")
        a = _array_name(node.args[0], ns)
        kw = _kwargs("np_sort", node, ns)
        if ns[a].ndim != 1 and kw.get("axis") not in (None, -1):
            raise UnsafeCellError("np.sort of a 2-D array along axis 0")
        return Recipe("np_sort", (a,), kw)
    if attr in ("matmul", "dot"):
        if len(node.args) != 2 or node.keywords:
            raise UnsafeCellError(f"np.{attr} needs exactly two positional arrays")
        return _matmul(_array_name(node.args[0], ns), _array_name(node.args[1], ns), ns)
    raise UnsafeCellError(f"numpy function {attr!r} is not in the allowlist")
