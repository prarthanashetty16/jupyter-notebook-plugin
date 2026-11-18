"""(4b.3) Does the khash int64 replica explain the config-dependent merge peak?

Resident table pages for the UNION of left and right keys (right keys inserted first, then left),
bucket count 2^21 at n = 1M, vs the measured get_join_indexers peaks (pf1 / pf3)."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "src"))
import numpy as np
from benchmarks.datasets import make_join_pair
from benchmarks.suite import BASE
from nexus.stats import _int64_hash
MIB = 2**20
MEASURED = {(0.25, 2.0, 0.1): 65.0, (0.25, 6.0, 0.1): 49.0, (0.25, 10.0, 0.1): 59.3, (0.2, 10.0, 0.15): 69.8, (0.9, 6.0, 0.1): 48.6, (1.0, 1.0, 0.1): 36.5}
def touched(keys, b):
    idx = (_int64_hash(keys) & np.uint64(b - 1)).astype(np.int64)
    return sum(len(np.unique(idx // (4096 // s))) * 4096 for s in (8, 8)) / MIB
if __name__ == "__main__":
    n, b = 1_000_000, 2**21
    print("config                  union      touched MiB   measured   measured - touched")
    for (o, f, r), meas in MEASURED.items():
        left, right = make_join_pair(BASE.with_(n_rows=n, seed=7), int(n * r), overlap=o, fanout=f, seed=11)
        lk, rk = left["k"].to_numpy(), right["k"].to_numpy()
        union = np.unique(np.concatenate([lk, rk]))
        t = touched(union, b)
        print(f"overlap={o:<4} fanout={f:<5} {len(union):>9,}   {t:8.1f}   {meas:8.1f}   {meas - t:8.1f}")
