"""Probe (RAM >= 200 MiB, OS peak): is a multi-statement cell's peak "retained outputs + current peak"?

HYPOTHESIS (the Phase 6c cell model): for statements s1..sk run in order, the cell's incremental peak is
``max_s [ retained(before s) + temporaries(s) + peak(op of s) ]``: a result bound to a name stays alive
(retained) until ``del``; an expression statement's result is freed after its statement; intermediate
results of a chain stay alive until the chain ends. NOT the maximum of the operations' peaks (Phase 8a found
0.56x on cells with several loads) and NOT their sum.

Method: each cell runs in a fresh process with its inputs loaded from disk. The child reads the OS peak and
the RSS after every statement (Windows: peak monotonic, so the peak after statement k is the running maximum;
RSS after a statement = what is retained). Every operation is also measured ALONE (its own incremental peak
and the RSS it leaves = its output). The prediction from those components is compared with the cell's peak.

    python docs/benchmarks/phase6c/probes/p_multistatement.py
"""

from __future__ import annotations

import gc
import multiprocessing as mp
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

MIB = 2**20
N = 3_000_000

CELLS = {
    "two loads": ["a = pd.read_csv(P1)", "b = pd.read_csv(P2)"],
    "three loads": ["a = pd.read_csv(P1)", "b = pd.read_csv(P2)", "c = pd.read_csv(P1)"],
    "load then merge": ["a = pd.read_csv(P1)", "m = a.merge(right, on='k')"],
    "load, sort, del, dedup": ["a = pd.read_csv(P1)", "s = a.sort_values('v')", "del a",
                               "d = s.drop_duplicates(subset=['k'])"],  # fmt: skip
    "chain (temporaries)": ["r = df.merge(right, on='k').sort_values('v').drop_duplicates(subset=['k'])"],
    "expression statements": ["df.sort_values('v')", "df.merge(right, on='k')", "x = df.copy()"],
    "copy then fillna": ["x = df.copy()", "y = x.fillna(0)"],
}


def _rss_peak() -> tuple[int, int]:
    from nexus.measure import read_memory

    m = read_memory()
    return m.rss, m.peak or 0


def _child(q, paths: dict[str, str], statements: list[str]) -> None:  # type: ignore[no-untyped-def]
    ns = {"pd": pd, "np": np, "P1": paths["p1"], "P2": paths["p2"],
          "df": pd.read_pickle(paths["df"]), "right": pd.read_pickle(paths["right"])}  # fmt: skip
    gc.collect()
    base, peak0 = _rss_peak()
    trace = []
    for st in statements:
        exec(compile(st, "cell", "exec"), ns)  # noqa: S102  (synthetic probe cells only)
        rss, peak = _rss_peak()
        trace.append((rss - base, max(0, peak - base) if peak > peak0 else 0))
    q.put(trace)


def run_cell(paths: dict[str, str], statements: list[str]) -> list[tuple[int, int]]:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(q, paths, statements))
    p.start()
    out = q.get(timeout=900)
    p.join()
    return out


def single(paths: dict[str, str], prefix: list[str], statement: str) -> tuple[int, int]:
    """(output bytes, own incremental peak) of ``statement`` after ``prefix`` (prefix effects removed)."""
    trace = run_cell(paths, [*prefix, statement])
    before = trace[-2][0] if prefix else 0
    peak_prefix = max((t[1] for t in trace[:-1]), default=0)
    out = trace[-1][0] - before
    own = max(trace[-1][1] - before, 0) if trace[-1][1] > peak_prefix else None
    return out, own


def main() -> None:
    rng = np.random.default_rng(5)
    with tempfile.TemporaryDirectory() as tmp:
        frame = pd.DataFrame({"k": rng.integers(0, 50_000, N), "v": rng.random(N), "w": rng.random(N),
                              "i": rng.integers(0, 10**6, N)})  # fmt: skip
        frame.loc[frame.index[::500], "w"] = np.nan
        paths = {"p1": str(Path(tmp) / "a.csv"), "p2": str(Path(tmp) / "b.csv"),
                 "df": str(Path(tmp) / "df.pkl"), "right": str(Path(tmp) / "r.pkl")}  # fmt: skip
        frame.to_csv(paths["p1"], index=False)
        frame.sample(frac=0.8, random_state=1).to_csv(paths["p2"], index=False)
        frame.to_pickle(paths["df"])
        pd.DataFrame({"k": np.arange(50_000), "z": rng.random(50_000)}).to_pickle(paths["right"])
        del frame
        gc.collect()
        print(f"pandas {pd.__version__}; peaks in MiB above the state after loading the inputs")
        print("cell                      measured  model(max of ops)  model(retained+current)  ratio(new)")
        for name, sts in CELLS.items():
            trace = run_cell(paths, sts)
            actual = max(t[1] for t in trace)
            # components: the RSS actually retained before each statement (measured in the cell) + that
            # statement's own incremental peak measured in a separate run (after the statements it needs)
            best, ops_peaks, unresolved = 0, [], 0
            for k, st in enumerate(sts):
                if st.startswith("del "):
                    continue
                _, own = single(paths, sts[:k], st)
                if own is None:  # its peak stayed below the prefix's: not resolvable on Windows
                    unresolved += 1
                    continue
                ops_peaks.append(own)
                before = trace[k - 1][0] if k else 0
                best = max(best, before + own)
            note = f"  ({unresolved} statement peak(s) unresolved)" if unresolved else ""
            print(f"{name:25} {actual / MIB:9.0f}  {max(ops_peaks, default=0) / MIB:17.0f}  "
                  f"{best / MIB:23.0f}  {(best / actual if actual else float('nan')):9.2f}{note}")


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "4")
    main()
