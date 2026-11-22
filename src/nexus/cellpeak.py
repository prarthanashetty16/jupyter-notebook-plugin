"""Cell-level peak RAM from the operations' estimates, in statement order (Phase 6c).

Replaces the v1 aggregation (``nexus.risk.combine``: max of the expected values, SUM of the highs),
which under-predicted cells with several retained loads (Phase 8a: 0.56x) and gave 17-29 GiB highs for
cells that used 3.8 GiB. Pre-registered in ``docs/benchmarks/phase6c-preregistration.md``:

    peak = max over operations o, in evaluation order, of
           retained(before o's statement) + temporaries(o's statement, before o) + peak(o)

for each of low / expected / high, using each operation's own range. ``peak(o)`` is the operation's
incremental peak (it includes its result); a result's size is ``models._output.output_range`` (the
whole peak when not derived: conservative). Liveness rules, conservative where unclear:

* an assignment keeps the result of its OUTERMOST modelled operation(s) (those not nested inside
  another modelled call: the end of a chain, ``concat``'s result rather than its inputs, every element
  of a tuple of calls) until an explicit ``del`` of a name bound to it in this cell; rebinding a name is
  NOT a release; an assignment to a subscript / attribute keeps it too (the result now lives in an object);
* earlier operations of the same statement (chain links, call arguments) stay alive until it ends;
* an expression statement's results are released after it, except for the last statement of the cell
  (IPython keeps its value in the output history);
* operations inside loops, comprehensions, lambdas, function / class bodies or ``try`` / ``with``
  blocks: the cell falls back to the v1 aggregation (flag "cell model: v1 aggregation (...)").

Times are summed as before (the time models are per operation; nothing changes there). The baseline is
the state resident before the cell: every figure is incremental.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from typing import Any

from nexus.models._output import output_range
from nexus.models.base import Estimate

FALLBACK_NODES = (
    ast.For, ast.AsyncFor, ast.While, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Try,
    ast.With, ast.AsyncWith, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Lambda,
)  # fmt: skip
if hasattr(ast, "TryStar"):
    FALLBACK_NODES = (*FALLBACK_NODES, ast.TryStar)
FLAG_V1 = "cell model: v1 aggregation"
BINDING = (ast.Assign, ast.AnnAssign, ast.AugAssign)


def _key(node: ast.AST) -> tuple[Any, ...]:
    return tuple(
        getattr(node, a, None) for a in ("lineno", "col_offset", "end_lineno", "end_col_offset")
    )


def _end(node: ast.AST) -> tuple[int, int]:
    return (getattr(node, "end_lineno", 0) or 0, getattr(node, "end_col_offset", 0) or 0)


def _contains(outer: ast.AST, inner: ast.AST) -> bool:
    return outer is not inner and any(n is inner for n in ast.walk(outer))


def _flatten(body: Sequence[ast.stmt]) -> list[ast.stmt]:
    """Top-level statements in order; both branches of an ``if`` run in sequence (conservative)."""
    out: list[ast.stmt] = []
    for st in body:
        if isinstance(st, ast.If):
            out.extend(_flatten(st.body))
            out.extend(_flatten(st.orelse))
        else:
            out.append(st)
    return out


def _bound_names(st: ast.stmt) -> list[str]:
    targets: list[ast.AST] = []
    if isinstance(st, ast.Assign):
        targets = list(st.targets)
    elif isinstance(st, (ast.AnnAssign, ast.AugAssign)):
        targets = [st.target]
    names = []
    for t in targets:
        for n in ast.walk(t):
            if isinstance(n, ast.Name):
                names.append(n.id)
    return names


def _v1(estimates: list[Estimate]) -> Estimate | None:
    from nexus.risk import combine

    return combine(estimates)


def cell_estimate(  # noqa: C901
    source: str, op_estimates: Sequence[Any]
) -> tuple[Estimate | None, str, list[str]]:
    """(cell estimate, mode, flags). ``op_estimates``: objects with ``op`` (``DetectedOp``),
    ``model``, ``estimate`` and ``features`` (``pipeline.OpEstimate``). Mode ``statements`` or ``v1``."""
    ests = [o.estimate for o in op_estimates]
    if not ests:
        return None, "none", []
    from nexus.analyzer import strip_magics

    try:
        tree = ast.parse(strip_magics(source))
    except SyntaxError:
        return _v1(ests), "v1", [f"{FLAG_V1} (source not parsed)"]
    by_pos = {_key(n): n for n in ast.walk(tree) if isinstance(n, ast.Call)}
    nodes = []
    for o in op_estimates:
        node = by_pos.get(_key(o.op.node))
        if node is None:
            return _v1(ests), "v1", [f"{FLAG_V1} (operation not located)"]
        nodes.append(node)
    statements = _flatten(tree.body)
    owner: list[int] = []
    for node in nodes:
        idx = next(
            (i for i, st in enumerate(statements) if any(n is node for n in ast.walk(st))), None
        )
        if idx is None:
            return _v1(ests), "v1", [f"{FLAG_V1} (operation outside a statement)"]
        st = statements[idx]
        if isinstance(st, FALLBACK_NODES) or any(
            isinstance(n, FALLBACK_NODES) and _contains(n, node) for n in ast.walk(st)
        ):
            kind = type(st).__name__ if isinstance(st, FALLBACK_NODES) else "comprehension / lambda"
            return _v1(ests), "v1", [f"{FLAG_V1} (operation inside {kind})"]
        owner.append(idx)
    if len(op_estimates) == 1:  # one operation: the cell's peak IS its peak (estimate unchanged)
        return ests[0], "statements", []
    outs = []
    for o in op_estimates:
        r = output_range(o.model, o.features or {}, o.estimate)
        e = o.estimate
        outs.append(
            r if r is not None else (float(e.ram_low), float(e.ram_expected), float(e.ram_high))
        )
    peaks = [(float(e.ram_low), float(e.ram_expected), float(e.ram_high)) for e in ests]
    retained = [0.0, 0.0, 0.0]
    bound: dict[str, list[tuple[float, float, float]]] = {}
    best = [0.0, 0.0, 0.0]
    last = len(statements) - 1
    for si, st in enumerate(statements):
        if isinstance(st, ast.Delete):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    for amount in bound.pop(t.id, []):
                        for i in range(3):
                            retained[i] = max(retained[i] - amount[i], 0.0)
            continue
        mine = sorted((k for k, s in enumerate(owner) if s == si), key=lambda k: _end(nodes[k]))
        if not mine:
            continue
        temps = [0.0, 0.0, 0.0]
        for k in mine:
            for i in range(3):
                best[i] = max(best[i], retained[i] + temps[i] + peaks[k][i])
                temps[i] += outs[k][i]
        if isinstance(st, BINDING) or si == last:
            top = [
                k for k in mine if not any(_contains(nodes[j], nodes[k]) for j in mine if j != k)
            ]
            kept = [0.0, 0.0, 0.0]
            for k in top:
                for i in range(3):
                    kept[i] += outs[k][i]
            for i in range(3):
                retained[i] += kept[i]
            for name in _bound_names(st):
                bound.setdefault(name, []).append((kept[0], kept[1], kept[2]))
    lo, mid, hi = sorted(best)
    top_k = max(range(len(ests)), key=lambda k: peaks[k][1])
    worst = ests[top_k]
    cell = Estimate(
        ram_low=int(lo), ram_expected=int(mid), ram_high=int(max(hi, mid)),
        time_low=sum(e.time_low for e in ests), time_expected=sum(e.time_expected for e in ests),
        time_high=sum(e.time_high for e in ests), confidence=min(e.confidence for e in ests),
        tier=max(e.tier for e in ests), drivers=list(worst.drivers),
        note=next((e.note for e in ests if e.note), None),
        flags=tuple(dict.fromkeys(f for e in ests for f in e.flags)),
    )  # fmt: skip
    return cell, "statements", []
