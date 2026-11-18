"""Probes: read_csv parse cost by dtype, astype-to-str cost by source dtype, matmul by dtype and threads.

HYPOTHESES.
* read_csv: the frozen model divides the file size by ONE parse rate measured on a mixed file. If
  the cost is per FIELD and depends on the parsed type (text fields create Python objects, dates are
  parsed as strings by default, floats need a decimal conversion), files of floats/ints are
  over-predicted and text/date-heavy files under-predicted (observed: wide numeric 3x over, text /
  dates 0.3x under).
* astype(str): the frozen model uses the int->str rate for every source. float->str (repr of a
  double) and datetime->str (formatting) are slower; int->str with few distinct values faster.
* matmul: the frozen model uses the float64 BLAS rate for every dtype. float32 (sgemm) does about
  twice the flops per cycle (SIMD width), and small / thin products use fewer threads.

Synthetic data only, median of 3 timed calls in-process.

    python docs/benchmarks/phase6/probes/p_csv_astype_matmul.py
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time

import numpy as np
import pandas as pd


def t(fn, reps: int = 3) -> float:
    out = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return statistics.median(out)


def csv_probe(rng: np.random.Generator, tmp: str) -> None:
    n = 500_000
    kinds = {
        "int": lambda: rng.integers(0, 10**6, n),
        "float": lambda: rng.random(n) * 1000,
        "text12": lambda: np.array([f"w{x:011d}" for x in rng.integers(0, n // 10, n)], dtype=object),
        "text_distinct24": lambda: np.array([f"x{x:023d}" for x in rng.integers(0, 10**18, n)], dtype=object),
        "date": lambda: (1_500_000_000 + rng.integers(0, 10**8, n)).astype("datetime64[s]"),
    }
    print("read_csv, 4 columns of one type, 500k rows (C engine, default dtypes)")
    for name, make in kinds.items():
        df = pd.DataFrame({f"c{i}": make() for i in range(4)})
        path = os.path.join(tmp, f"{name}.csv")
        df.to_csv(path, index=False)
        size = os.path.getsize(path)
        sec = t(lambda p=path: pd.read_csv(p))
        print(
            f"  {name:16} {size / 2**20:7.1f} MiB  {sec:.3f} s  {sec / (n * 4) * 1e9:6.1f} ns/field  "
            f"{size / sec / 1e6:7.1f} MB/s  {size / (n * 4):5.1f} B/field"
        )


def astype_probe(rng: np.random.Generator) -> None:
    n = 1_000_000
    print("astype(str), 1M values: ns per element")
    srcs = {
        "int (1M distinct)": pd.Series(rng.integers(0, 10**9, n)),
        "int (1500 distinct)": pd.Series(rng.integers(0, 1500, n)),
        "float": pd.Series(rng.random(n) * 1000),
        "datetime": pd.Series((1_500_000_000 + rng.integers(0, 10**8, n)).astype("datetime64[s]")),
    }
    for name, s in srcs.items():
        print(f"  {name:20} {t(lambda s=s: s.astype(str)) / n * 1e9:7.1f}")


def gflops(d: tuple[int, int, int], dtype: str, rng: np.random.Generator) -> float:
    m, k, p = d
    a = rng.random((m, k)).astype(dtype)
    b = rng.random((k, p)).astype(dtype)
    return 2 * m * k * p / t(lambda: a @ b) / 1e9


def matmul_probe(rng: np.random.Generator) -> None:
    print("matmul GFLOP/s (m, k, p): float64 / float32 / ratio")
    for d in ((2000, 2000, 2000), (4000, 4000, 4000), (6000, 6000, 6000), (6000, 6000, 600)):
        g64, g32 = gflops(d, "float64", rng), gflops(d, "float32", rng)
        print(f"  {d}: {g64:7.1f} / {g32:7.1f} / {g32 / g64:.2f}")
    code = (
        "import numpy as np,time;a=np.random.rand(2000,2000);b=np.random.rand(2000,2000);a@b;"
        "t=time.perf_counter();a@b;print(2*2000**3/(time.perf_counter()-t)/1e9)"
    )
    env = {**os.environ, **{v: "1" for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}
    single = float(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout)
    print(f"  float64 2000^3 single thread: {single:.1f} GFLOP/s; logical CPUs {os.cpu_count()}")


def main() -> None:
    rng = np.random.default_rng(5)
    print(f"pandas {pd.__version__}, numpy {np.__version__}")
    with tempfile.TemporaryDirectory() as tmp:
        csv_probe(rng, tmp)
    astype_probe(rng)
    matmul_probe(rng)


if __name__ == "__main__":
    main()
