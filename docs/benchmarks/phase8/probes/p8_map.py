"""First derivation probe for Series.map mapper types; adoption bar +-15%."""

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
N = 25_000_000
CASES = (
    ("dict mapper", "s.map(mapper)", 8 * N),
    ("Series mapper", "s.map(mapper)", 16 * N),
    ("NumPy ufunc mapper", "s.map(np.negative)", 8 * N),
)


def setup(path: str, source: str) -> dict[str, Any]:
    s, mapper = pd.read_pickle(path)
    gc.collect()
    return {"s": s, "mapper": mapper, "np": np, "source": source}


def run(ns: dict[str, Any]) -> int:
    result = eval(ns["source"], ns)  # noqa: S307 - fixed probe statements
    return len(result)


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, source, derived) in enumerate(CASES):
            s = pd.Series(np.arange(N, dtype=np.int64) % 1000)
            mapper = dict(enumerate(range(1000))) if i == 0 else pd.Series(
                np.arange(1000, dtype=np.int64), index=np.arange(1000, dtype=np.int64)
            )
            path = str(Path(tmp) / f"{i}.pkl")
            pd.to_pickle((s, mapper), path)
            del s, mapper
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
