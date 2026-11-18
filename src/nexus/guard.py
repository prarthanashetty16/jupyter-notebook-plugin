"""Sanity guard for Tier 1 estimates: a refinement must never be worse than "no refinement".

A Tier 1 estimate is rejected (Tier 0 is kept and the reason recorded in ``Estimate.note``) when

* computing it failed, or any RAM / time figure is NaN or infinite;
* its expected RAM or time is not positive; or
* its expected RAM lies outside Tier 0's [low, high] RAM range widened by ``RANGE_SLACK`` on each
  side (a grossly inconsistent refinement).

Why widened: the strict condition (outside Tier 0's range) fires on no usable development point
(0 of 208 Tier 1 estimates with statistics; it only caught the three zero estimates), but Tier 0 does
not know about nulls, so a correct Tier 1 estimate can sit just outside it. Example (a regression
test): a datetime column with 4% nulls to ``str`` is 69 B/row (a null is not a string object), Tier 0's
low is 70.5 B/row. A guard that rejects that estimate would discard the better one, so the range
check only rejects estimates more than ``RANGE_SLACK`` x outside. It is only evaluated for RAM: Tier 1
and Tier 0 time use different centres with the same band, and that was not measured.
"""

from __future__ import annotations

import math

from nexus.models.base import Estimate

RANGE_SLACK = 2.0


def tier1_problem(tier1: Estimate, tier0: Estimate | None) -> str | None:
    """Why ``tier1`` must not be used (None: it is fine)."""
    figures = (tier1.ram_low, tier1.ram_expected, tier1.ram_high,
               tier1.time_low, tier1.time_expected, tier1.time_high)  # fmt: skip
    if not all(math.isfinite(x) for x in figures):
        return "non-finite figure"
    if tier1.ram_expected <= 0 or tier1.time_expected <= 0:
        return "non-positive expected value"
    if tier0 is not None and not (
        tier0.ram_low / RANGE_SLACK <= tier1.ram_expected <= tier0.ram_high * RANGE_SLACK
    ):
        return "expected RAM far outside Tier 0's range"
    return None
