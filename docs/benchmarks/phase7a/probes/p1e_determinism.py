"""Phase 7a probe 1e (information only): Tier 1 determinism and the 250 ms statistics budget on slow CPUs.

Prediction only (no RAM measurement), mains power checked at the start and the end of every condition.

* ``frozen``: ``Pipeline(tier=1)`` as frozen. The sampler's seeds are constants, so the only run-to-run
  freedom is the sample SIZE, which ``stats.affordable_rows`` derives from a timed pilot and the time
  left in the budget, and the budget fallback itself.
* ``prototype`` (patched in the probe child only; no frozen file changes): a FIXED sample size per call
  (``min(rows, 200_000)``, the stats default) with the seed mixed with a hash of the cell source. The
  budget only decides between that sample and no statistics, using the same pilot (fallback visible as
  ``tier1.reason``).

Conditions: all 16 logical CPUs; 2 CPUs (process affinity, inherited by the spawned children); 2 CPUs
plus 2 busy-loop processes pinned to them (about half a core each). 5 operations at 3M and 10M rows of
the multicell ``num`` shape; 5 repeats per (cell, size, condition, variant), each in a fresh process.

    python docs/benchmarks/phase7a/probes/p1e_determinism.py <scratch dir> > docs/benchmarks/phase7a/probes/p1e_determinism.out
"""

from __future__ import annotations

import gc
import hashlib
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from benchmarks.multicell.cases import KEYS, make_frame
from nexus.power import power_state

CELLS = {
    "drop_duplicates": "r = df.drop_duplicates(subset=['k'])",
    "groupby": "g = df.groupby('k')['v'].sum()",
    "merge": "m = df.merge(right, on='k')",
    "concat": "c = pd.concat([df, df2])",
    "astype": "c = df['k'].astype('category')",
}
SIZES = (3_000_000, 10_000_000)
REPEATS = 5
FIXED_ROWS = 200_000


def prepare(tmp: Path, rows: int) -> dict[str, str]:
    d = tmp / f"num_{rows}"
    d.mkdir(parents=True, exist_ok=True)
    p = {"df": d / "df.pkl", "df2": d / "df2.pkl", "right": d / "right.pkl"}
    if not (d / "DONE").exists():
        make_frame("num", rows, 1).to_pickle(p["df"])
        make_frame("num", rows, 2).to_pickle(p["df2"])
        pd.DataFrame({"k": np.arange(KEYS), "w": np.random.default_rng(3).random(KEYS)}).to_pickle(
            p["right"]
        )
        (d / "DONE").write_text("ok")
        gc.collect()
    return {k: str(v) for k, v in p.items()}


def _patch_prototype(src: str) -> None:
    from nexus import stats

    salt = int(hashlib.sha256(src.encode()).hexdigest()[:8], 16)
    orig_positions = stats.sample_positions

    def positions(n: int, m: int, seed: int = 0) -> np.ndarray:
        return orig_positions(n, m, (seed ^ salt) & 0x7FFFFFFF)

    def affordable(rows: int, budget_s: float | None, pilot) -> int:  # noqa: ANN001
        m = min(rows, FIXED_ROWS)
        if budget_s is None:
            return m
        m0 = min(rows, stats.PILOT_ROWS)
        per_row = max(pilot(m0) / m0, 1e-9)
        if per_row * m > budget_s:
            raise TimeoutError("time budget too small for the fixed sample")
        return m

    stats.sample_positions = positions
    stats.affordable_rows = affordable


def _child(q, paths, src, variant):  # noqa: ANN001
    if variant == "prototype":
        _patch_prototype(src)
    from nexus.pipeline import Pipeline

    ns = {"pd": pd, "df": pd.read_pickle(paths["df"]), "right": pd.read_pickle(paths["right"])}
    if "df2" in src:
        ns["df2"] = pd.read_pickle(paths["df2"])
    gc.collect()
    t0 = time.perf_counter()
    rep = Pipeline(tier=1).run(src, ns)
    took = time.perf_counter() - t0
    o = rep.estimates[0]
    t1 = (o.features or {}).get("tier1", {})
    e = o.estimate
    q.put({"tier": e.tier, "reason": t1.get("reason"), "sample": t1.get("sample"), "exp": e.ram_expected,
           "high": e.ram_high, "time_exp": e.time_expected, "analysis_s": took})  # fmt: skip


def _busy(cores: list[int]) -> None:
    psutil.Process().cpu_affinity(cores)
    x = 0
    while True:
        x = (x * 1103515245 + 12345) % 2147483648


def _get(q, p):  # noqa: ANN001
    """The child's result; fail at once if the child died without sending one."""
    import queue

    while True:
        try:
            return q.get(timeout=5)
        except queue.Empty:
            if not p.is_alive():
                raise RuntimeError(f"probe child died (exit code {p.exitcode})") from None


def main() -> None:  # noqa: C901
    tmp = Path(sys.argv[1])
    only = (
        sys.argv[2].split(":") if len(sys.argv) > 2 else None
    )  # "condition:rows:op" re-runs one group
    ctx = mp.get_context("spawn")
    all_cpus = psutil.Process().cpu_affinity()
    paths = {n: prepare(tmp, n) for n in SIZES}
    for condition in ("all", "cores2", "cores2_contended"):
        if only and condition != only[0]:
            continue
        if power_state() == "battery":
            raise SystemExit("on battery power: plug in first")
        psutil.Process().cpu_affinity(all_cpus if condition == "all" else [0, 1])
        hogs = []
        if condition == "cores2_contended":
            hogs = [ctx.Process(target=_busy, args=([0, 1],), daemon=True) for _ in range(2)]
            for h in hogs:
                h.start()
        print(json.dumps({"condition": condition, "power_start": power_state(),
                          "affinity": psutil.Process().cpu_affinity()}), flush=True)  # fmt: skip
        try:
            for rows in SIZES:
                for op, src in CELLS.items():
                    if only and (str(rows) != only[1] or op != only[2]):
                        continue
                    for variant in ("frozen", "prototype"):
                        reps = []
                        for _ in range(REPEATS):
                            q = ctx.Queue()
                            p = ctx.Process(target=_child, args=(q, paths[rows], src, variant))
                            p.start()
                            reps.append(_get(q, p))
                            p.join()
                        print(json.dumps({"condition": condition, "rows": rows, "op": op, "variant": variant,
                                          "reps": reps}), flush=True)  # fmt: skip
        finally:
            for h in hogs:
                h.terminate()
        print(json.dumps({"condition": condition, "power_end": power_state()}), flush=True)
    psutil.Process().cpu_affinity(all_cpus)


if __name__ == "__main__":
    main()
