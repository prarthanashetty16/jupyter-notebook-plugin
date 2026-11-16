"""Per-machine throughput profile used by the time models.

Models never hard-code hardware speeds: they read them from ``machine()``. The profile comes from
``nexus-calibrate-machine`` (``nexus.calibrate``), cached in a JSON file. Without one, the
documented *uncalibrated defaults* below are used (``calibrated=False``); those are guesses made
before any measurement and were what the Phase 3 baseline ran with.

Cache location: ``$NEXUS_MACHINE_PROFILE`` if set, else ``%LOCALAPPDATA%\\nexus\\machine.json``
(Windows) or ``$XDG_CACHE_HOME/nexus/machine.json`` (``~/.cache`` by default).
"""

from __future__ import annotations

import functools
import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

ENV_VAR = "NEXUS_MACHINE_PROFILE"


@dataclass(frozen=True)
class MachineProfile:
    """Throughputs; every field is measured by a dedicated microbenchmark in ``nexus.calibrate``."""

    copy_bps: float = 2.0e9  # bytes/s for large column copies
    num_hash_s: float = 25e-9  # s per element, factorize numeric
    text_hash_s: float = 120e-9  # s per element, factorize object strings
    num_argsort_s: float = 6e-9  # s per n*log2(n), argsort numeric
    text_argsort_s: float = 120e-9  # s per n*log2(n), argsort object strings
    np_sort_s: float = 8e-9  # s per n*log2(n), np.sort float64
    csv_parse_bps: float = 80e6  # CSV bytes/s through pandas.read_csv
    blas_flops: float = 3e10  # float64 matmul flop/s
    cast_s: float = 3e-9  # s per element, numeric astype
    to_str_s: float = 150e-9  # s per element, int -> str astype
    agg_s: float = 5e-9  # s per element, groupby sum beyond key factorization
    warm_copy_bps: float = 0.0  # bytes/s copying into already-touched memory (informational)
    first_touch_bps: float = 0.0  # bytes/s allocating + first write of fresh memory (informational)
    page_fault_s_per_byte: float = 0.0  # extra s/byte for first touch vs warm write (informational)
    calibrated: bool = False
    meta: dict[str, Any] = field(default_factory=dict, compare=False)


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


def load_profile(path: Path | None = None) -> MachineProfile | None:
    """The cached profile, or None if missing/unreadable (never raises)."""
    path = path or profile_path()
    try:
        raw = json.loads(path.read_text())
        known = {f.name for f in fields(MachineProfile)}
        return MachineProfile(**{k: v for k, v in raw.items() if k in known})
    except (OSError, ValueError, TypeError):
        return None


@functools.lru_cache(maxsize=1)
def machine() -> MachineProfile:
    """Cached profile if present, else the uncalibrated defaults."""
    return load_profile() or MachineProfile()
