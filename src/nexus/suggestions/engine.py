"""Collect, re-estimate, filter and rank suggestions (rules in ``rules.py``).

Pre-registered filters (docs/benchmarks/phase5-preregistration.md, B2): a suggestion is shown
only if its predicted saving is meaningful (>= 20% of the original expected peak AND >= 64 MiB),
the re-estimate is not a low-confidence fallback, and the re-estimated ``high`` is not above the
original ``high``. Ranking: predicted saving, then least semantic change.
"""

from __future__ import annotations

import ast
import logging
import os
from collections.abc import Collection, Mapping
from dataclasses import replace
from typing import Any

from nexus.analyzer import DetectedOp, analyze_cell, strip_magics
from nexus.failsafe import Deadline
from nexus.state import Inspection
from nexus.suggestions import rules as rules_mod
from nexus.suggestions.base import SEMANTICS, Context, Suggestion, SuggestionRule
from nexus.suggestions.reestimate import reestimate

log = logging.getLogger("nexus")

MIN_SAVING_FRAC = 0.20
MIN_SAVING_BYTES = 64 * 2**20
CONFIDENCE_FLOOR = 0.30


def _in_tree(tree: ast.Module, op: DetectedOp) -> DetectedOp | None:
    """``op`` with its node replaced by the same-position node of ``tree`` (the analyzer parses its own copy)."""
    key = tuple(
        getattr(op.node, a, None) for a in ("lineno", "col_offset", "end_lineno", "end_col_offset")
    )
    for node in ast.walk(tree):
        if type(node) is type(op.node) and key == tuple(
            getattr(node, a, None) for a in ("lineno", "col_offset", "end_lineno", "end_col_offset")
        ):
            return replace(op, node=node)
    return None


def default_rules(enable: Collection[str] = ()) -> list[SuggestionRule]:
    """Rules that are on by default plus those named in ``enable`` (explicit opt-in)."""
    return [cls() for cls in rules_mod.RULES if cls.enabled_by_default or cls.name in enable]


def env_enabled_rules() -> frozenset[str]:
    """Rule names opted in through ``NEXUS_ENABLE_RULES`` (comma-separated)."""
    raw = os.environ.get("NEXUS_ENABLE_RULES", "")
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def meaningful(saving: int, before_expected: int) -> bool:
    return saving >= MIN_SAVING_BYTES and saving >= MIN_SAVING_FRAC * max(before_expected, 1)


def _finish(s: Suggestion, op: DetectedOp, state: Inspection) -> Suggestion | None:
    """Re-estimate ``s``; None when it must not be shown."""
    ch = s.virtual
    if (
        ch.descriptor_saving is not None
    ):  # no frozen model for the avoided allocation (copy, delete)
        # Only the 64 MiB floor is applied here; the 20% fraction cannot be checked because no
        # peak is estimated for the unmodified cell (Amendment 2). saving_frac stays 0.0 = "not estimated".
        saving = int(ch.descriptor_saving)
        if saving < MIN_SAVING_BYTES:
            return None
        return replace(s, saving_bytes=saving, saving_frac=0.0, estimate_source="descriptor")
    pair = reestimate(op, state, ch)
    if pair is None:
        return None
    before, after = pair
    if after.confidence < CONFIDENCE_FLOOR or after.ram_high > before.ram_high:
        return None
    saving = before.ram_expected - after.ram_expected
    if not meaningful(saving, before.ram_expected):
        return None
    return replace(
        s, before=before, after=after, saving_bytes=saving,
        saving_frac=saving / max(before.ram_expected, 1), op_name=op.name,
    )  # fmt: skip


def suggest(
    source: str,
    namespace: Mapping[str, Any],
    inspection: Inspection,
    ops: list[DetectedOp] | None = None,
    *,
    rules: list[SuggestionRule] | None = None,
    enable: Collection[str] = (),
    budget_s: float = 3.0,
    keep_hidden: bool = False,
) -> list[Suggestion]:
    """Ranked, re-estimated suggestions for a cell; never raises, never runs the cell.

    ``keep_hidden`` (evaluation only) also returns the candidates the filters removed. ``enable``
    names rules that are off by default and are opted in (plus ``NEXUS_ENABLE_RULES``).
    """
    try:
        if strip_magics(source) != source:
            return []  # magics are rewritten by the analyzer; patching the text would be unsafe
        tree = ast.parse(source)
        deadline = Deadline(budget_s)
        ops = ops if ops is not None else analyze_cell(source, namespace, deadline)
    except Exception:
        return []
    out: list[Suggestion] = []
    active = rules if rules is not None else default_rules(set(enable) | env_enabled_rules())
    ops = [m for m in (_in_tree(tree, o) for o in ops) if m is not None]
    for op in ops:
        for rule in active:
            try:
                if not rule.applies(op, inspection):
                    continue
                ctx = Context(source=source, tree=tree, op=op, inspection=inspection,
                              namespace=namespace, deadline=deadline, all_ops=ops)  # fmt: skip
                s = rule.propose(ctx)
                done = _finish(s, op, inspection) if s is not None else None
                if done is not None and (done.shown or keep_hidden):
                    out.append(done)
            except Exception:
                log.debug("nexus: suggestion rule %s failed", rule.name, exc_info=True)
    out.sort(key=lambda s: (not s.shown, -s.saving_bytes, SEMANTICS.index(s.semantics)))
    return out
