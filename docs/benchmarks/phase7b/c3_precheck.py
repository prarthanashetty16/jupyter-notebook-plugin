"""Phase 7b decision (3), before implementing risk C3 (stored DEV data only, no measurement).

1. Every val-v3 / val-v4 (now dev) merge point where Tier 1 UNDER-predicted: actual > the model's own Tier 1
   ``high`` (the bound C3 would WARN on) or actual > Tier 1 ``expected``. For each, per simulated limit
   where the point is positive, whether C0 (as frozen) and C3 alert.
2. Every merge / read_csv point whose Tier 1 statistics did NOT run (fallback): C3 must keep Tier 0's
   upper bound there (the stored policy-B ``high``), i.e. its class equals C0's at every limit.

    PYTHONPATH=. python docs/benchmarks/phase7b/c3_precheck.py > docs/benchmarks/phase7b/c3_precheck.out
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "docs/benchmarks/phase7a/probes")

from p1f_risk_v2 import _used, candidate_frames  # noqa: E402

from benchmarks.risk_eval import classify_all  # noqa: E402

MIB = 2**20


def main() -> None:  # noqa: C901
    frames, info = candidate_frames()
    c0, c3 = frames["C0"], frames["C3"]
    k0 = classify_all(c0).set_index(["limit_mb", "point_id"])
    k3 = classify_all(c3).set_index(["limit_mb", "point_id"])
    t1 = c0[(c0["tier"] == 1) & (c0["op"] == "merge") & c0["has_estimate"]]
    own = c3[(c3["tier"] == 1) & (c3["op"] == "merge")].set_index("point_id")
    print(json.dumps({"inputs": info}, default=str))
    print(
        "## 1. val-v3 / val-v4 merge points where Tier 1 under-predicted (dev since split v4 / v5)"
    )
    for _, r in t1.iterrows():
        pid = r["point_id"]
        if not (
            pid.startswith("v3/") or pid.startswith("v4/") or "val" in str(r.get("origin", ""))
        ):
            continue
        actual = r["ram_value"]
        if actual is None or actual != actual:
            continue
        own_high = float(own.loc[pid, "ram_high"])
        under_exp = actual > float(r["ram_expected"])
        under_high = actual > own_high
        if not (under_exp or under_high):
            continue
        rows = []
        for lim in sorted({i[0] for i in k0.index}):
            if (lim, pid) not in k0.index:
                continue
            a, b = k0.loc[(lim, pid)], k3.loc[(lim, pid)]
            if bool(a["positive"]):
                rows.append(
                    {
                        "limit_mb": int(lim),
                        "C0": a["risk"],
                        "C3": b["risk"],
                        "C3_alerts": bool(b["alert"]),
                    }
                )
        print(json.dumps({"point": pid, "origin": r.get("origin"), "actual_mib": actual / MIB,
                          "t1_expected_mib": r["ram_expected"] / MIB, "own_t1_high_mib": own_high / MIB,
                          "policyB_high_mib": r["ram_high"] / MIB, "above_own_high": under_high,
                          "positive_limits": rows}))  # fmt: skip
    print("## 2. merge / read_csv points whose Tier 1 statistics did not run: C3 must equal C0")
    fb = c0[
        (c0["tier"] == 1) & c0["op"].isin(["merge", "pandas.read_csv"]) & ~c0["features"].map(_used)
    ]
    diffs = 0
    for pid in fb["point_id"]:
        for lim in sorted({i[0] for i in k0.index}):
            if (lim, pid) in k0.index and k0.loc[(lim, pid), "risk"] != k3.loc[(lim, pid), "risk"]:
                diffs += 1
    swapped_high = c3.set_index(["point_id", "tier"]).loc[
        [(p, 1) for p in fb["point_id"]], "ram_high"
    ]
    stored_high = c0.set_index(["point_id", "tier"]).loc[
        [(p, 1) for p in fb["point_id"]], "ram_high"
    ]
    print(json.dumps({"fallback_points": len(fb), "class_differences_vs_C0": diffs,
                      "high_unchanged": bool((swapped_high.values == stored_high.values).all())}))  # fmt: skip


if __name__ == "__main__":
    main()
