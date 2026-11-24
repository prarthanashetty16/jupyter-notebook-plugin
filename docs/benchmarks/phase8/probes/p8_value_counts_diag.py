"""v4 item (1c) value_counts, DIAGNOSTIC step decomposition (not the adoption probe; no bar).

The v3 second attempt was contradicted at int64 n = 12M, u = 50k (0.34) and u = 1M (0.55). Source read since (pandas
3.1.1 ``hashtable_func_helper.pxi.in`` / ``khash.h``, fetched from GitHub):

* numeric ``value_count`` presizes the table to ``roundup32(n)`` buckets; the flag array (``n_buckets / 8`` bytes) is
  memset, while the key and value arrays (8 B / bucket each) are resident only on pages a key lands on;
* the int64 hash is ``(k >> 33) ^ k ^ (k << 11)``, NOT a random hash, so the touched pages depend on the key
  values, not only on their count;
* the key Vector grows x4 through ``ndarray.resize`` (zero-filled), then shrinks in place.

To locate the u = 1M gap, this probe measures each step on its own (same OS-peak instrument, fresh process, inputs
from disk, median of 3):

1. ``htable.value_count(values, True)`` alone (phase 1: the table);
2. ``s.value_counts(sort=False)`` (+ Index and Series);
3. ``s.value_counts()`` (+ the stable descending sort);
4. ``s.sort_values(ascending=False, kind="stable")`` on a Series of u counts, as phase 2 alone.

DERIVED phase 1 (printed next to step 1; fixed in this file before it ran): with B = roundup32(n) buckets, P = B / 512
pages of 4 KiB per 8-byte array,
* flags ``B / 8`` bytes (``__ac_fsize``: one uint32 per 32 buckets, memset to 0xff);
* key and value arrays (8 B / bucket each) resident only on touched pages: the distinct pages of the keys' FIRST
  buckets ``hash(k) & (B - 1)`` (exact, from the keys), plus, for keys whose first bucket collides, the murmur
  double-hashing step lands on effectively random pages: + (P - pages_first)(1 - exp(-collided / P));
* the key Vector: capacity 128 x 4^j >= u, zero-filled by ``ndarray.resize`` (8 B each), and the counts (8 u).
Phase 1 = flags + 2 x pages x 4 KiB + 8 x capacity + 8 u. The v3 attempt missed u = 1M by 0.55; this derivation's
phase 1 alone gives about 98 MiB there against 151 measured, so the miss is expected OUTSIDE the table (step 2-4).

    python docs/benchmarks/phase8/probes/p8_value_counts_diag.py > docs/benchmarks/phase8/probes/p8_value_counts_diag.out
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from pandas._libs import hashtable as htable

from nexus.measure import measure_call

MIB = 2**20
N = 12_000_000


def roundup32(x: int) -> int:
    x -= 1
    for sh in (1, 2, 4, 8, 16):
        x |= x >> sh
    return x + 1


def table_derived(keys: np.ndarray, n: int) -> float:
    """Derived phase-1 bytes (module docstring) from the distinct int64 keys."""
    b = roundup32(n)
    mask = np.uint64(b - 1)
    k = keys.astype(np.int64).view(np.uint64)
    h = ((k >> np.uint64(33)) ^ k ^ (k << np.uint64(11))) & np.uint64(0xFFFFFFFF)
    first = np.unique(h & mask)
    pages_first = np.unique(first >> np.uint64(9)).size
    pages_total = b // 512
    collided = len(keys) - first.size
    pages = pages_first + (pages_total - pages_first) * (1 - np.exp(-collided / pages_total))
    u = len(keys)
    cap = 128
    while cap < u:
        cap *= 4
    return b / 8 + 2 * pages * 4096 + 8 * cap + 8 * u


def setup(path: str) -> pd.Series:
    s = pd.read_pickle(path)
    gc.collect()
    return s


def step_table(s: pd.Series) -> int:
    keys, counts, _ = htable.value_count(s.to_numpy(), True)
    return len(keys)


def step_unsorted(s: pd.Series) -> int:
    return len(s.value_counts(sort=False))


def step_full(s: pd.Series) -> int:
    return len(s.value_counts())


def step_sort_only(s: pd.Series) -> int:
    return len(s.sort_values(ascending=False, kind="stable"))


def main() -> None:
    print(f"pandas {pd.__version__}, numpy {np.__version__}, n = {N}")
    print("| keys | step | measured MiB | derived phase 1 MiB |")
    print("|---|---|---|---|")
    rng = np.random.default_rng(5)
    with tempfile.TemporaryDirectory() as tmp:
        for u in (50_000, 1_000_000, 6_000_000):
            s = pd.Series(rng.integers(0, u, N))
            derived = table_derived(np.unique(s.to_numpy()), N) / MIB
            counts = s.value_counts(sort=False).reset_index(drop=True)
            p_s, p_c = str(Path(tmp) / "s.pkl"), str(Path(tmp) / "c.pkl")
            s.to_pickle(p_s)
            counts.to_pickle(p_c)
            del s, counts
            gc.collect()
            for label, fn, path in (("1 table (htable.value_count)", step_table, p_s),
                                    ("2 value_counts(sort=False)", step_unsorted, p_s),
                                    ("3 value_counts()", step_full, p_s),
                                    ("4 sort of the u counts alone", step_sort_only, p_c)):  # fmt: skip
                m = measure_call(fn, setup=setup, setup_args=(path,), repeats=3)
                got = "censored" if m.delta_bytes is None else f"{m.delta_bytes / MIB:.1f}"
                d = f"{derived:.1f}" if label.startswith("1") else ""
                print(f"| int64 u={u} | {label} | {got} | {d} |")


if __name__ == "__main__":
    main()
