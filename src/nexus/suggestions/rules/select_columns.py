"""Drop columns the rest of the cell provably never reads, before a ``groupby`` or ``merge``.

Safe only when the cell consumes the result through a literal column selection (or a bound
result whose uses are all literal column reads). Binding the result keeps it visible to later
cells, which this analysis cannot see, so that case is labelled ``changes_results`` instead of
``preserving``. Anything not provable is refused.
"""

from __future__ import annotations

import ast

from nexus.suggestions import patch
from nexus.suggestions.base import (
    CHANGES_RESULTS,
    PRESERVING,
    Context,
    Suggestion,
    SuggestionRule,
    VirtualChange,
)
from nexus.suggestions.liveness import cell_is_analysable, column_uses
from nexus.suggestions.rules._common import (
    bound_target,
    call_receiver,
    literal_cols,
    live_frame,
    merge_operands,
    quote_list,
    result_use,
)
from nexus.suggestions.virtual import profile_frame, virtual_frame


class SelectColumnsRule(SuggestionRule):
    name = "select_columns"
    ops = ("groupby", "merge", "pandas.merge")

    def propose(self, ctx: Context) -> Suggestion | None:
        if cell_is_analysable(ctx.tree) or not isinstance(ctx.op.node, ast.Call):
            return None
        return self._groupby(ctx) if ctx.op.name == "groupby" else self._merge(ctx)

    def _groupby(self, ctx: Context) -> Suggestion | None:
        op, call = ctx.op, ctx.op.node
        assert isinstance(call, ast.Call)
        recv = call_receiver(op)
        by = (
            call.args[0]
            if call.args
            else next((k.value for k in call.keywords if k.arg == "by"), None)
        )
        keys = literal_cols(op.args[0] if op.args else op.kwargs.get("by"))
        if recv is None or not keys or by is None:
            return None
        kind, cols = result_use(ctx, call)
        if kind != "chain":  # groupby(...)["v"]: the selection is part of the same expression
            return None
        live = live_frame(ctx, recv.id)
        if live is None:
            return None
        df, desc = live
        need = set(keys) | set(cols)
        if not need <= set(df.columns):
            return None
        keep = [c for c in df.columns if c in need]
        if len(keep) == len(df.columns):
            return None
        profs = profile_frame(df, None, ctx.deadline)
        if len(profs) != len(df.columns):
            return None
        new = virtual_frame(desc, profs, keep=keep)
        modified = patch.replace_nodes(ctx.source, [(recv, f"{recv.id}[{quote_list(keep)}]")])
        if modified is None:
            return None
        return Suggestion(
            rule=self.name,
            title=f"select only the columns {recv.id}.groupby needs",
            explanation=(
                f"The cell only reads {sorted(need)} of {recv.id}'s {df.shape[1]} columns. Selecting "
                "them first keeps the other columns out of the grouping work."
            ),
            original_source=ctx.source,
            modified_source=modified,
            semantics=PRESERVING,
            semantics_detail=(
                f"the result is the same: the dropped columns are never read and {recv.id} itself "
                "is not changed"
            ),
            virtual=VirtualChange(frames={recv.id: new}, temp_bytes=new.moved_bytes),
        )

    def _merge(self, ctx: Context) -> Suggestion | None:  # noqa: C901
        op, call = ctx.op, ctx.op.node
        assert isinstance(call, ast.Call)
        operands = merge_operands(op)
        keys = literal_cols(op.kwargs.get("on"))
        if operands is None or not keys:
            return None
        if any(
            k in op.kwargs
            for k in ("left_on", "right_on", "left_index", "right_index", "suffixes", "indicator")
        ):
            return None
        kind, used = result_use(ctx, call)
        if kind == "chain":
            result_cols = used
            label = PRESERVING
            detail = (
                "the result expression selects its columns by name; the dropped columns never "
                "appear in it"
            )
        elif kind == "bound":
            u = column_uses(ctx.tree, used, bound_target(ctx, call))
            if not u.proven or not u.columns:
                return None
            result_cols = u.columns
            label = CHANGES_RESULTS
            detail = (
                f"`{used}` will contain only the key and the columns this cell reads; later cells "
                "that use its other columns will fail or change"
            )
        else:
            return None
        left_n, right_n = operands
        ll, rr = live_frame(ctx, left_n.id), live_frame(ctx, right_n.id)
        if ll is None or rr is None:
            return None
        (ldf, ldesc), (rdf, rdesc) = ll, rr
        lcols, rcols = set(ldf.columns), set(rdf.columns)
        if not set(keys) <= lcols & rcols or (lcols & rcols) - set(keys):
            return None  # missing keys, or shared non-key columns that suffixes would rename
        wanted = set(result_cols) - set(keys)
        if not wanted <= (lcols | rcols):
            return None
        edits, frames, temp = [], {}, 0
        for node, df, desc, cols in ((left_n, ldf, ldesc, lcols), (right_n, rdf, rdesc, rcols)):
            keep = [c for c in df.columns if c in set(keys) | (wanted & cols)]
            if len(keep) == len(df.columns):
                continue
            profs = profile_frame(df, None, ctx.deadline)
            if len(profs) != len(df.columns):
                return None
            frames[node.id] = virtual_frame(desc, profs, keep=keep)
            temp += frames[node.id].moved_bytes
            edits.append((node, f"{node.id}[{quote_list(keep)}]"))
        modified = patch.replace_nodes(ctx.source, edits) if edits else None
        if modified is None:
            return None
        return Suggestion(
            rule=self.name,
            title="merge only the columns the cell reads",
            explanation=(
                f"The cell reads {sorted(result_cols)} of the merge result; the other columns of "
                "both frames are carried through the merge for nothing."
            ),
            original_source=ctx.source,
            modified_source=modified,
            semantics=label,
            semantics_detail=detail,
            virtual=VirtualChange(frames=frames, temp_bytes=temp),
        )
