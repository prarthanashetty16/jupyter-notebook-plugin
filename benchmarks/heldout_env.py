"""The machine-profile and power check of held-out runs (Phase 6d; outside the frozen files).

Every held-out entry point (``benchmarks full`` with protected points, ``benchmarks.multicell.run run
--heldout``, the real-notebook harness without ``--dev``) calls ``require_profile(run_dir)`` after the
freeze guard. ``run_dir`` is the run's results folder; its ``meta.json`` carries the profile PIN.

* Every invocation refuses on battery power (throttled throughput changes the Tier 1 budget and every
  time estimate).
* The FIRST invocation of a run (no pin in ``meta.json``) checks the profile and pins it (profile id and a
  hash of the profile file):
  - on the REFERENCE machine (the platform, processor and CPU count of the reference profile frozen in the
    manifest, ``src/nexus/calibration/reference_machine.json``) the cached profile must BE the reference
    profile (same id): anything else, e.g. a quick or battery profile written over it, aborts;
  - on any other machine (e.g. the Linux VM) there is no reference, so the profile must have been measured
    in this session: by ``nexus-calibrate-machine --force`` (not ``--quick``), on mains or with an unknown
    power state (VMs), at most ``MAX_PROFILE_AGE_H`` hours earlier.
* Every LATER invocation of the same run (a resume after an interruption, the full run after a ``--pilot``)
  requires the pinned profile: the same id and an unchanged profile file. Its age is ignored (a 20-30 h run
  must not be refused for outliving the calibration); a re-calibration or a profile overwritten mid-run
  aborts, because the run's results would mix two profiles.

The returned record (profile id, mode, timestamp, power, reference id, the pin) is written into the
results. ``profile_record()`` gives the same fields without enforcing anything (for dev runs).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

MAX_PROFILE_AGE_H = 12.0
IDENTITY_KEYS = ("platform", "processor", "cpu_count")
PIN_KEY = "heldout_profile"  # in the run's meta.json
_now = time.time  # replaced in tests (resume after 30 h)


class HeldoutEnvironmentError(RuntimeError):
    """The machine profile or the power state is not acceptable for a held-out run."""


def _identity(meta: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(meta.get(k) for k in IDENTITY_KEYS)


def _this_machine() -> tuple[Any, ...]:
    import os
    import platform

    return (platform.platform(), platform.processor(), os.cpu_count())


def profile_record() -> dict[str, Any]:
    """Profile id, its timestamp and the power state now (recorded by every run, held-out or not)."""
    from nexus.machine import load_profile, reference_profile
    from nexus.power import power_state

    prof = load_profile()
    return {
        "profile_id": prof.profile_id if prof is not None else None,
        "profile_timestamp": prof.meta.get("timestamp") if prof is not None else None,
        "reference_profile_id": reference_profile().profile_id,
        "power": power_state(),
    }


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _read_meta(run_dir: Path) -> dict[str, Any]:
    try:
        return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _check_first(prof: Any, ref: Any, now: float | None) -> str:
    """The first invocation's check; returns the profile mode (or raises)."""
    if _identity(ref.meta) == _this_machine():
        if prof.profile_id != ref.profile_id:
            raise HeldoutEnvironmentError(
                f"held-out run refused: this is the reference machine, but its cached profile "
                f"({prof.profile_id}, {prof.meta.get('timestamp')}, quick={prof.meta.get('quick')}) is not the "
                f"reference profile frozen in the manifest ({ref.profile_id}). Restore it: copy "
                "src/nexus/calibration/reference_machine.json to the profile path "
                "(`nexus-calibrate-machine --show` prints it)."
            )
        return "reference machine: reference profile"
    if prof.meta.get("quick"):
        raise HeldoutEnvironmentError("held-out run refused: the profile is a --quick measurement")
    if prof.meta.get("power") == "battery" or prof.meta.get("power_plugged_start") is False:
        raise HeldoutEnvironmentError("held-out run refused: the profile was measured on battery")
    try:
        measured = time.mktime(time.strptime(str(prof.meta.get("timestamp")), "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        raise HeldoutEnvironmentError(
            "held-out run refused: the profile has no timestamp"
        ) from None
    age_h = ((now if now is not None else _now()) - measured) / 3600.0
    if age_h > MAX_PROFILE_AGE_H or age_h < -0.1:
        raise HeldoutEnvironmentError(
            f"held-out run refused: this is the FIRST invocation of the run on a new machine, so the profile "
            f"must be measured in this session (at most {MAX_PROFILE_AGE_H:g} h before; it is {age_h:.1f} h "
            "old). Run `nexus-calibrate-machine --force` first."
        )
    return f"new machine: measured {age_h:.1f} h before the first invocation"


def require_profile(run_dir: Path | str, now: float | None = None) -> dict[str, Any]:
    """Abort (``HeldoutEnvironmentError``) unless the profile and power suit this held-out run.

    The first call for ``run_dir`` pins the profile in ``run_dir/meta.json``; later calls require it.
    """
    from nexus.machine import load_profile, profile_path, reference_profile
    from nexus.power import power_state

    run_dir = Path(run_dir)
    power = power_state()
    if power == "battery":
        raise HeldoutEnvironmentError(
            "held-out run refused: the machine is on battery power; plug in"
        )
    prof = load_profile()
    ref = reference_profile()
    if prof is None or not prof.calibrated or not prof.is_current_format:
        raise HeldoutEnvironmentError(
            "held-out run refused: no calibrated machine profile of the current format; run "
            "`nexus-calibrate-machine --force` first"
        )
    record = {**profile_record(), "power": power}
    sha = _file_sha256(profile_path())
    meta = _read_meta(run_dir)
    pin = meta.get(PIN_KEY)
    if pin:
        if prof.profile_id != pin.get("profile_id") or sha != pin.get("profile_file_sha256"):
            what = "id" if prof.profile_id != pin.get("profile_id") else "file (same id)"
            raise HeldoutEnvironmentError(
                f"held-out run refused: this run was started with machine profile {pin.get('profile_id')} "
                f"(pinned {pin.get('pinned_at')} in {run_dir / 'meta.json'}), but the profile {what} on this "
                f"machine has changed (now {prof.profile_id}). A resumed run must use the SAME profile: restore "
                "the original profile file, or start a NEW run in a new results folder (with a fresh "
                "`nexus-calibrate-machine --force`)."
            )
        return {
            **record,
            "profile_mode": f"resumed: pinned profile ({pin.get('mode')})",
            PIN_KEY: pin,
        }
    mode = _check_first(prof, ref, now)
    pin = {
        "profile_id": prof.profile_id,
        "profile_file_sha256": sha,
        "profile_timestamp": prof.meta.get("timestamp"),
        "pinned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "meta.json").write_text(
        json.dumps({**meta, PIN_KEY: pin}, indent=2, default=str), encoding="utf-8"
    )
    return {**record, "profile_mode": f"first invocation: {mode}", PIN_KEY: pin}
