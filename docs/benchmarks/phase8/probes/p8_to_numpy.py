"""First derivation probe for Series/DataFrame.to_numpy; adoption bar +-15%."""

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
CASES = (
    ("single Series, default zero-copy", "s.to_numpy()", 0),
    ("consolidated homogeneous frame, zero-copy", "df.to_numpy()", 0),
    ("mixed frame, consolidation to object", "df.to_numpy()", N * 2 * 8),
)


def setup(path: str, kind: str) -> dict[str, Any]:
    obj = pd.read_pickle(path)
    gc.collect()
    return {"s": obj if kind == "series" else None, "df": obj if kind != "series" else None}


def run(ns: dict[str, Any]) -> int:
    source = "s.to_numpy()" if ns["s"] is not None else "df.to_numpy()"
    result = eval(source, ns)  # noqa: S307 - fixed probe statements
    return result.shape[0]


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, _, derived) in enumerate(CASES):
            if i == 0:
                obj, kind = pd.Series(np.arange(N, dtype=np.float64)), "series"
            elif i == 1:
                obj, kind = pd.DataFrame(np.ones((N, 2), dtype=np.float64)), "frame"
            else:
                obj = pd.DataFrame(
                    {"a": np.arange(N, dtype=np.float64), "b": np.arange(N, dtype=np.int64)}
                )
                kind = "frame"
            path = str(Path(tmp) / f"{i}.pkl")
            pd.to_pickle(obj, path)
            del obj
            gc.collect()
            measured = measure_call(run, setup=setup, setup_args=(path, kind), repeats=3)
            actual = measured.delta_bytes
            ratio = None if actual is None or derived == 0 else actual / derived
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
