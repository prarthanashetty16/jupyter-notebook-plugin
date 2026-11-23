"""Power checks of the DEV-ONLY harness steps, with a user-accepted battery option (outside the freeze).

``--allow-battery`` exists only for development steps that do not feed calibration or a held-out claim:
the multi-statement dev evaluation, the determinism check, the dev re-prediction and the real-notebook
SUBSAMPLE run (``run_notebook --dev``). It is refused for every held-out entry point (``context=
"heldout"``: they keep their own refusal in ``benchmarks.heldout_env``) and for calibration (``context=
"calibrate"``). When it is used, every result records ``power: battery (user-accepted)`` with the raw
``psutil.sensors_battery()`` reading and, on Windows, the WMI ``root\\wmi BatteryStatus`` instance, and
reports carry ``BATTERY_NOTE``: their TIMING figures are battery-throttled and must not be used for
calibration or any timing claim (RAM figures are not affected by the power state).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

ACCEPTED = "battery (user-accepted)"
ENV_FLAG = "NEXUS_BATTERY_ACCEPTED"  # set by an accepted dev step; inherited by its spawned workers
STOP_PERCENT = 30
DEV_CONTEXTS = frozenset({"dev"})
BATTERY_NOTE = (
    "**Battery run (user-accepted):** these results were made on battery power. Timing figures (analysis "
    "time, Tier 1 fallbacks on the time budget, wall times) are battery-throttled and are NOT usable for "
    "calibration or for any timing claim; RAM figures do not depend on the power state."
)


def psutil_reading() -> str:
    try:
        import psutil

        return str(psutil.sensors_battery())
    except Exception as exc:  # noqa: BLE001
        return f"unavailable ({type(exc).__name__})"


def wmi_reading() -> Any:
    """``root\\wmi BatteryStatus`` (PowerOnline, Charging, Discharging, RemainingCapacity) on Windows."""
    if sys.platform != "win32":
        return "not Windows"
    cmd = ("Get-CimInstance -Namespace root\\wmi -ClassName BatteryStatus | Select-Object PowerOnline,Charging,"
           "Discharging,RemainingCapacity,Voltage | ConvertTo-Json -Compress")  # fmt: skip
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                             timeout=20, check=False).stdout.strip()  # fmt: skip
        return json.loads(out) if out else "no BatteryStatus instance"
    except Exception as exc:  # noqa: BLE001
        return f"unavailable ({type(exc).__name__})"


def battery_percent() -> float | None:
    try:
        import psutil

        b = psutil.sensors_battery()
        return None if b is None else float(b.percent)
    except Exception:  # noqa: BLE001
        return None


def power_record(allow_battery: bool, context: str = "dev") -> dict[str, Any]:
    """The power fields a dev result records; SystemExit when the step may not run on this power state."""
    from nexus.power import power_state

    state = power_state()
    if state != "battery":
        return {"power": state}
    if not allow_battery:
        raise SystemExit("on battery power: plug in first (dev-only steps accept --allow-battery)")
    if context not in DEV_CONTEXTS:
        raise SystemExit(f"--allow-battery is refused for {context} runs: plug in")
    os.environ[ENV_FLAG] = "1"
    return {"power": ACCEPTED, "battery_psutil": psutil_reading(), "battery_wmi": wmi_reading()}


def recorded(state: str) -> str:
    """The power value a result row stores: ``battery (user-accepted)`` inside an accepted dev step."""
    return ACCEPTED if state == "battery" and os.environ.get(ENV_FLAG) == "1" else state


def below_stop_level() -> bool:
    """True when on battery below ``STOP_PERCENT``: finish the current step, then stop."""
    from nexus.power import power_state

    pct = battery_percent()
    return power_state() == "battery" and pct is not None and pct < STOP_PERCENT
