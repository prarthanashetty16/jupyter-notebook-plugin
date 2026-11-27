"""First derivation probe for DataFrame.sample row takes; adoption bar +-15%."""

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
    ("10% without replacement", 1_500_000, False),
    ("50% without replacement", 7_500_000, False),
    ("all rows with replacement", 15_000_000, True),
)


def setup(path: str, selected: int, replace: bool) -> dict[str, Any]:
    gc.collect()
    return {"df": pd.read_pickle(path), "selected": selected, "replace": replace}


def run(ns: dict[str, Any]) -> int:
    result = ns["df"].sample(
        n=ns["selected"], replace=ns["replace"], random_state=17
    )
    return len(result)


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        rng = np.random.default_rng(77)
        frame = pd.DataFrame({"a": rng.random(N), "b": rng.integers(0, 100, N, dtype=np.int64)})
        path = str(Path(tmp) / "frame.pkl")
        frame.to_pickle(path)
        del frame
        gc.collect()
        moved = 16 * N
        for label, selected, replace in CASES:
            derived = moved * (max(1.0, selected / N) if replace else selected / N)
            measured = measure_call(
                run, setup=setup, setup_args=(path, selected, replace), repeats=3
            )
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
