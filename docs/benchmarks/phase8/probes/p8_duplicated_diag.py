"""v4 Should ``duplicated``, DIAGNOSTIC (amendment 3 (a)): the peak after each internal step, next to the first
derivation's term for it. No bar; it locates the wrong term before the one allowed second derivation.

Steps, each a cumulative prefix of pandas 3.1.1 ``DataFrame.duplicated`` (``frame.py``), measured in a fresh process
(OS peak, inputs from disk, median of 3):

1. ``factorize`` of the FIRST key only (``algorithms.factorize(vals, size_hint=n)``, then ``.astype("i8")``);
2. ``factorize`` of every key, the i8 code arrays kept in ``labels`` (as ``map(f, vals)`` keeps them);
3. + ``get_group_index(labels, shape, sort=False, xnull=False)`` (the combined int64 ids);
4. + ``algorithms.duplicated(ids, keep="first")`` (the key-only hash table and the bool result);
5. the real ``df.duplicated(...)`` (the Series wrap).

The first derivation's terms (``p8_duplicated.py``): factorize phase ``8n(k-1) + 16n + table + 8 key_frac n`` (table =
``khash_presized_bytes(key_frac n, n)``); ids phase ``8nk + 16n + ids_table + n + 8n nulls``.

The ``str`` Series variant was censored in the first probe: its peak (about 1 B/row plus a table sized by 200k
distinct values) stays below the ~8 B/row transient of loading a ``str`` column at any row count. MEASUREMENT FIX: the
same statement on a ``str`` Series whose 8M values are all distinct, so the table term dominates.

    python docs/benchmarks/phase8/probes/p8_duplicated_diag.py > docs/benchmarks/phase8/probes/p8_duplicated_diag.out
"""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pandas.core import algorithms
from pandas.core.sorting import get_group_index

from nexus.measure import measure_call
from nexus.models._util import khash_presized_bytes

MIB = 2**20


def _codes(df: pd.DataFrame, cols: list[str], upto: int) -> tuple[list[np.ndarray], list[int]]:
    labels, shape = [], []
    for c in cols[:upto]:
        lab, uniq = algorithms.factorize(df[c]._values, size_hint=len(df))
        labels.append(lab.astype("i8"))
        shape.append(len(uniq))
    return labels, shape


def step(ns: dict[str, Any]) -> int:
    df, cols, k = ns["df"], ns["cols"], ns["step"]
    if k == 5:
        r = df.duplicated(subset=cols) if len(cols) > 1 else df[cols[0]].duplicated()
        return len(r)
    labels, shape = _codes(df, cols, 1 if k == 1 else len(cols))
    if k <= 2:
        return len(labels)
    ids = get_group_index(labels, tuple(shape), sort=False, xnull=False)
    if k == 3:
        return len(ids)
    return len(algorithms.duplicated(ids, keep="first"))


def setup(path: str, cols: list[str], k: int) -> dict[str, Any]:
    ns = {"df": pd.read_pickle(path), "cols": cols, "step": k}
    gc.collect()
    return ns


def frames() -> list[tuple[str, pd.DataFrame, list[str]]]:
    rng = np.random.default_rng(51)  # the first probe's seed and frames
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
    uniq = pd.DataFrame(
        {"s": pd.array(np.array([f"u{i:09d}" for i in range(n)], dtype=object), dtype="str")}
    )
    return [
        ("3 keys, all rows distinct", distinct, ["a", "b", "c"]),
        ("subset of 2 low-cardinality keys", low, ["a", "b"]),
        ("3 mixed keys with nulls", mixed, ["k", "f", "s"]),
        ("str Series, 8M distinct (measurement fix)", uniq, ["s"]),
    ]


def first_terms(df: pd.DataFrame, cols: list[str]) -> dict[str, float]:
    n, k = len(df), len(cols)
    key = max(df[c].nunique(dropna=False) for c in cols) / n
    rows = (len(df[cols].drop_duplicates()) if k > 1 else df[cols[0]].nunique(dropna=False)) / n
    nulls = sum(bool(df[c].isna().any()) for c in cols)
    table = khash_presized_bytes(key * n, n)
    ids_table = khash_presized_bytes(rows * n, n, key_only=True)
    if k <= 1:
        return {"hash (1 key)": ids_table + n, "table": ids_table}
    return {"factorize phase": 8 * n * (k - 1) + 16 * n + table + 8 * key * n, "table (per key)": table,
            "ids phase": 8 * n * k + 16 * n + ids_table + n + 8 * n * nulls, "ids_table": ids_table}  # fmt: skip


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__}))
    with tempfile.TemporaryDirectory() as tmp:
        for label, df, cols in frames():
            terms = {k: v / MIB for k, v in first_terms(df, cols).items()}
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            steps = (5,) if len(cols) == 1 else (1, 2, 3, 4, 5)
            for k in steps:
                m = measure_call(step, setup=setup, setup_args=(path, cols, k), repeats=3)
                print(json.dumps({"variant": label, "step": k, "measured_mib": None if m.delta_bytes is None
                                  else m.delta_bytes / MIB, "censored": m.delta_bytes is None,
                                  "bound_mib": m.bound_bytes / MIB, "first_derivation_terms_mib": terms}))  # fmt: skip


if __name__ == "__main__":
    main()
