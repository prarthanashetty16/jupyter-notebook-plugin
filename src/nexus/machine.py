"""Per-machine throughput profile used by the time models (format 3: working-set curves).

Models never hard-code hardware speeds: they read them from ``machine()``. The profile comes from
``nexus-calibrate-machine`` (``nexus.calibrate``), cached in a JSON file. Format 3 stores most
throughputs as CURVES over the size that sets the working set (bytes copied, distinct keys hashed,
elements sorted, flops of a product), because a cache-resident pass is several times faster per
element than a RAM-resident one (Phase 6 probes: factorize 9 ns/row at 100 distinct keys vs 107 ns
at 3M; an object take 7 ns at 1k distinct objects vs 116 ns at 3M). ``at(name, x)`` interpolates
log-log between the measured points and extrapolates with the last segment's slope (clamped to
0..1 in the exponent, so a per-element cost never falls and never grows faster than linearly).

Without a calibrated format-3 profile the **generic profile** is used (``calibrated=False``): the
reference machine's profile shipped in ``nexus/calibration/reference_machine.json`` with every cost
doubled and every throughput halved. Estimates made with it carry the flag "uncalibrated machine"
and wider time ranges (pre-registration section 4).

Cache location: ``$NEXUS_MACHINE_PROFILE`` if set, else ``%LOCALAPPDATA%\\nexus\\machine.json``
(Windows) or ``$XDG_CACHE_HOME/nexus/machine.json`` (``~/.cache`` by default).
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field, fields, replace
from importlib import resources
from pathlib import Path
from typing import Any

ENV_VAR = "NEXUS_MACHINE_PROFILE"
PROFILE_FORMAT = 3
GENERIC_SLOWDOWN = 2.0  # generic profile = reference machine with every cost x2 (documented guess)
UNCALIBRATED_FLAG = "uncalibrated machine"

# curve name -> True if it is a throughput (higher = faster), False if it is a cost per unit
CURVES: dict[str, bool] = {
    "copy_bps": True,  # bytes/s, cold copy into fresh memory, x = bytes copied
    "read_bps": True,  # bytes/s, streaming read (sum), x = bytes read
    "num_factorize_s": False,  # s/row, factorize int64, x = distinct keys
    "text_factorize_s": False,  # s/row, factorize shared str objects, x = distinct keys
    "object_take_s": False,  # s/element, take of Python objects (incref), x = distinct objects
    "num_argsort_s": False,  # s per n*log2(n), argsort int64/float64, x = n
    "text_argsort_s": False,  # s per n*log2(n), argsort str objects, x = n
    "np_sort_s": False,  # s per n*log2(n), np.sort float64 (copy + in-place sort), x = n
    "blas64_flops": True,  # flop/s, float64 matmul, x = m*k*p
    "blas32_flops": True,  # flop/s, float32 matmul, x = m*k*p
}
SCALARS_COST = (
    "csv_num_field_s", "csv_text_field_s", "int_to_str_s", "float_to_str_s",
    "datetime_to_str_s", "cast_s", "agg_s", "page_fault_s_per_byte",
)  # fmt: skip
SCALARS_RATE = ("first_touch_bps", "blas_single_thread_flops")


@dataclass(frozen=True)
class MachineProfile:
    """Measured primitives; every value comes from a dedicated microbenchmark (``nexus.calibrate``)."""

    curves: dict[str, list[list[float]]] = field(default_factory=dict)
    csv_num_field_s: float = 20e-9  # s per numeric CSV field (C engine)
    csv_text_field_s: float = 200e-9  # s per text / date CSV field (a new str object each)
    int_to_str_s: float = 120e-9  # s per element, astype(str) from int64
    float_to_str_s: float = 500e-9  # s per element, astype(str) from float64
    datetime_to_str_s: float = 260e-9  # s per element, astype(str) from datetime64
    cast_s: float = 3e-9  # s per element, numeric astype
    agg_s: float = 5e-9  # s per element, groupby sum beyond key factorization
    first_touch_bps: float = 2.8e9  # bytes/s, allocate + first write
    page_fault_s_per_byte: float = 2e-10  # extra s/byte of first touch over a warm write
    blas_single_thread_flops: float = 5e10  # flop/s, float64 matmul on one thread
    calibrated: bool = False
    meta: dict[str, Any] = field(default_factory=dict, compare=False)

    def at(self, name: str, x: float) -> float:
        """Curve ``name`` at size ``x`` (log-log interpolation, bounded extrapolation)."""
        pts = sorted((float(a), float(b)) for a, b in self.curves.get(name, ()) if a > 0 and b > 0)
        if not pts:
            raise KeyError(f"machine profile has no curve {name!r}")
        if len(pts) == 1:
            return pts[0][1]
        lx = math.log(max(x, 1.0))
        xs = [math.log(a) for a, _ in pts]
        ys = [math.log(b) for _, b in pts]
        if lx <= xs[0]:
            return pts[0][1]  # below the smallest working set: cache-resident, flat
        i = next((j for j in range(1, len(xs)) if lx <= xs[j]), len(xs) - 1)
        slope = (ys[i] - ys[i - 1]) / (xs[i] - xs[i - 1])
        if lx > xs[-1]:  # beyond the largest measured size: last slope, bounded
            lo, hi = (-1.0, 0.0) if CURVES.get(name, False) else (0.0, 1.0)
            slope = min(max(slope, lo), hi)
        return math.exp(ys[i - 1] + slope * (lx - xs[i - 1]))

    @property
    def profile_id(self) -> str:
        """Content hash of the measured values and the format (provenance of an estimate)."""
        body = {k: v for k, v in asdict(self).items() if k != "meta"}
        body["format"] = self.meta.get("format", PROFILE_FORMAT)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        return digest[:12]

    @property
    def is_current_format(self) -> bool:
        return self.meta.get("format") == PROFILE_FORMAT and set(CURVES) <= set(self.curves)


def scaled(profile: MachineProfile, factor: float) -> MachineProfile:
    """Every cost multiplied and every throughput divided by ``factor``."""
    curves = {
        name: [[x, y / factor if CURVES.get(name, False) else y * factor] for x, y in pts]
        for name, pts in profile.curves.items()
    }
    changes: dict[str, Any] = {k: getattr(profile, k) * factor for k in SCALARS_COST}
    changes.update({k: getattr(profile, k) / factor for k in SCALARS_RATE})
    return replace(profile, curves=curves, **changes)


def profile_path() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "nexus" / "machine.json"


def save_profile(profile: MachineProfile, path: Path | None = None) -> Path:
    path = path or profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(profile), indent=2))
    machine.cache_clear()
    return path


def _from_raw(raw: dict[str, Any]) -> MachineProfile:
    known = {f.name for f in fields(MachineProfile)}
    return MachineProfile(**{k: v for k, v in raw.items() if k in known})


def load_profile(path: Path | None = None) -> MachineProfile | None:
    """The cached profile, or None if missing/unreadable (never raises)."""
    path = path or profile_path()
    try:
        return _from_raw(json.loads(path.read_text()))
    except (OSError, ValueError, TypeError):
        return None


@functools.lru_cache(maxsize=1)
def reference_profile() -> MachineProfile:
    """The reference machine's measured profile shipped with the package (provenance in ``meta``)."""
    text = resources.files("nexus.calibration").joinpath("reference_machine.json").read_text()
    return _from_raw(json.loads(text))


def generic_profile() -> MachineProfile:
    """Conservative stand-in for an uncalibrated machine (``calibrated=False``)."""
    ref = reference_profile()
    meta = {**ref.meta, "generic": True, "slowdown": GENERIC_SLOWDOWN}
    return replace(scaled(ref, GENERIC_SLOWDOWN), calibrated=False, meta=meta)


@functools.lru_cache(maxsize=1)
def machine() -> MachineProfile:
    """The calibrated profile of this machine (current format), else the generic profile."""
    cached = load_profile()
    if cached is not None and cached.calibrated and cached.is_current_format:
        return cached
    return generic_profile()
