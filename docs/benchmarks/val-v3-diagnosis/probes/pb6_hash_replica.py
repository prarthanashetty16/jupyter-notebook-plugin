"""(b) Replicate khash's X31 string hash and the bucket -> page mapping; compare predicted vs measured
resident table growth (2M rows, 2^21 buckets) for sequential and random strings."""

import string, hashlib
import numpy as np


def x31(strings):
    width = max(len(s) for s in strings)
    mat = np.zeros((len(strings), width), dtype=np.uint64)
    for i, s in enumerate(strings):
        b = s.encode()
        mat[i, : len(b)] = np.frombuffer(b, dtype=np.uint8)
    lens = np.array([len(s.encode()) for s in strings])
    h = mat[:, 0].copy()
    for j in range(1, width):
        nxt = (h * np.uint64(31) + mat[:, j]) & np.uint64(0xFFFFFFFF)
        h = np.where(j < lens, nxt, h)
    return h


def pages(idx, per_page):
    return len(np.unique(idx // per_page))


def vocab_of(kind, U, rng):
    if kind == "seq15":
        return [f"value_{i:09d}" for i in range(U)]
    if kind == "seq12":
        return [f"{i:012d}" for i in range(U)]
    if kind == "rand12":
        a = rng.integers(0, 26, size=(U, 12))
        return ["".join(map(string.ascii_lowercase.__getitem__, r)) for r in a]
    if kind == "hex12":
        return [hashlib.md5(str(i).encode()).hexdigest()[:12] for i in range(U)]


if __name__ == "__main__":
    b, U = 2**21, 12000
    measured_add = {
        "seq15": 47.8 - 46.0,
        "seq12": 48.0 - 46.0,
        "rand12": 86.2 - 46.0,
        "hex12": 86.0 - 46.0,
    }
    for kind in measured_add:
        v = vocab_of(kind, U, np.random.default_rng(4))
        idx = (x31(v) & np.uint64(b - 1)).astype(np.int64)
        row = {}
        for stride in (4, 8, 16):
            per = 4096 // stride
            row[stride] = pages(idx, per) * 4096 / 2**20 * 1.0
        print(
            f"{kind:7s} measured add {measured_add[kind]:5.1f} MiB | predicted touched MiB by array stride: "
            + ", ".join(f"{s}B:{row[s]:5.1f}" for s in row)
            + f" | sum(8B keys + 8B vals) {2 * row[8]:5.1f}  sum(16B+8B) {row[16] + row[8]:5.1f}"
        )
