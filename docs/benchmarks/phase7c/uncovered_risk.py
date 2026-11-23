"""Phase 7c item 1 (information only, DEV): risk class of the v3 engine for multi-statement cells with uncovered
operations, at simulated headrooms. Prediction only (fresh processes) on the v1 cells (all dev); stored actuals.

For every cell with an uncovered operation, and for the two cells above the v3 high: the class at each headroom,
whether it is ever OK, whether the class is OK while the ACTUAL exceeds the headroom (a missed overrun), and
whether the UNKNOWN message names the uncovered operation.

    PYTHONPATH=. python docs/benchmarks/phase7c/uncovered_risk.py [--allow-battery] > docs/benchmarks/phase7c/uncovered_risk.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from benchmarks.childproc import run_child
from benchmarks.multicell import cases
from benchmarks.multicell.run import CACHE, load_inputs
from benchmarks.powerguard import BATTERY_NOTE, power_record

MIB = 2**20
HEADROOMS_MIB = (64, 128, 256, 512, 1024, 2048, 4096, 8192)
PARTS = (
    Path("benchmarks/results/multicell/dev/results.jsonl"),
    Path("benchmarks/results/multicell/heldout/results.jsonl"),
)


def child(paths: dict[str, str], src: str) -> dict:
    from dataclasses import replace

    from nexus.cellpeak import cell_estimate
    from nexus.pipeline import Pipeline
    from nexus.risk import classify, describe_uncovered, warn_high_estimate

    rep = Pipeline(tier=1).run(src, load_inputs(paths, src))
    covered = {id(e.op) for e in rep.estimates}
    missing = [o for o in rep.ops if id(o) not in covered]
    cell, _, _ = cell_estimate(src, rep.estimates)
    warn, _, _ = cell_estimate(
        src, [replace(e, estimate=warn_high_estimate(e)) for e in rep.estimates]
    )
    out = {}
    for h in HEADROOMS_MIB:  # the same call risk.assess makes, with a simulated headroom
        r = classify([e.estimate for e in rep.estimates], None, headroom=h * MIB, uncovered=len(missing),
                     drivers_from=rep.estimates or None, cell=cell, warn_high=warn.ram_high,
                     uncovered_ops=describe_uncovered(missing) if missing else None)  # fmt: skip
        out[h] = {"class": r.risk.value, "reason": r.reason}
    return {
        "missing": [describe_uncovered([o]) for o in missing],
        "high": cell.ram_high,
        "classes": out,
    }


def main() -> None:
    rec = power_record("--allow-battery" in sys.argv[1:], "dev")
    from benchmarks.multicell.run import _log_access

    _log_access("READ stored former held-out multicell rows (dev since 2026-11-22) | reason: Phase 7c item 1, "
                "risk class of cells with uncovered operations (prediction only)")  # fmt: skip
    print(
        "# Multi-statement dev cells: v3 risk class where an operation is uncovered (Phase 7c, DEV, information only)\n"
    )
    if rec["power"] != "mains":
        print(f"{BATTERY_NOTE}\n\nPower: `{json.dumps(rec, default=str)}`\n")
    print("Prediction only on the v1 cells (66, all dev; stored actuals). A **missed overrun** = class OK while the actual "
          "exceeds the simulated headroom.\n")  # fmt: skip
    print("| cell | actual MiB | v3 high MiB | uncovered | " + " | ".join(f"{h}" for h in HEADROOMS_MIB)
          + " | ever OK | missed overrun | UNKNOWN names it |")  # fmt: skip
    print("|---|---|---|---|" + "---|" * len(HEADROOMS_MIB) + "---|---|---|")
    n_unc = n_ok = n_missed = 0
    for path in PARTS:
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            if not r.get("actual"):
                continue
            cell = cases.Cell(cases.Config(r["template"], r["shape"]), r["rows"])
            paths = cases.prepare(CACHE, r["shape"], r["rows"])
            res = run_child(child, paths, cases.source(cell, paths), timeout_s=600)
            above = r["actual"] > res["high"]
            if not res["missing"] and not above:
                continue
            n_unc += bool(res["missing"])
            classes = res["classes"]
            ever_ok = any(c["class"] == "OK" for c in classes.values())
            missed = any(c["class"] == "OK" and r["actual"] > h * MIB for h, c in classes.items())
            names = [c["reason"] for c in classes.values() if c["class"] == "UNKNOWN"]
            named = (
                all(any(m.strip("`") in t for m in res["missing"]) for t in names)
                if names and res["missing"]
                else None
            )
            n_ok += ever_ok
            n_missed += missed
            print(f"| {r['id']}{' (above high)' if above else ''} | {r['actual'] / MIB:.0f} | {res['high'] / MIB:.0f} | "
                  f"{', '.join(res['missing']) or '-'} | " + " | ".join(c["class"] for c in classes.values())
                  + f" | {ever_ok} | {missed} | {named} |")  # fmt: skip
    print(
        f"\nCells with an uncovered operation: {n_unc}; ever OK: {n_ok}; missed overruns: {n_missed}."
    )


if __name__ == "__main__":
    main()
