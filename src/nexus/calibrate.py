"""Per-machine throughput calibration: dedicated microbenchmarks, never benchmark data.

Each microbenchmark builds its own small synthetic input, runs the operation a few times, and
takes the median. Nothing here touches the benchmark suite's datasets or grid points.
CLI: ``nexus-calibrate-machine [--quick] [--force] [--show]``.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from nexus.machine import MachineProfile, load_profile, profile_path, save_profile

REPEATS = 5


def _median_time(run: Callable[[Any], Any], prepare: Callable[[], Any] | None = None) -> float:
    """Median seconds of ``run`` over REPEATS timed calls (one untimed warm-up first)."""
    times = []
    for i in range(REPEATS + 1):
        arg = prepare() if prepare else None
        t0 = time.perf_counter()
        run(arg)
        dt = time.perf_counter() - t0
        if i > 0:
            times.append(dt)
    return statistics.median(times)


def _nlogn(n: int) -> float:
    return n * math.log2(n)


def measure_profile(quick: bool = False) -> MachineProfile:
    """Run every microbenchmark and return the resulting (calibrated) profile."""
    s = 0.1 if quick else 1.0
    rng = np.random.default_rng(12345)
    out: dict[str, float] = {}

    n = int(8_000_000 * s)  # memcpy
    src, dst = rng.random(n), np.empty(n)
    out["copy_bps"] = src.nbytes / _median_time(lambda _: np.copyto(dst, src))

    n = int(2_000_000 * s)  # numeric factorize
    ints = rng.integers(0, 200_000, n)
    t_fact = _median_time(lambda _: pd.factorize(ints))
    out["num_hash_s"] = t_fact / n

    n_text = int(300_000 * s)  # text factorize
    words = np.array([f"s{i:08d}" for i in rng.integers(0, 100_000, n_text)], dtype=object)
    out["text_hash_s"] = _median_time(lambda _: pd.factorize(words)) / n_text

    n = int(2_000_000 * s)  # numeric sorts
    floats = rng.random(n)
    out["np_sort_s"] = _median_time(np.sort, floats.copy) / _nlogn(n)
    out["num_argsort_s"] = _median_time(np.argsort, floats.copy) / _nlogn(n)
    n_text = int(200_000 * s)
    text = np.array([f"s{i:08d}" for i in rng.permutation(n_text)], dtype=object)
    out["text_argsort_s"] = _median_time(np.argsort, text.copy) / _nlogn(n_text)

    rows = int(300_000 * s)  # CSV parse rate (generic 8-column mixed file)
    frame = pd.DataFrame(
        {
            **{f"f{i}": rng.random(rows) for i in range(4)},
            **{f"i{i}": rng.integers(0, 1000, rows) for i in range(2)},
            **{f"s{i}": [f"v{x}" for x in rng.integers(0, 5000, rows)] for i in range(2)},
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "calibrate.csv")
        frame.to_csv(path, index=False)
        size = os.path.getsize(path)
        out["csv_parse_bps"] = size / _median_time(lambda _: pd.read_csv(path))

    d = int(1000 * (s**0.5 if quick else 1.0))  # BLAS float64 matmul
    a, b = rng.random((d, d)), rng.random((d, d))
    out["blas_flops"] = 2 * d**3 / _median_time(lambda _: a @ b)

    n = int(4_000_000 * s)  # numeric cast
    big_ints = rng.integers(0, 10**6, n)
    out["cast_s"] = _median_time(lambda _: big_ints.astype("float32")) / n

    n_str = int(300_000 * s)  # int -> str
    series = pd.Series(rng.integers(0, 10**6, n_str))
    out["to_str_s"] = _median_time(lambda _: series.astype(str)) / n_str

    n = int(2_000_000 * s)  # groupby sum beyond factorization
    keys = rng.integers(0, 1000, n)
    gdf = pd.DataFrame({"k": keys, "v": rng.random(n)})
    t_group = _median_time(lambda _: gdf.groupby("k")["v"].sum())
    t_key = _median_time(lambda _: pd.factorize(keys))
    out["agg_s"] = max(1e-10, (t_group - t_key) / n)

    meta = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "quick": quick,
    }
    return MachineProfile(**out, calibrated=True, meta=meta)


def _fingerprint(meta: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(meta.get(k) for k in ("platform", "cpu_count", "numpy", "pandas"))


def ensure_profile(*, quick: bool = False, force: bool = False) -> MachineProfile:
    """Cached profile if it matches this machine/library stack, else measure and cache it."""
    current = load_profile()
    if current is not None and current.calibrated and not force:
        probe = {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        }
        if _fingerprint(current.meta) == _fingerprint(probe):
            return current
    profile = measure_profile(quick=quick)
    save_profile(profile)
    return profile


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nexus-calibrate-machine", description=__doc__)
    parser.add_argument("--quick", action="store_true", help="smaller inputs, noisier result")
    parser.add_argument("--force", action="store_true", help="re-measure even if cached")
    parser.add_argument("--show", action="store_true", help="print the cached profile and exit")
    args = parser.parse_args(argv)
    if args.show:
        profile = load_profile()
        print(profile if profile else "no calibrated profile at " + str(profile_path()))
        return
    profile = ensure_profile(quick=args.quick, force=args.force)
    print(f"profile ({profile_path()}):")
    for name, value in vars(profile).items():
        if name not in ("meta",):
            print(
                f"  {name:16s} {value:.4g}" if isinstance(value, float) else f"  {name:16s} {value}"
            )


if __name__ == "__main__":
    main()
