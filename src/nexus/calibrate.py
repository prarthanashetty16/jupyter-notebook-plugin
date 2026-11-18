"""Per-machine calibration: dedicated microbenchmarks, never benchmark data (profile format 3).

Every microbenchmark builds its own synthetic input, runs one primitive a few times and takes the
median. Nothing here touches the benchmark suite's datasets or grid points, and nothing is fitted
to benchmark results. Format 3 measures how the cost of each primitive depends on its WORKING
SET (``nexus.machine``): copy / read throughput from cache-resident (256 KiB) to RAM-resident
(256 MiB) buffers, factorize cost per row against the number of distinct keys, the cost of taking
Python objects against the number of distinct objects, sort cost per n*log2(n) against n, BLAS
throughput for float64 and float32 against the product size, plus first-touch / page-fault cost,
CSV field costs by type, astype-to-str by source dtype and single-thread BLAS (thread scaling).

CLI: ``nexus-calibrate-machine [--quick] [--force] [--show]``.
"""

from __future__ import annotations

import argparse
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
import psutil

from nexus.machine import (
    PROFILE_FORMAT,
    MachineProfile,
    load_profile,
    profile_path,
    save_profile,
)

REPEATS = 3
CALIBRATION_VERSION = 3
MIB = 2**20


def power_plugged() -> bool | None:
    """True on mains power, False on battery, None when the machine reports no battery.

    Throughput measured on battery can be throttled (the CPU and memory clocks drop), so a profile
    records the power state and the CLI refuses to measure on battery unless told to.
    """
    try:
        battery = psutil.sensors_battery()
    except Exception:
        return None
    return None if battery is None else bool(battery.power_plugged)


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
    return n * math.log2(max(n, 2))


def _words(rng: np.random.Generator, k: int) -> np.ndarray:
    """``k`` distinct 13-character str objects (the benchmark-independent text unit)."""
    return np.array([f"w{x:012d}" for x in rng.permutation(max(k, 1) * 7)[:k]], dtype=object)


def _copy_curve(sizes: list[int]) -> tuple[list[list[float]], list[list[float]]]:
    copy, read = [], []
    for nbytes in sizes:
        src = np.ones(nbytes // 8)
        reps = max(1, int(64 * MIB // nbytes))  # small buffers: repeat so the timer resolves

        def cold(_: Any, src: np.ndarray = src, reps: int = reps) -> None:
            for _ in range(reps):
                src.copy()

        def stream(_: Any, src: np.ndarray = src, reps: int = reps) -> None:
            for _ in range(reps):
                src.sum()

        copy.append([nbytes, nbytes * reps / _median_time(cold)])
        read.append([nbytes, nbytes * reps / _median_time(stream)])
    return copy, read


def _factorize_curves(
    rng: np.random.Generator, distincts: list[int], n_min: int
) -> tuple[list[list[float]], list[list[float]], list[list[float]]]:
    num, text, take = [], [], []
    for g in distincts:
        n = max(n_min, g)
        codes = rng.integers(0, g, n)
        ints = rng.integers(0, 2**62, g)[codes]
        num.append([g, _median_time(lambda _, a=ints: pd.factorize(a)) / n])
        vocab = _words(rng, g)
        objs = vocab[codes]
        text.append([g, _median_time(lambda _, a=objs: pd.factorize(a)) / n])
        take.append([g, _median_time(lambda _, v=vocab, c=codes: v.take(c)) / n])
    return num, text, take


def _sort_curves(
    rng: np.random.Generator, num_sizes: list[int], text_sizes: list[int]
) -> dict[str, list[list[float]]]:
    out: dict[str, list[list[float]]] = {"num_argsort_s": [], "np_sort_s": [], "text_argsort_s": []}
    for n in num_sizes:
        x = rng.random(n)
        out["num_argsort_s"].append([n, _median_time(np.argsort, x.copy) / _nlogn(n)])
        out["np_sort_s"].append([n, _median_time(lambda _, a=x: np.sort(a)) / _nlogn(n)])
    for n in text_sizes:
        words = _words(rng, n)
        out["text_argsort_s"].append([n, _median_time(np.argsort, words.copy) / _nlogn(n)])
    return out


def _blas_curves(
    rng: np.random.Generator, dims: list[int]
) -> tuple[list[list[float]], list[list[float]]]:
    c64, c32 = [], []
    for d in dims:
        a, b = rng.random((d, d)), rng.random((d, d))
        flops = 2.0 * d**3
        c64.append([d**3, flops / _median_time(lambda _, a=a, b=b: a @ b)])
        a32, b32 = a.astype(np.float32), b.astype(np.float32)
        c32.append([d**3, flops / _median_time(lambda _, a=a32, b=b32: a @ b)])
    return c64, c32


def _single_thread_flops(d: int) -> float:
    """float64 matmul on one BLAS thread, in a fresh interpreter (thread count is fixed at load)."""
    code = (
        "import numpy as np,time,statistics;"
        f"a=np.random.rand({d},{d});b=np.random.rand({d},{d});a@b;ts=[]\n"
        "for _ in range(3):\n t=time.perf_counter();a@b;ts.append(time.perf_counter()-t)\n"
        f"print(2*{d}**3/statistics.median(ts))"
    )
    env = {**os.environ}
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        env[var] = "1"
    try:
        done = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120
        )
        return float(done.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def _csv_field_costs(rng: np.random.Generator, rows: int) -> tuple[float, float]:
    """Seconds per numeric field and per text field of the C parser (4-column files)."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for kind in ("num", "text"):
            if kind == "num":
                cols = {f"c{i}": rng.random(rows) * 1000 for i in range(2)}
                cols.update({f"i{i}": rng.integers(0, 10**6, rows) for i in range(2)})
            else:
                vocab = _words(rng, max(rows // 10, 1))
                cols = {f"s{i}": vocab[rng.integers(0, len(vocab), rows)] for i in range(4)}
            path = os.path.join(tmp, f"{kind}.csv")
            pd.DataFrame(cols).to_csv(path, index=False)
            out.append(_median_time(lambda _, p=path: pd.read_csv(p)) / (rows * 4))
    return out[0], out[1]


def measure_profile(quick: bool = False) -> MachineProfile:
    """Run every microbenchmark and return the resulting (calibrated) profile."""
    s = 0.05 if quick else 1.0
    rng = np.random.default_rng(12345)
    t_start = time.perf_counter()
    plugged_start = power_plugged()
    curves: dict[str, list[list[float]]] = {}
    sizes = [256 * 1024, 4 * MIB, 32 * MIB, 256 * MIB] if not quick else [256 * 1024, 4 * MIB]
    curves["copy_bps"], curves["read_bps"] = _copy_curve(sizes)

    distincts = [100, 10_000, 100_000, 1_000_000, 3_000_000]
    if quick:
        distincts = [100, 10_000, 50_000]
    curves["num_factorize_s"], curves["text_factorize_s"], curves["object_take_s"] = (
        _factorize_curves(rng, distincts, n_min=int(2_000_000 * s) or 100_000)
    )
    num_sizes = [100_000, 1_000_000, 8_000_000] if not quick else [50_000, 200_000]
    text_sizes = [100_000, 1_000_000, 2_000_000] if not quick else [20_000, 100_000]
    curves.update(_sort_curves(rng, num_sizes, text_sizes))
    dims = [500, 1000, 2000, 4000] if not quick else [200, 400]
    curves["blas64_flops"], curves["blas32_flops"] = _blas_curves(rng, dims)

    out: dict[str, float] = {}
    n = max(100_000, int(16_000_000 * s))  # first touch vs warm write, 128 MB (quick: 0.8 MB)
    dst = np.empty(n)
    dst[:] = 0.0

    def cold_write(_: Any) -> None:
        fresh = np.empty(n)
        fresh[:] = 1.0

    def warm_write(_: Any) -> None:
        dst[:] = 1.0

    t_cold, t_warm = _median_time(cold_write), _median_time(warm_write)
    out["first_touch_bps"] = dst.nbytes / t_cold
    out["page_fault_s_per_byte"] = max(0.0, (t_cold - t_warm) / dst.nbytes)
    dst = np.empty(0)  # release the 128 MB working set

    out["csv_num_field_s"], out["csv_text_field_s"] = _csv_field_costs(
        rng, max(20_000, int(500_000 * s))
    )
    m = max(20_000, int(1_000_000 * s))
    for name, series in (
        ("int_to_str_s", pd.Series(rng.integers(0, 10**9, m))),
        ("float_to_str_s", pd.Series(rng.random(m) * 1000)),
        ("datetime_to_str_s", pd.Series((1_500_000_000 + rng.integers(0, 10**8, m)).astype("datetime64[s]"))),
    ):  # fmt: skip
        out[name] = _median_time(lambda _, x=series: x.astype(str)) / m
    big = rng.integers(0, 10**6, max(100_000, int(16_000_000 * s)))
    out["cast_s"] = _median_time(lambda _: big.astype("float32")) / big.size
    n = max(100_000, int(8_000_000 * s))  # groupby sum beyond factorization, 1000 groups
    keys = rng.integers(0, 1000, n)
    gdf = pd.DataFrame({"k": keys, "v": rng.random(n)})
    t_group = _median_time(lambda _: gdf.groupby("k")["v"].sum())
    t_key = _median_time(lambda _: pd.factorize(keys))
    out["agg_s"] = max(1e-10, (t_group - t_key) / n)
    out["blas_single_thread_flops"] = _single_thread_flops(1000 if not quick else 300)

    meta = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "quick": quick,
        "calibration_version": CALIBRATION_VERSION,
        "format": PROFILE_FORMAT,
        "seconds": round(time.perf_counter() - t_start, 1),
        "power_plugged_start": plugged_start,
        "power_plugged_end": power_plugged(),
    }
    return MachineProfile(curves=curves, **out, calibrated=True, meta=meta)


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
        if _fingerprint(current.meta) == _fingerprint(probe) and current.is_current_format:
            return current
    profile = measure_profile(quick=quick)
    save_profile(profile)
    return profile


def describe(profile: MachineProfile) -> str:
    lines = [f"profile id {profile.profile_id} (calibrated={profile.calibrated})"]
    for name, pts in sorted(profile.curves.items()):
        lines.append(f"  {name:18s} " + "  ".join(f"{x:.3g}:{y:.3g}" for x, y in pts))
    for name in (
        "csv_num_field_s", "csv_text_field_s", "int_to_str_s", "float_to_str_s",
        "datetime_to_str_s", "cast_s", "agg_s", "first_touch_bps", "page_fault_s_per_byte",
        "blas_single_thread_flops",
    ):  # fmt: skip
        lines.append(f"  {name:24s} {getattr(profile, name):.4g}")
    lines.append(f"  meta {profile.meta}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nexus-calibrate-machine", description=__doc__)
    parser.add_argument("--quick", action="store_true", help="smaller inputs, noisier result")
    parser.add_argument("--force", action="store_true", help="re-measure even if cached")
    parser.add_argument("--show", action="store_true", help="print the cached profile and exit")
    parser.add_argument(
        "--allow-battery",
        action="store_true",
        help="measure even on battery power (the profile records it; throughput may be throttled)",
    )
    args = parser.parse_args(argv)
    if args.show:
        profile = load_profile()
        print(describe(profile) if profile else "no calibrated profile at " + str(profile_path()))
        return
    if power_plugged() is False and not args.allow_battery and not args.quick:
        raise SystemExit(
            "nexus-calibrate-machine: the machine is on battery power; throughput may be throttled. "
            "Plug in and re-run, or pass --allow-battery (recorded in the profile)."
        )
    profile = ensure_profile(quick=args.quick, force=args.force)
    print(f"profile ({profile_path()}):")
    print(describe(profile))


if __name__ == "__main__":
    main()
