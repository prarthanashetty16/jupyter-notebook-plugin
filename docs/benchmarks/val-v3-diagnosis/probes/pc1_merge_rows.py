"""(c) merge: Tier 1's output-row estimate and interval vs the true output rows, and the RAM formula
evaluated at the TRUE row count (is the error in M, or in the formula given M?).

Reads the stored actuals of the former val-v3 merge points (dev since split v4) for ``out_rows`` and
``ram``; re-runs the Tier 1 statistics on the regenerated inputs (cached on disk).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd  # noqa: E402

from benchmarks import workers  # noqa: E402
from benchmarks.suite import build_grid  # noqa: E402
from nexus.models.merge import MergeModel  # noqa: E402

MIB = 2**20

if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "merge/"
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    act = pd.read_csv(ROOT / "benchmarks/results/dev-v4-before/actuals.csv").set_index("point_id")
    grid = [
        p
        for p in build_grid("full", splits=("dev",), max_size=3_000_000)
        if pattern in p.id and p.id.startswith("v3/") and p.size <= 3_000_000
    ]
    cache = ROOT / "benchmarks" / ".cache"
    for pt in grid:
        a = act.loc[pt.id]
        if a.status != "ok":
            continue
        state = workers.build_state(
            {"inputs": list(pt.inputs), "source": pt.source, "cache_dir": str(cache)}
        )
        true_rows = int(a.out_rows)
        ram = json.loads(a.ram_delta_all)
        ram_actual = sorted(ram)[len(ram) // 2] / MIB
        for tier in (0, 1):
            out = workers.predict(state, tier=tier)
            est = out["estimates"][0]
            f = est["features"]
            o = f["out_rows"]
            line = (
                f"{pt.id:52s} T{tier} out_rows est (low/mid/high) = "
                f"{o[0]:>12,.0f} {o[1]:>12,.0f} {o[2]:>12,.0f}   TRUE {true_rows:>12,}"
            )
            m = MergeModel
            at_true = (
                m.ram_at(
                    f,
                    true_rows,
                    left_elided=bool(f.get("left_elided", False)),
                    right_distinct=(f.get("right_distinct") or (f["n_right"],) * 3)[1],
                    right_unique=bool(f.get("right_unique", True)),
                )
                / MIB
            )
            print(line)
            print(
                f"{'':52s}    RAM actual {ram_actual:7.1f}  est {est['ram_low'] / MIB:7.1f}/"
                f"{est['ram_expected'] / MIB:7.1f}/{est['ram_high'] / MIB:7.1f}  formula at TRUE M {at_true:7.1f}"
                f"   tier1={f.get('tier1')}  elided={f.get('left_elided')} unique={f.get('right_unique')}"
            )
