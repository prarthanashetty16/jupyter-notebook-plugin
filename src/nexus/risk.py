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
from typing import Any

from nexus.models.base import Estimate
from nexus.pipeline import CellReport, OpEstimate
from nexus.render import human_bytes
from nexus.state import ResourceSnapshot
from nexus.timebuckets import bucket_index, bucket_label

WARN_MARGIN = 0.85  # WARN when high > margin * headroom (reserve for drift, fragmentation, the OS)
# Risk v2 (Phase 7b, candidate C3, selected on dev by the rule committed before computing:
# docs/benchmarks/phase7a/risk_v2_selection_rule.md): for these models, when their Tier 1 statistics ran,
# WARN uses the model's OWN Tier 1 upper bound instead of the policy-B high (Tier 0's), whose 2..24 B/field
# (read_csv) and unknown key uniqueness (merge) made most of their alarms false (R2 per operation). A
# fallback to Tier 0 keeps Tier 0's high. HIGH_RISK (expected > headroom) and the displayed range are
# unchanged.
OWN_TIER1_HIGH_FOR_WARN = frozenset({"read_csv", "merge"})
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
    partial: bool = False
    covered_operations: int | None = None
    total_operations: int | None = None

    def lines(self) -> list[str]:
        out = [f"[nexus] {self.risk.value}: {self.reason}"]
        if self.ram_expected is not None:
            if self.partial:
                coverage = (
                    f" (covers {self.covered_operations} of {self.total_operations} operations)"
                    if self.covered_operations is not None and self.total_operations is not None
                    else ""
                )
                out.append(
                    f"  covered part: at least {human_bytes(self.ram_low or 0)}{coverage}; "
                    "no upper bound for the full cell"
                    + (
                        f" (vs {human_bytes(self.headroom)} available)"
                        if self.headroom is not None
                        else ""
                    )
                )
            elif self.headroom is not None:
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
        if self.time_bucket and not self.partial:
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


def warn_high_estimate(item: OpEstimate) -> Estimate:
    """The operation's estimate with the ``high`` that WARN uses (risk v2, ``OWN_TIER1_HIGH_FOR_WARN``)."""
    from dataclasses import replace

    f = item.features or {}
    own = f.get("tier1_own_ram_high")
    used = bool((f.get("tier1") or {}).get("used")) and item.estimate.tier >= 1
    if item.model in OWN_TIER1_HIGH_FOR_WARN and used and own is not None:
        e = item.estimate
        return replace(e, ram_high=max(int(own), e.ram_expected))
    return item.estimate


def describe_uncovered(ops: list[Any]) -> str:
    """``df.fillna(0)``, ``a.merge(right, on='k')``: the uncovered operations as written (shortened), each
    deferred one followed by the reason it is not modelled (``nexus.deferred``)."""
    import ast

    from nexus.deferred import reason

    out = []
    for op in ops:
        try:
            text = ast.unparse(op.node)
        except Exception:
            text = getattr(op, "name", "?")
        why = reason(op)
        shown = f"`{text if len(text) <= 60 else text[:57] + '...'}`"
        out.append(f"{shown} ({why})" if why else shown)
    return ", ".join(out)


def classify(  # noqa: C901
    estimates: list[Estimate],
    resources: ResourceSnapshot | None = None,
    *,
    headroom: int | None = None,
    uncovered: int = 0,
    drivers_from: list[OpEstimate] | None = None,
    cell: Estimate | None = None,
    warn_high: int | None = None,
    uncovered_ops: str | None = None,
    covered_operations: int | None = None,
    total_operations: int | None = None,
) -> RiskReport:
    """Classify a cell from its operation estimates.

    ``headroom`` overrides the snapshot's effective available RAM (the evaluation simulates
    ``limit - baseline`` with it). ``uncovered`` is the number of detected operations without an
    estimate: when the class would be OK they make it UNKNOWN (``uncovered_ops`` names them).
    Partial cells expose only a covered-part lower bound, never a full-cell upper bound.
    ``warn_high`` is the upper bound WARN uses (risk v2); None: the cell's ``high``.
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
        why = f"no estimate for {uncovered_ops}" if uncovered_ops else "no estimate for this cell"
        return RiskReport(risk=RiskClass.UNKNOWN, reason=why, headroom=headroom, **snap)
    if any(not _finite(e) for e in estimates):
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason="an estimate has non-finite figures",
            headroom=headroom,
            **snap,
        )
    if cell is None:  # no cell-level estimate given: the v1 aggregation
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
    covered_count = covered_operations if covered_operations is not None else len(estimates)
    total_count = total_operations if total_operations is not None else covered_count + uncovered
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
        "partial": bool(uncovered),
        "covered_operations": covered_count if uncovered else None,
        "total_operations": total_count if uncovered else None,
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
    upper = cell.ram_high if warn_high is None else max(int(warn_high), cell.ram_expected)
    if upper > WARN_MARGIN * headroom:
        return RiskReport(
            risk=RiskClass.WARN,
            reason=f"upper estimate {human_bytes(upper)} is above {WARN_MARGIN:.0%} of the "
            f"{human_bytes(headroom)} available{why}",
            **common,
        )
    if uncovered:
        return RiskReport(
            risk=RiskClass.UNKNOWN,
            reason=(
                f"no estimate for {uncovered_ops}; the rest of the cell fits"
                if uncovered_ops
                else f"{uncovered} operation(s) of this cell have no estimate; the rest fits"
            ),
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
    covered = {id(e.op) for e in report.estimates}
    missing = [o for o in report.ops if id(o) not in covered]
    cell = warn = None
    if report.estimates and report.source:
        from dataclasses import replace

        from nexus.cellpeak import cell_estimate

        try:
            cell, _mode, _flags = cell_estimate(report.source, report.estimates)
            warn_items = [replace(e, estimate=warn_high_estimate(e)) for e in report.estimates]
            warn, _m, _f = cell_estimate(report.source, warn_items)
        except Exception:
            cell = warn = None  # the v1 aggregation in classify
    return classify(
        [e.estimate for e in report.estimates],
        report.resources,
        uncovered=len(missing),
        drivers_from=report.estimates or None,
        cell=cell,
        warn_high=None if warn is None else warn.ram_high,
        uncovered_ops=describe_uncovered(missing) if missing else None,
        covered_operations=len(covered),
        total_operations=len(report.ops),
    )
