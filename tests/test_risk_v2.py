"""Phase 7b risk v2 (C3): read_csv / merge WARN on their own Tier 1 high when statistics ran; a fallback
keeps Tier 0's high; HIGH_RISK and the display are unchanged; UNKNOWN names the uncovered operation."""

from __future__ import annotations

import pandas as pd

from nexus.models.base import Estimate
from nexus.pipeline import OpEstimate, Pipeline
from nexus.risk import RiskClass, assess, classify, warn_high_estimate

MIB = 2**20


def _item(model: str, used: bool, tier: int = 1, own: int | None = 200 * MIB) -> OpEstimate:
    from nexus.analyzer import analyze_cell

    op = analyze_cell("x = df.sort_values('a')", {"df": pd.DataFrame({"a": [1]})})[0]
    est = Estimate(ram_low=50 * MIB, ram_expected=100 * MIB, ram_high=2000 * MIB, time_low=0.1,
                   time_expected=0.2, time_high=0.3, confidence=0.7, tier=tier)  # fmt: skip
    features: dict = {"tier1": {"used": used}}
    if own is not None:
        features["tier1_own_ram_high"] = own
    return OpEstimate(op=op, model=model, estimate=est, features=features)


def test_own_tier1_high_only_for_read_csv_and_merge_with_statistics():
    assert warn_high_estimate(_item("read_csv", True)).ram_high == 200 * MIB
    assert warn_high_estimate(_item("merge", True)).ram_high == 200 * MIB
    assert warn_high_estimate(_item("groupby", True)).ram_high == 2000 * MIB  # other models: policy B
    # statistics did not run (fallback to Tier 0): Tier 0's high stays
    assert warn_high_estimate(_item("merge", False, tier=0)).ram_high == 2000 * MIB
    assert warn_high_estimate(_item("read_csv", False, tier=0, own=None)).ram_high == 2000 * MIB


def test_warn_uses_the_warn_high_and_high_risk_is_unchanged():
    e = _item("merge", True).estimate
    head = 1000 * MIB
    assert classify([e], headroom=head).risk is RiskClass.WARN  # policy-B high 2000 > 850
    assert classify([e], headroom=head, warn_high=200 * MIB).risk is RiskClass.OK
    assert classify([e], headroom=90 * MIB, warn_high=200 * MIB).risk is RiskClass.HIGH_RISK


def test_unknown_names_the_uncovered_operation():
    df = pd.DataFrame({"a": range(1000), "b": range(1000)})
    rep = Pipeline(tier=1).run("y = df.sort_values('a')\nz = df['a'].value_counts()", {"df": df})
    assert len(rep.ops) > len(rep.estimates)  # value_counts has no model (second attempt failed)
    r = classify(
        [e.estimate for e in rep.estimates], headroom=10**12, uncovered=1,
        uncovered_ops="`df['a'].value_counts()`",
    )  # fmt: skip
    assert r.risk is RiskClass.UNKNOWN and "no estimate for `df['a'].value_counts()`" in r.reason
    full = assess(rep)
    assert full is not None
    assert full.risk is not RiskClass.UNKNOWN or "df['a'].value_counts()" in full.reason
