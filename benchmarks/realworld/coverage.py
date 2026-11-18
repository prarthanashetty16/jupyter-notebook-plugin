"""How much real notebook code do NEXUS's estimators and the Tier 2 safety analyzer cover?

    python -m benchmarks.realworld.coverage <folder with .ipynb files> [--out DIR] [--min-cells N]

For every code cell of every notebook under the folder (recursively) it reports

1. whether the code analyzer detects a supported operation (the ones Tier 0 / Tier 1 have a model for,
   i.e. where an estimate could be produced given live data);
2. whether the Tier 2 safety analyzer would accept the cell, and if not, why;
3. which Tier 2 relaxation PROPOSAL would unlock it (counting only: nothing is changed, see
   ``benchmarks.multistatement_report``), and a ranking of the proposals by cells unlocked.

It NEVER executes cell code. A notebook is parsed as JSON, a cell as text (``ast.parse``); the analyzers
only walk syntax trees. Because there is no live kernel, operands are STAND-INS: every name used as an
operand is bound to a small pandas DataFrame (or a numeric array where the cell does matrix algebra or
``np.sort``) whose columns are the string literals of the cell, and ``pd`` / ``np`` and ``from pandas
import x`` names are bound to the real modules from the notebook's own imports. A literal file path is
treated as existing (the file is not on this machine). A relaxation's "unlock" means: after the
simulated source rewrite described in ``PROPOSALS`` the unchanged analyzer accepts the cell.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import numpy as np
import pandas as pd

from benchmarks.multistatement_report import classify
from nexus.analyzer import analyze_cell, strip_magics
from nexus.dryrun_safety import analyze_safety
from nexus.models.builtin import load_builtin_models
from nexus.registry import default_registry

PROPOSALS = {
    "P1": "resolve non-literal arguments from literal assignments (names bound to a str / number / list of them)",
    "P2": "per-statement dry runs (accept a multi-statement cell if one statement alone is accepted)",
    "P3": "whitelisted chains (run the innermost supported operation of a chain)",
    "P4": "pure result wrappers after a supported operation (.head / .tail / .reset_index / .copy)",
    "P5": "filters before a supported operation (boolean mask, .query, .loc, .dropna)",
    "P6": "aggregation dictionaries / names in groupby(...).agg(...)",
    "P7": "imports of pandas / numpy / time in front of a supported statement",
    "P8": "bare function names imported from pandas / numpy (`from pandas import read_csv`; `read_csv(...)`)",
}
WRAPPERS = frozenset({"head", "tail", "reset_index", "copy"})
FILTER_METHODS = frozenset({"query", "loc", "dropna", "rename"})
SAFE_IMPORTS = frozenset({"pandas", "numpy", "time", "warnings"})


@dataclass
class CellRecord:
    notebook: str
    index: int
    source_lines: int
    parses: bool
    detected_ops: list[str] = field(default_factory=list)
    supported: bool = False  # a Tier 0 / Tier 1 model matches at least one detected operation
    accepted: bool = False  # the Tier 2 safety analyzer accepts the cell
    reason: str = ""
    reason_class: str = ""
    unlocked_by: list[str] = field(default_factory=list)


# -- notebooks -------------------------------------------------------------------------------------------------
def code_cells(path: Path) -> Iterator[str]:
    """Source text of the code cells of one notebook (nbformat 4, or 3's worksheets); never executes anything."""
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    cells = data.get("cells")
    if cells is None:  # nbformat 3
        cells = [c for ws in data.get("worksheets", []) for c in ws.get("cells", [])]
    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        src = cell.get("source", cell.get("input", ""))
        yield "".join(src) if isinstance(src, list) else str(src)


def notebooks(folder: Path) -> list[Path]:
    return sorted(folder.rglob("*.ipynb"))


# -- the stand-in namespace -------------------------------------------------------------------------------------
class StandIns(dict):
    """Namespace that answers every unknown name with a small stand-in object (see the module docstring)."""

    def __init__(self, base: dict[str, Any], columns: list[str], arrays: set[str]) -> None:
        super().__init__(base)
        self._columns, self._arrays = columns, arrays

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str)

    def __getitem__(self, name: str) -> Any:
        if name in self.keys():
            return dict.__getitem__(self, name)
        if name in self._arrays:
            return np.ones((4, 4))
        frame = pd.DataFrame({c: np.arange(8.0) for c in (self._columns or ["x"])})
        dict.__setitem__(self, name, frame)
        return frame


def _string_constants(tree: ast.AST) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and 0 < len(node.value) < 64
        ):
            if node.value not in out:
                out.append(node.value)
    return out


def _array_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
            names |= {n.id for n in (node.left, node.right) if isinstance(n, ast.Name)}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"matmul", "dot", "sort"}
        ):
            names |= {a.id for a in node.args if isinstance(a, ast.Name)}
    return names


def import_namespace(sources: list[str]) -> dict[str, Any]:  # noqa: C901
    """Names the notebook binds through pandas / numpy imports, as the real modules / functions (no cell code runs)."""
    ns: dict[str, Any] = {}
    for src in sources:
        try:
            tree = ast.parse(strip_magics(src))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == "pandas":
                        ns[a.asname or "pandas"] = pd
                    elif a.name == "numpy":
                        ns[a.asname or "numpy"] = np
            elif isinstance(node, ast.ImportFrom) and node.module in ("pandas", "numpy"):
                mod = pd if node.module == "pandas" else np
                for a in node.names:
                    if hasattr(mod, a.name):
                        ns[a.asname or a.name] = getattr(mod, a.name)
    ns.setdefault(
        "pd", pd
    )  # most notebooks follow the convention even when the import cell is missing
    ns.setdefault("np", np)
    return ns


def literal_bindings(sources: list[str]) -> dict[str, Any]:
    """Notebook-level ``name = <literal>`` assignments (for the P1 count only)."""
    out: dict[str, Any] = {}
    for src in sources:
        try:
            tree = ast.parse(strip_magics(src))
        except SyntaxError:
            continue
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError, TypeError):
                    continue
                if isinstance(value, (str, int, float, bool, list, tuple)):
                    out[node.targets[0].id] = value
    return out


# -- verdicts ----------------------------------------------------------------------------------------------------
def verdict(source: str, base: dict[str, Any]) -> tuple[bool, str]:
    """Tier 2 safety verdict with stand-in operands. Returns (accepted, first reason)."""
    try:
        tree = ast.parse(strip_magics(source))
    except SyntaxError:
        return False, "does not parse as Python"
    ns = StandIns(base, _string_constants(tree), _array_names(tree))
    with mock.patch(
        "nexus.dryrun_safety.os.path.isfile", lambda p: True
    ):  # the literal file is not on this machine
        v = analyze_safety(source, ns)
    return v.safe, ("" if v.safe else v.reasons[0])


def _detected(source: str, base: dict[str, Any]) -> list[str]:
    try:
        return [op.name for op in analyze_cell(source, base)]
    except Exception:
        return []


def _supported(source: str, base: dict[str, Any]) -> bool:
    try:
        ops = analyze_cell(source, base)
    except Exception:
        return False
    return any(default_registry.find(op) for op in ops)


# -- relaxation simulations (source rewrites; the analyzer itself is untouched) ---------------------------------------
def _try(tree: ast.AST, base: dict[str, Any]) -> bool:
    src = ast.unparse(ast.fix_missing_locations(tree))
    return verdict(src, base)[0]


class _Literalize(ast.NodeTransformer):
    def __init__(self, bindings: dict[str, Any]) -> None:
        self.bindings, self.hit = bindings, False

    def visit_Name(self, node: ast.Name) -> ast.AST:  # noqa: N802
        if isinstance(node.ctx, ast.Load) and node.id in self.bindings:
            self.hit = True
            return ast.copy_location(
                ast.parse(repr(self.bindings[node.id]), mode="eval").body, node
            )
        return node


class _Strip(ast.NodeTransformer):
    """Unwrap trailing wrappers / filtered receivers / agg arguments, depending on ``mode``."""

    def __init__(self, mode: str) -> None:
        self.mode, self.hit = mode, False

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)  # type: ignore[assignment]
        f = node.func
        if self.mode == "P4" and isinstance(f, ast.Attribute) and f.attr in WRAPPERS:
            self.hit = True
            return f.value
        if self.mode == "P5" and isinstance(f, ast.Attribute) and f.attr in FILTER_METHODS:
            self.hit = True
            return f.value
        if self.mode == "P6" and isinstance(f, ast.Attribute) and f.attr == "agg":
            self.hit = True
            return ast.copy_location(
                ast.Call(
                    func=ast.Attribute(value=f.value, attr="sum", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                ),
                node,
            )
        return node

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)  # type: ignore[assignment]
        if self.mode == "P5" and isinstance(
            node.slice, (ast.Compare, ast.BoolOp, ast.UnaryOp, ast.BinOp, ast.Call, ast.Attribute)
        ):
            self.hit = True
            return node.value
        return node


class _Qualify(ast.NodeTransformer):
    """P8: ``read_csv(x)`` imported with ``from pandas import read_csv`` -> ``pd.read_csv(x)``."""

    def __init__(self, base: dict[str, Any]) -> None:
        self.base, self.hit = base, False

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)  # type: ignore[assignment]
        f = node.func
        obj = self.base.get(f.id) if isinstance(f, ast.Name) else None
        mod = getattr(obj, "__module__", "") or ""
        if (
            obj is not None
            and callable(obj)
            and mod.split(".")[0] in ("pandas", "numpy")
            and f.id not in ("pd", "np")
        ):
            root = "pd" if mod.startswith("pandas") else "np"
            self.hit = True
            node.func = ast.Attribute(
                value=ast.Name(id=root, ctx=ast.Load()),
                attr=getattr(obj, "__name__", f.id),
                ctx=ast.Load(),
            )
        return node


def _innermost_supported(tree: ast.Module, base: dict[str, Any]) -> bool:
    """P3: does some call inside a chain, taken alone, pass the analyzer?"""
    for stmt in tree.body[:1] if len(tree.body) == 1 else []:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and node is not getattr(stmt, "value", None):
                if verdict(ast.unparse(node), base)[0]:
                    return True
    return False


def unlocked_by(source: str, base: dict[str, Any], literals: dict[str, Any]) -> list[str]:
    """Which proposals, applied alone as a source rewrite, make the (rejected) cell acceptable."""
    try:
        tree = ast.parse(strip_magics(source))
    except SyntaxError:
        return []
    out: list[str] = []
    lit = _Literalize(literals)
    t1 = lit.visit(ast.parse(strip_magics(source)))
    if lit.hit and _try(t1, base):
        out.append("P1")
    if len(tree.body) > 1 and any(verdict(ast.unparse(s), base)[0] for s in tree.body):
        out.append("P2")
    if _innermost_supported(tree, base) and len(tree.body) == 1:
        out.append("P3")
    for mode in ("P4", "P5", "P6"):
        s = _Strip(mode)
        t = s.visit(ast.parse(strip_magics(source)))
        if s.hit and _try(t, base):
            out.append(mode)
    q = _Qualify(base)
    tq = q.visit(ast.parse(strip_magics(source)))
    if q.hit and _try(tq, base):
        out.append("P8")
    kept = [
        s
        for s in tree.body
        if not (isinstance(s, (ast.Import, ast.ImportFrom)) and _safe_import(s))
    ]
    if len(kept) < len(tree.body) and kept and _try(ast.Module(body=kept, type_ignores=[]), base):
        out.append("P7")
    return out


def _safe_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.Import):
        return all(a.name.split(".")[0] in SAFE_IMPORTS for a in node.names)
    return isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in SAFE_IMPORTS


# -- the study -----------------------------------------------------------------------------------------------------------
def study(folder: Path) -> tuple[list[CellRecord], dict[str, int]]:
    load_builtin_models()
    records: list[CellRecord] = []
    stats = {"notebooks": 0, "unreadable_notebooks": 0, "code_cells": 0, "blank_cells": 0}
    for nb in notebooks(folder):
        try:
            sources = list(code_cells(nb))
        except (OSError, ValueError, AttributeError):
            stats["unreadable_notebooks"] += 1
            continue
        stats["notebooks"] += 1
        base, literals = import_namespace(sources), literal_bindings(sources)
        for i, src in enumerate(sources):
            stats["code_cells"] += 1
            body = strip_magics(src).strip()
            if not body or all(
                line.strip().startswith("#") or not line.strip() for line in body.splitlines()
            ):
                stats["blank_cells"] += 1
                continue
            ok, reason = verdict(src, base)
            parses = reason != "does not parse as Python"
            rec = CellRecord(str(nb.relative_to(folder)), i, len(src.splitlines()), parses, _detected(src, base),
                             _supported(src, base), ok, reason, "" if ok else (classify(reason) if parses else "does not parse as Python"))  # fmt: skip
            if not ok and parses:
                rec.unlocked_by = unlocked_by(src, base, literals)
            records.append(rec)
    return records, stats


def pct(a: int, b: int) -> str:
    return f"{a} ({a / b:.0%})" if b else "0"


def report(records: list[CellRecord], stats: dict[str, int]) -> str:
    n = len(records)
    sup = [r for r in records if r.supported]
    acc = [r for r in records if r.accepted]
    sup_acc = [r for r in sup if r.accepted]
    lines = [
        "# Real-notebook coverage (static analysis; no cell code was executed)\n",
        f"{stats['notebooks']} notebooks read ({stats['unreadable_notebooks']} unreadable), {stats['code_cells']} code cells, "
        f"{stats['blank_cells']} blank / comment-only; **{n} cells analysed**.\n",
        "## Headline\n",
        "| question | cells | share of analysed |",
        "|---|---|---|",
        f"| a supported operation is detected (an estimate is possible with live data) | {len(sup)} | {len(sup) / n:.0%} |"
        if n
        else "| - | 0 | - |",
        f"| the Tier 2 safety analyzer accepts the cell | {len(acc)} | {len(acc) / n:.0%} |"
        if n
        else "",
        f"| supported operation AND accepted by Tier 2 | {len(sup_acc)} | {len(sup_acc) / n:.0%} |"
        if n
        else "",
        f"\nAmong the {len(sup)} cells with a supported operation, Tier 2 accepts {pct(len(sup_acc), len(sup))}.\n",
        "## By detected operation\n",
        "| operation | cells containing it | accepted by Tier 2 |",
        "|---|---|---|",
    ]
    ops = Counter(o for r in records for o in set(r.detected_ops))
    for op, k in ops.most_common():
        a = sum(1 for r in records if op in r.detected_ops and r.accepted)
        lines.append(f"| {op} | {k} | {pct(a, k)} |")
    lines += [
        "\n## Why cells are rejected by the Tier 2 safety analyzer\n",
        "| reason | all cells | cells with a supported operation |",
        "|---|---|---|",
    ]
    all_r = Counter(r.reason_class for r in records if not r.accepted)
    sup_r = Counter(r.reason_class for r in sup if not r.accepted)
    for why, k in all_r.most_common():
        lines.append(f"| {why} | {pct(k, n)} | {pct(sup_r.get(why, 0), len(sup))} |")
    rej_sup = [r for r in sup if not r.accepted]
    lines += ["\n## Candidate ranking of the Tier 2 relaxation proposals (COUNTING ONLY; nothing is implemented)\n",
              f"Among the {len(rej_sup)} rejected cells with a supported operation (and, for reference, all {n - len(acc)} rejected cells), "
              "how many each proposal would unlock when applied ALONE as the source rewrite described in the module docstring:\n",
              "| rank | proposal | unlocks (supported-op cells) | unlocks (all rejected cells) | description |", "|---|---|---|---|---|"]  # fmt: skip
    counts = {
        p: (
            sum(p in r.unlocked_by for r in rej_sup),
            sum(p in r.unlocked_by for r in records if not r.accepted),
        )
        for p in PROPOSALS
    }
    for rank, (p, (a, b)) in enumerate(
        sorted(counts.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0])), 1
    ):
        lines.append(
            f"| {rank} | {p} | {pct(a, len(rej_sup))} | {pct(b, n - len(acc))} | {PROPOSALS[p]} |"
        )
    union = sum(1 for r in rej_sup if r.unlocked_by)
    lines.append(f"\nAny one proposal would unlock {pct(union, len(rej_sup))} of the rejected supported-operation cells; "
                 f"{len(rej_sup) - union} would stay rejected (mutation, control flow, unsupported operations, unparseable code).\n")  # fmt: skip
    lines += ["## Method and limits\n", "* operands are stand-ins (see the module docstring); a cell that only works with real column names, dtypes or files may be classified differently on a live kernel;",
              "* \"supported operation\" is detection by the syntactic analyzer plus a matching Tier 0 / 1 model, not a proof that live data would yield an estimate;",
              "* an unlock is a source rewrite accepted by the UNCHANGED analyzer: it says nothing about whether the relaxation is safe (see the risks in `docs/benchmarks/phase4d-dev/multistatement.md`);",
              "* a handful of notebooks says little: the percentages come from the folder you provided, not from notebooks in general."]  # fmt: skip
    return "\n".join(x for x in lines if x is not None) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", type=Path, help="folder with .ipynb files (searched recursively)")
    ap.add_argument("--out", type=Path, help="write coverage.md, cells.csv and summary.json here")
    ap.add_argument(
        "--min-cells", type=int, default=0, help="exit with an error if fewer cells were analysed"
    )
    ap.add_argument(
        "--heldout",
        action="store_true",
        help="Phase 8a held-out use: abort unless the working tree is the frozen model stack "
        "(benchmarks.frozen) and record its commit in summary.json",
    )
    args = ap.parse_args(argv)
    frozen: dict[str, object] = {}
    if args.heldout:
        from benchmarks.frozen import NotFrozenError, require_frozen

        try:
            frozen = require_frozen()
        except NotFrozenError as exc:
            raise SystemExit(str(exc)) from None
    if not args.folder.is_dir():
        raise SystemExit(f"{args.folder} is not a folder")
    records, stats = study(args.folder)
    text = report(records, stats)
    print(text)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "coverage.md").write_text(text, encoding="utf-8")
        pd.DataFrame(
            [
                {
                    **r.__dict__,
                    "detected_ops": ",".join(r.detected_ops),
                    "unlocked_by": ",".join(r.unlocked_by),
                }
                for r in records
            ]
        ).to_csv(args.out / "cells.csv", index=False)
        n = len(records)
        (args.out / "summary.json").write_text(json.dumps({**stats, **frozen, "analysed": n, "supported": sum(r.supported for r in records),
                                                           "accepted": sum(r.accepted for r in records)}, indent=2), encoding="utf-8")  # fmt: skip
    return 1 if len(records) < args.min_cells else 0


if __name__ == "__main__":
    raise SystemExit(main())
