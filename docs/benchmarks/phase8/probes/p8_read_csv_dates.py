"""First derivation probe for read_csv(parse_dates); adoption bar +-15%."""

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
N = 5_000_000


def setup(path: str, dates: list[str] | None) -> dict[str, Any]:
    return {"path": path, "dates": dates}


def run(ns: dict[str, Any]) -> int:
    if ns["dates"] is None:
        frame = pd.read_csv(ns["path"])
    else:
        frame = pd.read_csv(ns["path"], parse_dates=ns["dates"])
    return len(frame)


def _measure(path: str, dates: list[str] | None) -> float | None:
    measured = measure_call(run, setup=setup, setup_args=(path, dates), repeats=3)
    return measured.delta_bytes


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "rows": N, "bar": 0.15}))
    with tempfile.TemporaryDirectory() as tmp:
        rng = np.random.default_rng(42)
        dates = pd.date_range("2020-01-01", periods=N, freq="s")
        for i, parsed in enumerate((["d0"], ["d0", "d1"])):
            df = pd.DataFrame(
                {
                    "d0": dates,
                    "d1": dates + pd.Timedelta(days=30),
                    "v": rng.integers(0, 1000, N, dtype=np.int64),
                }
            )
            path = str(Path(tmp) / f"{i}.csv")
            df.to_csv(path, index=False)
            del df
            gc.collect()
            base = _measure(path, None)
            actual = _measure(path, parsed)
            extra = None if base is None or actual is None else actual - base
            derived = 8 * N * len(parsed)
            ratio = None if extra is None else extra / derived
            print(
                json.dumps(
                    {
                        "variant": f"{len(parsed)} parsed date column(s)",
                        "base_peak_mib": None if base is None else base / MIB,
                        "parsed_peak_mib": None if actual is None else actual / MIB,
                        "measured_extra_mib": None if extra is None else extra / MIB,
                        "derived_extra_mib": derived / MIB,
                        "ratio": ratio,
                        "within_bar": None if ratio is None else abs(ratio - 1) <= 0.15,
                        "censored": base is None or actual is None,
                    }
                )
            )


if __name__ == "__main__":
    main()
