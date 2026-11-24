"""Dev evaluation of one v4 item: every measured multicell cell (v1 / v2 / v3; dev parts and the consumed held-out
parts) predicted by the v3 models and by the working tree, scored on the stored actuals.

Categories: cells newly estimated by the tree (v3 had no cell range: an uncovered operation, no estimate), cells that
lost their estimate, and cells both estimate (where W(a) applies). Highs are the model highs: the item C factors are
computed once, on the final v4 models, so no calibration is applied here.

    python -m benchmarks.v4_item_eval --v3-tree src/nexus:38d1ec5d9126ea43 --item "1a text fillna" --out <md>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from benchmarks import upper_calibration as uc

REASON = "v4 item dev evaluation (prediction only)"


def _cells(tree: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in uc.REPREDICT_CACHE.open(encoding="utf-8"):
        r = json.loads(line)
        if r["tree"] == tree:
            out[r["id"]] = r
    return out


def _actuals() -> dict[str, dict[str, Any]]:
    from benchmarks.multicell.run import SUITES
    from benchmarks.multicell.split import consumed_heldout_results

    out = {}
    for v in uc.MULTICELL_VERSIONS:
        for path in (SUITES[v][1] / "dev" / "results.jsonl", consumed_heldout_results(v, REASON)):
            for line in path.open(encoding="utf-8"):
                r = json.loads(line)
                if r.get("actual") and not r.get("censored") and r.get("status") == "ok":
                    out[f"v{v}|{r['id']}"] = {"actual": float(r["actual"]), "config": f"mc{v}:{r['config']}",
                                              "template": r["template"]}  # fmt: skip
    return out


def _row(key: str, act: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    c = p["cell"]
    return {"id": key, "unit": act["config"], "template": act["template"], "actual": act["actual"],
            "low": float(c["ram_low"]), "expected": float(c["ram_expected"]), "high": float(c["ram_high"]),
            "tier": c["tier"]}  # fmt: skip


def _line(name: str, d: pd.DataFrame) -> str:
    if d.empty:
        return f"| {name} | 0 | 0 | - | - | - | - | - | - |"
    s = uc.summary(d, d["high"])
    return (f"| {name} | {s['points']} | {s['configs']} | {s['above_pts']} ({s['above_pts_rate']:.1%}) | "
            f"{s['above_cfg']} ({s['above_cfg_rate']:.1%}) | {s['median_err']:.1%} | {s['coverage']:.1%} | "
            f"{s['width_med']:.2f} | {s['width_p90']:.2f} |")  # fmt: skip


def evaluate(v3_tree: str, item: str) -> str:
    uc.multicell_points(repredict=True)  # fills the cache for the working tree
    tree = uc._tree_state()
    a, b, act = _cells(v3_tree), _cells(tree), _actuals()
    new, lost, both_a, both_b = [], [], [], []
    for key, x in act.items():
        pa, pb = a.get(key), b.get(key)
        if pa is None or pb is None:
            continue
        ea, eb = uc._exclusion(pa), uc._exclusion(pb)
        if ea is not None and eb is None:
            new.append(_row(key, x, pb))
        elif ea is None and eb is not None:
            lost.append({"id": key, "why": eb})
        elif ea is None and eb is None:
            both_a.append(_row(key, x, pa))
            both_b.append(_row(key, x, pb))
    dn, da, db = pd.DataFrame(new), pd.DataFrame(both_a), pd.DataFrame(both_b)
    changed = (
        (da["expected"] != db["expected"]) | (da["high"] != db["high"])
        if not da.empty
        else pd.Series()
    )
    wa = (
        ((db["high"] / db["expected"]) / (da["high"] / da["expected"]))
        if not da.empty
        else pd.Series()
    )
    nl = chr(10)
    head = ("| cells | points | configs | above high (points) | above high (configs) | median error | coverage | "
            "high/expected median | p90 |")  # fmt: skip
    lines = [
        f"# v4 item {item}: DEV evaluation (multicell cells, prediction only)",
        "",
        f"v3 models `{v3_tree}`; working tree `{tree}`. Model highs (no item C factors yet). "
        f"Measured cells with a prediction in both: {sum(1 for k in act if k in a and k in b)}.",
        "",
        head,
        "|---|---|---|---|---|---|---|---|---|",
        _line("NEW: estimated by the tree, not by v3", dn),
        _line("both, v3 prediction", da),
        _line("both, tree prediction", db),
        _line("both, changed by the item (tree)", db[changed.values] if not db.empty else db),
        "",
        f"* Cells that lost their estimate: {len(lost)} {[(x['id'], x['why']) for x in lost][:10]}",
        f"* W(a) on cells both estimate: median {wa.median():.3f} (bar 1.30); cells whose prediction changed: "
        f"{int(changed.sum()) if len(changed) else 0}.",
        "* W(b) on NEW cells: " + (f"median {(dn['high'] / dn['expected']).median():.2f} (bar 2.0), p90 "
                                    f"{(dn['high'] / dn['expected']).quantile(0.9):.2f} (bar 4.0); "
                                    f"{len(dn)} cells" + (" (< 30: INCONCLUSIVE)." if len(dn) < 30 else ".") if not dn.empty else "no new cell."),
        "",
        "NEW cells (template, actual / low / expected / high MiB):",
        "",
    ]  # fmt: skip
    for _, r in dn.sort_values("id").iterrows() if not dn.empty else []:
        m = 2**20
        lines.append(f"* `{r['id']}`: {r['actual'] / m:.0f} / {r['low'] / m:.0f} / {r['expected'] / m:.0f} / "
                     f"{r['high'] / m:.0f}" + ("  **ABOVE HIGH**" if r["actual"] > r["high"] else ""))  # fmt: skip
    return nl.join(lines) + nl


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.v4_item_eval")
    ap.add_argument("--v3-tree", required=True)
    ap.add_argument("--item", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    from benchmarks.powerguard import power_record

    power_record(False, "dev")
    text = evaluate(args.v3_tree, args.item)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
