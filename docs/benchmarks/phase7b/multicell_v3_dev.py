"""Phase 7b dev evaluation: the v1 multi-statement cells (all 33 configurations / 66 cells: the Phase 6c dev part
and the former held-out part, dev since 2026-11-22) re-predicted with the v3 working tree (prediction only, in
fresh processes) and scored on their STORED actuals, next to the stored v2 predictions.

    PYTHONPATH=. python docs/benchmarks/phase7b/multicell_v3_dev.py [--allow-battery] > docs/benchmarks/phase7b/multicell_v3_dev.md
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.childproc import ChildFailureError, run_child
from benchmarks.multicell import cases
from benchmarks.multicell.run import CACHE, MIB, _predict_child, _table, metrics
from benchmarks.powerguard import BATTERY_NOTE, power_record

PARTS = {"dev": Path("benchmarks/results/multicell/dev/results.jsonl"),
         "former held-out (dev)": Path("benchmarks/results/multicell/heldout/results.jsonl")}  # fmt: skip


def main() -> None:
    import sys

    rec = power_record("--allow-battery" in sys.argv[1:], "dev")
    from benchmarks.multicell.run import _log_access

    _log_access("READ stored former held-out multicell rows (dev since 2026-11-22) | reason: Phase 7b dev "
                "evaluation of the v3 working tree (prediction only, no measurement)")  # fmt: skip
    rows = []
    for part, path in PARTS.items():
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if not r.get("actual"):
                continue
            cell = cases.Cell(cases.Config(r["template"], r["shape"]), r["rows"])
            paths = cases.prepare(CACHE, r["shape"], r["rows"])
            try:
                pred = run_child(_predict_child, paths, cases.source(cell, paths), timeout_s=600)
            except ChildFailureError as fail:
                rows.append({**r, "part": part, "harness": fail.record()})
                continue
            rows.append(
                {
                    **r,
                    "part": part,
                    "v2": r["new"],
                    "new": pred["new"],
                    "v3_uncovered": pred["uncovered"],
                }
            )
    scored = [r for r in rows if not r.get("harness")]
    print("# Multi-statement cells v1 (all 66, DEV): v3 working tree vs stored v2 predictions\n")
    if rec["power"] != "mains":
        print(f"{BATTERY_NOTE}\n\nPower: `{json.dumps(rec, default=str)}`\n")
    print(f"Prediction only (fresh processes), stored actuals; power {rec['power']}. Harness events: "
          f"{[(r['id'], r['harness']['status']) for r in rows if r.get('harness')] or 'none'}.\n")  # fmt: skip
    print("\n".join(_table([{"model": "v3 (cellpeak, v3 models)", **metrics(scored, "new")},
                            {"model": "v2 (stored)", **metrics(scored, "v2")}])))  # fmt: skip
    for part in PARTS:
        g = [r for r in scored if r["part"] == part]
        print(f"\n## {part}\n")
        print(
            "\n".join(
                _table([{"model": "v3", **metrics(g, "new")}, {"model": "v2", **metrics(g, "v2")}])
            )
        )
    print("\n## Per template (v3 vs v2 bias; v3 uncovered operations)\n")
    per = []
    for t in sorted({r["template"] for r in scored}):
        g = [r for r in scored if r["template"] == t]
        m3, m2 = metrics(g, "new"), metrics(g, "v2")
        per.append({"template": t, "n": m3.get("n", 0), "v3_bias": m3.get("bias", float("nan")),
                    "v2_bias": m2.get("bias", float("nan")), "v3_err_med": m3.get("err_med", float("nan")),
                    "v3_above_high": m3.get("above_high", float("nan")), "v3_coverage": m3.get("coverage", float("nan")),
                    "v3_uncovered_ops": sum(r["v3_uncovered"] for r in g)})  # fmt: skip
    print("\n".join(_table(per)))
    above = [r for r in scored if r.get("new") and r["actual"] > r["new"]["ram_high"]]
    print(
        f"\nCells above the v3 high: {[(r['id'], round(r['actual'] / MIB), round(r['new']['ram_high'] / MIB)) for r in above] or 'none'}"
    )


if __name__ == "__main__":
    main()
