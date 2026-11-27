"""First derivation probe for np.linspace; adoption bar +-15%."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from nexus.measure import measure_call

MIB = 2**20
CASES = (
    (40_000_000, "float64"),
    (60_000_000, "float32"),
    (30_000_000, "float64"),
)


def setup(num: int, dtype: str) -> dict[str, Any]:
    return {"num": num, "dtype": dtype}


def run(ns: dict[str, Any]) -> int:
    result = np.linspace(0.0, 1.0, ns["num"], dtype=ns["dtype"])
    return len(result)


def main() -> None:
    print(json.dumps({"numpy": np.__version__, "bar": 0.15}))
    for num, dtype in CASES:
        derived = num * np.dtype(dtype).itemsize
        measured = measure_call(run, setup=setup, setup_args=(num, dtype), repeats=3)
        actual = measured.delta_bytes
        ratio = None if actual is None else actual / derived
        print(
            json.dumps(
                {
                    "variant": f"{num} {dtype}",
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
