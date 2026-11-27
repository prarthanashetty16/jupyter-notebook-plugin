"""v4 item (1b) copy -> fillna, DIAGNOSTIC per-statement measurement (dev; no bar).

The dev cells ``x = df.copy(); y = x.fillna(0)`` (multicell v3 template ``copy_then_fillna``) measure 0.9-1.6% above a
cell high equal to its expected (Tier 0: the fillna runs on a frame made in the cell). To locate the gap, each prefix of
the cell and each statement on its own is measured on the same cached inputs (OS peak, fresh process, inputs from disk,
median of 3), next to the model's per-operation estimate:

1. ``x = df.copy()`` (the copy alone);
2. ``y = df.fillna(0)`` (the fillna alone, on the loaded frame);
3. ``x = df.copy(); y = x.fillna(0)`` (the cell).

    python docs/benchmarks/phase8/probes/p8_copy_fillna_steps.py > docs/benchmarks/phase8/probes/p8_copy_fillna_steps.out
    python docs/benchmarks/phase8/probes/p8_copy_fillna_steps.py 5000000 > docs/benchmarks/phase8/probes/p8_copy_fillna_cells_1b.out

With a row count argument it is the item (1b) adoption probe: every shape at >= 200 MiB, bar +-15% on the CELL row
(numeric: num; text: text, textwide; mixed: mixed, narrow).
"""

from __future__ import annotations

import gc
from typing import Any

import pandas as pd

from benchmarks.multicell import cases_v3
from benchmarks.multicell.run import SUITES
from nexus.measure import measure_call

MIB = 2**20
STEPS = {
    "1 copy alone": "x = df.copy()",
    "2 fillna alone": "y = df.fillna(0)",
    "3 cell": "x = df.copy()\ny = x.fillna(0)",
}


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def predicted(path: str, src: str) -> list[tuple[str, int, float, float, float]]:
    from nexus.cellpeak import cell_estimate
    from nexus.pipeline import Pipeline

    ns = setup(path, src)
    rep = Pipeline(tier=1).run(src, ns)
    out = [(e.model, e.estimate.tier, e.estimate.ram_low / MIB, e.estimate.ram_expected / MIB,
            e.estimate.ram_high / MIB) for e in rep.estimates]  # fmt: skip
    cell, _m, _f = cell_estimate(src, rep.estimates)
    if cell is not None and len(rep.estimates) > 1:
        out.append(
            ("CELL", cell.tier, cell.ram_low / MIB, cell.ram_expected / MIB, cell.ram_high / MIB)
        )
    return out


def main() -> None:
    cache = SUITES[3][2]
    print(f"pandas {pd.__version__}")
    print("| shape@rows | step | measured MiB | model (name, tier, low / expected / high MiB) |")
    print("|---|---|---|---|")
    import sys

    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2_500_000
    shapes = ("num", "narrow", "text", "textwide") + (("mixed",) if len(sys.argv) > 1 else ())
    for shape in shapes:
        path = cases_v3.prepare(cache, shape, rows)["df"]
        for label, src in STEPS.items():
            m = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
            got = "censored" if m.delta_bytes is None else f"{m.delta_bytes / MIB:.1f}"
            pred = "; ".join(
                f"{n} T{t} {lo:.1f} / {ex:.1f} / {hi:.1f}"
                for n, t, lo, ex, hi in predicted(path, src)
            )
            print(f"| {shape}@{rows} | {label} | {got} | {pred} |")


if __name__ == "__main__":
    main()
