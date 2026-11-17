"""(b) astype('category'): OS peak (instrument) and tracemalloc peak versus n and distinct count U.

tracemalloc sees pandas hash tables (khash uses a traced allocator) and numpy buffers, so it isolates
the Python-visible allocations from OS effects (page rounding, working-set trimming).
"""

import sys, pathlib, tracemalloc

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
import probe_lib as P
from nexus.measure import measure_call
from benchmarks.suite import BASE


def run_traced(state):
    ns, code = state
    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    res = eval(code, ns)
    peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()
    return {"traced": peak, "res": res}


def summarize_traced(out):
    return {"traced_peak": out["traced"]}


def traced(frames, code):
    dirs = {k: frame_dir(c) for k, c in frames.items()}
    m = measure_call(
        run_traced, setup=P.setup, setup_args=(dirs, code), summarize=summarize_traced, repeats=1
    )
    return m.info.get("traced_peak")


def one_col(n, U, kind, seed=11):
    if kind == "text":
        return BASE.with_(
            n_rows=n,
            n_int=0,
            n_float=0,
            n_object=1,
            n_category=0,
            n_datetime=0,
            cardinality=U,
            seed=seed,
            with_key=False,
        )
    return BASE.with_(
        n_rows=n,
        n_int=1,
        n_float=0,
        n_object=0,
        n_category=0,
        n_datetime=0,
        cardinality=U,
        seed=seed,
        with_key=False,
    )


if __name__ == "__main__":
    kind = sys.argv[1]
    col = "s0" if kind == "text" else "i0"
    for U in (12, 12_000):
        for n in (300_000, 600_000, 1_000_000, 1_500_000, 2_000_000, 3_000_000, 4_000_000):
            cfg = one_col(n, U, kind)
            code = f'df["{col}"].astype("category")'
            r = probe({"df": cfg}, code, repeats=2)
            t = traced({"df": cfg}, code)
            print(
                f"{kind} U={U:>6} n={n:>9,}  OS peak={r['ram_MiB']:>7} MiB ({r['B_per_row']:>5} B/row)  tracemalloc={t / MIB:>7.1f} MiB ({t / n:>5.1f} B/row)",
                flush=True,
            )
