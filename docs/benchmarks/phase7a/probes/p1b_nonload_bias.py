"""Phase 7a probe 1b (information only): where the 10-17% over-prediction of the multi-statement
templates WITHOUT loads comes from (copy_fillna, chain, rebinding, astype_groupby).

Per template, at a size where the cell peaks at >= 200 MiB, on the multicell input shapes
(``benchmarks.multicell.cases.make_frame``):

* predicted: the frozen-v2 Tier 1 pipeline on the cell (per operation: peak range and output range
  from ``models._output``; the cell estimate of ``nexus.cellpeak``), in a fresh process;
* measured, tracemalloc (one fresh process): per statement, peak above the memory held before it and
  the bytes it leaves behind (numpy registers its data allocations with tracemalloc);
* measured, OS peak (``nexus.measure.measure_call``, median of 3): the cell's prefixes (statements 1..k),
  so the instrument of record cross-checks the tracemalloc statement peaks;
* for ``chain``: the same three operations written as separate statements with the temporaries
  released exactly as CPython releases them inside a chain (a link's receiver dies when the next link
  returns), to measure each link alone.

    python docs/benchmarks/phase7a/probes/p1b_nonload_bias.py <scratch dir> > docs/benchmarks/phase7a/probes/p1b_nonload_bias.out
"""

from __future__ import annotations

import gc
import json
import multiprocessing as mp
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.multicell.cases import KEYS, TEMPLATES, make_frame
from nexus.measure import measure_call
from nexus.power import power_state

MIB = 2**20
CASES = [("copy_fillna", "mixed", 4_000_000), ("chain", "mixed", 4_000_000),
         ("rebinding", "mixed", 4_000_000), ("astype_groupby", "num", 10_000_000)]  # fmt: skip
CHAIN_SPLIT = ["t1 = df.merge(right, on='k')", "t2 = t1.sort_values('v')", "del t1",
               "r = t2.drop_duplicates(subset=['k'])", "del t2"]  # fmt: skip


def prepare(tmp: Path, shape: str, rows: int) -> dict[str, str]:
    d = tmp / f"{shape}_{rows}"
    d.mkdir(parents=True, exist_ok=True)
    paths = {"df": d / "df.pkl", "df2": d / "df2.pkl", "right": d / "right.pkl"}
    if not (d / "DONE").exists():
        make_frame(shape, rows, 1).to_pickle(paths["df"])
        make_frame(shape, rows, 2).to_pickle(paths["df2"])
        pd.DataFrame({"k": np.arange(KEYS), "w": np.random.default_rng(3).random(KEYS)}).to_pickle(
            paths["right"]
        )
        (d / "DONE").write_text("ok")
    return {k: str(v) for k, v in paths.items()}


def load(paths: dict[str, str], stmts: list[str], need_df2: bool) -> dict:
    ns = {
        "pd": pd,
        "df": pd.read_pickle(paths["df"]),
        "right": pd.read_pickle(paths["right"]),
        "__stmts__": stmts,
    }
    if need_df2:
        ns["df2"] = pd.read_pickle(paths["df2"])
    gc.collect()
    return ns


def run_prefix(ns: dict) -> int:
    for s in ns["__stmts__"]:
        exec(s, ns)  # noqa: S102  (fixed probe statements)
    return 0


def _predict(q, paths, src, need_df2):  # noqa: ANN001
    from nexus.cellpeak import cell_estimate
    from nexus.models._output import output_range
    from nexus.pipeline import Pipeline

    ns = load(paths, [], need_df2)
    rep = Pipeline(tier=1).run(src, ns)
    cell, mode, _ = cell_estimate(src, rep.estimates)
    ops = []
    for o in rep.estimates:
        e = o.estimate
        out = output_range(o.model, o.features or {}, e)
        ops.append({"model": o.model, "tier": e.tier, "line": o.op.node.lineno,
                    "peak": [e.ram_low, e.ram_expected, e.ram_high], "out": list(out) if out else None,
                    "features": {k: v for k, v in (o.features or {}).items()
                                 if isinstance(v, (int, float, str, bool)) and k != "tier1"}})  # fmt: skip
    q.put({"cell": [cell.ram_low, cell.ram_expected, cell.ram_high] if cell else None, "mode": mode,
           "uncovered": len(rep.ops) - len(rep.estimates), "ops": ops})  # fmt: skip


def _trace(q, paths, stmts, need_df2):  # noqa: ANN001
    ns = load(paths, [], need_df2)
    tracemalloc.start()
    res = []
    for s in stmts:
        gc.collect()
        cur0 = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        exec(s, ns)  # noqa: S102
        cur1, peak = tracemalloc.get_traced_memory()
        res.append({"stmt": s, "peak_above_before": peak - cur0, "left_behind": cur1 - cur0})
    q.put(res)


def child(target, *args):  # noqa: ANN001, ANN002
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=target, args=(q, *args))
    p.start()
    import queue

    while True:  # a child that died sends nothing: fail at once instead of waiting for the timeout
        try:
            out = q.get(timeout=5)
            break
        except queue.Empty:
            if not p.is_alive():
                raise RuntimeError(f"probe child died (exit code {p.exitcode})") from None
    p.join()
    return out


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "power": power_state()}))
    for template, shape, rows in CASES:
        paths = prepare(tmp, shape, rows)
        src = (
            TEMPLATES[template].replace("{{", "{").replace("}}", "}")
        )  # the templates are format strings
        stmts = src.split("\n")
        need_df2 = "df2" in src
        pred = child(_predict, paths, src, need_df2)
        trace = child(_trace, paths, stmts, need_df2)
        prefixes = []
        for k in range(1, len(stmts) + 1):
            m = measure_call(
                run_prefix, setup=load, setup_args=(paths, stmts[:k], need_df2), repeats=3
            )
            prefixes.append({"k": k, "os_peak": m.delta_bytes, "spread": m.ram_spread, "status": m.status,
                             "time_s": m.time_s, "power": power_state()})  # fmt: skip
        rec = {
            "template": template,
            "shape": shape,
            "rows": rows,
            "pred": pred,
            "trace": trace,
            "os_prefix": prefixes,
        }
        if template == "chain":
            rec["split_trace"] = child(_trace, paths, CHAIN_SPLIT, need_df2)
            m = measure_call(
                run_prefix, setup=load, setup_args=(paths, CHAIN_SPLIT, need_df2), repeats=3
            )
            rec["split_os_peak"] = m.delta_bytes
        print(json.dumps(rec), flush=True)


if __name__ == "__main__":
    main()
