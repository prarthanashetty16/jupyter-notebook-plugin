"""Dtype rules: downcast numeric columns, low-cardinality text -> category, key dtype.

All three rewrite the operand inline (``df`` -> ``df.astype({...})``): the variable itself is
never changed, but ``astype`` with a dict copies the whole frame, so the re-estimate charges that
copy (``VirtualChange.temp_bytes``). Whether the change is worth it is the estimator's call.

Labels: floats -> float32 is ``changes_precision``; narrower ints and ``category`` are
``changes_dtype`` (values equal, result dtypes differ; never ``preserving``, because the
pre-registered check compares dtypes too). Integer narrowing is proved with the exact min / max of
the live column, so values never overflow.
"""

from __future__ import annotations

import ast

import pandas as pd

from nexus.suggestions import patch
from nexus.suggestions.base import (
    CHANGES_DTYPE,
    CHANGES_PRECISION,
    Context,
    Suggestion,
    SuggestionRule,
    VirtualChange,
)
from nexus.suggestions.liveness import cell_is_analysable
from nexus.suggestions.rules._common import (
    call_receiver,
    literal_cols,
    live_frame,
    merge_operands,
)
from nexus.suggestions.virtual import (
    ColumnProfile,
    profile_frame,
    smallest_signed_int,
    virtual_frame,
)

CATEGORY_MAX_DISTINCT_SHARE = 0.5
FRAME_OPS = ("groupby", "merge", "pandas.merge", "sort_values", "drop_duplicates")


def operand_names(ctx: Context) -> list[ast.Name]:
    op = ctx.op
    if op.name in ("merge", "pandas.merge"):
        both = merge_operands(op)
        return list(both) if both else []
    recv = call_receiver(op)
    return [recv] if recv is not None else []


def key_columns(ctx: Context) -> set[str]:
    """Literal key columns of the operation (``on`` / ``by`` / ``subset``)."""
    op = ctx.op
    cols: set[str] = set()
    for key in ("on", "by", "subset", "left_on", "right_on"):
        cols |= set(literal_cols(op.kwargs.get(key)) or [])
    if op.args and op.name in ("groupby", "sort_values"):
        cols |= set(literal_cols(op.args[0]) or [])
    return cols


def _build(
    ctx: Context, rule: str, title: str, plan: dict[str, dict[str, str]], label: str, detail: str
) -> Suggestion | None:
    """Edit every operand in ``plan`` (name -> {column: dtype}) and build the virtual state."""
    edits, frames, temp, parts = [], {}, 0, []
    for node in operand_names(ctx):
        retype = plan.get(node.id)
        if not retype:
            continue
        live = live_frame(ctx, node.id)
        if live is None:
            return None
        df, desc = live
        profs = profile_frame(df, None, ctx.deadline)
        if len(profs) != len(df.columns):
            return None
        new = virtual_frame(desc, profs, retype=retype)
        frames[node.id] = new
        temp += new.moved_bytes
        mapping = ", ".join(f"{c!r}: {t!r}" for c, t in retype.items())
        edits.append((node, f"{node.id}.astype({{{mapping}}})"))
        parts.append(f"{node.id}: " + ", ".join(f"{c} -> {t}" for c, t in retype.items()))
    modified = patch.replace_nodes(ctx.source, edits) if edits else None
    if modified is None:
        return None
    return Suggestion(
        rule=rule,
        title=title,
        explanation="; ".join(parts),
        original_source=ctx.source,
        modified_source=modified,
        semantics=label,
        semantics_detail=detail,
        virtual=VirtualChange(frames=frames, temp_bytes=temp),
    )


def _narrow(p: ColumnProfile) -> str | None:
    if p.is_int and p.lo is not None and p.hi is not None:
        target = smallest_signed_int(int(p.lo), int(p.hi))
        return target if target and target != p.dtype else None
    if p.is_float and p.dtype == "float64":
        return "float32"
    return None


class DowncastRule(SuggestionRule):
    name = "downcast_numeric"
    ops = FRAME_OPS

    def propose(self, ctx: Context) -> Suggestion | None:  # noqa: C901
        if cell_is_analysable(ctx.tree):
            return None
        plan: dict[str, dict[str, str]] = {}
        for node in operand_names(ctx):
            live = live_frame(ctx, node.id)
            if live is None:
                return None
            df = live[0]
            num = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c].dtype)]
            profs = profile_frame(df, num, ctx.deadline)
            keys = key_columns(ctx)
            moves = {c: t for c, p in profs.items() if c not in keys and (t := _narrow(p))}
            if moves:
                plan[node.id] = moves
        if not plan:
            return None
        floats = any(t == "float32" for m in plan.values() for t in m.values())
        label = CHANGES_PRECISION if floats else CHANGES_DTYPE
        detail = (
            "float64 -> float32 keeps about 7 significant digits (sums and means can differ in the "
            "last digits); narrower integers hold exactly the same values but the result columns "
            "have the new dtype"
            if floats
            else "values are identical (the exact min / max of each column fits); the result "
            "columns have the narrower dtype"
        )
        return _build(
            ctx, self.name, "use narrower numeric dtypes for the operands", plan, label, detail
        )


class CategoryRule(SuggestionRule):
    name = "text_to_category"
    ops = FRAME_OPS

    def propose(self, ctx: Context) -> Suggestion | None:  # noqa: C901
        if cell_is_analysable(ctx.tree):
            return None
        plan: dict[str, dict[str, str]] = {}
        keys = key_columns(ctx)
        for node in operand_names(ctx):
            live = live_frame(ctx, node.id)
            if live is None:
                return None
            df = live[0]
            text = [
                c
                for c in df.columns
                if c not in keys
                and (df[c].dtype == object or pd.api.types.is_string_dtype(df[c].dtype))
            ]
            profs = profile_frame(df, text, ctx.deadline)
            moves = {
                c: "category"
                for c, p in profs.items()
                if p.is_text and (p.distinct or p.n_rows) < CATEGORY_MAX_DISTINCT_SHARE * p.n_rows
            }
            if moves:
                plan[node.id] = moves
        if not plan:
            return None
        return _build(
            ctx,
            self.name,
            "store repeated text columns as category",
            plan,
            CHANGES_DTYPE,
            "values are identical; the columns have dtype category in the result (some operations "
            "behave differently on categoricals, e.g. groupby on them or comparisons of unordered "
            "categories)",
        )


class KeyDtypeRule(SuggestionRule):
    name = "key_dtype"
    ops = ("sort_values", "merge", "pandas.merge")

    def propose(self, ctx: Context) -> Suggestion | None:  # noqa: C901
        if cell_is_analysable(ctx.tree):
            return None
        keys = key_columns(ctx)
        if not keys:
            return None
        names = operand_names(ctx)
        if not names:
            return None
        profs_by: dict[str, dict[str, ColumnProfile]] = {}
        for node in names:
            live = live_frame(ctx, node.id)
            if live is None or not keys <= set(live[0].columns):
                return None
            profs_by[node.id] = profile_frame(live[0], sorted(keys), ctx.deadline)
        plan: dict[str, dict[str, str]] = {}
        for k in sorted(keys):
            ps = [profs_by[n.id].get(k) for n in names]
            if any(p is None for p in ps):
                return None
            if all(p.is_int for p in ps):  # type: ignore[union-attr]
                lo = min(int(p.lo) for p in ps)  # type: ignore[union-attr, arg-type]
                hi = max(int(p.hi) for p in ps)  # type: ignore[union-attr, arg-type]
                target = smallest_signed_int(lo, hi)
                if target and any(p.dtype != target for p in ps):  # type: ignore[union-attr]
                    for n in names:
                        plan.setdefault(n.id, {})[k] = target
            elif ctx.op.name == "merge" or ctx.op.name == "pandas.merge":
                continue  # category keys on merge: object/category mismatches are left alone
            elif all(p.is_text for p in ps):  # type: ignore[union-attr]
                p = ps[0]
                assert p is not None
                if (p.distinct or p.n_rows) < CATEGORY_MAX_DISTINCT_SHARE * p.n_rows:
                    plan.setdefault(names[0].id, {})[k] = "category"
        if not plan:
            return None
        return _build(
            ctx,
            self.name,
            "use a compact dtype for the key column",
            plan,
            CHANGES_DTYPE,
            "key values are identical (integer keys are narrowed only to a dtype that holds the "
            "exact min / max); the key column has the new dtype in the result",
        )
