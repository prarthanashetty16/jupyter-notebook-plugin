"""``read_csv`` rules: ``usecols`` (only columns the cell reads) and ``chunksize``.

``usecols`` needs the column set the cell reads, proved by ``liveness.column_uses`` on the
variable the call is bound to (or a literal subscript of the call itself). Binding keeps the
frame visible to later cells, so that case is ``changes_results``; only a call consumed inside
the cell by a literal column selection is ``preserving``. ``chunksize`` always changes what the
call returns (an iterator), so it is ``changes_results`` and the user must adapt the code after it.

``dtype=`` is NOT proposed: the frozen read_csv model has no dtype feature, so a saving could not
be re-estimated and an un-re-estimable suggestion is never shown (pre-registration, B2).
"""

from __future__ import annotations

import ast
import csv
import os

from nexus.state import FileDescriptor
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
from nexus.suggestions.rules._common import bound_target, quote_list, result_use

SAMPLE_LINES = 4000
CHUNK_FRACTION = 0.1
MIN_CHUNK_ROWS = 100_000
BLOCKING = frozenset(
    {"usecols", "chunksize", "iterator", "nrows", "dtype", "index_col", "names", "header"}
)


def _csv_path(ctx: Context) -> str | None:
    op = ctx.op
    values = list(op.args[:1]) + [v for k, v in op.kwargs.items() if k in ("filepath_or_buffer",)]
    for v in values:
        if isinstance(v, str) and not type(v).__name__ == "Expr" and v in ctx.inspection.files:
            return v
    return None


def _profile(path: str) -> tuple[list[str], list[int], int] | None:
    """Header, summed characters per column over the sampled lines, and lines sampled."""
    try:
        with open(os.path.expanduser(path), newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            sums = [0] * len(header)
            n = 0
            for row in reader:
                if len(row) != len(header):
                    return None
                for i, cell in enumerate(row):
                    sums[i] += len(cell) + 1
                n += 1
                if n >= SAMPLE_LINES:
                    break
    except (OSError, UnicodeDecodeError, StopIteration, csv.Error):
        return None
    return (header, sums, n) if n else None


class ReadCsvRule(SuggestionRule):
    name = "read_csv_options"
    ops = ("pandas.read_csv",)

    def propose(self, ctx: Context) -> Suggestion | None:  # noqa: C901
        op, call = ctx.op, ctx.op.node
        assert isinstance(call, ast.Call)
        path = _csv_path(ctx)
        if path is None or BLOCKING & set(op.kwargs) or len(op.args) > 1:
            return None
        prof = _profile(path)
        if prof is None:
            return None
        header, sums, n_sample = prof
        fdesc = ctx.inspection.files[path]
        found = self._usecols(ctx, call, header, sums, path, fdesc)
        if found is not None:
            return found
        return self._chunksize(ctx, call, header, sums, n_sample, path, fdesc)

    def _usecols(
        self,
        ctx: Context,
        call: ast.Call,
        header: list[str],
        sums: list[int],
        path: str,
        fdesc: FileDescriptor,
    ) -> Suggestion | None:
        if cell_is_analysable(ctx.tree) or len(set(header)) != len(header):
            return None
        kind, used = result_use(ctx, call)
        if kind == "chain":
            cols, label = used, PRESERVING
            detail = "the call is consumed by a column selection in the same expression; the dropped columns never appear"
        elif kind == "bound":
            u = column_uses(ctx.tree, used, bound_target(ctx, call))
            if not u.proven or not u.columns:
                return None
            cols, label = u.columns, CHANGES_RESULTS
            detail = (
                f"`{used}` will only contain {sorted(cols)}; later cells that use its other columns "
                "will fail or change"
            )
        else:
            return None
        if not cols <= set(header):
            return None
        keep = [c for c in header if c in cols]
        if len(keep) == len(header):
            return None
        share = sum(s for c, s in zip(header, sums, strict=True) if c in cols) / max(sum(sums), 1)
        modified = patch.insert_keywords(ctx.source, call, f"usecols={quote_list(keep)}")
        if modified is None:
            return None
        scaled = FileDescriptor(name=path, nbytes=max(1, int(fdesc.nbytes * share)))
        return Suggestion(
            rule=self.name,
            title="read only the columns the cell uses",
            explanation=(
                f"The cell reads {sorted(cols)} of the file's {len(header)} columns "
                f"(about {share:.0%} of its text)."
            ),
            original_source=ctx.source,
            modified_source=modified,
            semantics=label,
            semantics_detail=detail,
            virtual=VirtualChange(files={path: scaled}),
        )

    def _chunksize(
        self, ctx: Context, call: ast.Call, header: list[str], sums: list[int], n_sample: int,
        path: str, fdesc: FileDescriptor,
    ) -> Suggestion | None:  # fmt: skip
        avg_line = max(sum(sums) / n_sample, 1.0)
        rows = fdesc.nbytes / avg_line
        chunk = max(MIN_CHUNK_ROWS, int(rows * CHUNK_FRACTION) // 1000 * 1000)
        if chunk >= rows * 0.5:
            return None
        modified = patch.insert_keywords(ctx.source, call, f"chunksize={chunk}")
        if modified is None:
            return None
        scaled = FileDescriptor(name=path, nbytes=max(1, int(chunk * avg_line)))
        return Suggestion(
            rule=self.name,
            title=f"read the file in chunks of {chunk:,} rows",
            explanation=(
                f"The file has about {int(rows):,} rows; one chunk of {chunk:,} rows is held at a time "
                "if the code processes and discards each chunk."
            ),
            original_source=ctx.source,
            modified_source=modified,
            semantics=CHANGES_RESULTS,
            semantics_detail=(
                "read_csv then returns an iterator of DataFrames, not one DataFrame: the code after "
                "it must loop over the chunks and combine partial results itself"
            ),
            virtual=VirtualChange(files={path: scaled}),
            notes=("the memory saving holds only if each chunk is processed and released",),
        )
