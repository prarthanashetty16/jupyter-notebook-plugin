"""Which existing development points the model-based planner would skip or flag.

For every development point with a stored actual and stored predictions it evaluates
``benchmarks.planner.decide`` (baseline + the tightest ``high``) against the cap the run used and
compares the verdict with what happened: measured fine (total RSS under the cap), killed by the cap,
or skipped before measuring by the old static rule. Reads development results only.

    python -m benchmarks.planner_report benchmarks/results/tier1-v2 --cap-gb 2.5 [--out FILE]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import load_joined, md_table
from benchmarks.planner import baseline_bytes, best_high
from benchmarks.suite import build_grid

GIB = 2**30


def _total_rss(row: pd.Series) -> float | None:
    """Baseline + incremental peak of a measured point (None when censored or killed)."""
    if row["status"] != "ok" or row["ram_class"] != "valid":
        return None
    return float(row["baseline_bytes"]) + float(row["ram_value"])


def report(results: Path, cap: int) -> tuple[pd.DataFrame, str]:
    df = load_joined(results)
    est_in = {p.id: p.est_input_bytes() for p in build_grid("full", splits=("dev",), max_size=None)}
    rows = []
    for pid, g in df.groupby("point_id"):
        preds = {
            int(t): r.to_dict()
            for t, (_, r) in zip(
                g["tier"].dropna(), g.dropna(subset=["tier"]).iterrows(), strict=False
            )
        }
        first = g.iloc[0]
        if pid not in est_in:
            continue
        high, source = best_high(
            {t: {**r, "features": r.get("features", "")} for t, r in preds.items()}
        )
        base = baseline_bytes(est_in[pid])
        planned = None if high is None else base + high
        total = _total_rss(first)
        rows.append({
            "point_id": pid, "status": first["status"], "source": source,
            "baseline_MiB": base / 2**20, "high_MiB": None if high is None else high / 2**20,
            "planned_GiB": None if planned is None else planned / GIB,
            "measured_total_GiB": None if total is None else total / GIB,
            "would_skip": planned is not None and planned > cap,
        })  # fmt: skip
    t = pd.DataFrame(rows)
    ran = t[t["status"] == "ok"]
    killed = t[t["status"] == "memory_limit"]
    lines = [
        f"# Model-based planner on the existing development points (cap {cap / GIB:.2f} GiB)\n"
    ]
    lines.append(
        f"Points with a stored actual and a prediction: {len(t)}. Measured fine (status ok): {len(ran)}; "
        f"killed by the cap: {len(killed)}; the old static rule skipped others before measuring "
        f"(they have no prediction here and are unchanged).\n"
    )
    would = ran[ran["would_skip"]]
    lines.append(
        f"* **Killed by the cap and now skipped before running:** "
        f"{int(killed['would_skip'].sum())} of {len(killed)}.\n"
        f"* **Measured fine but the planner would now skip (planned footprint above the cap; the "
        f"price of using an upper bound):** {len(would)} of {len(ran)} "
        f"({len(would) / max(len(ran), 1):.0%}); of these the measured total RSS was within "
        f"{(would['measured_total_GiB'].max() if len(would) else 0):.2f} GiB at most.\n"
    )
    if len(killed):
        lines.append("## Killed by the cap\n")
        lines.append(md_table(killed.drop(columns=["status"])))
    if len(would):
        lines.append("## Measured fine, would now be skipped\n")
        lines.append(
            md_table(
                would.drop(columns=["status", "would_skip"]).sort_values(
                    "planned_GiB", ascending=False
                )
            )
        )
    return t, "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--cap-gb", type=float, default=2.5)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    _, text = report(a.results, int(a.cap_gb * GIB))
    print(text)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
