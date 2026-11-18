"""Probe (not a model change): where is the peak of ``left.merge(right, on="k")["v"]`` made, with and
without the dropped columns?

HYPOTHESIS (stated before running). The frozen Tier 0 model predicts the saving of the
``select_columns`` suggestion as roughly proportional to the bytes of the dropped columns (46-59%
predicted on the Phase 5 dev and held-out cells, 13-19% measured). If the real peak is
``a + b * carried_bytes`` with a large width-independent part ``a`` (the join indexers, the key
factorisation / hash table, the copies that the selection itself makes, the single column that is
read at the end), then dropping columns can only remove ``b * dropped_bytes`` and the measured
saving stays far below the proportional one. The probe refutes the hypothesis if, across mixes,
the measured saving fraction tracks the dropped share of the bytes (slope ~ 1, intercept ~ 0).

The cell mirrors benchmark template M1 (``left`` has k, v and a payload mix; ``right`` has k, w, x0,
x1; every left row matches exactly one right row). Variants:
  full         left.merge(right, on="k")["v"]
  selected     left[["k","v"]].merge(right[["k"]], on="k")["v"]   (what the rule proposes; the
               selection copies are inside the measured region)
  preselected  the same merge on frames narrowed in setup (merge-only peak, no selection copy)
Each variant runs in fresh spawned processes with inputs loaded from disk. Measurements: OS peak
above baseline via ``nexus.measure.measure_call`` (median of repeats) and one tracemalloc run per
variant (stage peaks: selection / merge / final column, plus the allocation sites live when the
traced memory was near its maximum, sampled by a 1 ms polling thread; a snapshot costs time and
holds the GIL, so the sites are indicative, not exact).

Run (not part of the test suite; do not run while a benchmark is running):
    python docs/benchmarks/probes/merge_peak_probe.py --out docs/benchmarks/probes/merge_peak_probe_results.md
"""

from __future__ import annotations

import argparse
import gc
import itertools
import json
import multiprocessing as mp
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
MIXES = {
    # name: (extra float cols, extra int64 cols, object string cols)
    "float6": (6, 0, 0),
    "float2": (2, 0, 0),
    "int6": (0, 6, 0),
    "mixed": (2, 2, 2),
}
SIZES = (500_000, 1_000_000, 2_000_000)
KEY_CARDS = (1_000, 500_000)  # rows of ``right``; every left row matches exactly one
VARIANTS = ("full", "selected", "preselected")


def make_frames(rows: int, mix: str, key_card: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    nf, ni, ns = MIXES[mix]
    rng = np.random.default_rng(7)
    cols: dict[str, np.ndarray] = {
        "k": rng.integers(0, key_card, rows),
        "v": rng.random(rows),
    }
    for i in range(nf):
        cols[f"f{i}"] = rng.random(rows)
    for i in range(ni):
        cols[f"i{i}"] = rng.integers(0, 10**9, rows)
    for i in range(ns):
        cols[f"s{i}"] = np.array([f"id{v:08d}" for v in rng.integers(0, 10**6, rows)], dtype=object)
    left = pd.DataFrame(cols)
    right = pd.DataFrame({"k": np.arange(key_card)})
    for name in ("w", "x0", "x1"):
        right[name] = rng.random(key_card)
    return left, right


def _load(paths: dict[str, str], variant: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    suffix = "narrow" if variant == "preselected" else "full"
    left = pd.read_pickle(paths[f"left_{suffix}"])
    right = pd.read_pickle(paths[f"right_{suffix}"])
    gc.collect()
    return left, right


def setup(paths: dict[str, str], variant: str) -> tuple:
    return (*_load(paths, variant), variant)


def run_variant(state: tuple) -> float:
    left, right, variant = state
    if variant == "selected":
        left, right = left[["k", "v"]], right[["k"]]
    return float(left.merge(right, on="k")["v"].sum())


def _trace_child(paths: dict[str, str], variant: str, q) -> None:  # type: ignore[no-untyped-def]
    left, right = _load(paths, variant)
    tracemalloc.start(8)
    base = tracemalloc.get_traced_memory()[0]
    best: dict = {"cur": 0, "snap": None}
    stop = threading.Event()

    def poll() -> None:
        while not stop.is_set():
            cur = tracemalloc.get_traced_memory()[0]
            if cur > best["cur"] * 1.10 and cur > base:
                best["cur"] = cur
                best["snap"] = tracemalloc.take_snapshot()
            time.sleep(0.001)

    th = threading.Thread(target=poll, daemon=True)
    th.start()
    stages: dict[str, float] = {}
    tracemalloc.reset_peak()
    if variant == "selected":
        l2, r2 = left[["k", "v"]], right[["k"]]
    else:
        l2, r2 = left, right
    stages["select_MiB"] = (tracemalloc.get_traced_memory()[1] - base) / MIB
    c0 = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    m = l2.merge(r2, on="k")
    stages["merge_MiB"] = (tracemalloc.get_traced_memory()[1] - c0) / MIB
    stages["merge_result_MiB"] = (tracemalloc.get_traced_memory()[0] - c0) / MIB
    c1 = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    _ = m["v"]
    stages["final_column_MiB"] = (tracemalloc.get_traced_memory()[1] - c1) / MIB
    stop.set()
    th.join()
    sites = []
    if best["snap"] is not None:
        for st in best["snap"].statistics("traceback")[:5]:
            frames = [f"{Path(f.filename).name}:{f.lineno}" for f in st.traceback][-2:]
            sites.append({"MiB": round(st.size / MIB, 1), "where": " <- ".join(reversed(frames))})
    q.put({"stages": stages, "sites": sites, "near_peak_MiB": (best["cur"] - base) / MIB})


def traced(paths: dict[str, str], variant: str) -> dict:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_trace_child, args=(paths, variant, q))
    p.start()
    out = q.get(timeout=600)
    p.join()
    return out


def _mib_bytes(df: pd.DataFrame) -> int:
    return int(df.memory_usage(deep=True).sum())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--sizes", default=",".join(map(str, SIZES)))
    ap.add_argument("--mixes", default=",".join(MIXES))
    ap.add_argument("--key-cards", default=",".join(map(str, KEY_CARDS)))
    args = ap.parse_args()
    rows_out: list[dict] = []
    grid = itertools.product(
        args.mixes.split(","), map(int, args.key_cards.split(",")), map(int, args.sizes.split(","))
    )
    with tempfile.TemporaryDirectory() as tmp:
        for mix, key_card, rows in grid:
            left, right = make_frames(rows, mix, key_card)
            tag = f"{mix}_{rows}_{key_card}"
            paths = {
                k: str(Path(tmp) / f"{k}_{tag}.pkl")
                for k in ("left_full", "right_full", "left_narrow", "right_narrow")
            }
            left.to_pickle(paths["left_full"])
            right.to_pickle(paths["right_full"])
            left[["k", "v"]].to_pickle(paths["left_narrow"])
            right[["k"]].to_pickle(paths["right_narrow"])
            total = _mib_bytes(left) + _mib_bytes(right)
            kept = _mib_bytes(left[["k", "v"]]) + _mib_bytes(right[["k"]])
            del left, right
            gc.collect()
            row: dict = {
                "mix": mix,
                "rows": rows,
                "key_card": key_card,
                "inputs_MiB": total / MIB,
                "dropped_share_of_inputs": 1 - kept / total,
            }
            for variant in VARIANTS:
                m = measure_call(
                    run_variant, setup=setup, setup_args=(paths, variant), repeats=args.repeats
                )
                row[f"os_{variant}_MiB"] = None if m.delta_bytes is None else m.delta_bytes / MIB
                row[f"censored_{variant}"] = m.censored
                row[f"trace_{variant}"] = traced(paths, variant)
            rows_out.append(row)
            print(
                mix,
                key_card,
                rows,
                {k: v for k, v in row.items() if k.startswith("os_")},
                flush=True,
            )
            for pth in paths.values():
                Path(pth).unlink(missing_ok=True)
    if args.out:
        Path(args.out).with_suffix(".json").write_text(json.dumps(rows_out, indent=1))
        Path(args.out).write_text(render(rows_out), encoding="utf-8")


def render(rows: list[dict]) -> str:
    def f(x: float | None) -> str:
        return "censored" if x is None else f"{x:,.0f}"

    out = [
        "# Merge peak probe (results)\n",
        "OS peak above baseline, MiB (median of repeats; `censored` = below the setup peak). "
        "`saving` = 1 - selected/full; `merge-only` = 1 - preselected/full. `dropped share` = "
        "bytes of the dropped columns (both frames) / bytes of both input frames.\n",
        "| mix | rows | right rows | inputs MiB | dropped share | full | selected | preselected "
        "| saving | merge-only saving |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        full, sel, pre = r["os_full_MiB"], r["os_selected_MiB"], r["os_preselected_MiB"]
        s = "n/a" if not (full and sel is not None) else f"{1 - sel / full:.0%}"
        s2 = "n/a" if not (full and pre is not None) else f"{1 - pre / full:.0%}"
        out.append(
            f"| {r['mix']} | {r['rows']:,} | {r['key_card']:,} | {r['inputs_MiB']:,.0f} | "
            f"{r['dropped_share_of_inputs']:.0%} | {f(full)} | {f(sel)} | {f(pre)} | {s} | {s2} |"
        )
    out += ["\n## tracemalloc stage peaks (MiB above the stage start); sites live near the peak\n"]
    for r in rows:
        for v in VARIANTS:
            t = r[f"trace_{v}"]
            st = ", ".join(f"{k.removesuffix('_MiB')} {x:,.0f}" for k, x in t["stages"].items())
            sites = "; ".join(f"{s['MiB']} MiB @ {s['where']}" for s in t["sites"][:3])
            out.append(
                f"* {r['mix']} {r['rows']:,}/{r['key_card']:,} {v}: {st}; "
                f"near-peak {t['near_peak_MiB']:,.0f}. Sites: {sites}"
            )
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
