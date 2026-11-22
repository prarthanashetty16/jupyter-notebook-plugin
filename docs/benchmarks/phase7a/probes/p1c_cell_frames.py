"""Phase 7a probe 1c (information only): what an operation on a frame CREATED EARLIER IN THE SAME CELL
needs, and whether propagating predicted shapes / dtypes is enough or column statistics must be carried.

Pattern: ``a = pd.read_csv(P)`` then an operation on ``a`` (merge with unique / duplicated right keys,
fillna, groupby) and ``pd.concat`` of two reads. For each downstream operation:

* measured: its own OS peak with ``a`` already loaded (``measure_call``: setup reads the CSV in the
  child, the measured window is the operation only; median of 3);
* "shapes propagated": the frozen Tier 0 estimate on the TRUE frame. Tier 0 reads only descriptors
  (rows, columns, dtypes, bytes), and the Phase 6c follow-up showed the predicted retained read_csv frame is
  exact for these files, so this is what perfect shape / dtype propagation can give;
* "column statistics carried": the frozen Tier 1 estimate on the true frame (an oracle: statistics of
  the real columns);
* "statistics from the read_csv sample": what the read_csv Tier 1 sample (head + 3 seeked chunks, the
  bytes ``stats.csv_profile`` already reads) says about the column the operation needs (key distinct
  count, NaN presence per column), against the truth.

    python docs/benchmarks/phase7a/probes/p1c_cell_frames.py > docs/benchmarks/phase7a/probes/p1c_cell_frames.out
"""

from __future__ import annotations

import gc
import io
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.multicell.cases import KEYS
from nexus.measure import measure_call
from nexus.power import power_state

MIB = 2**20
P1 = "benchmarks/.cache/multicell/wide_2000000/p1.csv"
P2 = "benchmarks/.cache/multicell/wide_2000000/p2.csv"
RIGHT_U = pd.DataFrame({"k": np.arange(KEYS), "w": np.random.default_rng(3).random(KEYS)})
RIGHT_D = pd.concat(
    [RIGHT_U, RIGHT_U], ignore_index=True
)  # every key twice: the merge doubles the rows
OPS = {
    "merge_unique_right": "m = a.merge(right, on='k')",
    "merge_dup_right": "m = a.merge(right, on='k')",
    "fillna0": "b = a.fillna(0)",
    "groupby_sum": "g = a.groupby('k')['v'].sum()",
    "concat_two_reads": "c = pd.concat([a, a2])",
}


def _frame(csv: str) -> pd.DataFrame:
    """The frame ``read_csv`` returns, loaded from a pickle of it: reading the CSV in the measured child
    would set the (non-resettable on Windows) OS peak above the operation's own peak and censor it."""
    pkl = Path(csv).with_suffix(".frame.pkl")
    if not pkl.exists():
        pd.read_csv(csv).to_pickle(pkl)
    return pd.read_pickle(pkl)


def setup(case: str) -> dict:
    ns = {"pd": pd, "a": _frame(P2), "right": RIGHT_D if case == "merge_dup_right" else RIGHT_U}
    if case == "concat_two_reads":
        ns["a2"] = _frame(P1)
    ns["__src__"] = OPS[case]
    gc.collect()
    return ns


def run(ns: dict) -> int:
    exec(ns["__src__"], ns)  # noqa: S102  (fixed probe statements)
    return 0


def _predict(q, case):  # noqa: ANN001
    from nexus.pipeline import Pipeline

    ns = setup(case)
    out = {}
    for tier in (0, 1):
        rep = Pipeline(tier=tier).run(OPS[case], ns)
        e = rep.estimates[0].estimate if rep.estimates else None
        out[f"tier{tier}"] = None if e is None else {"low": e.ram_low, "exp": e.ram_expected, "high": e.ram_high,
                                                     "tier": e.tier, "note": e.note}  # fmt: skip
    a = ns["a"]
    out["truth"] = {"rows": len(a), "k_distinct": int(a["k"].nunique()),
                    "nan_cols": [c for c in a.columns if a[c].isna().any()]}  # fmt: skip
    q.put(out)


def sample_stats() -> dict:
    """What the read_csv Tier 1 sample (head 1 MiB + 3 seeked 256 KiB chunks) says about ``k`` and NaNs."""
    from nexus.stats import distinct_from_counts

    size = __import__("os").path.getsize(P2)
    parts = []
    sampled = 0
    with open(P2, "rb") as fh:
        head = fh.read(1 << 20)
        head = head[: head.rfind(b"\n") + 1]
        first = pd.read_csv(io.BytesIO(head))
        parts.append(first)
        sampled += len(head)
        for i in range(3):
            fh.seek((1 << 20) + int((size - (1 << 20) - (256 << 10)) * (i + 0.5) / 3))
            raw = fh.read(256 << 10)
            raw = raw[raw.find(b"\n") + 1 : raw.rfind(b"\n") + 1]
            sampled += len(raw)
            parts.append(pd.read_csv(io.BytesIO(raw), header=None, names=list(first.columns)))
    s = pd.concat(parts, ignore_index=True)
    est_rows = size / (sampled / len(s))
    counts = np.bincount(pd.factorize(s["k"])[0])
    d = distinct_from_counts(counts, int(est_rows))
    return {"sample_rows": len(s), "k_distinct_est": [d.low, d.value, d.high],
            "nan_cols_in_sample": [c for c in s.columns if s[c].isna().any()]}  # fmt: skip


def _get(q, p):  # noqa: ANN001
    """The child's result; fail at once if the child died without sending one."""
    import queue

    while True:
        try:
            return q.get(timeout=5)
        except queue.Empty:
            if not p.is_alive():
                raise RuntimeError(f"probe child died (exit code {p.exitcode})") from None


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    print(json.dumps({"pandas": pd.__version__, "power": power_state(), "sample": sample_stats()}))
    ctx = mp.get_context("spawn")
    for case in OPS:
        q = ctx.Queue()
        p = ctx.Process(target=_predict, args=(q, case))
        p.start()
        pred = _get(q, p)
        p.join()
        m = measure_call(run, setup=setup, setup_args=(case,), repeats=3)
        print(json.dumps({"case": case, "src": OPS[case], "measured": m.delta_bytes, "spread": m.ram_spread,
                          "status": m.status, "time_s": m.time_s, "power": power_state(), **pred}), flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
