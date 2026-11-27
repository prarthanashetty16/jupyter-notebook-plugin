"""First derivation probe for DataFrame.describe; adoption bar +-15%."""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
N = 15_000_000


def setup(path: str) -> dict[str, Any]:
    gc.collect()
    return {"df": pd.read_pickle(path)}


def run(ns: dict[str, Any]) -> int:
    result = ns["df"].describe()
    return result.shape[0]


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    rng = np.random.default_rng(42)
    vocab = np.array([f"word_{i:06d}" for i in range(100_000)], dtype=object)
    cases = (
        ("two numeric columns", 2, 0),
        ("one numeric and one str column", 1, 1),
        ("two str columns", 0, 2),
    )
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, numeric, text) in enumerate(cases):
            if i == 0:
                frame = pd.DataFrame({"a": rng.random(N), "b": rng.random(N)})
            elif i == 1:
                text1 = pd.array(vocab[rng.integers(0, len(vocab), N)], dtype="str")
                frame = pd.DataFrame({"a": rng.random(N), "s": text1})
                del text1
            else:
                text1 = pd.array(vocab[rng.integers(0, len(vocab), N)], dtype="str")
                text2 = pd.array(vocab[rng.integers(0, len(vocab), N)], dtype="str")
                frame = pd.DataFrame({"s0": text1, "s1": text2})
                del text1, text2
            derived = N * (8 * numeric + 16 * text)
            path = str(Path(tmp) / f"{i}.pkl")
            frame.to_pickle(path)
            del frame
            gc.collect()
            measured = measure_call(run, setup=setup, setup_args=(path,), repeats=3)
            actual = measured.delta_bytes
            ratio = None if actual is None else actual / derived
            print(
                json.dumps(
                    {
                        "variant": label,
                        "measured_mib": None if actual is None else actual / MIB,
                        "bound_mib": measured.bound_bytes / MIB,
                        "derived_mib": derived / MIB,
                        "ratio": ratio,
                        "within_bar": None if ratio is None else abs(ratio - 1) <= 0.15,
                        "censored": actual is None,
                    }
                )
            )


if __name__ == "__main__":
    main()
