"""``nexus-calibrate-machine``: measure this machine's profile, with the power state recorded.

The measurement itself is ``nexus.calibrate`` (frozen with the model stack, unchanged); this entry
point adds the power policy of Phase 6b (``nexus.power``): it refuses only when battery power is
positively detected (unless ``--allow-battery``), warns and proceeds when the power state is unknown
(cloud VMs, Linux servers without a battery sensor, sensor errors), and records ``power``
(``mains`` / ``battery`` / ``unknown``) at the start and end in the profile's ``meta``. The meta is
provenance only: it is not part of the profile id and does not change any estimate.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace

from nexus import calibrate
from nexus.machine import load_profile, profile_path, save_profile
from nexus.power import power_state

UNKNOWN_WARNING = (
    "nexus-calibrate-machine: power state unknown (no battery sensor, e.g. a VM or server); "
    "measuring anyway and recording power: unknown"
)
BATTERY_REFUSAL = (
    "nexus-calibrate-machine: the machine is on battery power; throughput may be throttled. "
    "Plug in and re-run, or pass --allow-battery (recorded in the profile)."
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-calibrate-machine", description=__doc__)
    parser.add_argument("--quick", action="store_true", help="smaller inputs, noisier result")
    parser.add_argument("--force", action="store_true", help="re-measure even if cached")
    parser.add_argument("--show", action="store_true", help="print the cached profile and exit")
    parser.add_argument(
        "--allow-battery", action="store_true", help="measure even on battery power (recorded)"
    )
    args = parser.parse_args(argv)
    if args.show:
        profile = load_profile()
        print(
            calibrate.describe(profile) if profile else f"no calibrated profile at {profile_path()}"
        )
        return 0
    start = power_state()
    if start == "battery" and not args.allow_battery and not args.quick:
        print(BATTERY_REFUSAL, file=sys.stderr)
        return 2
    if start == "unknown":
        print(UNKNOWN_WARNING, file=sys.stderr)
    before = load_profile()
    profile = calibrate.ensure_profile(quick=args.quick, force=args.force)
    measured = before is None or before.meta.get("timestamp") != profile.meta.get("timestamp")
    if measured:  # a fresh measurement: record where it was made
        meta = {**profile.meta, "power": start, "power_end": power_state()}
        profile = replace(profile, meta=meta)
        save_profile(profile)
    print(f"profile ({profile_path()}):")
    print(calibrate.describe(profile))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
