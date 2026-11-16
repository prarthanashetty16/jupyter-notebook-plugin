"""AST-based detection of known pandas/numpy operations in a cell.

Detection is purely syntactic: ``x.copy()`` is reported even if ``x`` is a list. Models must
confirm from the live state (see ``nexus.state``) that the variable is what they expect.
Unknown code yields an empty list, never a guess. Ops are returned in execution order
(arguments and receivers before the call that consumes them).
"""

from __future__ import annotations

import ast
import re
import types
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from nexus.failsafe import Deadline

MAX_SOURCE_CHARS = 200_000
MAX_OPS = 500

KNOWN_FUNCTIONS = frozenset(
    {
        "pandas.read_csv",
        "pandas.read_table",
        "pandas.read_parquet",
        "pandas.read_excel",
        "pandas.read_json",
        "pandas.read_feather",
        "pandas.concat",
        "pandas.merge",
        "pandas.get_dummies",
        "pandas.pivot_table",
        "pandas.crosstab",
        "numpy.zeros",
        "numpy.ones",
        "numpy.empty",
        "numpy.full",
        "numpy.arange",
        "numpy.linspace",
        "numpy.array",
        "numpy.concatenate",
        "numpy.stack",
        "numpy.vstack",
        "numpy.hstack",
        "numpy.tile",
        "numpy.repeat",
        "numpy.outer",
        "numpy.dot",
        "numpy.matmul",
        "numpy.tensordot",
        "numpy.einsum",
        "numpy.sort",
        "numpy.argsort",
        "numpy.unique",
        "numpy.cumsum",
        "numpy.load",
        "numpy.loadtxt",
        "numpy.genfromtxt",
        "numpy.linalg.inv",
        "numpy.linalg.svd",
        "numpy.linalg.eig",
        "numpy.linalg.solve",
        "numpy.random.rand",
        "numpy.random.randn",
        "numpy.random.random",
        "numpy.random.normal",
        "numpy.random.randint",
    }
)

KNOWN_METHODS = frozenset(
    {
        "drop_duplicates",
        "duplicated",
        "merge",
        "join",
        "groupby",
        "sort_values",
        "sort_index",
        "pivot",
        "pivot_table",
        "melt",
        "stack",
        "unstack",
        "fillna",
        "dropna",
        "astype",
        "copy",
        "apply",
        "applymap",
        "map",
        "explode",
        "reset_index",
        "set_index",
        "value_counts",
        "nunique",
        "describe",
        "corr",
        "rolling",
        "resample",
        "nlargest",
        "sample",
        "query",
        "assign",
        "to_csv",
        "to_parquet",
        "to_numpy",
        "dot",
        "reshape",
        "flatten",
        "ravel",
        "argsort",
        "sort",
        "cumsum",
    }
)

_TRANSPARENT_MAGICS = frozenset({"time", "timeit", "prun", "capture"})
_CELL_MAGIC = re.compile(r"^\s*%%(?P<name>\w+)")
_LINE_MAGIC = re.compile(r"^(?P<indent>\s*)%{1,2}(?P<name>\w+)(?:[ \t]+(?P<rest>.*))?$")
_TIMING_OPTS = re.compile(r"^(?:-[A-Za-z]\s*\d*\s+)*")
_SHELL_LINE = re.compile(r"^(?P<indent>\s*)!(?!=)")
_ASSIGN_SPECIAL = re.compile(r"^(?P<indent>\s*)(?P<lhs>[\w.\[\], ]+?)\s*=\s*[!%]\S.*$")
_HELP_LINE = re.compile(r"^(?P<indent>\s*)(?:\?\??\s*[\w.]*|[\w.]+\?\??)\s*$")


class Expr(str):
    """Source text of an argument that is not a literal (e.g. a variable name)."""

    __slots__ = ()


@dataclass(frozen=True, eq=False)
class DetectedOp:
    """One recognised operation.

    ``name`` is a canonical dotted name for module functions (``pandas.read_csv``) and the bare
    method name for method calls (``drop_duplicates``). ``variables`` are the user variables the
    call touches, with simple aliases (``df2 = df``) resolved to their root name. ``args`` and
    ``kwargs`` hold literal values, or ``Expr`` for anything that is not a literal.
    """

    name: str
    node: ast.AST
    variables: tuple[str, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    args: tuple[Any, ...] = ()
    receiver: str | None = None
    lineno: int = 0


def strip_magics(source: str) -> str:
    """Turn an IPython cell into plain Python, keeping code that magics merely wrap.

    ``%time``/``%timeit``/``%%time``/``%%capture`` keep their body; other magics, ``!`` shell
    lines and ``?`` help lines become ``pass``. Unknown cell magics (``%%bash``...) drop the cell.
    """
    lines = source.splitlines()
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return ""
    cell_magic = _CELL_MAGIC.match(lines[first])
    if cell_magic:
        if cell_magic["name"] not in _TRANSPARENT_MAGICS:
            return ""
        lines = lines[first + 1 :]
    return "\n".join(_strip_line(line) for line in lines)


def _strip_line(line: str) -> str:
    if m := _ASSIGN_SPECIAL.match(line):
        return f"{m['indent']}{m['lhs']} = None"
    if m := _LINE_MAGIC.match(line):
        rest = m["rest"]
        if m["name"] in _TRANSPARENT_MAGICS and rest:
            body = _TIMING_OPTS.sub("", rest)
            if body.strip():
                return m["indent"] + body
        return m["indent"] + "pass"
    if (m := _SHELL_LINE.match(line)) or (m := _HELP_LINE.match(line)):
        return m["indent"] + "pass"
    return line


def analyze_cell(
    source: str,
    namespace: Mapping[str, Any] | None = None,
    deadline: Deadline | None = None,
) -> list[DetectedOp]:
    """Return the known operations in ``source``, or ``[]`` if there are none or it won't parse.

    ``namespace`` lets names imported in earlier cells (``pd``, ``np``, ``read_csv``) resolve.
    Raises TimeoutError if ``deadline`` expires.
    """
    if not isinstance(source, str) or len(source) > MAX_SOURCE_CHARS:
        return []
    try:
        code = strip_magics(source)
        if not code.strip():
            return []
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError):
        return []
    collector = _Collector(namespace if namespace is not None else {}, deadline)
    try:
        collector.visit(tree)
    except RecursionError:
        return []
    return collector.ops


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        try:
            return Expr(ast.unparse(node))
        except Exception:
            return Expr("<unparseable>")


def _namespace_symbol(obj: Any) -> str | None:
    """Canonical dotted name for a module or known function found in the user namespace."""
    if isinstance(obj, types.ModuleType):
        return obj.__name__
    if not callable(obj):
        return None
    module, qualname = getattr(obj, "__module__", None), getattr(obj, "__name__", None)
    if isinstance(module, str) and isinstance(qualname, str):
        for candidate in (f"{module}.{qualname}", f"{module.split('.')[0]}.{qualname}"):
            if candidate in KNOWN_FUNCTIONS:
                return candidate
    return None


class _NameCollector(ast.NodeVisitor):
    """Collect data-like names read inside an expression (not called names, not lambda params)."""

    def __init__(self) -> None:
        self.names: list[str] = []
        self._skip: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id not in self._skip:
            self.names.append(node.id)

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name):
            self.visit(node.func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        a = node.args
        params = {x.arg for x in [*a.posonlyargs, *a.args, *a.kwonlyargs]}
        params |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
        added = params - self._skip
        self._skip |= added
        self.visit(node.body)
        self._skip -= added


class _Collector(ast.NodeVisitor):
    def __init__(self, namespace: Mapping[str, Any], deadline: Deadline | None) -> None:
        self.ops: list[DetectedOp] = []
        self._ns = namespace
        self._deadline = deadline
        self._symbols: dict[str, str] = {}  # local name -> canonical dotted module/function
        self._aliases: dict[str, str] = {}  # df2 -> df
        self._shadowed: set[str] = set()  # names rebound to something else in this cell

    # -- bindings -------------------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.asname:
                self._bind_symbol(alias.asname, alias.name)
            else:
                root = alias.name.split(".")[0]
                self._bind_symbol(root, root)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level or not node.module:
            return
        for alias in node.names:
            if alias.name != "*":
                self._bind_symbol(alias.asname or alias.name, f"{node.module}.{alias.name}")

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        for target in node.targets:
            self.visit(target)
        for target in node.targets:
            self._bind(target, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)
        if node.value is not None:
            self._bind(node.target, node.value)

    def _bind_symbol(self, local: str, canonical: str) -> None:
        self._symbols[local] = canonical
        self._aliases.pop(local, None)
        self._shadowed.discard(local)

    def _bind(self, target: ast.AST, value: ast.AST) -> None:
        if not isinstance(target, ast.Name):
            return
        name = target.id
        canonical = self._canonical(value)
        root = self._resolve_var(value.id) if isinstance(value, ast.Name) else None
        self._symbols.pop(name, None)
        self._aliases.pop(name, None)
        if canonical is not None:
            self._symbols[name] = canonical
            self._shadowed.discard(name)
            return
        self._shadowed.add(name)
        if root is not None and root != name:
            self._aliases[name] = root

    # -- name resolution ------------------------------------------------------------------
    def _symbol(self, name: str) -> str | None:
        if name in self._symbols:
            return self._symbols[name]
        if name in self._shadowed or name in self._aliases:
            return None
        return _namespace_symbol(self._ns.get(name))

    def _canonical(self, node: ast.AST) -> str | None:
        parts: list[str] = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        base = self._symbol(cur.id)
        if base is None:
            return None
        return ".".join([base, *reversed(parts)])

    def _resolve_var(self, name: str) -> str:
        for _ in range(16):
            if name not in self._aliases:
                break
            name = self._aliases[name]
        return name

    def _root_var(self, node: ast.AST) -> str | None:
        cur = node
        while True:
            if isinstance(cur, (ast.Attribute, ast.Subscript)):
                cur = cur.value
            elif isinstance(cur, ast.Call):
                cur = cur.func
            else:
                break
        if isinstance(cur, ast.Name) and self._symbol(cur.id) is None:
            return self._resolve_var(cur.id)
        return None

    def _variables(self, nodes: list[ast.AST]) -> tuple[str, ...]:
        collector = _NameCollector()
        for node in nodes:
            collector.visit(node)
        out: list[str] = []
        for name in collector.names:
            if self._symbol(name) is not None:
                continue
            root = self._resolve_var(name)
            if root not in out:
                out.append(root)
        return tuple(out)

    # -- detection ------------------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        if self._deadline is not None:
            self._deadline.check()
        self.generic_visit(node)
        if len(self.ops) < MAX_OPS:
            op = self._detect(node)
            if op is not None:
                self.ops.append(op)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.generic_visit(node)
        if isinstance(node.op, ast.MatMult) and len(self.ops) < MAX_OPS:
            self.ops.append(
                DetectedOp(
                    name="operator.matmul",
                    node=node,
                    variables=self._variables([node.left, node.right]),
                    receiver=self._root_var(node.left),
                    lineno=node.lineno,
                )
            )

    def _detect(self, node: ast.Call) -> DetectedOp | None:
        func = node.func
        canonical = self._canonical(func)
        if canonical is not None:
            return self._make(node, canonical, None, None) if canonical in KNOWN_FUNCTIONS else None
        if isinstance(func, ast.Attribute) and func.attr in KNOWN_METHODS:
            return self._make(node, func.attr, self._root_var(func.value), func.value)
        return None

    def _make(
        self, node: ast.Call, name: str, receiver: str | None, receiver_node: ast.AST | None
    ) -> DetectedOp:
        nodes: list[ast.AST] = [receiver_node] if receiver_node is not None else []
        nodes += node.args
        nodes += [kw.value for kw in node.keywords]
        return DetectedOp(
            name=name,
            node=node,
            variables=self._variables(nodes),
            kwargs={kw.arg: _literal(kw.value) for kw in node.keywords if kw.arg is not None},
            args=tuple(_literal(a) for a in node.args),
            receiver=receiver,
            lineno=node.lineno,
        )
