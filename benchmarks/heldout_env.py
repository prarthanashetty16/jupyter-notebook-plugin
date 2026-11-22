"""The machine-profile and power check of held-out runs (Phase 6d; outside the frozen files).

Every held-out entry point (``benchmarks full`` with protected points, ``benchmarks.multicell.run run
--heldout``, the real-notebook harness without ``--dev``) calls ``require_profile()`` after the freeze guard:

* refuse on battery power (throttled throughput changes the Tier 1 budget and every time estimate);
* on the REFERENCE machine (the platform, processor and CPU count of the reference profile frozen in the
  manifest, ``src/nexus/calibration/reference_machine.json``) the cached profile must BE the reference
  profile (same profile id): anything else, e.g. a quick or battery profile written over it, aborts;
* on any other machine (e.g. the Linux VM) there is no reference to compare with, so the profile must have
  been measured in this session: by ``nexus-calibrate-machine`` (not ``--quick``), on mains or with an unknown
  power state (VMs), at most ``MAX_PROFILE_AGE_H`` hours before the run; its id is recorded.

The returned record (profile id, mode, timestamp, power, reference id) is written into the run's results.
``profile_record()`` gives the same fields without enforcing anything (for dev runs).
"""

from __future__ import annotations

import time
from typing import Any

MAX_PROFILE_AGE_H = 12.0
IDENTITY_KEYS = ("platform", "processor", "cpu_count")


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


def require_profile(now: float | None = None) -> dict[str, Any]:
    """Abort (``HeldoutEnvironmentError``) unless the profile and power suit a held-out run."""
    from nexus.machine import load_profile, reference_profile
    from nexus.power import power_state

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
    if _identity(ref.meta) == _this_machine():
        if prof.profile_id != ref.profile_id:
            raise HeldoutEnvironmentError(
                f"held-out run refused: this is the reference machine, but its cached profile "
                f"({prof.profile_id}, {prof.meta.get('timestamp')}, quick={prof.meta.get('quick')}) is not the "
                f"reference profile frozen in the manifest ({ref.profile_id}). Restore it: copy "
                "src/nexus/calibration/reference_machine.json to the profile path "
                "(`nexus-calibrate-machine --show` prints it)."
            )
        return {**record, "profile_mode": "reference machine: reference profile"}
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
    age_h = ((now if now is not None else time.time()) - measured) / 3600.0
    if age_h > MAX_PROFILE_AGE_H or age_h < -0.1:
        raise HeldoutEnvironmentError(
            f"held-out run refused: on a new machine the profile must be measured in this session "
            f"(at most {MAX_PROFILE_AGE_H:g} h before the run; it is {age_h:.1f} h old). Run "
            "`nexus-calibrate-machine --force` first."
        )
    return {**record, "profile_mode": f"new machine: measured {age_h:.1f} h before the run"}
