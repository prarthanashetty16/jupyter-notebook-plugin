"""Rules about variables, not operations: avoid a temporary ``.copy()``, delete unreferenced data.

Neither has a frozen operation model: the saving is the exact size of the avoided allocation or of
the freed variable (descriptor sizes), shown without a re-estimated range and ranked below no one;
the thresholds still apply. Delete suggestions free *headroom*, never lower the cell's own peak,
and always warn that other cells may use the variables.
"""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd

from nexus.state import FrameDescriptor
from nexus.suggestions import patch
from nexus.suggestions.base import (
    CHANGES_RESULTS,
    PRESERVING,
    Context,
    Suggestion,
    SuggestionRule,
    VirtualChange,
)
from nexus.suggestions.liveness import cell_is_analysable, parents
from nexus.suggestions.rules._common import call_receiver

# methods that always return NEW data (never a view of the receiver) when called without inplace
FRESH_RESULT_METHODS = frozenset(
    {"sort_values", "groupby", "merge", "drop_duplicates", "describe", "nunique", "value_counts",
     "sum", "mean", "min", "max", "count"}
)  # fmt: skip
MIN_DELETE_BYTES = 64 * 2**20


class CopyAvoidRule(SuggestionRule):
    """``x.copy().method(...)``: the copy is a temporary consumed by a non-mutating call."""

    name = "avoid_copy"
    ops = ("copy",)

    def propose(self, ctx: Context) -> Suggestion | None:
        op, call = ctx.op, ctx.op.node
        if (
            not isinstance(call, ast.Call)
            or call.args
            or call.keywords
            or cell_is_analysable(ctx.tree)
        ):
            return None
        recv = call_receiver(op)
        if recv is None:
            return None
        par = parents(ctx.tree)
        attr = par.get(call)
        outer = par.get(attr) if attr is not None else None
        if not (
            isinstance(attr, ast.Attribute) and attr.value is call and isinstance(outer, ast.Call)
        ):
            return None
        if outer.func is not attr or attr.attr not in FRESH_RESULT_METHODS:
            return None
        if any(k.arg == "inplace" or k.arg is None for k in outer.keywords):
            return None
        desc = ctx.inspection.variables.get(recv.id)
        if not isinstance(desc, FrameDescriptor):
            return None
        s = _copy_span(ctx.source, call, recv)
        if s is None:
            return None
        return Suggestion(
            rule=self.name,
            title=f"drop the temporary {recv.id}.copy()",
            explanation=(
                f"{recv.id}.copy() makes a full copy only to call .{attr.attr}(...) on it, which "
                f"already returns new data; the copy costs about {desc.moved_bytes / 2**20:,.0f} MiB."
            ),
            original_source=ctx.source,
            modified_source=s,
            semantics=PRESERVING,
            semantics_detail=(
                f".{attr.attr}() does not modify its receiver and returns a new object, so {recv.id} "
                "and the result are unchanged"
            ),
            virtual=VirtualChange(descriptor_saving=desc.moved_bytes),
        )


def _copy_span(source: str, call: ast.Call, recv: ast.Name) -> str | None:
    """Replace ``x.copy()`` by ``x``."""
    return patch.replace_nodes(source, [(call, recv.id)])


class DeleteVariablesRule(SuggestionRule):
    """Large variables the cell does not mention: free them (suggestion only)."""

    name = "delete_unreferenced"

    def applies(self, op, state) -> bool:  # type: ignore[no-untyped-def]
        return True

    def propose(self, ctx: Context) -> Suggestion | None:
        if ctx.op is not ctx.all_ops[0]:
            return None  # one suggestion per cell
        mentioned = {n.id for n in ast.walk(ctx.tree) if isinstance(n, ast.Name)}
        groups: dict[int, tuple[list[str], int]] = {}
        for name, obj in list(ctx.namespace.items()):
            if name.startswith("_") or name in mentioned:
                continue
            size = _size(obj)
            if size < MIN_DELETE_BYTES:
                continue
            names, _ = groups.get(id(obj), ([], size))
            groups[id(obj)] = (names + [name], size)
        if not groups:
            return None
        mentioned_ids = {id(ctx.namespace[n]) for n in mentioned if n in ctx.namespace}
        picks = sorted(
            ((names, size) for key, (names, size) in groups.items() if key not in mentioned_ids),
            key=lambda t: -t[1],
        )[:3]
        if not picks:
            return None
        names = sorted(n for ns, _ in picks for n in ns)
        total = sum(size for _, size in picks)
        modified = ctx.source.rstrip("\n") + "\ndel " + ", ".join(names) + "\n"
        return Suggestion(
            rule=self.name,
            kind="headroom",
            title=f"free {', '.join(names)} (not used by this cell)",
            explanation=(
                f"{', '.join(names)} hold about {total / 2**20:,.0f} MiB and this cell does not use "
                "them. Deleting them returns that memory to the process (not always to the OS)."
            ),
            original_source=ctx.source,
            modified_source=modified,
            semantics=CHANGES_RESULTS,
            semantics_detail=(
                "the variables are removed from the kernel: any other cell that uses them will raise "
                "NameError. History (Out[n], _) may keep a reference alive and block the release"
            ),
            virtual=VirtualChange(descriptor_saving=total),
            notes=("frees headroom for later cells; it does not lower this cell's own peak",),
        )


def _size(obj: object) -> int:
    try:
        if isinstance(obj, np.ndarray):
            return int(obj.nbytes)
        if isinstance(obj, pd.DataFrame):
            return int(obj.memory_usage(index=True).sum())
        if isinstance(obj, pd.Series):
            return int(obj.memory_usage(index=True))
    except Exception:
        return 0
    return 0
