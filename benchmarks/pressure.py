"""Memory-pressure screen for time measurements (Phase 4a, step 0).

Superlinear time slopes at 10M rows could be paging, not algorithmics. A run is *suspect* when any
of these held (rules fixed before the data was looked at; thresholds are deliberately round):

* the machine's available RAM fell below the operation's own absolute footprint (baseline + peak)
  plus 1 GiB, at start or at its lowest polled value;
* swap/pagefile use rose by more than 64 MiB while the operation ran;
* the child took more than 3x the page faults its peak footprint explains (one soft fault per
  4 KiB page touched once): re-touching reclaimed pages is the signature of working-set trimming;
* (Unix only) any major page fault.

Usage::

    python -m benchmarks.pressure benchmarks/results/pressure-check [more dirs ...]

Prints one row per point and writes ``pressure.csv`` next to each ``actuals.csv``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

GIB = 2**30
MIB = 2**20
PAGE = 4096


def _med(text: object) -> float | None:
    try:
        vals = [v for v in json.loads(str(text)) if v is not None]
    except (ValueError, TypeError):
        return None
    return float(sorted(vals)[len(vals) // 2]) if vals else None


def screen(actuals: pd.DataFrame) -> pd.DataFrame:
    """One row per measured point with the pressure evidence and a ``suspect`` verdict."""
    rows = []
    for _, r in actuals[actuals["status"] == "ok"].iterrows():
        ram = _med(r.get("ram_delta_all"))
        t = _med(r.get("time_s_all"))
        base = float(r.get("baseline_bytes") or 0)
        peak_abs = base + (ram if ram is not None else float(r.get("ram_bound_bytes") or 0))
        avail0, availmin = r.get("avail_start_bytes"), r.get("avail_min_bytes")
        have = pd.notna(avail0) and str(avail0) != ""
        faults = _med(r.get("page_faults_all"))
        major = _med(r.get("major_faults_all"))
        swap = _med(r.get("swap_rise_all")) or 0.0
        reasons = []
        if have:
            need = peak_abs + GIB
            if float(avail0) < need:
                reasons.append("avail_start<footprint+1GiB")
            if float(availmin) < need:
                reasons.append("avail_min<footprint+1GiB")
        else:
            reasons.append("no_pressure_data")
        if swap > 64 * MIB:
            reasons.append("swap_rise>64MiB")
        explained = peak_abs / PAGE
        if faults is not None and faults > 3 * explained:
            reasons.append("faults>3x_footprint_pages")
        if major:
            reasons.append("major_faults")
        rows.append(
            {
                "point_id": r["point_id"],
                "split": r.get("split"),
                "size": r["size"],
                "time_s": t,
                "peak_footprint_MiB": round(peak_abs / MIB),
                "avail_start_MiB": round(float(avail0) / MIB) if have else None,
                "avail_min_MiB": round(float(availmin) / MIB) if have else None,
                "faults_per_footprint_page": round(faults / explained, 2) if faults else None,
                "swap_rise_MiB": round(swap / MIB, 1),
                "suspect": bool(reasons),
                "reasons": ",".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def slopes(screened: pd.DataFrame, floor_s: float = 0.1) -> pd.DataFrame:
    """Log-log slope of time vs size per scenario: all valid points, and non-suspect points only.

    Only points above the time floor count. ``slope_clean`` needs two non-suspect sizes.
    """
    import numpy as np

    rows = []
    df = screened.assign(scenario=screened["point_id"].str.split("|n=", regex=False).str[0])
    for scenario, grp in df.groupby("scenario"):
        grp = grp[grp["time_s"] >= floor_s].sort_values("size")

        def fit(g: pd.DataFrame) -> float | None:
            if len(g) < 2 or g["size"].nunique() < 2:
                return None
            return float(np.polyfit(np.log(g["size"].astype(float)), np.log(g["time_s"]), 1)[0])

        clean = grp[~grp["suspect"]]
        rows.append(
            {
                "scenario": scenario,
                "points": len(grp),
                "suspect": int(grp["suspect"].sum()),
                "slope_all": fit(grp),
                "clean_points": len(clean),
                "slope_clean": fit(clean),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for arg in sys.argv[1:]:
        path = Path(arg)
        out = screen(pd.read_csv(path / "actuals.csv"))
        out.to_csv(path / "pressure.csv", index=False)
        with pd.option_context("display.width", 250, "display.max_rows", 500):
            print(out.drop(columns=["split"]).to_string(index=False))
        sl = slopes(out)
        sl.to_csv(path / "pressure_slopes.csv", index=False)
        print()
        print(sl.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
