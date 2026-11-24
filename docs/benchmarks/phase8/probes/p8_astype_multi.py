"""First derivation probe for multi-column/dict astype; adoption bar +-15%."""

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
N = 12_000_000
CASES = (
    ("dict converts two of three columns", "df.astype({'a': 'float32', 'b': 'float32'})", 2 * 4 * N),
    ("multi-column selection then astype", "df[['a', 'b']].astype('float32')", 2 * 4 * N),
    ("dict mixed targets", "df.astype({'a': 'int32', 'b': 'float64'})", (4 + 8) * N),
)


def setup(path: str, source: str) -> dict[str, Any]:
    gc.collect()
    return {"df": pd.read_pickle(path), "source": source}


def run(ns: dict[str, Any]) -> int:
    result = eval(ns["source"], ns)  # noqa: S307 - fixed probe statements
    return len(result)


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, source, derived) in enumerate(CASES):
            rng = np.random.default_rng(900 + i)
            df = pd.DataFrame(
                {
                    "a": rng.random(N),
                    "b": rng.random(N),
                    "c": rng.integers(0, 100, N, dtype=np.int64),
                }
            )
            path = str(Path(tmp) / f"{i}.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            measured = measure_call(run, setup=setup, setup_args=(path, source), repeats=3)
            actual = measured.delta_bytes
            ratio = None if actual is None else actual / derived
            print(
                json.dumps(
                    {
                        "variant": label,
                        "statement": source,
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
