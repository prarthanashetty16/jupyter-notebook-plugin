"""groupby: categorical keys, key combinations, and which phase sets the peak (4b probes)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
import probe_lib as P
from p_gb import peak

if __name__ == "__main__":
    N = 2_000_000
    rng = np.random.default_rng(21)
    for G in (100, 100_000):
        codes = rng.permutation(np.concatenate([np.arange(G), rng.integers(0, G, N - G)]))
        cats = pd.Index([f"c{i:08d}" for i in range(G)])
        df = pd.DataFrame(
            {
                "ck": pd.Categorical.from_codes(codes, categories=cats),
                "i2": rng.integers(0, 50, N),
                "i3": rng.integers(0, 40, N),
                "f0": rng.random(N),
            }
        )
        out = {}
        for lab, code in (
            ("cat key", 'df.groupby("ck")["f0"].sum()'),
            ("cat key observed=True", 'df.groupby("ck", observed=True)["f0"].sum()'),
            ("2 small int keys (G=2000)", 'df.groupby(["i2","i3"])["f0"].sum()'),
        ):
            v = peak(df, f"cat{G}", code)
            out[lab] = None if v is None else round(v / N, 1)
        print(f"G={G:>7}: B/row", out, flush=True)
