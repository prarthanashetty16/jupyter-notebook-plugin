"""Tier 0 / Tier 1 model for ``pandas.concat`` (row-wise)."""

from __future__ import annotations

from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

INDEX_BYTES_PER_ROW = 12  # int64 result index + concatenation transient, measured (docstring)
POINTER_BYTES = 8  # one object pointer per row of a materialised categorical column


@register_model
class ConcatModel(OperationModel):
    """Peak RAM and time of ``pd.concat([a, b, ...])`` (row-wise).

    RAM, derived from ``pandas.core.internals.concat.concatenate_managers``: every output block
    is built by one ``np.concatenate`` over the inputs' blocks, so the result holds the sum of the
    inputs' ``moved_bytes``. For object/str columns that is 8-byte POINTERS: the string objects
    are shared with the inputs and are not copied, whether or not they repeat, so
    ``memory_usage(deep=True)`` (which counts the string payload) overstates the copy. The result
    index is an int64 ``Index`` unless ``ignore_index=True`` makes it a ``RangeIndex``; the probes
    measured 12 B/row for it (8 B/row of values plus a 4 B/row transient of the index
    concatenation) and exactly 0 with ``ignore_index``.
    Inputs stay alive, so the increment is exactly that copy; there is no intermediate larger
    than it when dtypes agree.

    Range: ``low`` is the copy alone, ``expected`` adds the int64 index, ``high`` adds a second
    copy of the values for the dtype-unification case (e.g. int + float, or categoricals with
    different categories becoming object), which Tier 0 cannot rule out.

    A frame with pyarrow-backed strings stores the characters inside the array, so its shallow
    bytes already include them and are copied (``moved_bytes`` covers it).

    Verified with isolated allocation probes on synthetic 1.5-2M-row frames (not benchmark
    points): numeric frames of 8..64 B/row peaked at exactly ``moved + 12`` B/row (and ``moved``
    with ``ignore_index``); frames with object/category/datetime columns, shared or unshared
    strings, 2 or 3 inputs, peaked 4-13% above ``moved + index`` (the residual is not explained;
    it stays inside the ``expected``..``high`` range). The peak does not follow the deep size.

    Time (Phase 6, ``nexus.models._time.concat``): a cold copy of the moved bytes, plus an incref
    of a Python object per row for every object column and for every categorical column whose
    categories DIFFER between the inputs: pandas cannot concatenate the codes then and returns a
    ``str`` column (probe ``docs/benchmarks/phase6/probes/p_concat_category.py``: 13-17 ns per row
    and column at 50-5,000 categories vs < 1 ns for identical categories). The incref cost follows
    the number of distinct objects touched (machine curve ``object_take_s``). Tier 1 compares the
    inputs' categories and estimates the distinct objects from a sample.

    RAM of differing categories (Phase 6, Tier 1 only; pandas ``concat_compat``): the common dtype
    of categoricals with different categories is object / str, so every input piece of such a
    column is converted to an array of pointers to the categories' (shared) string objects and the
    pieces are concatenated; columns are processed one after another. The result holds 8 B/row per
    such column instead of its 1-4 B/row of codes, and while the last one is concatenated its
    converted pieces (8 B/row) are alive as well: ``moved - codes + 8 n c + 8 n``. Isolated probes:
    tracemalloc 10.7 B/row/column at c = 3 (= (c + 1) x 8 / c), and the OS peak at >= 200 MiB
    (``docs/benchmarks/phase6/probes/p_concat_category_ram.py``). Tier 0 cannot see whether the
    categories agree; its ``high`` (two copies of the moved bytes) already covers this case.
    """

    name = "concat"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "pandas.concat"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if op.kwargs.get("axis", 0) not in (0, "index"):
            raise NoEstimateError("only axis=0 is modelled")
        if len(op.variables) < 2:
            raise NoEstimateError("need at least two known frames")
        frames = [u.frame(state, v) for v in op.variables]
        return {
            "total_bytes": sum(f.nbytes for f in frames),
            "moved_bytes": sum(f.moved_bytes for f in frames),
            "total_rows": sum(f.shape[0] for f in frames),
            "n_frames": len(frames),
            "ignore_index": op.kwargs.get("ignore_index") is True,
            "object_cols": max(f.text_columns for f in frames),
            "category_cols": max(
                sum(1 for d in f.dtypes.values() if d == "category") for f in frames
            ),
        }

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Which categorical columns have different categories across the inputs, and how many
        distinct objects the text / mismatched categorical columns hold (read-only)."""
        frames = [ctx.obj(v) for v in op.variables]
        first = frames[0]
        cat_cols = [c for c in first.columns if str(first[c].dtype) == "category"]
        mismatch, cat_distinct, codes = 0, [], 0
        for c in cat_cols:
            ctx.deadline.check()
            dtypes = [f[c].dtype if c in f.columns else None for f in frames]
            if any(d != dtypes[0] for d in dtypes[1:]):
                mismatch += 1
                cat_distinct.append(sum(len(d.categories) for d in dtypes if d is not None))
                codes += sum(int(f[c].array.codes.nbytes) for f in frames if c in f.columns)
        text_cols = [c for c in first.columns if u.is_text(str(first[c].dtype))]
        obj_distinct = []
        for c in text_cols[:4]:  # the incref working set: distinct objects (sum over inputs)
            ctx.deadline.check()
            obj_distinct.append(
                sum(
                    stats.distinct_count(f[c], deadline=ctx.deadline).value
                    for f in frames
                    if c in f.columns
                )
            )
        return {
            "category_mismatch": mismatch,
            "mismatch_codes_bytes": codes,
            "category_distinct": max(cat_distinct) if cat_distinct else None,
            "object_distinct": max(obj_distinct) if obj_distinct else None,
            "tier1": {"used": True, "method": "category dtype comparison + sampled distinct"},
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        total = features["total_bytes"]
        moved = features.get("moved_bytes", total)
        index = (
            0
            if features.get("ignore_index")
            else INDEX_BYTES_PER_ROW * features.get("total_rows", 0)
        )
        low, expected, high = moved, moved + index, 2 * moved + index
        mism = int(features.get("category_mismatch") or 0) if tier >= 1 else 0
        if mism:  # Tier 1: materialised pointers (see the class docstring)
            rows = features.get("total_rows", 0)
            low = moved - features.get("mismatch_codes_bytes", 0) + POINTER_BYTES * rows * mism
            expected = low + POINTER_BYTES * rows + index
            high = max(high, expected)
        return u.build(
            (low, expected, high),
            u.time_band(tt.concat(features)),
            0.7,
            tier,
            [
                "new frame holding every input row (pointers, not string objects)",
                "possible dtype-unification temporaries",
            ],
        )
