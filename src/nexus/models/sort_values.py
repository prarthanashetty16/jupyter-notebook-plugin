"""Tier 0 model for ``DataFrame.sort_values``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

SORT_TEMP_BYTES_PER_ROW = 5 * 8 + 2  # nargsort: five int64-sized arrays + two bool masks
LEXSORT_NUMERIC_BYTES_PER_ROW = 16  # indexer + merge buffer; never above phase 2 in the probes
SORT_PROBE_TOLERANCE = 0.02  # probe: formula 42 vs measured 41.2 B/row (-2%); take phase +-0.5%
LEXSORT_TEXT_BASE, LEXSORT_TEXT_PER_KEY = 45, 5  # B/row, measured on probes (see docstring)


@register_model
class SortValuesModel(OperationModel):
    """Peak RAM and time of ``df.sort_values(by)``.

    RAM, derived from ``DataFrame.sort_values`` and ``pandas.core.sorting`` (pandas 3.1). The
    peak is the larger of two phases that do not overlap, because phase 1's temporaries are locals
    of ``nargsort`` / ``lexsort_indexer`` and are freed when they return:

    1. *Computing the indexer.* Single key, ``nargsort``: NaN mask and its negation (1 B/row
       each), ``idx = arange(n)``, ``non_nans`` (a copy of the key), ``non_nan_idx``, the
       ``argsort`` result, ``indexer = non_nan_idx[argsort]`` and ``np.concatenate`` for the NaN
       placement: five int64-sized arrays are alive together (5 x 8 B/row) plus the masks.
       Several keys, ``lexsort_indexer``: numeric keys go to ``np.lexsort`` without a copy;
       text keys are converted through ``Categorical`` (codes, plus a hash table by distinct
       values).
    2. *Applying it.* ``self._mgr.take(indexer)`` copies every block while the 8 B/row indexer
       is alive, and the new index (a RangeIndex becomes an int64 Index, 8 B/row). Object
       columns are copied as 8-byte POINTERS: the string objects are shared with the input and
       never copied, so the copy is ``FrameDescriptor.moved_bytes`` (shallow), not ``nbytes``
       (deep, which counts the string payload).

    peak = max(phase 1, phase 2). ``expected`` is that maximum;
    ``low`` is that figure minus the 2% by which the probes fell below the formula;
    ``high`` is phase 1 + phase 2 (the bound if nothing were returned between phases) plus the
    distinct-value tables of text keys. A frame that is already sorted skips the copy
    (``is_range_indexer``), so the estimate is an upper bound for it.

    Verified with isolated allocation probes on synthetic 2M-row frames (not benchmark points;
    each peak measured with ``nexus.measure`` from inputs loaded from disk): frames of 8..168
    shallow B/row; key dtype int/float/text; shared vs unshared strings. Phase 2 matched
    ``moved + 16`` B/row to within 0.5%; phase 1 for one key measured 41.2 B/row (formula 42);
    several numeric keys never exceeded phase 2; several keys with text add about 5 B/row per text
    key to a base of ~45 (measured 49.7, 54.9, 58.8, 63.5 for 1..4 text keys), and about 10 B/row
    more when the text keys are all distinct. The multi-key text figures are measured
    mechanism constants of ``Categorical`` conversion, not derived.

    Time: n*log2(n) comparisons (text comparisons are slower) plus the copy. The complexity class
    is unchanged in Phase 4a (see docs/PROGRESS.md: measured super-linearity is a cache effect
    of the working set, not a different class).
    """

    name = "sort_values"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "sort_values"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        keys = u.literal_columns(u.arg_or_kwarg(op, 0, "by"))
        n_keys, n_text = u.text_count(df, keys)
        return {
            "n_rows": df.shape[0],
            "n_keys": n_keys if keys else 1,
            "n_text_keys": n_text if keys else 0,
            "input_bytes": df.nbytes,
            "moved_bytes": df.moved_bytes,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, k, kt, size = (features[x] for x in ("n_rows", "n_keys", "n_text_keys", "input_bytes"))
        moved = features.get("moved_bytes", size)
        take_phase = moved + 8 * n + 8 * n  # block copies + indexer + new int64 index
        if k <= 1:
            sort_phase = SORT_TEMP_BYTES_PER_ROW * n
        elif kt == 0:
            sort_phase = LEXSORT_NUMERIC_BYTES_PER_ROW * n
        else:
            sort_phase = (LEXSORT_TEXT_BASE + LEXSORT_TEXT_PER_KEY * kt) * n
        distinct_tables = LEXSORT_TEXT_PER_KEY * kt * n if k > 1 else 0
        expected = max(take_phase, sort_phase)
        ram = (
            expected * (1 - SORT_PROBE_TOLERANCE),
            expected,
            take_phase + sort_phase + distinct_tables,
        )
        cmp_s = (k - kt) * u.machine().num_argsort_s + kt * u.machine().text_argsort_s
        seconds = n * u.log2n(n) * cmp_s + size / u.machine().copy_bps
        return u.build(
            ram,
            u.time_band(seconds),
            0.6,
            tier,
            [
                "nargsort/lexsort temporaries, then int64 indexer",
                "copy of every column's values/pointers (string objects are shared)",
                f"{kt} text key column(s): slow comparisons" if kt else "numeric keys only",
            ],
        )
