"""Phase 7b: isolated probes of the implemented v3 changes (mains power, OS peak or tracemalloc, >= 200 MiB).

Each section compares the v3 prediction (made in a fresh process with the same settings) with the
measurement, against the pre-registered bar (``docs/benchmarks/phase7-preregistration.md``: every variant
within +-15% of the derived expected; the serial read_csv path is a range and must contain the measurement).

A. read_csv at 1 / 2 / default workers (``mode.max_threads``) and with the process pinned to 1 CPU
   (pandas reads affinity only on Linux: on Windows the default stays min(cpu_count, 6)); usecols,
   nrows, dtype dict / scalar.
B. merge OUTPUT term (what the result leaves behind, tracemalloc): every left row matched once in order
   (left elided), 20% of left keys unmatched, how='left', duplicated right keys, sort=True, outer.
C. copy: a consolidated frame with two pandas-3 ``str`` columns (pandas' own consolidation check ignores
   extension blocks), a fragmented numeric frame, a fragmented frame with ``str`` columns.
D. the v1 multicell ``rebinding`` cell (rebinding release), 4M rows.
E. Series.explode: mean list length 2 (8M rows), 12 (2M rows), 30% empty lists, string elements.
F. Series.apply(ufunc): np.log on float32 (30M), np.exp on int64 (16M).

    PYTHONPATH=. python docs/benchmarks/phase7b/probes/p7b_changes.py <scratch> > docs/benchmarks/phase7b/probes/p7b_changes.out
"""

from __future__ import annotations

import gc
import json
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

from benchmarks.childproc import run_child
from benchmarks.multicell.cases import KEYS, TEMPLATES, make_frame
from nexus.measure import measure_call
from nexus.power import power_state

MIB = 2**20
BAR = (0.85, 1.15)


def _settings(threads: int | None, pin: bool) -> None:
    if threads is not None:
        pd.set_option("mode.max_threads", threads)
    if pin:
        psutil.Process().cpu_affinity([0])


# -- generic child functions -------------------------------------------------------------------------
def setup_ns(
    paths: dict[str, str], stmt: str, threads: int | None = None, pin: bool = False
) -> dict:
    _settings(threads, pin)
    ns = {"pd": pd, "np": np, "__stmt__": stmt}
    for k, p in paths.items():
        ns[k] = pd.read_pickle(p) if p.endswith(".pkl") else p
    gc.collect()
    return ns


def run_stmt(ns: dict) -> int:
    exec(ns["__stmt__"], ns)  # noqa: S102  (fixed probe statements)
    return 0


def predict(paths: dict[str, str], src: str, threads: int | None, pin: bool) -> dict:
    from nexus.cellpeak import cell_estimate
    from nexus.models._output import output_range
    from nexus.pipeline import Pipeline

    ns = setup_ns(paths, src, threads, pin)
    rep = Pipeline(tier=1).run(src, ns)
    cell, _, _ = cell_estimate(src, rep.estimates) if rep.estimates else (None, None, None)
    ops = []
    for e in rep.estimates:
        out = output_range(e.model, e.features or {}, e.estimate)
        ops.append({"model": e.model, "tier": e.estimate.tier, "reason": (e.features.get("tier1") or {}).get("reason"),
                    "path": e.features.get("reader_path"), "workers": e.features.get("workers"),
                    "peak": [e.estimate.ram_low, e.estimate.ram_expected, e.estimate.ram_high],
                    "out": list(out) if out else None})  # fmt: skip
    return {
        "cell": None if cell is None else [cell.ram_low, cell.ram_expected, cell.ram_high],
        "ops": ops,
    }


def retained(paths: dict[str, str], stmt: str) -> int:
    ns = setup_ns(paths, stmt)
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    exec(stmt, ns)  # noqa: S102
    gc.collect()
    return tracemalloc.get_traced_memory()[0] - before


def score(measured: float | None, pred: list[float], serial: bool = False) -> dict:
    lo, exp, hi = pred
    if measured is None:
        return {"ratio": None, "in_range": None, "pass": False}
    ratio = measured / max(exp, 1.0)
    inr = lo <= measured <= hi
    return {"ratio": ratio, "in_range": inr, "pass": inr if serial else BAR[0] <= ratio <= BAR[1]}


def emit(section: str, label: str, **kw: object) -> None:
    print(
        json.dumps(
            {"section": section, "variant": label, "power": power_state(), **kw}, default=float
        ),
        flush=True,
    )


def save(tmp: Path, name: str, obj: object) -> str:
    p = tmp / f"{name}.pkl"
    if not p.exists():
        pd.to_pickle(obj, p)
    return str(p)


# -- sections ------------------------------------------------------------------------------------------
def section_a(tmp: Path) -> None:
    rng = np.random.default_rng(31)
    f8, f16 = tmp / "a_f8.csv", tmp / "a_f16.csv"
    if not f8.exists():
        pd.DataFrame({f"F{i}": rng.random(2_000_000) for i in range(8)}).to_csv(f8, index=False)
    if not f16.exists():
        pd.DataFrame({f"F{i}": rng.random(2_000_000) for i in range(16)}).to_csv(f16, index=False)
    cols = [f"F{i}" for i in range(16)]
    variants = [
        ("default workers", f8, {}, None, False), ("max_threads=2", f8, {}, 2, False),
        ("max_threads=1 (serial)", f8, {}, 1, False), ("affinity 1 CPU", f8, {}, None, True),
        ("usecols 4 of 16", f16, {"usecols": cols[:4]}, None, False), ("nrows 700k of 2M", f16, {"nrows": 700_000}, None, False),
        ("dtype dict float32 x8", f16, {"dtype": dict.fromkeys(cols[:8], "float32")}, None, False),
        ("dtype float32 scalar", f16, {"dtype": "float32"}, None, False),
        ("usecols 4, max_threads=1", f16, {"usecols": cols[:4]}, 1, False),
    ]  # fmt: skip
    for label, path, kw, threads, pin in variants:
        src = f"a = pd.read_csv({str(path)!r}, {', '.join(f'{k}={v!r}' for k, v in kw.items())})"
        pred = run_child(predict, {}, src, threads, pin)["ops"][0]
        m = measure_call(run_stmt, setup=setup_ns, setup_args=({}, src, threads, pin), repeats=3)
        emit("A", label, src=src[-60:], measured_mib=(m.delta_bytes or 0) / MIB, pred_mib=[x / MIB for x in pred["peak"]],
             path=pred["path"], workers=pred["workers"], tier=pred["tier"], spread=m.ram_spread,
             **score(m.delta_bytes, pred["peak"], serial=pred["path"] == "serial"))  # fmt: skip


def section_b(tmp: Path) -> None:
    rng = np.random.default_rng(32)
    n = 4_000_000
    left = pd.DataFrame({"k": rng.integers(0, KEYS, n), **{f"f{i}": rng.random(n) for i in range(4)},
                         "i0": rng.integers(0, 10**6, n)})  # fmt: skip
    right = pd.DataFrame({"k": np.arange(KEYS), "w": rng.random(KEYS), "w2": rng.random(KEYS)})
    part = right[right["k"] % 5 != 0]  # 20% of the left keys find no match
    dup = pd.concat([right, right], ignore_index=True)
    paths = {"left": save(tmp, "b_left", left), "right": save(tmp, "b_right", right),
             "part": save(tmp, "b_part", part), "dup": save(tmp, "b_dup", dup)}  # fmt: skip
    del left
    gc.collect()
    for label, stmt in [("all matched once (elided)", "m = left.merge(right, on='k')"),
                        ("20% unmatched", "m = left.merge(part, on='k')"),
                        ("how=left, partial", "m = left.merge(part, on='k', how='left')"),
                        ("duplicated right keys", "m = left.merge(dup, on='k')"),
                        ("sort=True", "m = left.merge(right, on='k', sort=True)"),
                        ("outer, partial", "m = left.merge(part, on='k', how='outer')")]:  # fmt: skip
        pred = run_child(predict, paths, stmt, None, False)["ops"][0]
        got = run_child(retained, paths, stmt)
        emit("B", label, retained_mib=got / MIB, out_pred_mib=[x / MIB for x in pred["out"]],
             **score(got, pred["out"]))  # fmt: skip


def _fragmented(n: int, rng: np.random.Generator, text: bool) -> pd.DataFrame:
    df = pd.DataFrame({"k": rng.integers(0, 10**6, n)})
    for i in range(5):  # column insertion: one block per column
        df[f"f{i}"] = rng.random(n)
    if text:
        vocab = np.array([f"w{x:07d}" for x in range(2000)], dtype=object)
        for i in range(2):
            df[f"s{i}"] = pd.array(vocab[rng.integers(0, len(vocab), n)], dtype="str")
    return df


def section_c(tmp: Path) -> None:
    rng = np.random.default_rng(33)
    n = 4_000_000
    paths = {"mixed": save(tmp, "c_mixed", make_frame("mixed", n, 5)),
             "frag": save(tmp, "c_frag", _fragmented(n, rng, False)),
             "fragtext": save(tmp, "c_fragtext", _fragmented(n, rng, True))}  # fmt: skip
    for label, name in [("consolidated + 2 str columns", "mixed"), ("fragmented numeric", "frag"),
                        ("fragmented + 2 str columns", "fragtext")]:  # fmt: skip
        stmt = f"x = {name}.copy()"
        pred = run_child(predict, {name: paths[name]}, stmt, None, False)["ops"][0]
        m = measure_call(
            run_stmt, setup=setup_ns, setup_args=({name: paths[name]}, stmt), repeats=3
        )
        emit("C", label, measured_mib=(m.delta_bytes or 0) / MIB, pred_mib=[x / MIB for x in pred["peak"]],
             **score(m.delta_bytes, pred["peak"]))  # fmt: skip


def section_d(tmp: Path) -> None:
    n = 4_000_000
    paths = {"df": save(tmp, "d_df", make_frame("mixed", n, 1)), "df2": save(tmp, "d_df2", make_frame("mixed", n, 2)),
             "right": save(tmp, "d_right", pd.DataFrame({"k": np.arange(KEYS), "w": np.random.default_rng(3).random(KEYS)}))}  # fmt: skip
    src = TEMPLATES["rebinding"]
    pred = run_child(predict, paths, src, None, False)
    m = measure_call(run_stmt, setup=setup_ns, setup_args=(paths, src), repeats=3)
    emit("D", "rebinding/mixed@4M (cell)", measured_mib=(m.delta_bytes or 0) / MIB,
         pred_mib=[x / MIB for x in pred["cell"]], **score(m.delta_bytes, pred["cell"]))  # fmt: skip


def section_e(tmp: Path) -> None:
    rng = np.random.default_rng(34)
    small = list(range(256))
    words = [f"t{i:05d}" for i in range(5000)]

    def lists(n: int, mean: float, empty: float = 0.0, text: bool = False) -> pd.Series:
        lens = rng.poisson(mean, n)
        lens[rng.random(n) < empty] = 0
        src = words if text else small
        return pd.Series([src[: int(k)] if not text else [src[j] for j in rng.integers(0, 5000, int(k))]
                          for k in lens], dtype=object)  # fmt: skip

    for label, name, maker in [("mean 2, 8M rows", "e2", lambda: lists(8_000_000, 2)),
                               ("mean 12, 2M rows", "e12", lambda: lists(2_000_000, 12)),
                               ("30% empty, mean 6, 3M", "eempty", lambda: lists(3_000_000, 6, 0.3)),
                               ("string elements, mean 5, 2M", "etext", lambda: lists(2_000_000, 5, text=True))]:  # fmt: skip
        path = save(tmp, name, maker())
        gc.collect()
        stmt = "e = s.explode()"
        pred = run_child(predict, {"s": path}, stmt, None, False)["ops"]
        m = measure_call(run_stmt, setup=setup_ns, setup_args=({"s": path}, stmt), repeats=3)
        p = pred[0]["peak"] if pred else [0, 0, 0]
        emit("E", label, measured_mib=(m.delta_bytes or 0) / MIB, pred_mib=[x / MIB for x in p],
             tier=pred[0]["tier"] if pred else None, **score(m.delta_bytes, p))  # fmt: skip


def section_f(tmp: Path) -> None:
    rng = np.random.default_rng(35)
    for label, name, obj, stmt in [
        ("np.log on float32, 30M", "f32", pd.Series(rng.random(30_000_000).astype("float32") + 1), "a = s.apply(np.log)"),
        ("np.exp on int64, 16M", "i64", pd.Series(rng.integers(0, 5, 16_000_000)), "a = s.apply(np.exp)"),
    ]:  # fmt: skip
        path = save(tmp, name, obj)
        pred = run_child(predict, {"s": path}, stmt, None, False)["ops"][0]
        m = measure_call(run_stmt, setup=setup_ns, setup_args=({"s": path}, stmt), repeats=3)
        emit("F", label, measured_mib=(m.delta_bytes or 0) / MIB, pred_mib=[x / MIB for x in pred["peak"]],
             **score(m.delta_bytes, pred["peak"]))  # fmt: skip


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else set("ABCDEF")
    print(
        json.dumps(
            {"pandas": pd.__version__, "numpy": np.__version__, "power": power_state(), "bar": BAR}
        )
    )
    for key, fn in (("A", section_a), ("B", section_b), ("C", section_c), ("D", section_d), ("E", section_e),
                    ("F", section_f)):  # fmt: skip
        if key in only:
            if power_state() == "battery":
                raise SystemExit("on battery power: plug in first")
            fn(tmp)


if __name__ == "__main__":
    main()
