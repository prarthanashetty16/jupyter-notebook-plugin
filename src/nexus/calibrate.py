"""Per-machine throughput calibration: dedicated microbenchmarks, never benchmark data.

Every microbenchmark builds its own synthetic input, runs one primitive a few times and takes the
median. Nothing here touches the benchmark suite's datasets or grid points, and nothing is fitted
to benchmark results. Version 2 makes the primitives more representative of real operations:
working sets are far larger than CPU caches (64-256 MB), each repetition allocates its output
fresh so first-touch page faults are included (cold), and the page-fault cost is also measured
separately (``first_touch_bps``, ``page_fault_s_per_byte``; informational, no model uses it yet).

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
CALIBRATION_VERSION = 2


def _median_time(run: Callable[[Any], Any], prepare: Callable[[], Any] | None = None) -> float:
    """Median seconds of ``run`` over REPEATS timed calls (one untimed warm-up first).

    ``prepare`` builds a fresh argument for every call (untimed); ``run`` allocates its output
    anew each time, so allocation and first-touch costs are part of what is timed.
    """
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


def _scaled(n: int, s: float, floor: int = 10_000) -> int:
    return max(floor, int(n * s))


def measure_profile(quick: bool = False) -> MachineProfile:  # noqa: C901
    """Run every microbenchmark and return the resulting (calibrated) profile."""
    s = 0.05 if quick else 1.0
    rng = np.random.default_rng(12345)
    out: dict[str, float] = {}

    n = _scaled(16_000_000, s)  # 128 MB working set: cold copy, warm copy, first touch
    src = rng.random(n)
    out["copy_bps"] = src.nbytes / _median_time(lambda a: a.copy(), lambda: src)  # fresh output
    dst = np.empty(n)
    dst[:] = 0.0
    out["warm_copy_bps"] = src.nbytes / _median_time(lambda _: np.copyto(dst, src))

    def cold_write(_: Any) -> None:
        fresh = np.empty(n)
        fresh[:] = 1.0

    def warm_write(_: Any) -> None:
        dst[:] = 1.0

    t_cold, t_warm = _median_time(cold_write), _median_time(warm_write)
    out["first_touch_bps"] = src.nbytes / t_cold
    out["page_fault_s_per_byte"] = max(0.0, (t_cold - t_warm) / src.nbytes)
    src = dst = None  # release the 128 MB working set

    n = _scaled(8_000_000, s)  # numeric factorize, 64 MB, 1M distinct values
    ints = rng.integers(0, 1_000_000, n)
    out["num_hash_s"] = _median_time(lambda _: pd.factorize(ints)) / n

    n_text = _scaled(1_000_000, s)  # text factorize, ~300k distinct python strings
    words = np.array([f"s{i:08d}" for i in rng.integers(0, 300_000, n_text)], dtype=object)
    out["text_hash_s"] = _median_time(lambda _: pd.factorize(words)) / n_text

    n = _scaled(16_000_000, s)  # np.sort on 128 MB (copy made untimed, in-place sort timed)
    floats = rng.random(n)
    out["np_sort_s"] = _median_time(np.sort, floats.copy) / _nlogn(n)
    n = _scaled(8_000_000, s)
    out["num_argsort_s"] = _median_time(np.argsort, rng.random(n).copy) / _nlogn(n)
    n_text = _scaled(1_000_000, s)
    text = np.array([f"s{i:08d}" for i in rng.permutation(n_text)], dtype=object)
    out["text_argsort_s"] = _median_time(np.argsort, text.copy) / _nlogn(n_text)
    del floats, text

    rows = _scaled(1_500_000, s, 20_000)  # CSV parse rate: generic 8-column mixed file, ~100 MB
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
    del frame

    d = max(200, int(2000 * (s**0.5)))  # BLAS float64 matmul (result 32 MB at d=2000)
    a, b = rng.random((d, d)), rng.random((d, d))
    out["blas_flops"] = 2 * d**3 / _median_time(lambda _: a @ b)

    n = _scaled(16_000_000, s)  # numeric cast, 128 MB in, 64 MB out
    big_ints = rng.integers(0, 10**6, n)
    out["cast_s"] = _median_time(lambda _: big_ints.astype("float32")) / n

    n_str = _scaled(1_000_000, s)  # int -> str
    series = pd.Series(rng.integers(0, 10**6, n_str))
    out["to_str_s"] = _median_time(lambda _: series.astype(str)) / n_str

    n = _scaled(8_000_000, s)  # groupby sum beyond factorization
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
        "calibration_version": CALIBRATION_VERSION,
    }
    return MachineProfile(**out, calibrated=True, meta=meta)


def _fingerprint(meta: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("platform", "cpu_count", "numpy", "pandas", "calibration_version")
    return tuple(meta.get(k) for k in keys)


def ensure_profile(*, quick: bool = False, force: bool = False) -> MachineProfile:
    """Cached profile if it matches this machine/library stack/calibration version, else measure."""
    current = load_profile()
    if current is not None and current.calibrated and not force:
        probe = {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "calibration_version": CALIBRATION_VERSION,
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
        if name != "meta":
            print(
                f"  {name:22s} {value:.4g}" if isinstance(value, float) else f"  {name:22s} {value}"
            )


if __name__ == "__main__":
    main()
