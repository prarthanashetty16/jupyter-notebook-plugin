"""Conservative liveness of DataFrame columns inside ONE cell.

Question answered: which columns of ``name`` can the rest of the cell possibly read? The answer is
a set of literal column names, or a refusal reason. Anything that is not a literal subscript read
(attribute access, passing the frame whole, a computed key, ``**kwargs``, ``eval``, ``locals``,
rebinding, ``del``, ...) is a refusal: when in doubt the caller must not claim the columns are
unused. Only the cell is analysed; later cells are invisible, which callers must say in their
labels (see the rules).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

DYNAMIC_CALLS = frozenset(
    {"eval", "exec", "locals", "globals", "vars", "getattr", "setattr", "delattr", "compile",
     "__import__", "dir", "open", "input"}
)  # fmt: skip


@dataclass(frozen=True)
class Uses:
    columns: frozenset[str] | None  # None: unknown (refused)
    reason: str | None = None

    @property
    def proven(self) -> bool:
        return self.columns is not None


def parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}


def cell_is_analysable(tree: ast.AST) -> str | None:
    """A reason the cell defeats static reasoning, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in DYNAMIC_CALLS:
                return f"dynamic code ({f.id})"
            if any(k.arg is None for k in node.keywords):
                return "**kwargs in a call"
            if any(isinstance(a, ast.Starred) for a in node.args):
                return "*args in a call"
        elif isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
            return "star import"
        elif isinstance(node, ast.Global | ast.Nonlocal):
            return "global / nonlocal"
        elif isinstance(node, ast.Delete):
            return "del statement"
    return None


def _literal_columns(node: ast.AST) -> frozenset[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({node.value})
    if isinstance(node, ast.List | ast.Tuple) and node.elts:
        out: set[str] = set()
        for e in node.elts:
            if not (isinstance(e, ast.Constant) and isinstance(e.value, str)):
                return None
            out.add(e.value)
        return frozenset(out)
    return None


def column_uses(tree: ast.Module, name: str, ignore: frozenset[ast.AST] = frozenset()) -> Uses:
    """Columns of the frame bound to ``name`` that the cell reads, outside the ``ignore`` nodes.

    ``ignore`` holds AST nodes (the Name occurrences or whole sub-trees) the caller accounts for
    itself, typically the operation's own receiver. Rebinding or mutating ``name`` is refused.
    """
    why = cell_is_analysable(tree)
    if why:
        return Uses(None, why)
    par = parents(tree)
    skip: set[ast.AST] = set()
    for node in ignore:
        skip.update(ast.walk(node))
    cols: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Name) and node.id == name) or node in skip:
            continue
        if not isinstance(node.ctx, ast.Load):
            return Uses(None, f"{name} is rebound or deleted in the cell")
        parent = par.get(node)
        if isinstance(parent, ast.Subscript) and parent.value is node:
            if not isinstance(parent.ctx, ast.Load):
                return Uses(None, f"a column of {name} is assigned")
            got = _literal_columns(parent.slice)
            if got is None:
                return Uses(None, f"{name} is indexed with a non-literal key")
            # a subscript whose value is used with a method that reads other columns of the
            # SAME frame is impossible here: df["a"] is a Series
            cols |= got
            continue
        if isinstance(parent, ast.Attribute):
            return Uses(None, f"attribute access {name}.{parent.attr}")
        return Uses(None, f"{name} is used as a whole")
    return Uses(frozenset(cols))
