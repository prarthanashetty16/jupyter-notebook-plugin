"""Tier 2 sample pitfalls (dev evidence): key layout, presize cap, fixed costs, cold-start.

1. KEY LAYOUT. ``df["s"].astype("category")`` on 3M rows with 12,000 distinct strings, random vs
   sequential (``id_0000000123``) keys: the real peak differs by ~38 MiB (4b.2: random keys touch
   the whole presized hash table, sequential keys a few pages). The dry run samples rows (astype is
   row-wise), so every sample table is small and fully resident; what does the extrapolation say?
2. PRESIZE CAP. The same call at several sample sizes: B/row falls as the table saturates at 2^20
   entries, which no linear / n log n / quadratic law can represent.
3. FIXED COSTS / COLD START. The first call in a fresh child vs the median of later calls, on a tiny
   sample (first-touch, allocator and import effects the intercept has to absorb).

Run from the repo root while nothing else is running: python docs/benchmarks/tier2-dev/probes/p_sample_pitfalls.py
"""

import pathlib
import string
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nexus import dryrun  # noqa: E402

MIB = 2**20


def column(kind, n, u, rng):
    if kind == "sequential":
        vocab = np.array([f"id_{i:010d}" for i in range(u)], dtype=object)
    else:
        chars = np.array(list(string.ascii_lowercase))
        vocab = np.array(
            ["".join(r) for r in chars[rng.integers(0, 26, size=(u, 14))]], dtype=object
        )
    codes = rng.permutation(np.concatenate([np.arange(u), rng.integers(0, u, n - u)]))
    return pd.DataFrame({"s": pd.Series(vocab[codes], dtype=object)})


def real_peak(df, tmp):
    """The real peak through the project instrument (spawned child, inputs from disk)."""
    from nexus.dryrun_io import save_frame

    save_frame(df, pathlib.Path(tmp) / "real" / "df")
    spec = {"dir": str(pathlib.Path(tmp) / "real"), "objects": ["df"], "csv": False, "result": str(pathlib.Path(tmp) / "r.json"),
            "recipe": {"kind": "astype", "operands": ["df"], "kwargs": {}, "extra": {"column": "s", "target": "category"}}}  # fmt: skip
    return dryrun.run_child(spec, pathlib.Path(tmp) / "s.json", 300, 6 * 2**30)


if __name__ == "__main__":
    rng = np.random.default_rng(3)
    n, u = 3_000_000, 12_000
    print(f"== 1/2: astype category, n={n:,}, U={u:,}")
    for kind in ("random", "sequential"):
        df = column(kind, n, u, rng)
        with tempfile.TemporaryDirectory() as tmp:
            res = dryrun.run_dryrun('df["s"].astype("category")', {"df": df, "pd": pd, "np": np})
            real = real_peak(df, tmp)
        print(
            f"-- {kind} keys: real peak {real['delta_bytes'] / MIB:.1f} MiB, real time {real['time_s']:.3f} s"
        )
        for lv in res.levels:
            print(
                f"   sample {lv['n_eff']:>9,.0f} rows: {lv['delta_bytes'] / MIB:6.2f} MiB ({lv['delta_bytes'] / lv['n_eff']:5.1f} B/row)  {lv['time_s'] * 1e3:6.1f} ms"
            )
        q = res.ram
        print(
            f"   RAM fit ok={q.ok} {q.reason or ''} best={q.best} expected={q.expected / MIB if q.ok else float('nan'):.1f} MiB "
            f"range=[{q.low / MIB if q.ok else float('nan'):.1f}, {q.high / MIB if q.ok else float('nan'):.1f}] -> expected/real = "
            f"{q.expected / real['delta_bytes'] if q.ok else float('nan'):.2f}"
        )
    print("== 3: first call vs later calls in one fresh interpreter (tiny sample)")
    import subprocess

    code = (
        "import time,numpy as np,pandas as pd;a=np.random.default_rng(0).random(50_000);df=pd.DataFrame({'f':a});"
        "t=[];[t.append((lambda t0:(df.sort_values('f'),time.perf_counter()-t0)[1])(time.perf_counter())) for _ in range(6)];"
        "print(' '.join(f'{x*1e3:.2f}' for x in t))"
    )
    for _ in range(3):
        print(
            "   sort_values 50k rows, ms per call:",
            subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True
            ).stdout.strip(),
        )
