"""Phase 7b, decision (2): SECOND-ATTEMPT derivations for set_index and value_counts.

Labelled as second attempts: the first derivations were contradicted in Phase 7a (probe 1d: set_index
0.003, value_counts 1.40 / 2.14; ``docs/benchmarks/phase7a/probes/p1d_coverage.out``). This file, with
the derivations, the FRESH grid (no variant of 1d is repeated) and the bar below, is committed BEFORE it
runs. An operation is adopted only if EVERY variant of its grid passes.

**Bar (fixed before the run):** measured / derived within [0.85, 1.15], or both the derived peak and
the measured peak (or the censoring bound) below the instrument's 32 MiB floor.

SECOND DERIVATIONS (pandas 3.1.1 source, written down before measuring):

* ``df.set_index(col)`` (drop=True or False): ``self.copy(deep=False)`` shares every block;
  ``ensure_index_from_sequences`` builds the Index from the column's own array WITHOUT a copy (the
  measured 0.4 MiB of 1d says the first derivation's "Index copies an ndarray" was wrong);
  ``del frame[col]`` splits the column out of its block as views. -> **peak = 0** (metadata only)
  for numeric keys; for a pandas-3 ``str`` key the Index wraps the same StringArray -> 0 as well.
* ``s.value_counts()`` (numeric): ``htable.value_count`` presizes its hash table for **n entries** (not
  capped at 2**20 + 7 as the factorize tables are; the first derivation assumed the cap). The flag
  array is written in full (resident: 0.25 B/bucket); the key and value arrays (8 B/bucket each) are
  resident only on pages a key lands on (``_util.table_touch``, random keys); then keys + counts
  (16 u). Phase 2 (table freed) as in the first attempt: 65 u (keys, counts, Index copy, nargsort).
  -> **peak = max(0.25 B + 2 x touch(u, B, 8) x 8 B + 16 u, 65 u)**, B = buckets for n entries.

FRESH GRID: set_index on 12M rows (int key with 3 other dtype groups, float key, int key drop=False);
value_counts: int64 n = 12M with u = 300, 50k, 1M, 6M; float64 n = 12M with u = 3M.

    PYTHONPATH=. python docs/benchmarks/phase7b/probes/p7b_second_attempts.py <scratch> > docs/benchmarks/phase7b/probes/p7b_second_attempts.out
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
FLOOR = 32 * MIB
BAR = (0.85, 1.15)


def vc_derived(n: int, distinct: int) -> float:
    b = u.hash_buckets(n)
    table = 0.25 * b + 2 * u.table_touch(distinct, b, 8) * 8 * b
    return max(table + 16 * distinct, 65 * distinct)


def setup(path: str, stmt: str) -> dict:
    ns = {"pd": pd, "np": np, "x": pd.read_pickle(path), "__stmt__": stmt}
    gc.collect()
    return ns


def run(ns: dict) -> int:
    exec(ns["__stmt__"], ns)  # noqa: S102  (fixed probe statements)
    return 0


def verdict(measured: float | None, bound: float, derived: float) -> bool:
    if derived < FLOOR and (measured if measured is not None else bound) < FLOOR:
        return True
    return measured is not None and BAR[0] <= measured / max(derived, 1.0) <= BAR[1]


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(23)
    n = 12_000_000
    cases: list[tuple[str, str, str, float]] = []

    def save(name: str, obj: object) -> str:
        p = tmp / f"{name}.pkl"
        if not p.exists():
            pd.to_pickle(obj, p)
        return str(p)

    f = save("si", pd.DataFrame({"k": rng.integers(0, 10**9, n), "f0": rng.random(n), "f1": rng.random(n),
                                 "i1": rng.integers(0, 100, n).astype("int32"), "b": rng.random(n) > 0.5}))  # fmt: skip
    cases += [("set_index", "int key, 3 other groups", f, "r = x.set_index('k')"),
              ("set_index", "float key", f, "r = x.set_index('f0')"),
              ("set_index", "int key drop=False", f, "r = x.set_index('k', drop=False)")]  # fmt: skip
    for d in (300, 50_000, 1_000_000, 6_000_000):
        cases.append(("value_counts", f"int64 n=12M u={d}", save(f"vc_{d}", pd.Series(rng.integers(0, d, n))),
                      "r = x.value_counts()"))  # fmt: skip
    cases.append(("value_counts", "float64 n=12M u=3M",
                  save("vc_f", pd.Series(rng.integers(0, 3_000_000, n).astype("float64") / 7.0)), "r = x.value_counts()"))  # fmt: skip
    print(
        json.dumps(
            {"pandas": pd.__version__, "numpy": np.__version__, "power": power_state(), "bar": BAR}
        )
    )
    passed: dict[str, bool] = {}
    for op, label, path, stmt in cases:
        if op == "set_index":
            derived = 0.0
        else:
            s = pd.read_pickle(path)
            derived = vc_derived(len(s), int(s.nunique()))
            del s
            gc.collect()
        m = measure_call(run, setup=setup, setup_args=(path, stmt), repeats=3, run_timeout_s=900)
        ok = verdict(m.delta_bytes, m.bound_bytes, derived)
        passed[op] = passed.get(op, True) and ok
        print(json.dumps({"op": op, "variant": label, "measured_mib": None if m.delta_bytes is None else m.delta_bytes / MIB,
                          "bound_mib": m.bound_bytes / MIB, "censored": m.censored, "derived_mib": derived / MIB,
                          "ratio": None if not m.delta_bytes or not derived else m.delta_bytes / derived,
                          "pass": ok, "time_s": m.time_s, "status": m.status, "power": power_state()}), flush=True)  # fmt: skip
    print(json.dumps({"adopt": passed}))


if __name__ == "__main__":
    main()
