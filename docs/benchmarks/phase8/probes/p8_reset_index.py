"""Reset-index derivation probe (adoption bar +-15%)."""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20


def run(ns: dict) -> int:
    df = ns["df"]
    y = df.reset_index(**ns["kwargs"])
    return len(y)


def setup(path: str, kwargs: dict) -> dict:
    ns = {"df": pd.read_pickle(path), "kwargs": kwargs}
    gc.collect()
    return ns


def main() -> None:
    rng = np.random.default_rng(81)
    n = 8_000_000
    variants = [
        ("RangeIndex, drop=False", {"drop": False}),
        ("RangeIndex, drop=True", {"drop": True}),
        ("materialised index, drop=False", {"drop": False}),
    ]
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__}))
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, kwargs) in enumerate(variants):
            df = pd.DataFrame({"a": rng.random(n), "b": rng.integers(0, 100, n)})
            if i == 2:
                df.index = pd.Index(rng.permutation(n), name="old")
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(run, setup=setup, setup_args=(path, kwargs), repeats=3)
            print(json.dumps({"variant": label, "measured_mib": None if m.delta_bytes is None else m.delta_bytes / MIB,
                              "bound_mib": m.bound_bytes / MIB}))


if __name__ == "__main__":
    main()
