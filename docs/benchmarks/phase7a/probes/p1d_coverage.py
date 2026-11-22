"""Phase 7a probe 1d (information only): RAM and time of set_index, value_counts, apply, explode and
fillna on pandas-3 text columns, against derivations written from pandas 3.1.1 source BEFORE the run.

Isolated (``nexus.measure.measure_call``: fresh spawned process, inputs from a pickle on disk,
incremental OS peak, median of 3), mains power. Inputs >= 200 MiB; peaks reported as measured.
**Adoption bar (fixed before the run): an operation is derivable for v3 only if EVERY variant below is
within +-15% of its derived peak** (measurements censored below the instrument's floor count as
consistent only when the derived peak is also below the floor). n = rows, u = distinct values,
E = exploded elements.

DERIVATIONS (bytes; ``_util`` helpers are the validated factorize / khash ones):

* ``df.set_index(col)`` (drop=True): ``self.copy(deep=False)``; ``ensure_index_from_sequences`` ->
  ``maybe_sequence_to_range`` (``infer_dtype`` scan and ``is_sequence_range`` early exit: no allocation
  for non-range keys) -> ``Index(values)``, which COPIES an ndarray in pandas 3 (8 B/row for int64 /
  float64 / object or str pointers); ``del frame[col]`` on the shallow copy splits blocks as views.
  -> peak = n x itemsize(col).
* ``s.value_counts()`` (sort=True, numeric): phase 1 ``htable.value_count``: hash table presized for
  min(n, 2**20+7) entries, grown when u exceeds 77% of it, resident pages per ``factorize_parts``'
  table term, + keys and counts (16 u) built while the table is alive; phase 2 (table freed):
  keys + counts + the Index copy of the keys (24 u) + ``nargsort`` (mask u, arange 8u, non-NaN values
  8u, non-NaN idx 8u, argsort result fancy-indexed 8u, concatenate 8u: 41 u). -> peak = max(table +
  16u, 65u).
* ``s.explode()`` (lists of small cached ints: no new element objects): ``reshape.explode``: counts
  (8 n) and the object result (8 E); ``index.repeat(counts)``: int64 (8 E). -> peak = 8n + 16E.
* ``df.explode(col)`` with one other float64 column: the Series part (8n + 16E) + ``drop(col).join``
  on a monotonic index: join index + left indexer (16 E; right indexer None for the unique left) +
  the other column taken (8 E) + ``self.index.take`` (8 E). -> peak = 8n + 48E.
* ``s.apply(np.sqrt)`` (ufunc): applied to the array: the float64 result (8 n). -> peak = 8n.
* ``s.apply(lambda x: x * 2)`` (float64): ``lib.map_infer``: object result (8 n) + one new float per
  row (24 B, pymalloc size class 32) + ``maybe_convert_objects`` -> float64 (8 n) while both alive.
  -> peak = 48 n.
* ``df.apply(lambda r: r['a'] + r['b'], axis=1)`` (float64 frame, single block): row Series from a
  reused view; results in a dict {int: float}: per row an int key object (32 B; > 256), a float
  (32 B) and a dict entry (combined table: 8 B index + 24 B entry, at <= 2/3 load after the last
  doubling: ~48 B average); then ``Series(dict)``: keys list + values list (16 n) and the float64
  result (8 n). -> peak ~ 136 n (the dict term is a range: 32..96 B per entry).
* text ``s.fillna('z')`` (pandas-3 ``str``, python storage: no pyarrow): ``Block.fillna``:
  ``isna`` (1 B/row) and ``putmask`` on a copy of the pointer array (8 B/row); the filled value is one
  shared object. -> peak = 9n.
* text ``s.fillna(0)`` (incompatible value): coerced to ``object`` (``astype(object)``: 8 B/row pointer
  copy), then the numpy-block fillna on it: mask (1 n) + putmask copy (8 n). -> peak = 17n.

    python docs/benchmarks/phase7a/probes/p1d_coverage.py <scratch dir> > docs/benchmarks/phase7a/probes/p1d_coverage.out
"""

from __future__ import annotations

import gc
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call
from nexus.models import _util as u
from nexus.power import power_state

MIB = 2**20


def vc_derived(n: int, distinct: int) -> float:
    table, _ = u.factorize_parts("numeric", n, distinct)
    table -= (
        u.FACTORIZE_BASE["numeric"] * n + u.UNIQUE_BYTES["numeric"] * distinct
    )  # table term only
    return max(table + 16 * distinct, 65 * distinct)


def build(tmp: Path) -> dict[str, tuple[str, str, float]]:
    """name -> (pickle path, statement, derived peak bytes)."""
    rng = np.random.default_rng(11)
    cases: dict[str, tuple[str, str, float]] = {}

    def save(name: str, obj: object) -> str:
        p = tmp / f"{name}.pkl"
        if not p.exists():
            pd.to_pickle(obj, p)
        return str(p)

    n = 16_000_000
    f = save(
        "si_frame",
        pd.DataFrame(
            {"k": rng.integers(0, 10**9, n), **{f"f{i}": rng.random(n) for i in range(4)}}
        ),
    )
    cases["set_index int key 16M"] = (f, "r = x.set_index('k')", 8.0 * n)
    cases["set_index float key 16M"] = (f, "r = x.set_index('f0')", 8.0 * n)
    vocab = np.array([f"id{x:010d}" for x in range(200_000)], dtype=object)
    ft = save("si_text", pd.DataFrame({"s": pd.array(vocab[rng.integers(0, len(vocab), 8_000_000)], dtype="str"),
                                       **{f"f{i}": rng.random(8_000_000) for i in range(4)}}))  # fmt: skip
    cases["set_index str key 8M"] = (ft, "r = x.set_index('s')", 8.0 * 8_000_000)
    n, d = 20_000_000, 8_000_000
    v1 = save("vc_high", pd.Series(rng.integers(0, d, n)))
    real_d = int(pd.read_pickle(v1).nunique())
    cases["value_counts 20M u~8M"] = (v1, "r = x.value_counts()", vc_derived(n, real_d))
    v2 = save("vc_low", pd.Series(rng.integers(0, 1000, 40_000_000)))
    cases["value_counts 40M u=1000"] = (v2, "r = x.value_counts()", vc_derived(40_000_000, 1000))
    n = 3_000_000
    lens = rng.poisson(6, n)
    small = list(range(256))
    lists = [small[: int(k)] for k in lens]
    e = int(lens.sum()) + int((lens == 0).sum())  # an empty list becomes one NaN row
    sx = save("ex_series", pd.Series(lists, dtype=object))
    cases["Series.explode 3M x6"] = (sx, "r = x.explode()", 8.0 * n + 16.0 * e)
    fx = save("ex_frame", pd.DataFrame({"l": pd.Series(lists, dtype=object), "v": rng.random(n)}))
    cases["DataFrame.explode 3M x6 +1 col"] = (fx, "r = x.explode('l')", 8.0 * n + 48.0 * e)
    n = 25_000_000
    fs = save("ap_series", pd.Series(rng.random(n)))
    cases["apply ufunc np.sqrt 25M"] = (fs, "r = x.apply(np.sqrt)", 8.0 * n)
    n = 6_000_000
    fs2 = save("ap_series6", pd.Series(rng.random(n)))
    cases["apply lambda elementwise 6M"] = (fs2, "r = x.apply(lambda v: v * 2)", 48.0 * n)
    n = 1_500_000
    fr = save(
        "ap_frame", pd.DataFrame({"a": rng.random(n), "b": rng.random(n), "c": rng.random(n)})
    )
    cases["apply axis=1 rowwise 1.5M"] = (
        fr,
        "r = x.apply(lambda r: r['a'] + r['b'], axis=1)",
        136.0 * n,
    )
    n = 25_000_000
    vocab = np.array([f"w{x:07d}" for x in range(5000)], dtype=object)
    vals = vocab[rng.integers(0, len(vocab), n)]
    vals[rng.random(n) < 0.05] = None
    st = save("fill_text", pd.Series(pd.array(vals, dtype="str")))
    cases["str fillna('z') 25M"] = (st, "r = x.fillna('z')", 9.0 * n)
    cases["str fillna(0) 25M (coerce)"] = (st, "r = x.fillna(0)", 17.0 * n)
    return cases


def setup(path: str, stmt: str) -> dict:
    ns = {"pd": pd, "np": np, "x": pd.read_pickle(path), "__stmt__": stmt}
    gc.collect()
    return ns


def run(ns: dict) -> int:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        exec(ns["__stmt__"], ns)  # noqa: S102  (fixed probe statements)
    return 0


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "power": power_state()}))
    cases = build(tmp)
    gc.collect()
    for name, (path, stmt, want) in cases.items():
        m = measure_call(run, setup=setup, setup_args=(path, stmt), repeats=3, run_timeout_s=900)
        got = m.delta_bytes
        print(json.dumps({"case": name, "stmt": stmt, "measured_mib": None if got is None else got / MIB,
                          "derived_mib": want / MIB, "ratio": None if got is None else got / want,
                          "censored": m.censored, "bound_mib": m.bound_bytes / MIB, "spread": m.ram_spread,
                          "time_s": m.time_s, "status": m.status, "power": power_state(),
                          "input_mib": Path(path).stat().st_size / MIB}), flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
