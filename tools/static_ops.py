"""Static (AST-only) census of pandas / NumPy operations in notebooks.

Never executes cell code, never reads data, records nothing: it prints Markdown tables only. That is what lets it run
on a dev notebook set without turning it into measured data; it must still NOT be run on a held-out batch before the
models are frozen (the census itself reveals which operations the batch exercises).

Per operation: name-covered (at least one registry model matches the operation name) or not covered. This intentionally
ignores arguments, receiver forms and live state, so its cell share is an OVERSTATING ceiling on run-time coverage.

Usage: ``python tools/static_ops.py <folder of .ipynb> --model-version <tag>``.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


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
    """Whether an operation name has a registered model, ignoring its arguments."""
    return "covered" if registry.find(op) else "not covered"


def main(argv: list[str] | None = None) -> None:
    """Print the name-only, overstating coverage ceiling for a notebook folder."""
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--model-version", required=True)
    args = ap.parse_args(argv)

    from nexus.analyzer import analyze_cell, strip_magics
    from nexus.pipeline import load_builtin_models
    from nexus.registry import default_registry

    load_builtin_models()
    totals = {"code": 0, "with_op": 0, "fully": 0}
    all_ops: Counter = Counter()
    for path in sorted(args.folder.glob("*.ipynb")):
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
        print(f"\n### {path.name}: {len(cells)} code cells, {with_op} with an operation, "
              f"{fully} name-covered (OVERSTATING)")  # fmt: skip
        print("| operation | calls | name match |\n|---|---|---|")
        for (name, st), n in sorted(ops_count.items(), key=lambda x: (-x[1], x[0])):
            all_ops[(name, st)] += n
            print(f"| `{name}` | {n} | {'yes' if st == 'covered' else '**NO**'} |")
    share = totals["fully"] / totals["with_op"] if totals["with_op"] else 0.0
    print(f"\nModel version: `{args.model_version}`.")
    print(f"Static name-match share (OVERSTATING): {totals['fully']}/{totals['with_op']} "
          f"({share:.1%}); it ignores arguments, receivers, runtime state and deadlines.")  # fmt: skip
    print(f"\n### Totals: {totals['code']} code cells, {totals['with_op']} with an operation, "
          f"{totals['fully']} name-covered (OVERSTATING)")  # fmt: skip
    print("| operation | calls | name match |\n|---|---|---|")
    for (name, st), n in sorted(all_ops.items(), key=lambda x: (-x[1], x[0])):
        print(f"| `{name}` | {n} | {'yes' if st == 'covered' else '**NO**'} |")


if __name__ == "__main__":
    main()
