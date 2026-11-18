"""False negatives of the simulated OOM warning (development data): which points, what was predicted.

A point is *positive* at limit L if input bytes + measured peak exceed L (or it was killed by a cap
>= L); NEXUS *warns* if inspected bytes + predicted ``high`` (or ``expected``) exceed L. For every miss
the report also says whether the model-based planner rule (``benchmarks/planner``: baseline +
tightest ``high`` > L) would have flagged it.

    python -m benchmarks.oom_misses <results dir> [--limit-mb 2048] [--out FILE]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import load_joined, md_table
from benchmarks.planner import baseline_bytes
from benchmarks.suite import build_grid

MIB = 2**20


def misses(results: Path, limit_mb: int) -> pd.DataFrame:
    df = load_joined(results)
    limit = limit_mb * MIB
    est_in = {p.id: p.est_input_bytes() for p in build_grid("full", splits=("dev",))}
    rows = []
    for tier in (0, 1):
        d = df[(df["tier"] == tier) & (df["pred_status"] == "ok") & (df["status"] == "ok")]
        ram = d["ram_value"].fillna(d["ram_bound_bytes"]).fillna(0)
        positive = (d["input_bytes"].fillna(d["inspected_bytes"]) + ram) > limit
        for rule, col in (("high", "ram_high"), ("expected", "ram_expected")):
            warn = d["has_estimate"] & ((d["inspected_bytes"] + d[col]) > limit)
            for _, r in d[positive & ~warn].iterrows():
                planned = baseline_bytes(est_in.get(r["point_id"], 0)) + float(r["ram_high"])
                rows.append({
                    "tier": tier, "rule": rule, "point_id": r["point_id"],
                    "actual_MiB": r["ram_value"] / MIB if pd.notna(r["ram_value"]) else None,
                    "input_MiB": (r["input_bytes"] if pd.notna(r["input_bytes"]) else r["inspected_bytes"]) / MIB,
                    "predicted_MiB": r[col] / MIB, "low_MiB": r["ram_low"] / MIB,
                    "planner_footprint_MiB": planned / MIB, "planner_flags": planned > limit,
                })  # fmt: skip
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--limit-mb", type=int, default=2048)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    t = misses(a.results, a.limit_mb)
    text = f"# OOM false negatives at {a.limit_mb} MB (development data)\n\n" + (
        md_table(t) if len(t) else "none\n"
    )
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
