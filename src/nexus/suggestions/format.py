"""Plain-text rendering of suggestions: what changes in the result, and how the saving was found.

Every suggestion states its semantics in words and says "no estimate of saving" when the frozen
models cannot give one (a descriptor-sized saving is the size of an avoided allocation, not a
predicted change of the cell's peak).
"""

from __future__ import annotations

from collections.abc import Sequence

from nexus.suggestions.base import SEMANTICS_WORDS, Suggestion


def _mib(n: int | float) -> str:
    return f"{n / 2**20:,.0f} MiB"


def saving_line(sg: Suggestion) -> str:
    """One line on the saving; "no estimate of saving" when no model re-estimated the peak."""
    if sg.before is not None and sg.after is not None:
        return (
            f"predicted peak {_mib(sg.before.ram_expected)} -> {_mib(sg.after.ram_expected)} "
            f"(range {_mib(sg.after.ram_low)}-{_mib(sg.after.ram_high)}, Tier 0 re-estimate; "
            f"predicted saving about {sg.saving_frac:.0%})"
        )
    if sg.kind == "headroom":
        return (
            f"no estimate of saving in this cell's peak; frees about {_mib(sg.saving_bytes)} "
            "of memory for later cells (exact size)"
        )
    return (
        "no estimate of saving: the effect on this cell's peak is not modelled "
        f"(it avoids a copy of about {_mib(sg.saving_bytes)})"
    )


def describe(i: int, sg: Suggestion) -> list[str]:
    """Lines for suggestion number ``i``."""
    lines = [
        f"[{i}] {sg.title}  [{sg.semantics}]",
        f"    {sg.explanation}",
        f"    {saving_line(sg)}",
        f"    what changes: {SEMANTICS_WORDS.get(sg.semantics, sg.semantics)}",
        f"    detail: {sg.semantics_detail}",
    ]
    lines += [f"    note: {n}" for n in sg.notes]
    return lines


def describe_all(suggestions: Sequence[Suggestion]) -> list[str]:
    out: list[str] = []
    for i, sg in enumerate(suggestions, 1):
        out += describe(i, sg)
    return out
