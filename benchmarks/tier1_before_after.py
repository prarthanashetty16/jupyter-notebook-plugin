"""Before/after comparison of Tier 0 and Tier 1 RAM predictions on IDENTICAL measurements (4b.2).

``before`` and ``after`` are results directories with the same development ``actuals.csv`` rows
(the original dev cases plus the former val-v3, dev since split version 4) and the predictions of
the old and the new models. Tables are per operation, per origin (``dev`` = original dev incl.
exposed-v1, ``val-v3`` = the former held-out group, which the fixes were *informed* by: its rows are
no longer evidence of generalisation), counted per point and per configuration. Only development
data is read; ``sealed/`` and ``validation/`` are never touched.

    python -m benchmarks.tier1_before_after benchmarks/results/dev-v4-before \
        benchmarks/results/tier1-v2 docs/benchmarks/tier1-v2
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import Floors, accuracy_table, load_joined, md_table

COLS = ["ram_n", "ram_err_med", "ram_err_p90", "ram_bias", "ram_cov", "ram_above_high",
        "ram_below_low", "ram_width"]  # fmt: skip
PCT = {"ram_err_med", "ram_err_p90", "ram_cov", "ram_above_high", "ram_below_low", "ram_width"}


def _frame(directory: Path, tier: int, floors: Floors | None) -> pd.DataFrame:
    df = load_joined(directory, floors)
    df = df[(df["tier"] == tier) & (df["ram_class"] == "valid") & ~df["ram_lower_bound"]]
    return df.assign(split=df["origin"].where(df["origin"].isin(["val-v3", "val-v4"]), "dev"))


def table(df: pd.DataFrame) -> pd.DataFrame:
    parts = [
        accuracy_table(df, ["op", "split"]),
        accuracy_table(df.assign(op="ALL"), ["op", "split"]),
    ]
    return pd.concat(parts, ignore_index=True)


def per_config(df: pd.DataFrame) -> pd.DataFrame:
    """Configurations (cases) with at least one point above the predicted high, per operation."""
    d = df.assign(above=df["ram_value"] > df["ram_high"], below=df["ram_value"] < df["ram_low"])
    g = (
        d.groupby(["op", "split", "case"])
        .agg(above=("above", "any"), below=("below", "any"))
        .reset_index()
    )
    out = g.groupby(["op", "split"]).agg(configs=("case", "count"), cfg_above_high=("above", "mean"),
                                         cfg_below_low=("below", "mean")).reset_index()  # fmt: skip
    total = g.assign(op="ALL").groupby(["op", "split"]).agg(configs=("case", "count"), cfg_above_high=("above", "mean"),
                                                            cfg_below_low=("below", "mean")).reset_index()  # fmt: skip
    return pd.concat([out, total], ignore_index=True)


def side_by_side(before: pd.DataFrame, after: pd.DataFrame, split: str) -> pd.DataFrame:
    keep = [c for c in COLS if c in before and c in after]
    b = before[before["split"] == split].set_index("op")[keep]
    a = after[after["split"] == split].set_index("op")[keep]
    j = b.join(a, lsuffix="_before", rsuffix="_after", how="outer")
    return j.loc[sorted(j.index, key=lambda o: (o == "ALL", o))].reset_index()


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 3:
        raise SystemExit(__doc__)
    before_dir, after_dir, out = Path(args[0]), Path(args[1]), Path(args[2])
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# Tier 1 before / after the 4b.2 fixes (development data only)\n",
             "Identical measured actuals; `before` = predictions of the 4b models, `after` = the 4b.2 models. "
             "RAM, valid points, memory-limit lower bounds excluded. `val-v3` = the former held-out group: "
             "the fixes were informed by its failures, so its numbers are NOT evidence of generalisation "
             "(val-v4 is).\n"]  # fmt: skip
    for tier in (1, 0):
        tb = table(_frame(before_dir, tier, None))
        ta = table(_frame(after_dir, tier, None))
        cb = per_config(_frame(before_dir, tier, None))
        ca = per_config(_frame(after_dir, tier, None))
        tb.to_csv(out / f"tier{tier}_before.csv", index=False)
        ta.to_csv(out / f"tier{tier}_after.csv", index=False)
        for split in ("dev", "val-v3", "val-v4"):
            lines.append(f"\n## Tier {tier}: {split} (per point)\n")
            lines.append(
                md_table(
                    side_by_side(tb, ta, split), {c + s for c in PCT for s in ("_before", "_after")}
                )
            )
            lines.append(
                f"\n### Tier {tier}: {split} (per configuration: share with any point above high / below low)\n"
            )
            j = (
                cb[cb["split"] == split]
                .set_index("op")
                .join(ca[ca["split"] == split].set_index("op"), lsuffix="_before", rsuffix="_after")
            )
            lines.append(
                md_table(
                    j.drop(columns=["split_before", "split_after"]).reset_index(),
                    {
                        "cfg_above_high_before",
                        "cfg_above_high_after",
                        "cfg_below_low_before",
                        "cfg_below_low_after",
                    },
                )
            )
    (out / "before_after.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out / 'before_after.md'}")


if __name__ == "__main__":
    main()
