"""Static coverage of notebook cells (DEV information; the Phase 8b criterion's measure, never executed):
the share of code cells with >= 1 detected operation whose EVERY detected operation has a matching model.

Run once with the v3 working tree and once with ``models-frozen-v2`` (a git worktree on PYTHONPATH):

    PYTHONPATH=<tree>/src:. python docs/benchmarks/phase7b/static_coverage.py <nb> [<nb> ...]

Static: a matching model may still refuse at run time (unknown shapes, unsupported arguments), so this is
an upper bound of the share that gets an estimate. Prints counts and per-operation gaps only (no code).
"""

from __future__ import annotations

import json
import sys
from collections import Counter

import numpy as np
import pandas as pd


def main() -> None:
    import nexus
    from nexus.analyzer import analyze_cell, strip_magics
    from nexus.pipeline import load_builtin_models
    from nexus.registry import default_registry

    load_builtin_models()
    ns = {"pd": pd, "np": np}
    cells = with_op = full = 0
    missing: Counter[str] = Counter()
    for path in sys.argv[1:]:
        nb = json.load(open(path, encoding="utf-8"))
        for c in nb.get("cells", []):
            if c.get("cell_type") != "code":
                continue
            src = "".join(c.get("source", []))
            cells += 1
            try:
                ops = analyze_cell(strip_magics(src), ns)
            except Exception:  # noqa: BLE001
                continue
            if not ops:
                continue
            with_op += 1
            gaps = [o.name for o in ops if not default_registry.find(o)]
            full += not gaps
            missing.update(gaps)
    print(json.dumps({"nexus": nexus.__file__, "code_cells": cells, "cells_with_op": with_op,
                      "fully_matched": full, "share": full / max(with_op, 1),
                      "unmatched_ops": dict(missing.most_common(15))}))  # fmt: skip


if __name__ == "__main__":
    main()
