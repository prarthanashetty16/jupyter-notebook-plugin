"""Risk engine: OK / WARN / HIGH_RISK / UNKNOWN from frozen Estimates and the live resources.

Implements ``docs/benchmarks/phase5-preregistration.md`` (Part A) exactly; the constants below are
the pre-registered ones and are not tuned. It only *reads* Estimates (Tier 0/1/2 are frozen) and
never touches the user's cell: any problem becomes UNKNOWN or no report, never OK.

Why UNKNOWN exists: "no estimate" must not look like "safe". Why HIGH_RISK uses ``expected``:
the model's own central figure says the cell does not fit. Why WARN uses ``high``: a missed
crash loses work, a false alarm costs one line of text. Swap is never headroom: a cell that fits
only by swapping does not crash but can make the notebook unusable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from nexus.models.base import Estimate
from nexus.pipeline import CellReport, OpEstimate
from nexus.render import human_bytes
from nexus.state import ResourceSnapshot
from nexus.timebuckets import bucket_index, bucket_label

WARN_MARGIN = 0.85  # WARN when high > margin * headroom (reserve for drift, fragmentation, the OS)
CONFIDENCE_FLOOR = 0.30  # below it an otherwise-OK cell is UNKNOWN (Tier 2's floor; no-op is 0)
LONG_RUN_BUCKET = bucket_index(60.0)  # first bucket of "1-10 min"


class RiskClass(str, Enum):
    OK = "OK"
    WARN = "WARN"
    HIGH_RISK = "HIGH_RISK"
    UNKNOWN = "UNKNOWN"

    @property
    def is_alert(self) -> bool:
        return self in (RiskClass.WARN, RiskClass.HIGH_RISK)


@dataclass(frozen=True, kw_only=True)
class RiskReport:
    """Structured verdict. Figures are bytes; ``time_bucket`` is the only time statement."""

    risk: RiskClass
    reason: str
    headroom: int | None = None  # effective available RAM at classification time
    swap_free: int | None = None
    cgroup_limit: int | None = None
    total_ram: int | None = None
    ram_low: int | None = None
    ram_expected: int | None = None
    ram_high: int | None = None
    tier: int | None = None
    confidence: float | None = None
    fallback: str | None = None  # Estimate.note (guard fallback), if any
    time_bucket: str | None = None
    long_run: bool = False
    drivers: tuple[str, ...] = ()

    def lines(self) -> list[str]:
        out = [f"[nexus] {self.risk.value}: {self.reason}"]
        if self.ram_expected is not None and self.headroom is not None:
            out.append(
                f"  predicted peak {human_bytes(self.ram_low or 0)}-{human_bytes(self.ram_high or 0)} "
                f"(expected {human_bytes(self.ram_expected)}) vs {human_bytes(self.headroom)} available"
                + (
                    f" (container limit {human_bytes(self.cgroup_limit)})"
                    if self.cgroup_limit
                    else ""
                )
            )
        if self.tier is not None:
            conf = f"{self.confidence:.2f}" if self.confidence is not None else "n/a"
            fb = f"; fallback: {self.fallback}" if self.fallback else ""
            out.append(f"  tier {self.tier}, confidence {conf}{fb}")
        if self.time_bucket:
            out.append(
                f"  time: about {self.time_bucket}" + (" (long run)" if self.long_run else "")
            )
        return out

    def format(self) -> str:
        return "\n".join(self.lines())


def combine(estimates: list[Estimate]) -> Estimate | None:
    """Cell range: max of lows and of expected, SUM of highs (intermediates may stay alive).

    The sum is an upper bound, the max is not; the combination is unit-tested only (benchmark
    points are single operations) and is not part of any success criterion.
    """
    if not estimates:
        return None
    if len(estimates) == 1:
        return estimates[0]
    worst = max(estimates, key=lambda e: e.ram_expected)
    low = max(e.ram_low for e in estimates)
    expected = max(e.ram_expected for e in estimates)
    return Estimate(
        ram_low=low,
        ram_expected=expected,
        ram_high=max(sum(e.ram_high for e in estimates), expected),
        time_low=sum(e.time_low for e in estimates),
        time_expected=sum(e.time_expected for e in estimates),
        time_high=sum(e.time_high for e in estimates),
        confidence=min(e.confidence for e in estimates),
        tier=max(e.tier for e in estimates),
        drivers=list(worst.drivers),
        note=next((e.note for e in estimates if e.note), None),
    )


def _finite(e: Estimate) -> bool:
    figures = (e.ram_low, e.ram_expected, e.ram_high, e.time_low, e.time_expected, e.time_high)
    return all(math.isfinite(x) for x in figures) and math.isfinite(e.confidence)


def _bucket(e: Estimate) -> tuple[str, bool]:
    idx = bucket_index(e.time_expected)
    return bucket_label(e.time_expected), idx >= LONG_RUN_BUCKET


def classify(  # noqa: C901
    estimates: list[Estimate],
    resources: ResourceSnapshot | None = None,
    *,
    headroom: int | None = None,
    uncovered: int = 0,
    drivers_from: list[OpEstimate] | None = None,
) -> RiskReport:
    """Classify a cell from its operation estimates.

    ``headroom`` overrides the snapshot's effective available RAM (the evaluation simulates
    ``limit - baseline`` with it). ``uncovered`` is the number of detected operations without
    an estimate: when the class would be OK they make it UNKNOWN.
    """
    snap = {}
    if resources is not None:
        snap = {
            "swap_free": resources.swap_free,
            "cgroup_limit": resources.cgroup.limit if resources.cgroup else None,
            "total_ram": resources.effective_total,
        }
    if headroom is None and resources is not None:
        headroom = resources.effective_available
    if not estimates:
        return RiskReport(
            risk=RiskClass.UNKNOWN, reason="no estimate for this cell", headroom=headroom, **snap
        )
    if any(not _finite(e) for e in estimates):
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason="an estimate has non-finite figures",
            headroom=headroom,
            **snap,
        )
    try:
        cell = combine(estimates)
    except ValueError:
        cell = None
    if cell is None:
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason="estimates could not be combined",
            headroom=headroom,
            **snap,
        )
    bucket, long_run = _bucket(cell)
    drivers = tuple(cell.drivers)
    if drivers_from:
        top = max(drivers_from, key=lambda o: o.estimate.ram_expected)
        drivers = tuple(top.estimate.drivers)
    common = {
        "headroom": headroom,
        "ram_low": cell.ram_low,
        "ram_expected": cell.ram_expected,
        "ram_high": cell.ram_high,
        "tier": cell.tier,
        "confidence": cell.confidence,
        "fallback": cell.note,
        "time_bucket": bucket,
        "long_run": long_run,
        "drivers": drivers,
        **snap,
    }
    if headroom is None:
        return RiskReport(
            risk=RiskClass.UNKNOWN, reason="available RAM could not be measured", **common
        )
    why = _drivers_text(drivers)
    swap = snap.get("swap_free")
    if cell.ram_expected > headroom:
        swapnote = (
            "; it may swap instead of failing"
            if swap is not None and cell.ram_expected <= headroom + swap
            else ""
        )
        limit = snap.get("cgroup_limit")
        cg = (
            " (container limit applies)"
            if limit and headroom < (resources.available_ram if resources else 0)
            else ""
        )
        return RiskReport(
            risk=RiskClass.HIGH_RISK,
            reason=f"expected peak {human_bytes(cell.ram_expected)} exceeds the {human_bytes(max(headroom, 0))} "
            f"available{cg}{swapnote}{why}",
            **common,
        )
    if cell.ram_high > WARN_MARGIN * headroom:
        return RiskReport(
            risk=RiskClass.WARN,
            reason=f"upper estimate {human_bytes(cell.ram_high)} is above {WARN_MARGIN:.0%} of the "
            f"{human_bytes(headroom)} available{why}",
            **common,
        )
    if uncovered:
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason=f"{uncovered} operation(s) of this cell have no estimate; the rest fits",
            **common,
        )
    if cell.confidence < CONFIDENCE_FLOOR:
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason=f"fits, but confidence {cell.confidence:.2f} is below {CONFIDENCE_FLOOR:.2f}",
            **common,
        )
    return RiskReport(risk=RiskClass.OK, reason="predicted peak fits with margin", **common)


def _drivers_text(drivers: tuple[str, ...]) -> str:
    return f"; cost drivers: {'; '.join(drivers[:3])}" if drivers else ""


def assess(report: CellReport) -> RiskReport | None:
    """Risk of a ``CellReport``; None when the cell has no known operation (nothing to say)."""
    if not report.ops:
        return None
    uncovered = len({id(o) for o in report.ops} - {id(e.op) for e in report.estimates})
    return classify(
        [e.estimate for e in report.estimates],
        report.resources,
        uncovered=uncovered,
        drivers_from=report.estimates or None,
    )
