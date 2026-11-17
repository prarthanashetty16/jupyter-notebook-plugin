"""Isolated allocation probes: measure the peak RAM of one pandas call on a purpose-built frame.

Uses the project's own instrument (spawned child, inputs loaded from disk, OS peak counters).
These probes test MECHANISMS (what is copied, what is a temporary); they are not benchmark points.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))
from benchmarks import store  # noqa: E402
from benchmarks.datasets import DatasetConfig, make_frame  # noqa: E402
from nexus.measure import measure_call  # noqa: E402

CACHE = Path(__file__).parent / "probe_cache"
MIB = 2**20


def frame_dir(cfg: DatasetConfig) -> str:
    key = hashlib.sha1(repr(cfg).encode()).hexdigest()[:16]
    path = CACHE / key
    if not (path / "meta.json").exists():
        store.save(make_frame(cfg), path)
    return str(path)


def setup(dirs: dict[str, str], code: str):
    ns = {"pd": pd, "np": np}
    for name, path in dirs.items():
        ns[name] = store.load(Path(path))
    return ns, compile(code, "<probe>", "eval")


def run(state):
    ns, code = state
    return eval(code, ns)


def summarize(res):
    if isinstance(res, pd.DataFrame):
        return {
            "out_rows": int(len(res)),
            "out_shallow": int(res.memory_usage(index=True, deep=False).sum()),
        }
    return {}


def probe(frames: dict[str, DatasetConfig], code: str, repeats: int = 2, units: int | None = None):
    dirs = {k: frame_dir(c) for k, c in frames.items()}
    m = measure_call(
        run, setup=setup, setup_args=(dirs, code), summarize=summarize, repeats=repeats
    )
    n = units or next(iter(frames.values())).n_rows
    ram = None if m.delta_bytes is None else m.delta_bytes
    return {
        "status": m.status,
        "ram_MiB": None if ram is None else round(ram / MIB, 1),
        "B_per_row": None if ram is None else round(ram / n, 1),
        "bound_MiB": round(m.bound_bytes / MIB, 1),
        "time_s": round(m.time_s, 3),
        "info": m.info,
        "err": m.error,
    }


def shallow_row_bytes(cfg: DatasetConfig) -> float:
    df = make_frame(cfg)
    return float(df.memory_usage(index=False, deep=False).sum()) / len(df)
