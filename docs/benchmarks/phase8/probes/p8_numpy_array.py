"""First derivation probe for np.array copies of known ndarrays; adoption bar +-15%."""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from nexus.measure import measure_call

MIB = 2**20
CASES = (
    (40_000_000, None),
    (60_000_000, "float32"),
    (40_000_000, "int32"),
)


def setup(path: str, target: str | None) -> dict[str, Any]:
    arr = np.load(path)
    gc.collect()
    return {"arr": arr, "target": target}


def run(ns: dict[str, Any]) -> int:
    if ns["target"] is None:
        result = np.array(ns["arr"], copy=True)
    else:
        result = np.array(ns["arr"], copy=True, dtype=ns["target"])
    return len(result)


def main() -> None:
    print(json.dumps({"numpy": np.__version__, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        for i, (n, target) in enumerate(CASES):
            arr = np.arange(n, dtype=np.float64)
            path = str(Path(tmp) / f"{i}.npy")
            np.save(path, arr)
            del arr
            gc.collect()
            dtype = np.dtype(target or "float64")
            derived = n * dtype.itemsize
            measured = measure_call(run, setup=setup, setup_args=(path, target), repeats=3)
            actual = measured.delta_bytes
            ratio = None if actual is None else actual / derived
            print(
                json.dumps(
                    {
                        "variant": f"{n} rows to {dtype}",
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
