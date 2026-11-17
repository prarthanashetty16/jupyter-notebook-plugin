"""Which grid points may run under the memory cap, decided from NEXUS's own upper bound.

The harness kills a child whose TOTAL resident memory (inputs already loaded + the operation's
incremental peak) exceeds the cap. The old rule skipped a point when ``estimated input bytes x a
per-case factor`` exceeded the cap; a point could pass it and still be killed (the null-heavy
``drop_duplicates`` at 10M rows: planned 2.3 GB, killed at 2.7 GB).

The model-based rule: ``planned footprint = baseline + high``, where ``high`` is the upper end of
the tightest estimate available (Tier 1 when it used statistics, else Tier 0) and the baseline is
the resident set after loading the inputs, ``FIXED + FACTOR x estimated input bytes``. The two
constants come from the 218 development points with a measured baseline (least squares through
55 MiB + 1.017 x estimated input bytes; the 95th percentile of the residual is +23 MiB, the
maximum +44 MiB, hence 100 MiB). A point whose planned footprint exceeds the cap is skipped
(``skipped_cap``) with the reason recorded; no value is read from a protected group.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIB = 2**20
FIXED_BASELINE_BYTES = 100 * MIB  # interpreter + pandas + numpy + worker, with margin
INPUT_RESIDENT_FACTOR = 1.02  # resident bytes per estimated input byte (dev fit: 1.017)


@dataclass(frozen=True)
class Decision:
    skip: bool
    footprint_bytes: int
    high_bytes: int | None
    high_source: str  # "tier1", "tier0" or "none"
    reason: str


def baseline_bytes(est_input_bytes: int) -> int:
    return int(FIXED_BASELINE_BYTES + INPUT_RESIDENT_FACTOR * est_input_bytes)


def best_high(preds: dict[int, dict[str, Any]]) -> tuple[int | None, str]:
    """The upper end of the tightest estimate: Tier 1 if it used statistics, else Tier 0."""
    for tier in (1, 0):
        row = preds.get(tier)
        if not row or str(row.get("has_estimate")).lower() not in ("true", "1"):
            continue
        try:
            high = int(float(row["ram_high"]))
        except (KeyError, TypeError, ValueError):
            continue
        if tier == 1 and '"used": false' in str(row.get("features", "")).lower():
            continue  # Tier 1 fell back to Tier 0's features: its range is the Tier 0 one
        return high, f"tier{tier}"
    return None, "none"


def decide(est_input_bytes: int, preds: dict[int, dict[str, Any]], cap_bytes: int) -> Decision:
    """Skip when baseline + high exceeds the cap; without any estimate keep the old rule's verdict."""
    high, source = best_high(preds)
    base = baseline_bytes(est_input_bytes)
    if high is None:
        return Decision(False, base, None, source, "no estimate: static footprint rule only")
    total = base + high
    if total > cap_bytes:
        return Decision(
            True, total, high, source,
            f"planned footprint {total} B (baseline {base} + {source} high {high}) > cap {cap_bytes}",
        )  # fmt: skip
    return Decision(False, total, high, source, "fits")
