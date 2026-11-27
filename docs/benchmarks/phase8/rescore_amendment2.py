"""Amendment 2 re-score: items (1a) / (1b) dev cells on the displayed v4 high, item C factor fitted
leave-one-configuration-out (LOCO) on all dev configurations except the scored one.

    PYTHONPATH=. python docs/benchmarks/phase8/rescore_amendment2.py > docs/benchmarks/phase8/rescore_amendment2.md
"""

from __future__ import annotations

import re
from pathlib import Path

from benchmarks import upper_calibration as uc

MIB = 2**20
SINGLE = Path(
    "benchmarks/results/phase7b-dev-final"
)  # fillna / copy are not in the single-op suite


def main() -> None:
    pts = uc.all_points(SINGLE, repredict=True)  # multicell re-predicted on the working tree
    lo = uc.loco(pts)
    new_ids = re.findall(
        r"`(v\d\|[^`]+)`",
        Path("docs/benchmarks/phase8/item1b_copy_fillna_dev.md").read_text(encoding="utf-8"),
    )
    groups = {
        "item (1b): copy -> fillna cells": [
            i for i in new_ids if "copy_then_fillna" in i or "copy_fillna" in i
        ],
        "item (1a): the six flagged text_fillna_cols cells": [
            i for i in new_ids if "text_fillna_cols" in i
        ],
        "all 52 cells new in v4 so far": new_ids,
    }
    print("# Amendment 2 re-score (dev): displayed v4 high, item C factor fitted LOCO\n")
    print(f"Tree `{uc._tree_state()}`; {len(pts)} dev points, {pts['unit'].nunique()} configurations. "
          "Displayed high = max(model high, expected x q), q from the item C procedure on every configuration except "
          "the scored one.\n")  # fmt: skip
    print(
        "| group | cells | above model high | above displayed (LOCO) high | max actual / displayed high |"
    )
    print("|---|---|---|---|---|")
    by_id = pts.set_index("id", drop=False) if "id" in pts else None
    for name, ids in groups.items():
        sel = pts[pts["id"].isin(ids)]
        missing = sorted(set(ids) - set(sel["id"]))
        above_m = int((sel["actual"] > sel["high"]).sum())
        above_d = int((sel["actual"] > lo[sel.index]).sum())
        worst = float((sel["actual"] / lo[sel.index]).max()) if len(sel) else float("nan")
        print(f"| {name} | {len(sel)} | {above_m} | **{above_d}** | {worst:.3f} |")
        if missing:
            print(f"|  (not in the residual set: {missing}) |  |  |  |  |")
    del by_id
    print("\n## Per cell (actual / expected / model high / displayed LOCO high, MiB)\n")
    for i in groups["all 52 cells new in v4 so far"]:
        r = pts[pts["id"] == i]
        if r.empty:
            print(f"* `{i}`: not in the residual set")
            continue
        k = r.index[0]
        flag = "  **ABOVE DISPLAYED HIGH**" if r.at[k, "actual"] > lo[k] else ""
        print(f"* `{i}`: {r.at[k, 'actual'] / MIB:.1f} / {r.at[k, 'expected'] / MIB:.1f} / {r.at[k, 'high'] / MIB:.1f} / "
              f"{lo[k] / MIB:.1f}{flag}")  # fmt: skip


if __name__ == "__main__":
    main()
