"""merge with non-unique keys / right and outer joins: which phase dominates (4b probe)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import probe_lib as P
from p_mg import mk, save
from probe_lib import MIB, measure_call


def phases(L, R, how, tag):
    dl, dr = save(L, tag + "L"), save(R, tag + "R")
    out = {}
    for lab, code in (
        (
            "indexers",
            f'__import__("pandas.core.reshape.merge", fromlist=["x"]).get_join_indexers([left["key"]._values],[right["key"]._values], how="{how}")',
        ),
        ("full", f'pd.merge(left, right, on="key", how="{how}")'),
    ):
        m = measure_call(P.run, setup=P.setup, setup_args=({"left": dl, "right": dr}, code), summarize=P.summarize, repeats=2)
        out[lab] = None if m.delta_bytes is None else m.delta_bytes / MIB
    M = len(pd.merge(L, R, on="key", how=how))
    return M, out


if __name__ == "__main__":
    N = 1_000_000
    rng = np.random.default_rng(15)
    row_l = 5  # key + 4 object columns (40 B/row)
    L = mk(N, rng.permutation(N), 1, 0, 0, n_obj=4)
    keys = rng.permutation(N)[: N // 8]
    R = mk(N // 2, keys[np.arange(N // 2) % len(keys)], 2, 0, 2, n_obj=1)  # right keys repeat 4x
    moved_l = float(L.memory_usage(index=False, deep=False).sum())
    moved_r = float(R.memory_usage(index=False, deep=False).sum())
    print(f"left {len(L)} rows {moved_l / len(L):.0f} B/row, right {len(R)} rows {moved_r / len(R):.0f} B/row, right distinct keys {R['key'].nunique()}")
    for how in ("inner", "right", "left", "outer"):
        M, ph = phases(L, R, how, "x3")
        formula_full = M * (moved_l / len(L) + moved_r / len(R) + 16) / MIB
        print(f"how={how:6s} M={M:>8}  indexers={ph['indexers']:.1f} MiB  full={ph['full']:.1f} MiB   M*(row_l+row_r+16)={formula_full:.1f} MiB  8M={8 * M / MIB:.1f}", flush=True)
