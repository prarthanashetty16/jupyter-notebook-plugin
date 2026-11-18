"""The adaptive controller: when to spend a dry run, and what to take from it.

Implements EXACTLY the rules pre-registered in ``docs/benchmarks/phase4d-preregistration.md``
(committed before any Phase 4d number was computed). Summary:

* RAM: Tier 1 (policy B) is the estimate; a Tier 2 RAM fit may only RAISE the high bound
  (``high = max(high_tier1, expected_tier2)``), never lower anything.
* Time: Tier 2's range for read_csv, astype and merge; Tier 2's range with the high bound x1.5 for
  groupby (1 / the dev bias 0.667); every other operation keeps the Tier 0 / 1 time.
* Escalation only on a trigger ((a) RAM high > 50% of free RAM, (b) Tier 1 time >= 5 s, (c) Tier 1
  fell back to Tier 0 on its time budget and Tier 0's range is wide), only if the cell passes the
  Tier 2 safety analyzer, and only if the dry run fits the memory budget (25% of the free RAM).
  Everything else FAILS CLOSED: the Tier 1 estimate is kept and the reason recorded.
* Every returned Estimate says in ``note`` which tier produced it and why; ``diagnostics["controller"]``
  holds triggers, budget figures and the rules applied.

The controller never raises and never touches the user's objects; the dry run itself lives in a
subprocess sandbox (``nexus.dryrun``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from nexus import dryrun
from nexus.dryrun_safety import SafetyVerdict, analyze_safety
from nexus.dryrun_sample import LARGEST_FRACTION, ROW_CAP
from nexus.models.base import Estimate

log = logging.getLogger("nexus")

MIB = 2**20
TIME_FROM_TIER2 = frozenset({"read_csv", "astype", "merge"})
GROUPBY_HIGH_MULTIPLIER = (
    1.5  # 1 / 0.667, the dev bias of Tier 2's groupby time (pre-registration R2)
)


@dataclass(frozen=True)
class ControllerConfig:
    """Constants fixed by the pre-registration (R0-R3)."""

    budget_s: float = 60.0
    ram_trigger_fraction: float = 0.5  # (a)
    min_run_s: float = 5.0  # (b)
    wide_range: float = 1.0  # (c)
    memory_fraction: float = 0.25  # dry-run budget as a share of the free RAM
    child_interpreter_bytes: int = 200 * MIB
    child_cap_max: int = 8 * 2**30
    groupby_high_multiplier: float = GROUPBY_HIGH_MULTIPLIER


@dataclass(frozen=True)
class Decision:
    """What the controller decided for one cell (also recorded in the diagnostics)."""

    escalated: bool = False
    triggers: tuple[str, ...] = ()
    reason: str = ""  # why no dry run / what failed ("" when a dry run produced something)
    budget_bytes: float | None = None
    need_bytes: float | None = None
    rules: tuple[str, ...] = ()
    overhead_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "escalated": self.escalated, "triggers": list(self.triggers), "reason": self.reason,
            "budget_bytes": self.budget_bytes, "need_bytes": self.need_bytes,
            "rules": list(self.rules), "overhead_s": self.overhead_s, **self.extra,
        }  # fmt: skip


def triggers(est: Estimate, tier0: Estimate | None, features: Mapping[str, Any], free_ram: float | None,
             cfg: ControllerConfig) -> list[str]:  # fmt: skip
    """The pre-registered escalation triggers that hold for this estimate."""
    out = []
    if free_ram is not None and est.ram_high > cfg.ram_trigger_fraction * free_ram:
        out.append("a:ram_high_over_half_of_free_ram")
    if est.time_expected >= cfg.min_run_s:
        out.append("b:expected_time_over_5s")
    reason = str((features.get("tier1") or {}).get("reason", ""))
    base = tier0 or est
    if est.tier == 0 and reason == "time budget":
        if (base.ram_high - base.ram_low) / max(base.ram_expected, 1) >= cfg.wide_range:
            out.append("c:statistics_exceeded_the_analysis_budget")
    return out


def dryrun_need_bytes(
    input_bytes: float, rows: float | None, ram_high: float, cfg: ControllerConfig
) -> float:
    """Expected peak of the dry run's child: interpreter + the sample fraction of (inputs + Tier 1 RAM high)."""
    f = LARGEST_FRACTION if not rows else min(LARGEST_FRACTION, ROW_CAP / max(rows, 1.0))
    return cfg.child_interpreter_bytes + f * (input_bytes + ram_high)


class Controller:
    """Decides escalation and merges a dry run into a Tier 1 estimate. Never raises."""

    def __init__(self, config: ControllerConfig | None = None,
                 dryrun_fn: Callable[..., dryrun.DryRunResult] | None = None,
                 safety_fn: Callable[[str, Mapping[str, Any]], SafetyVerdict] | None = None) -> None:  # fmt: skip
        self.config = config or ControllerConfig()
        self._dryrun = dryrun_fn or dryrun.run_dryrun
        self._safety = safety_fn or analyze_safety

    def refine(  # noqa: C901
        self, op_name: str, estimate: Estimate, tier0: Estimate | None, features: Mapping[str, Any],
        source: str, namespace: Mapping[str, Any], free_ram: float | None, input_bytes: float,
        rows: float | None,
    ) -> tuple[Estimate, dict[str, Any]]:  # fmt: skip
        """Return ``(estimate, controller_info)``; the estimate is Tier 1's unless a rule says otherwise."""
        cfg = self.config
        try:
            trig = triggers(estimate, tier0, features, free_ram, cfg)
            if not trig:
                return self._kept(estimate, Decision(reason="no trigger"), "no trigger")
            verdict = self._safety(source, namespace)
            if not verdict.safe or verdict.recipe is None:
                why = "unsafe cell: " + "; ".join(verdict.reasons)
                return self._kept(estimate, Decision(triggers=tuple(trig), reason=why), why)
            if not dryrun.matching_op(verdict.recipe.kind, op_name):
                why = (
                    f"the dry-run recipe ({verdict.recipe.kind}) is not this operation ({op_name})"
                )
                return self._kept(estimate, Decision(triggers=tuple(trig), reason=why), why)
            if free_ram is None or free_ram <= 0:
                why = "fail closed: free RAM unknown"
                return self._kept(estimate, Decision(triggers=tuple(trig), reason=why), why)
            budget = cfg.memory_fraction * free_ram
            need = dryrun_need_bytes(input_bytes, rows, estimate.ram_high, cfg)
            if need > budget:
                why = (f"fail closed: free RAM too low for a dry run (needs ~{need / MIB:.0f} MiB, "
                       f"budget {budget / MIB:.0f} MiB = {cfg.memory_fraction:.0%} of {free_ram / MIB:.0f} MiB free)")  # fmt: skip
                return self._kept(
                    estimate,
                    Decision(
                        triggers=tuple(trig), reason=why, budget_bytes=budget, need_bytes=need
                    ),
                    why,
                )
            result = self._dryrun(source, namespace, budget_s=cfg.budget_s,
                                  child_mem_cap=int(min(budget, cfg.child_cap_max)))  # fmt: skip
            return self._merge(op_name, estimate, trig, budget, need, result)
        except Exception as exc:  # the controller must never break the cell
            log.debug("nexus: controller failed", exc_info=True)
            why = f"controller error ({type(exc).__name__}): Tier 1 kept"
            return self._kept(estimate, Decision(reason=why), why)

    # -- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def _kept(estimate: Estimate, decision: Decision, why: str) -> tuple[Estimate, dict[str, Any]]:
        info = decision.as_dict()
        note = f"Tier {estimate.tier} kept: {why}"
        return replace(estimate, note=(estimate.note + "; " if estimate.note else "") + note), info

    def _merge(self, op: str, est: Estimate, trig: list[str], budget: float, need: float,
               result: dryrun.DryRunResult) -> tuple[Estimate, dict[str, Any]]:  # fmt: skip
        cfg = self.config
        base = Decision(True, tuple(trig), result.reason, budget, need, overhead_s=result.overhead_s,
                        extra={"dryrun": result.diagnostics()})  # fmt: skip
        ram, tim = result.ram, result.time
        rules: list[str] = []
        low, exp, high = est.ram_low, est.ram_expected, est.ram_high
        if ram and ram.ok and ram.expected > high:  # R1: only ever raise the high bound
            high = int(ram.expected)
            rules.append("R1: RAM high raised to the Tier 2 expected value")
        t_low, t_exp, t_high = est.time_low, est.time_expected, est.time_high
        kind = dryrun.kind_of_op(op)
        if tim and tim.ok and kind in TIME_FROM_TIER2:
            t_low, t_exp, t_high = tim.low, tim.expected, tim.high
            rules.append(f"R2: time from Tier 2 ({kind})")
        elif tim and tim.ok and kind == "groupby_agg":
            t_low, t_exp, t_high = tim.low, tim.expected, tim.high * cfg.groupby_high_multiplier
            rules.append(f"R2: time from Tier 2 (groupby), high x{cfg.groupby_high_multiplier:g}")
        info = replace(base, rules=tuple(rules)).as_dict()
        if not rules:
            why = (
                result.reason
                or "the dry run changed nothing (no accepted fit for a rule that applies)"
            )
            return self._kept(est, replace(base, reason=why), why)
        note = f"Tier 2 used ({'; '.join(rules)}); triggers {', '.join(trig)}"
        new = replace(
            est, ram_low=low, ram_expected=exp, ram_high=max(high, exp),
            time_low=min(t_low, t_exp), time_expected=t_exp, time_high=max(t_high, t_exp),
            tier=2, note=(est.note + "; " if est.note else "") + note, diagnostics=info,
        )  # fmt: skip
        return new, info
