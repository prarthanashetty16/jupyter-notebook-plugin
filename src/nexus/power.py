"""Power state of the machine, for the provenance of a machine profile (Phase 6b).

Throughput measured on battery can be throttled, so ``nexus-calibrate-machine`` records the power
state and refuses only when it POSITIVELY detects battery power. Cloud VMs and Linux servers have
no battery sensor (``psutil.sensors_battery()`` returns None) and some platforms raise: both are
"unknown", which is allowed with a warning (a refusal there would make the tool unusable on the
machines that run the held-out validation).
"""

from __future__ import annotations

from typing import Literal

import psutil

PowerState = Literal["mains", "battery", "unknown"]


def power_state() -> PowerState:
    """``mains`` / ``battery`` from the battery sensor; ``unknown`` without one or on any error."""
    try:
        battery = psutil.sensors_battery()
    except Exception:
        return "unknown"
    if battery is None:
        return "unknown"
    plugged = getattr(battery, "power_plugged", None)
    if plugged is None:
        return "unknown"
    return "mains" if plugged else "battery"
