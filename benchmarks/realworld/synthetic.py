"""Synthetic notebooks with KNOWN behaviour, to validate the Phase 8a harness before any real notebook.

Each notebook states what the harness must observe (``EXPECT``); ``tests/test_realworld_harness.py``
checks it, and ``python -m benchmarks.realworld.synthetic <dir>`` writes them for a manual run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MIB = 2**20
KNOWN_ALLOC_MIB = 400  # np.ones(400 MiB / 8) touches every page: incremental peak ~= 400 MiB


def _nb(cells: list[str]) -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "cells": [
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": src,
            }  # fmt: skip
            for src in cells
        ],
    }


def notebooks(rows: int = 1_000_000) -> dict[str, list[str]]:
    setup = (
        "import numpy as np\nimport pandas as pd\nrng = np.random.default_rng(0)\n"
        f"n = {rows}\n"
        "df = pd.DataFrame({'k': rng.integers(0, 1000, n), 'v': rng.random(n), "
        "'s': rng.choice(np.array(['a', 'b', 'c', 'd'], dtype=object), n)})\n"
        "right = pd.DataFrame({'k': np.arange(1000), 'w': rng.random(1000)})"
    )
    return {
        "syn_ops": [
            setup,
            "g = df.groupby('k')['v'].sum()",
            "m = df.merge(right, on='k')",
            "c = df['s'].astype('category')",
            "srt = df.sort_values('v')",
            "dd = df.drop_duplicates(subset=['k'])",
            "cc = pd.concat([df, df])",
            "df.to_csv('syn.csv', index=False)",
            "r = pd.read_csv('syn.csv')",
        ],
        "syn_fail": [
            "import numpy as np",
            "raise ValueError('a failing cell')",
            "!echo this shell cell must never run",
            "x = np.arange(10).sum()",
        ],
        "syn_alloc": [
            "import numpy as np",
            f"a = np.ones({KNOWN_ALLOC_MIB * MIB // 8})",  # raises the peak: valid, ~400 MiB
            f"del a\nb = np.ones({100 * MIB // 8})",  # a freed first: below the historical peak: CENSORED
            f"c = np.ones({2 * KNOWN_ALLOC_MIB * MIB // 8})",  # raises the peak again: valid, ~800 MiB
        ],
        "syn_watchdog": [
            "import numpy as np",
            f"big = np.ones({1600 * MIB // 8})",  # the test's cap is far below this: killed
            "print('never reached')",
        ],
        "syn_timeout": ["import time", "time.sleep(30)", "print('never reached')"],
        "syn_consecutive": [
            "import numpy as np",
            *["1 / 0" for _ in range(6)],
            "print('never reached after 5 consecutive failures')",
        ],
    }


def write(folder: Path, rows: int = 1_000_000) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, cells in notebooks(rows).items():
        path = folder / f"{name}.ipynb"
        path.write_text(json.dumps(_nb(cells), indent=1), encoding="utf-8")
        out[name] = path
    return out


if __name__ == "__main__":
    for p in write(Path(sys.argv[1])).values():
        print(p)
