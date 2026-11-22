"""Phase 7b decision (5): investigate the Phase 7a native child crash (exit code 3221225477 = 0xC0000005,
access violation) in the determinism probe (2 CPUs + 2 busy loops, 10M rows, astype group).

The group is repeated 25 times (5 rounds x 5 children) in the SAME condition through
``benchmarks.childproc.run_child``, which enables ``faulthandler`` in the child (its Python stack on a
native fault) and records a crash as a harness event. Also repeated without contention as a control.
Prediction only; mains power required (the condition is a CPU condition).

    PYTHONPATH=. python docs/benchmarks/phase7b/probes/p7b_crash.py <p1e scratch dir> > docs/benchmarks/phase7b/probes/p7b_crash.out
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, "docs/benchmarks/phase7a/probes")

from p1e_determinism import CELLS, _busy, prepare  # noqa: E402

from benchmarks.childproc import ChildFailureError, run_child  # noqa: E402
from nexus.power import power_state  # noqa: E402

ROUNDS, PER_ROUND = 5, 5


def child(paths: dict[str, str], src: str) -> dict:
    import gc

    import pandas as pd

    from nexus.pipeline import Pipeline

    ns = {"pd": pd, "df": pd.read_pickle(paths["df"]), "right": pd.read_pickle(paths["right"])}
    gc.collect()
    e = Pipeline(tier=1).run(src, ns).estimates[0].estimate
    return {"tier": e.tier, "exp": e.ram_expected}


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    paths = prepare(tmp, 10_000_000)
    src = CELLS["astype"]
    all_cpus = psutil.Process().cpu_affinity()
    ctx = mp.get_context("spawn")
    for condition in ("cores2_contended", "all"):
        psutil.Process().cpu_affinity([0, 1] if condition != "all" else all_cpus)
        hogs = []
        if condition == "cores2_contended":
            hogs = [ctx.Process(target=_busy, args=([0, 1],), daemon=True) for _ in range(2)]
            for h in hogs:
                h.start()
        try:
            results = []
            for r in range(ROUNDS):
                for _ in range(PER_ROUND):
                    t0 = time.monotonic()
                    try:
                        out = run_child(child, paths, src, timeout_s=600)
                        results.append(
                            {"round": r, "status": "ok", **out, "s": time.monotonic() - t0}
                        )
                    except ChildFailureError as fail:
                        results.append({"round": r, **fail.record(), "s": time.monotonic() - t0})
            print(json.dumps({"condition": condition, "power": power_state(), "runs": len(results),
                              "crashes": [x for x in results if x["status"] != "ok"],
                              "distinct_estimates": sorted({(x.get("tier"), x.get("exp")) for x in results
                                                            if x["status"] == "ok"})}), flush=True)  # fmt: skip
        finally:
            for h in hogs:
                h.terminate()
    psutil.Process().cpu_affinity(all_cpus)


if __name__ == "__main__":
    main()
