"""Probe (RAM, >= 200 MiB, OS peak): what does dropping unread columns before a merge save?

Follow-up of the Phase 5b probe (``docs/benchmarks/probes/merge_peak_probe.py``), which ran at
20-88 MiB with unique right keys only and did not reproduce the benchmark's 13-19% measured saving.
Here: peaks >= 200 MiB and three key structures, each with the full merge and the merge on the
columns the cell reads (left k, v; right k):

* ``unique``: every left row matches one right row (N:1; pandas skips the left copy);
* ``fanout2``: every right key appears twice (each left row matches 2 rows: the result is 2x);
* ``overlap50``: unique right keys covering half the left keys (inner join drops half the rows).

HYPOTHESIS (Phase 5b, pandas source): the peak is ``max(key factorisation, result assembly)``.
Dropping columns can only shrink the assembly phase, so the saving is large only where assembly
dominates (fan-out, or many carried right columns) and ~0 where the left copy is skipped and the
factorisation dominates (unique N:1). If that holds, a width-proportional saving (what the frozen
model implies) is wrong in the N:1 case and roughly right only when assembly dominates.

    python docs/benchmarks/phase6/probes/p_merge_select_columns.py
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20


def frames(n: int, key_card: int, shape: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(11)
    left = pd.DataFrame({"k": rng.integers(0, key_card, n), "v": rng.random(n)})
    for i in range(5):
        left[f"f{i}"] = rng.random(n)
    if shape == "unique":
        keys = np.arange(key_card)
    elif shape == "fanout2":
        keys = np.repeat(np.arange(key_card), 2)
    else:  # overlap50
        keys = np.arange(key_card // 2)
    right = pd.DataFrame({"k": keys})
    for name in ("w", "x0", "x1"):
        right[name] = rng.random(len(keys))
    return left, right


def setup(lp: str, rp: str, variant: str) -> tuple:
    left, right = pd.read_pickle(lp), pd.read_pickle(rp)
    gc.collect()
    return left, right, variant


def run(state: tuple) -> int:
    left, right, variant = state
    if variant == "selected":
        left, right = left[["k", "v"]], right[["k"]]
    return len(left.merge(right, on="k")["v"])


def main() -> None:
    print(f"pandas {pd.__version__}")
    print("shape      rows       full MiB  selected MiB  saving  inputs MiB")
    with tempfile.TemporaryDirectory() as tmp:
        for shape, n in (("unique", 6_000_000), ("fanout2", 3_000_000), ("overlap50", 6_000_000)):
            left, right = frames(n, 500_000, shape)
            lp, rp = str(Path(tmp) / "l.pkl"), str(Path(tmp) / "r.pkl")
            left.to_pickle(lp)
            right.to_pickle(rp)
            inputs = (left.memory_usage().sum() + right.memory_usage().sum()) / MIB
            del left, right
            gc.collect()
            res = {}
            for variant in ("full", "selected"):
                m = measure_call(run, setup=setup, setup_args=(lp, rp, variant), repeats=3)
                res[variant] = None if m.delta_bytes is None else m.delta_bytes / MIB
            full, sel = res["full"], res["selected"]
            saving = "n/a" if not (full and sel is not None) else f"{1 - sel / full:.0%}"
            print(
                f"{shape:9} {n:>10,}  {('censored' if full is None else f'{full:8.0f}'):>9}"
                f"  {('censored' if sel is None else f'{sel:8.0f}'):>12}  {saving:>6}  {inputs:8.0f}"
            )


if __name__ == "__main__":
    main()
