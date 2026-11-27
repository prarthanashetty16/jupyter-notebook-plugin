"""v4 Should item ``duplicated``: probe at >= 200 MiB (OS peak, fresh process, inputs from disk, median of 3); bar +-15%.

DERIVATION (pandas 3.1.1 source, written before this probe ran). ``DataFrame.drop_duplicates`` is
``self[-self.duplicated(subset, keep)]``, so ``duplicated`` is its hash phase WITHOUT the mask / take phase. The
v3 ``drop_duplicates`` model (``nexus/models/drop_duplicates.py``, verified within 0.2% on 3-key frames) gives that
phase: several key columns -> factorize each (8 B/row codes kept, a presized table by distinct values), fuse them
into int64 ids (8 B/row + a transient of the same size), hash the ids with a key-only table by distinct rows, and
return a bool array (1 B/row); the compress step when the key product can overflow; ``maybe_lift`` (8 B/row) per
key column holding a null. One key column (``df['c'].duplicated()`` or ``subset='c'``): the values are hashed
directly, a key-only table plus the bool result. The derived peak is ``DropDuplicatesModel.ram_at`` with the take
term removed, evaluated at the TRUE distinct fractions of each frame (known here).

    python docs/benchmarks/phase8/probes/p8_duplicated.py > docs/benchmarks/phase8/probes/p8_duplicated.out
"""

from __future__ import annotations

import gc
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.measure import measure_call
from nexus.models._util import group_ids_overflow, khash_presized_bytes

MIB = 2**20
BAR = 0.15


def hash_phase(
    n: int, k: int, key_frac: float, row_frac: float, null_keys: int, log2_shape: float
) -> float:
    """``DropDuplicatesModel.ram_at`` without the take term (same formula, copied so the probe is self-contained)."""
    table = khash_presized_bytes(key_frac * n, n)
    ids_table = khash_presized_bytes(row_frac * n, n, key_only=True)
    if k <= 1:
        return ids_table + n
    factorize = 8 * n * (k - 1) + 16 * n + table + 8 * key_frac * n
    ids = 8 * n * k + 16 * n + ids_table + n + 8 * n * null_keys
    compress = 0.0
    if log2_shape >= 63 or group_ids_overflow(k, key_frac * n):
        compress = 8 * n * k + 24 * n + khash_presized_bytes(row_frac * n, n) + 8 * n * null_keys
    return max(factorize, ids, compress)


def truth(df: pd.DataFrame, cols: list[str]) -> tuple[float, float, int, float]:
    n = len(df)
    key = max(df[c].nunique(dropna=False) for c in cols) / n
    rows = (
        len(df[cols].drop_duplicates()) if len(cols) > 1 else df[cols[0]].nunique(dropna=False)
    ) / n
    nulls = sum(bool(df[c].isna().any()) for c in cols)
    shape = sum(math.log2(df[c].nunique(dropna=False) + 1) for c in cols)
    return key, rows, nulls, shape


def frames() -> list[tuple[str, pd.DataFrame, str, list[str]]]:
    rng = np.random.default_rng(51)
    n = 8_000_000
    distinct = pd.DataFrame(
        {"a": rng.permutation(n), "b": rng.random(n), "c": rng.integers(0, 10**9, n)}
    )
    low = pd.DataFrame(
        {"a": rng.integers(0, 50, n), "b": rng.integers(0, 40, n), "v": rng.random(n)}
    )
    f = rng.random(n)
    f[::17] = np.nan
    vocab = np.array([f"w{i:06d}" for i in range(200_000)], dtype=object)
    s = vocab[rng.integers(0, len(vocab), n)].copy()
    s[::23] = None
    mixed = pd.DataFrame({"k": rng.integers(0, 1000, n), "f": f, "s": pd.array(s, dtype="str")})
    text = pd.DataFrame({"s": pd.array(vocab[rng.integers(0, len(vocab), n)], dtype="str")})
    return [
        ("3 keys, all rows distinct", distinct, "y = df.duplicated()", ["a", "b", "c"]),
        (
            "subset of 2 low-cardinality keys",
            low,
            "y = df.duplicated(subset=['a', 'b'])",
            ["a", "b"],
        ),
        ("3 mixed keys with nulls", mixed, "y = df.duplicated()", ["k", "f", "s"]),
        ("Series of str, 200k distinct", text, "y = df['s'].duplicated()", ["s"]),
    ]


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "bar": BAR}))
    with tempfile.TemporaryDirectory() as tmp:
        for label, df, src, cols in frames():
            key, rows, nulls, shape = truth(df, cols)
            want = hash_phase(len(df), len(cols), key, rows, nulls, shape)
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
            got = m.delta_bytes
            r = None if got is None else got / want
            print(json.dumps({"variant": label, "statement": src, "measured_mib": None if got is None else got / MIB,
                              "censored": got is None, "bound_mib": m.bound_bytes / MIB, "derived_mib": want / MIB,
                              "ratio": r, "within_bar": None if r is None else abs(r - 1) <= BAR,
                              "truth": {"key_frac": key, "row_frac": rows, "null_keys": nulls}}))  # fmt: skip


if __name__ == "__main__":
    main()
