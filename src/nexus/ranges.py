"""How a Tier 1 estimate's RAM range is built from its expected value.

The policy was chosen by a criterion fixed before any number was computed on the re-run
predictions (``benchmarks/range_policy.py``): above_high <= 3% per point and <= 5% per
configuration under leave-one-configuration-out, then the narrowest mean width. The constants below
are the winner's per-model multipliers of ``expected``, fitted on every development point
(including the former val-v3) and NOT re-tuned afterwards; val-v4 is the held-out check.

``TIER1_BANDS`` maps a model name to ``(low_multiplier, high_multiplier)``; an empty table means
"keep the range the model emits" (candidate A).

Phase 4b.3: val-v4 failed the criterion (above_high 5.4% per point; 3 astype points were a bug, fixed,
and 2 merge points are a model limitation that is not understood), so the pre-registered fallback C
is adopted GLOBALLY: ``[Tier 1 low, Tier 1 expected, Tier 0 high]``. On the development data the
criterion's own winner is still A (narrower and admissible); C is chosen by decision because it is the
only candidate with 0 points above ``high`` on all 284 development points, at a width cost of x2.9
(x9 for merge). The per-operation alternatives in docs/benchmarks/tier1-v3 are hypotheses that need
a fresh split.
"""

from __future__ import annotations

from dataclasses import replace

from nexus.models.base import Estimate

# model name -> (low, high) multipliers of the Tier 1 expected RAM; filled by the selection run
TIER1_BANDS: dict[str, tuple[float, float]] = {}
# True: the upper end never exceeds Tier 0's high (candidates C / D), False: no ceiling
CEILING_AT_TIER0_HIGH = False
# True: the upper end IS Tier 0's high (candidate C)
UPPER_IS_TIER0_HIGH = True


def apply(model: str, estimate: Estimate, tier0: Estimate | None) -> Estimate:
    """Return ``estimate`` with its RAM range rebuilt by the selected policy (Tier 1 only)."""
    if estimate.tier < 1:
        return estimate
    exp = estimate.ram_expected
    low, high = estimate.ram_low, estimate.ram_high
    if UPPER_IS_TIER0_HIGH and tier0 is not None:
        high = max(tier0.ram_high, exp)
    elif model in TIER1_BANDS:
        m_lo, m_hi = TIER1_BANDS[model]
        low, high = int(exp * min(m_lo, 1.0)), int(exp * max(m_hi, 1.0))
        if CEILING_AT_TIER0_HIGH and tier0 is not None:
            high = max(min(high, tier0.ram_high), exp)
    return replace(estimate, ram_low=min(low, exp), ram_high=max(high, exp))
