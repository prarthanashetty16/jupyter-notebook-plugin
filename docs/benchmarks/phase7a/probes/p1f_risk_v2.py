"""Phase 7a item 1f (design only, STORED dev data, no new measurement): risk-v2 candidates C0-C3.

Applies the rule committed beforehand in ``docs/benchmarks/phase7a/risk_v2_selection_rule.md``
(commit f8e4eba) exactly as written. The classes come from the frozen ``nexus.risk.classify``
through ``benchmarks.risk_eval.evaluate``; only the ``high`` given to it changes per candidate.

    python docs/benchmarks/phase7a/probes/p1f_risk_v2.py > docs/benchmarks/phase7a/probes/p1f_risk_v2.out
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from benchmarks.evaluate import load_joined
from benchmarks.risk_eval import (
    FAR_PER_OP_TARGET,
    FAR_TARGET,
    HIGH_PRECISION_TARGET,
    MIN_POSITIVES,
    RECALL_TARGET,
    evaluate,
)

V2 = Path("benchmarks/results/phase6c-dev")
OWN = Path("benchmarks/results/tier1-v3")


def _used(f: object) -> bool:
    d = json.loads(f) if isinstance(f, str) else (f if isinstance(f, dict) else {})
    return bool((d.get("tier1") or {}).get("used"))


def candidate_frames() -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    v2 = load_joined(V2)
    own = load_joined(OWN)
    own1 = own[own["tier"] == 1].set_index("point_id")
    info: dict[str, object] = {}
    swaps: dict[str, dict[str, float]] = {"pandas.read_csv": {}, "merge": {}}
    for op in swaps:
        rows = v2[(v2["tier"] == 1) & (v2["op"] == op) & v2["has_estimate"]]
        used = rows[rows["features"].map(_used)]
        mismatch = []
        for _, r in used.iterrows():
            o = own1.loc[r["point_id"]] if r["point_id"] in own1.index else None
            if o is None or not bool(o["has_estimate"]):
                mismatch.append(r["point_id"])
                continue
            if abs(float(o["ram_expected"]) - float(r["ram_expected"])) > 0.01 * float(
                r["ram_expected"]
            ):
                mismatch.append(r["point_id"])
                continue
            swaps[op][r["point_id"]] = max(float(o["ram_high"]), float(r["ram_expected"]))
        info[op] = {"tier1_rows": len(rows), "statistics_ran": len(used), "own_high_used": len(swaps[op]),
                    "excluded_mismatch": mismatch}  # fmt: skip

    def with_swap(ops: tuple[str, ...]) -> pd.DataFrame:
        d = v2.copy()
        for op in ops:
            for pid, high in swaps[op].items():
                m = (d["point_id"] == pid) & (d["tier"] == 1)
                d.loc[m, "ram_high"] = high
        return d

    frames = {"C0": v2, "C1": with_swap(("pandas.read_csv",)), "C2": with_swap(("merge",)),
              "C3": with_swap(("pandas.read_csv", "merge"))}  # fmt: skip
    return frames, info


def summary(res: dict) -> dict:
    pl, pa, pc = res["per_limit"], res["pooled_all"], res["pooled_claim"]
    per_op = res["per_op"]
    ops = {r.op: {"false_alarm": r.false_alarm, "non_positive": int(r.tn + r.fp), "recall": r.recall}
           for r in per_op.itertuples()}  # fmt: skip
    judged = {k: v for k, v in ops.items() if v["non_positive"] >= MIN_POSITIVES}
    r1 = (not res["verdict"]["R1a"]) and pa["recall"] >= RECALL_TARGET
    r2_ops = [k for k, v in judged.items() if v["false_alarm"] > FAR_PER_OP_TARGET]
    return {"R1_met": bool(r1), "recall_pooled": pa["recall"], "positives": pa["positives"], "fn": pa["fn"],
            "R2_pooled": pc.get("false_alarm"), "R2_ops_over": r2_ops,
            "max_op_far": max((v["false_alarm"] for v in judged.values()), default=math.nan),
            "R3": res["verdict"]["R3"], "per_op": ops, "claim_limits": res["claim_limits"],
            "per_limit_far": {int(r.limit_mb): r.false_alarm for r in pl.itertuples()}}  # fmt: skip


def main() -> None:
    frames, info = candidate_frames()
    print(json.dumps({"inputs": info}, default=str))
    res = {k: evaluate(f) for k, f in frames.items()}
    sm = {k: summary(r) for k, r in res.items()}
    base = res["C0"]["classified"].set_index(["limit_mb", "point_id"])
    for k, r in res.items():
        c = r["classified"].set_index(["limit_mb", "point_id"])
        both = base.join(c[["alert"]], rsuffix="_c")
        added = both[both["positive"] & both["alert"] & ~both["alert_c"]]
        sm[k]["added_misses"] = len(added)
        print(json.dumps({"candidate": k, **sm[k]}, default=str))
    # the rule, step by step
    eligible = [k for k in sm if sm[k]["R1_met"] and sm[k]["added_misses"] == 0
                and not (sm[k]["R3"] < HIGH_PRECISION_TARGET)]  # fmt: skip
    full = [k for k in eligible if sm[k]["R2_pooled"] <= FAR_TARGET and not sm[k]["R2_ops_over"]]
    changed = {"C0": 0, "C1": 1, "C2": 1, "C3": 2}
    if full:
        selected = sorted(full, key=lambda k: (changed[k], sm[k]["R2_pooled"]))[0]
        step = 2
    else:
        best = min(eligible, key=lambda k: sm[k]["max_op_far"]) if eligible else "C0"
        gain = sm["C0"]["max_op_far"] - sm[best]["max_op_far"]
        selected = best if gain >= 0.10 else "C0"
        step = 3
    print(json.dumps({"eligible": eligible, "meet_R2_in_full": full, "rule_step": step, "selected": selected,
                      "R2_on_dev": "MET" if selected in full else "FAILED"}))  # fmt: skip


if __name__ == "__main__":
    main()
