"""groupby peak RAM vs number of groups, key dtype, value columns (Phase 4b derivation probes)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np
import pandas as pd
from probe_lib import MIB, CACHE, measure_call, store
import probe_lib as P


def save(df, tag):
    path = CACHE / ("gb_" + tag)
    if not (path / "meta.json").exists():
        store.save(df, path)
    return str(path)


def peak(df, tag, code):
    d = save(df, tag)
    m = measure_call(P.run, setup=P.setup, setup_args=({"df": d}, code), summarize=P.summarize, repeats=2)
    return None if m.delta_bytes is None else m.delta_bytes


if __name__ == "__main__":
    N = 2_000_000
    rng = np.random.default_rng(11)
    vocab_all = np.array([f"key_{i:09d}" for i in range(N)], dtype=object)
    for G in (10, 20_000, 500_000, 2_000_000):
        codes = rng.permutation(np.concatenate([np.arange(G), rng.integers(0, G, N - G)])) if G < N else rng.permutation(N)
        base = {
            "ik": codes.astype(np.int64),
            "sk": pd.Series(vocab_all[codes], dtype=object),
            "f0": rng.random(N),
            "f1": rng.random(N),
            "f2": rng.random(N),
            "i1": rng.integers(0, 100, N),
        }
        df = pd.DataFrame(base)
        res = {}
        for lab, code in (
            ("int key, 1 value", 'df.groupby("ik")["f0"].sum()'),
            ("str key, 1 value", 'df.groupby("sk")["f0"].sum()'),
            ("str key, 3 values", 'df.groupby("sk")[["f0","f1","f2"]].sum()'),
            ("str key, sort=False", 'df.groupby("sk", sort=False)["f0"].sum()'),
            ("2 keys (int,str)", 'df.groupby(["ik","sk"])["f0"].sum()'),
        ):
            v = peak(df, f"{G}", code)
            res[lab] = None if v is None else round(v / N, 1)
        print(f"G={G:>8} (G/n={G/N:.4f})  B/row:", res, flush=True)
