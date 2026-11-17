"""(b) khash int64 hash replica: predicted touched table pages vs measured (pb5) for dense / random keys."""

import numpy as np


def h_int64(keys):
    k = keys.astype(np.uint64)
    return ((k >> np.uint64(33)) ^ k ^ (k << np.uint64(11))) & np.uint64(0xFFFFFFFF)


def touched_mib(keys, b, stride_arrays=(8, 8)):
    idx = (h_int64(keys) & np.uint64(b - 1)).astype(np.int64)
    out = 0.0
    for s in stride_arrays:
        out += len(np.unique(idx // (4096 // s))) * 4096 / 2**20
    return out


if __name__ == "__main__":
    b = 2**21
    meas = {  # pb5, n = 2M: (dense, random) peak MiB minus the U=100 baseline 16.5
        5000: (31.8 - 16.5, 38.3 - 16.5),
        12000: (32.0 - 16.5, 46.2 - 16.5),
        40000: (33.8 - 16.5, 49.0 - 16.5),
        200000: (39.2 - 16.5, 52.0 - 16.5),
    }
    rng = np.random.default_rng(4)
    for U, (md, mr) in meas.items():
        dense = touched_mib(np.arange(U), b)
        rand = touched_mib(rng.integers(0, 2**62, U), b)
        print(
            f"U={U:>7}: dense predicted {dense:5.1f} measured {md:5.1f} | random predicted {rand:5.1f} measured {mr:5.1f}  (MiB, keys+vals arrays)"
        )
