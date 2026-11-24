"""v4 Should ``duplicated``, SECOND DERIVATION (amendment 3 (a); the only one). Fresh variants, bar +-15%.

What the step diagnostic (``p8_duplicated_diag.out``) showed the first derivation got wrong:

1. a table that has to GROW was charged 1.5x its final size (``KHASH_RESIZE_OVERLAP``, "old and new table alive").
   khash grows by ``realloc``-ing the key array and then the value array to twice the buckets, so the last growth
   holds: new flags + new keys + the OLD values while the new values are allocated. For a map table that is
   (8 + 4 + 8 + 0.25 + 0.125) B / bucket = 1.25x the final 16.25; for a key-only set (8 + 4 + 0.375) = 1.5x the final
   8.25;
2. the uniques vector was charged at 8 B per distinct value; ``Int64Vector`` / ``Float64Vector`` grow x4 through a
   zero-filling ``ndarray.resize``: 8 B x capacity, capacity = 128 x 4^j >= distinct (``ObjectVector`` grows x2);
3. a ``str`` key is converted to an object ndarray by ``_ensure_data`` (8 B/row) while it is hashed;
4. group ids and hashing are separate phases: ``get_group_index`` holds the kept codes, the ``maybe_lift`` copies
   (8 B/row per key holding a null), ``out`` and one product temporary; the lifted copies are gone before
   ``duplicated(ids)`` hashes.

SECOND DERIVATION (pandas 3.1.1; n rows, k keys, d_j distinct values of key j, D distinct rows; T(d) = the table's
peak: presized for ``min(n, 2**20 + 7)`` entries, growth factor above when d needs more buckets):

* factorize phase of key j: 8n(j-1) kept codes + 8n codes + T_map(d_j) + 8 cap(d_j) [+ 8n for a ``str`` key];
  after it: 8n(j-1) + 8n codes + 8 cap(d_j) + 8n (``astype("i8")`` copy);
* group-ids phase: 8nk + 8n x (keys holding a null) + 16n;
* hash phase: 8nk + 8n (ids) + T_set(D) + n (bool result);
* one key (``subset`` of one column or a Series): [8n for ``str``] + T_set(d) + n;
* peak = max over the phases (the compress step when the key product can overflow is unchanged from v3).

FRESH VARIANTS (no frame of the first probe or the diagnostic is reused).

    python docs/benchmarks/phase8/probes/p8_duplicated_b2.py > docs/benchmarks/phase8/probes/p8_duplicated_b2.out
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

MIB = 2**20
BAR = 0.15
SIZE_HINT_LIMIT = (1 << 20) + 7
LOAD = 0.77


def buckets(entries: float) -> int:
    return 2 ** math.ceil(math.log2(max(entries / LOAD, 4)))


def table(d: float, n: int, key_only: bool) -> float:
    pre = buckets(min(n, SIZE_HINT_LIMIT))
    b = max(pre, buckets(d))
    final = b * ((8.25) if key_only else 16.25)
    if b <= pre:
        return final
    return b * (
        12.375 if key_only else 20.375
    )  # the last realloc growth (module docstring, item 1)


def cap(d: float, text: bool) -> float:
    c = 128
    while c < d:
        c *= 2 if text else 4
    return 8.0 * c


def derived(df: pd.DataFrame, cols: list[str]) -> float:
    n, k = len(df), len(cols)
    text = [str(df[c].dtype) == "str" for c in cols]
    d = [df[c].nunique(dropna=False) for c in cols]
    if k == 1:
        return 8.0 * n * text[0] + table(d[0], n, True) + n
    rows = len(df[cols].drop_duplicates())
    nulls = sum(bool(df[c].isna().any()) for c in cols)
    phases = []
    for j in range(k):
        kept = 8.0 * n * j
        phases.append(kept + 8 * n + table(d[j], n, False) + cap(d[j], text[j]) + 8.0 * n * text[j])
        phases.append(kept + 8 * n + cap(d[j], text[j]) + 8 * n)
    phases.append(8.0 * n * k + 8.0 * n * nulls + 16.0 * n)
    phases.append(8.0 * n * k + 8.0 * n + table(rows, n, True) + n)
    return max(phases)


def frames() -> list[tuple[str, pd.DataFrame, str, list[str]]]:
    rng = np.random.default_rng(61)
    out = []
    n = 7_000_000
    out.append(
        (
            "2 keys: random float + wide random int, all distinct",
            pd.DataFrame({"x": rng.random(n), "y": rng.integers(0, 2**40, n)}),
            "y = df.duplicated()",
            ["x", "y"],
        )
    )
    n = 9_000_000
    f = np.round(rng.random(n) * 100_000) / 7
    f[::31] = np.nan
    out.append(
        (
            "3 keys, low / mid cardinality, float with nulls",
            pd.DataFrame({"a": rng.integers(0, 1000, n), "b": rng.integers(0, 5000, n), "c": f}),
            "y = df.duplicated()",
            ["a", "b", "c"],
        )
    )
    n = 6_000_000
    vocab = np.array([f"t{i:07d}" for i in range(500_000)], dtype=object)
    out.append(
        (
            "subset: str key + int key",
            pd.DataFrame(
                {
                    "s": pd.array(vocab[rng.integers(0, len(vocab), n)], dtype="str"),
                    "i": rng.integers(0, 300, n),
                    "v": rng.random(n),
                }
            ),
            "y = df.duplicated(subset=['s', 'i'])",
            ["s", "i"],
        )
    )
    n = 6_000_000
    out.append(
        (
            "str Series, 3M distinct",
            pd.DataFrame(
                {
                    "s": pd.array(
                        np.array(
                            [f"q{i:08d}" for i in rng.integers(0, 3_000_000, n)], dtype=object
                        ),
                        dtype="str",
                    )
                }
            ),
            "y = df['s'].duplicated()",
            ["s"],
        )
    )
    n = 10_000_000
    out.append(
        (
            "one dense id-like int key (subset='id')",
            pd.DataFrame({"id": rng.permutation(n), "v": rng.random(n)}),
            "y = df.duplicated(subset='id')",
            ["id"],
        )
    )
    return out  # fmt: skip


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "bar": BAR, "attempt": 2}))
    with tempfile.TemporaryDirectory() as tmp:
        for label, df, src, cols in frames():
            want = derived(df, cols)
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
            got = m.delta_bytes
            r = None if got is None else got / want
            print(json.dumps({"variant": label, "statement": src, "measured_mib": None if got is None else got / MIB,
                              "censored": got is None, "bound_mib": m.bound_bytes / MIB, "derived_mib": want / MIB,
                              "ratio": r, "within_bar": None if r is None else abs(r - 1) <= BAR}))  # fmt: skip


if __name__ == "__main__":
    main()
