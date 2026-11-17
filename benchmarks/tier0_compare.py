"""Before/after Tier 0 comparison on IDENTICAL measurements (Phase 4a).

``before`` and ``after`` are two results directories whose ``actuals.csv`` are the same
measurements and whose ``predictions.csv`` come from the old and the new models. Metrics are
computed per operation and, separately, for the development group (``dev``, where the changes were
derived) and the held-out ``exposed-v1`` group (validation of the dev-derived changes; development
and diagnosis only, never a final claim). The sealed ``test-v2`` group is never read.

    python -m benchmarks.tier0_compare benchmarks/results/full benchmarks/results/tier0-v2 \
        docs/benchmarks/tier0-v2
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import Floors, accuracy_table, load_joined, md_table

KEEP = ["points", "ram_valid", "ram_censored", "ram_excluded", "ram_err_med", "ram_err_p90",
        "ram_bias", "ram_cov", "ram_above_high", "ram_below_low", "ram_width"]  # fmt: skip
TIME_KEEP = [c.replace("ram_", "time_") for c in KEEP]


def metrics(directory: Path, floors: Floors | None = None) -> pd.DataFrame:
    """Tier 0 accuracy table per (op, split) plus pooled ``ALL`` rows."""
    df = load_joined(directory, floors)
    df = df[df["tier"] == 0]
    df = df.assign(split=df["origin"])  # dev vs the former exposed-v1 (both are dev)
    parts = [accuracy_table(df, ["op", "split"])]
    pooled = accuracy_table(df.assign(op="ALL"), ["op", "split"])
    return pd.concat([parts[0], pooled], ignore_index=True)


def time_predictions_identical(before: Path, after: Path) -> bool:
    """True if every Tier 0 time prediction is unchanged (Phase 4a must not touch time models)."""
    b = load_joined(before)
    a = load_joined(after)
    cols = ["point_id", "time_low", "time_expected", "time_high"]
    m = b[b["tier"] == 0][cols].merge(a[a["tier"] == 0][cols], on="point_id", suffixes=("_b", "_a"))
    for c in cols[1:]:
        both = m[[f"{c}_b", f"{c}_a"]].dropna()
        if not (
            (both[f"{c}_b"] - both[f"{c}_a"]).abs() <= 1e-9 * both[f"{c}_b"].abs() + 1e-12
        ).all():
            return False
    return len(m) > 0


def side_by_side(
    before: pd.DataFrame, after: pd.DataFrame, split: str, metric: str
) -> pd.DataFrame:
    cols = KEEP if metric == "ram" else TIME_KEEP
    b = before[before["split"] == split].set_index("op")[[c for c in cols if c in before]]
    a = after[after["split"] == split].set_index("op")[[c for c in cols if c in after]]
    joined = b.join(a, lsuffix="_before", rsuffix="_after", how="outer")
    order = sorted(joined.index, key=lambda o: (o == "ALL", o))
    return joined.loc[order].reset_index()


def point_table(before: Path, after: Path) -> pd.DataFrame:
    """One row per RAM-valid point: actual, old and new expected/low/high, folds."""
    b, a = load_joined(before), load_joined(after)
    keep = ["point_id", "op", "case", "split", "size", "ram_class", "ram_value"]
    b, a = b[b["tier"] == 0], a[a["tier"] == 0]
    cols = ["ram_low", "ram_expected", "ram_high"]
    out = b[keep + cols].merge(
        a[["point_id", *cols]], on="point_id", suffixes=("_before", "_after")
    )
    out["fold_before"] = out["ram_expected_before"] / out["ram_value"]
    out["fold_after"] = out["ram_expected_after"] / out["ram_value"]
    return out.sort_values(["op", "case", "size"])


def write(before: Path, after: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    mb, ma = metrics(before), metrics(after)
    lines = [
        "# Tier 0 before/after (Phase 4a)",
        "",
        f"Before: `{before.name}` predictions (first-draft models). After: `{after.name}` "
        "predictions (Phase 4a models). **Both are scored against the same measurements**, so "
        "every difference is the model change. `dev` is where the changes were derived; "
        "`exposed-v1` is the held-out validation (development and diagnosis only, never a final "
        "claim). test-v2 is sealed and was not read.",
        "",
        "bias = median(expected/actual) (>1 over-predicts); coverage = share of valid points with "
        "actual in [low, high]; width = mean (high-low)/expected; err = |expected-actual|/actual. "
        "Only `valid` points enter the metrics; censored/excluded counts shown.",
        "",
        "Time predictions unchanged by this phase: "
        f"**{time_predictions_identical(before, after)}**.",
        "",
    ]
    for metric, title in (("ram", "RAM"), ("time", "Time")):
        for split in ("dev", "exposed-v1"):
            t = side_by_side(mb, ma, split, metric)
            t.to_csv(out_dir / f"{metric}_{split}.csv", index=False)
            pct = tuple(
                c for c in t.columns if any(k in c for k in ("cov", "above", "below", "err"))
            )
            lines += [f"## {title}, {split}", "", md_table(t, pct=pct), ""]
    pts = point_table(before, after)
    pts.to_csv(out_dir / "points_ram.csv", index=False)
    path = out_dir / "before_after.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    print(write(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))


if __name__ == "__main__":
    main()
