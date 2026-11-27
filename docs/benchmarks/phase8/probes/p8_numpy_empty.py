"""First derivation probe for np.empty allocation peak; adoption bar +-15%."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from nexus.measure import measure_call

MIB = 2**20
CASES = (
    ("32M float64", (32_000_000,), "float64"),
    ("64M float32", (64_000_000,), "float32"),
    ("24M int64", (24_000_000,), "int64"),
)


def setup(shape: tuple[int, ...], dtype: str) -> dict[str, Any]:
    return {"shape": shape, "dtype": dtype}


def run(ns: dict[str, Any]) -> int:
    result = np.empty(ns["shape"], dtype=ns["dtype"])
    return len(result)


def main() -> None:
    print(json.dumps({"numpy": np.__version__, "bar": 0.15}))
    for label, shape, dtype in CASES:
        derived = int(np.prod(shape)) * np.dtype(dtype).itemsize
        measured = measure_call(run, setup=setup, setup_args=(shape, dtype), repeats=3)
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
