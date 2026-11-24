"""Static coverage CEILING of the v4 scope on the real DEV notebooks (``real_notebooks/``), as decided on 2026-11-24:
value_counts deferred, ``head`` / ``tail`` copies no-estimate, every remaining Should and Easy item assumed to land.

AST only (never executes a cell, reads no data). A cell counts if every detected operation would have a model:

* covered by v3 or landed in v4 (fillna incl. text, astype incl. several columns / dict, read_csv incl. parse_dates);
* Should / Easy, assumed to land: duplicated, dropna, reset_index, to_numpy, map with a dict / Series / ufunc / name
  (a NAME argument is counted as covered: OPTIMISTIC, it may be a function), numpy zeros / empty / linspace,
  ``np.array`` of a name (a literal stays UNKNOWN, prereg item (3)), sample, describe;
* copy: the adopted receiver forms only (a name, a column selection, a mask with comparisons only, an ``iloc`` slice);
  chains (``df.dropna().copy()``), masks with calls (``isin``) and ``head`` / ``tail`` copies are NOT covered;
* apply: only ``np.<ufunc>``;
* everything else (value_counts, to_csv, join, get_dummies, corr, ravel, sort_index, ...) is NOT covered.

The pre-registered dev target (>= 55%) is a RUN-TIME share; this name-and-form-level count is its static upper bound.

    PYTHONPATH="src;." python docs/benchmarks/phase8/coverage_ceiling.py real_notebooks > docs/benchmarks/phase8/coverage_ceiling.md
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "tools")
import static_ops  # noqa: E402

V3_OR_LANDED = {"groupby", "pandas.concat", "sort_values", "drop_duplicates", "merge", "set_index", "fillna",
                "astype", "pandas.read_csv", "operator.matmul", "numpy.sort"}  # fmt: skip
SHOULD_EASY = {"duplicated", "dropna", "reset_index", "numpy.zeros", "numpy.empty", "numpy.linspace",
               "sample", "describe"}  # fmt: skip
UFUNC_PREFIX = ("np.", "numpy.")


def _arg0(op) -> ast.AST | None:  # noqa: ANN001
    call = op.node
    return call.args[0] if getattr(call, "args", None) else None


def _mask_ok(node: ast.AST) -> bool:
    return not any(isinstance(n, ast.Call) for n in ast.walk(node))


def copy_covered(op) -> bool:  # noqa: ANN001
    recv = getattr(getattr(op.node, "func", None), "value", None)
    if isinstance(recv, ast.Name):
        return True
    if isinstance(recv, ast.Subscript):
        base, sl = recv.value, recv.slice
        if isinstance(base, ast.Name):
            if isinstance(sl, ast.Constant) or isinstance(sl, ast.List):
                return True
            return isinstance(sl, (ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp)) and _mask_ok(
                sl
            )
        if isinstance(base, ast.Attribute) and base.attr == "iloc":
            return isinstance(sl, ast.Slice)
    return False


def status(op) -> str:  # noqa: ANN001
    name = op.name
    if name == "copy":
        return "covered" if copy_covered(op) else "not covered"
    if name == "astype":
        recv = getattr(getattr(op.node, "func", None), "value", None)
        if isinstance(recv, ast.Subscript) and isinstance(recv.slice, ast.Constant):
            return "covered"
        return "not covered"
    if name == "pandas.read_csv" and "parse_dates" in op.kwargs:
        return "not covered"
    if name == "apply":
        a = _arg0(op)
        return (
            "covered"
            if a is not None and ast.unparse(a).startswith(UFUNC_PREFIX)
            else "not covered"
        )
    if name == "map":
        return "not covered"
    if name == "numpy.array":
        a = _arg0(op)
        return (
            "covered" if isinstance(a, (ast.Name, ast.Attribute, ast.Subscript)) else "not covered"
        )
    if name in V3_OR_LANDED or name in SHOULD_EASY:
        return "covered"
    return "not covered"


def main() -> None:
    from nexus.analyzer import analyze_cell, strip_magics

    with_op = full = 0
    calls: Counter = Counter()
    for path in sorted(Path(sys.argv[1]).glob("*.ipynb")):
        nb = json.loads(path.read_text(encoding="utf-8"))
        cells = [
            "".join(c.get("source", []))
            for c in nb.get("cells", [])
            if c.get("cell_type") == "code"
        ]
        ns = static_ops.notebook_alias_namespace(cells)
        for src in cells:
            try:
                ops = analyze_cell(strip_magics(src), ns)
            except Exception:  # noqa: BLE001  (unparseable cell)
                continue
            if not ops:
                continue
            with_op += 1
            sts = [status(o) for o in ops]
            for o, s in zip(ops, sts, strict=True):
                calls[(o.name, s)] += 1
            full += all(s != "not covered" for s in sts)
    share = full / with_op if with_op else float("nan")
    print("# v4 static coverage CEILING, real DEV notebooks\n")
    print(f"{with_op} code cells with a detected operation; **{full} ({share:.1%})** would have every operation "
          f"covered if every remaining Should / Easy item lands. Dev target (run-time share): >= 55% -> "
          f"**{'the ceiling allows it' if share >= 0.55 else 'BELOW the target even at the ceiling'}**.\n")  # fmt: skip
    print("| operation | calls | status |\n|---|---|---|")
    for (name, s), n in sorted(calls.items(), key=lambda x: (-x[1], x[0])):
        print(f"| `{name}` | {n} | {s} |")


if __name__ == "__main__":
    main()
