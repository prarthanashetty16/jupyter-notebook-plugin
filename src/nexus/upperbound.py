"""Calibrated upper bound of a Tier 1 RAM range (v4 item C).

A model's ``high`` is a derivation, not an error bound: on the v3 held-out groups, cells whose operations were all
modelled still went above it. The pre-registered fix (``docs/benchmarks/phase8-preregistration.md``, item C) raises
the high to ``expected x q``, where ``q`` is a split-conformal factor (alpha = 0.02) computed on DEV residuals by
``benchmarks/upper_calibration.py`` and frozen in ``calibration/upper-v1.json``. It never lowers a high and never
changes ``low`` / ``expected``. Without the artifact nothing changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from nexus.models.base import Estimate

log = logging.getLogger(__name__)
ARTIFACT = Path(__file__).parent / "calibration" / "upper-v1.json"


@lru_cache(maxsize=1)
def _factors(path: Path = ARTIFACT) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:  # a broken artifact must never break a cell: no calibration
        log.debug("nexus: upper-bound artifact unreadable", exc_info=True)
        return None


def factor(model: str) -> float | None:
    """The family's own factor if it had >= 30 dev configurations, else the pooled one; None without artifact."""
    art = _factors()
    if art is None:
        return None
    fam = art.get("families", {}).get(model)
    return float((fam or art["pooled"])["q"])


def apply(model: str, estimate: Estimate) -> Estimate:
    """``estimate`` with ``high = max(high, expected x q)`` (Tier 1 only, the tier the residuals come from)."""
    if estimate.tier < 1:
        return estimate
    q = factor(model)
    if q is None:
        return estimate
    high = max(int(estimate.ram_high), int(estimate.ram_expected * q))
    return estimate if high == estimate.ram_high else replace(estimate, ram_high=high)
