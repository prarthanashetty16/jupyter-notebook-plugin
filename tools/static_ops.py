"""Static (AST-only) census of pandas / NumPy operations in notebooks.

Never executes cell code, never reads data, records nothing: it prints Markdown tables only. That is what lets it run
on a dev notebook set without turning it into measured data; it must still NOT be run on a held-out batch before the
models are frozen (the census itself reveals which operations the batch exercises).

Per operation: covered (a v3 model matches and has no argument limits), partial (a model exists but only for some
arguments / dtypes, which a static pass cannot always decide), not covered (no model).

Usage: ``python tools/static_ops.py <folder of .ipynb>`` (e.g. ``real_notebooks``).
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# v3 models whose coverage depends on arguments or dtypes (docs/benchmarks/phase7b/README.md)
PARTIAL = {
    "apply": "only Series.apply(np.<ufunc>)",
    "set_index": "only one numeric column key",
    "fillna": "not on text columns; scalar or dict value",
    "pandas.read_csv": "not parse_dates / text dtype / chunksize / low_memory=False",
    "astype": "single column df['c'].astype(...)",
    "merge": "two known frames",
    "copy": "known frame",
}


def notebook_alias_namespace(cells: list[str]) -> dict[str, object]:
    """Names the notebook binds to pandas / numpy, from its own import statements (parsed, not executed)."""
    ns: dict[str, object] = {"pd": pd, "np": np}
    for src in cells:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mod = {"pandas": pd, "numpy": np}.get(a.name)
                    if mod is not None:
                        ns[a.asname or a.name] = mod
    return ns


def classify(op, registry) -> str:  # noqa: ANN001
    """Coverage status of one analysed operation under the loaded registry."""
    models = registry.find(op)
    if not models:
        return "not covered"
    if op.name == "apply":
        arg = op.args[0] if op.args else op.kwargs.get("func")
        return (
            "covered"
            if isinstance(arg, str) and str(arg).startswith(("np.", "numpy."))
            else "not covered"
        )
    return "partial" if op.name in PARTIAL else "covered"


def main() -> None:
    """Print one table per notebook and a totals table."""
    from nexus.analyzer import analyze_cell, strip_magics
    from nexus.pipeline import load_builtin_models
    from nexus.registry import default_registry

    load_builtin_models()
    totals = {"code": 0, "with_op": 0, "fully": 0}
    all_ops: Counter = Counter()
    for path in sorted(Path(sys.argv[1]).glob("*.ipynb")):
        nb = json.loads(path.read_text(encoding="utf-8"))
        cells = [
            "".join(c.get("source", []))
            for c in nb.get("cells", [])
            if c.get("cell_type") == "code"
        ]
        ns = notebook_alias_namespace(cells)
        ops_count: Counter = Counter()
        with_op = fully = 0
        for src in cells:
            try:
                ops = analyze_cell(strip_magics(src), ns)
            except Exception:  # noqa: BLE001  (unparseable cell: no operation counted)
                continue
            if not ops:
                continue
            with_op += 1
            statuses = []
            for op in ops:
                st = classify(op, default_registry)
                ops_count[(op.name, st)] += 1
                statuses.append(st)
            fully += all(s != "not covered" for s in statuses)
        totals["code"] += len(cells)
        totals["with_op"] += with_op
        totals["fully"] += fully
        print(f"\n### {path.name}: {len(cells)} code cells, {with_op} with a pandas/NumPy operation, "
              f"{fully} with every operation at least partially modelled")  # fmt: skip
        print("| operation | cells' calls | NEXUS v3 |\n|---|---|---|")
        for (name, st), n in sorted(ops_count.items(), key=lambda x: (-x[1], x[0])):
            all_ops[(name, st)] += n
            note = f" ({PARTIAL[name]})" if st == "partial" else ""
            print(f"| `{name}` | {n} | {'**NOT COVERED**' if st == 'not covered' else st + note} |")
    print(f"\n### Totals: {totals['code']} code cells, {totals['with_op']} with an operation, {totals['fully']} with every "
          "operation at least partially modelled")  # fmt: skip
    print("| operation | calls | NEXUS v3 |\n|---|---|---|")
    for (name, st), n in sorted(all_ops.items(), key=lambda x: (-x[1], x[0])):
        print(f"| `{name}` | {n} | {'**NOT COVERED**' if st == 'not covered' else st} |")


if __name__ == "__main__":
    main()
