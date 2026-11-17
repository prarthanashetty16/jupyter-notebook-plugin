"""groupby: result-frame phase with many aggregated columns at high group counts (4b probe)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from p_gb import peak

if __name__ == "__main__":
    N = 2_000_000
    rng = np.random.default_rng(31)
    for G in (20_000, 2_000_000):
        codes = rng.permutation(np.concatenate([np.arange(G), rng.integers(0, G, N - G)])) if G < N else rng.permutation(N)
        df = pd.DataFrame({"ik": codes.astype(np.int64), **{f"f{j}": rng.random(N) for j in range(10)}})
        out = {}
        for k in (1, 4, 10):
            cols = [f"f{j}" for j in range(k)]
            for lab, code in (("sum", f'df.groupby("ik")[{cols!r}].sum()'), ("mean", f'df.groupby("ik")[{cols!r}].mean()')):
                v = peak(df, f"res{G}", code)
                out[f"{k} cols {lab}"] = None if v is None else round(v / N, 1)
        out["whole frame sum"] = round(peak(df, f"res{G}", 'df.groupby("ik").sum()') / N, 1)
        print(f"G={G:>8}: B/row", out, flush=True)
