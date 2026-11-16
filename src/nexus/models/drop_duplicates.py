"""Tier 0 model for ``DataFrame.drop_duplicates``."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

OUTPUT_FRACTION_PRIOR = 0.5  # share of input rows assumed to survive; unknown at Tier 0


@register_model
class DropDuplicatesModel(OperationModel):
    """Peak RAM and time of ``df.drop_duplicates(subset=...)``.

    Hypothesised cost drivers (to be verified by the benchmark, not yet established):
    peak RAM is driven by data size, dtypes and object-column hashing: pandas factorizes each
    key column into int64 codes (8 bytes/row/column), combines them into group ids, builds a
    boolean mask, and copies the surviving rows. The duplicate fraction should mainly affect the
    OUTPUT size (surviving rows), not the factorization cost. Time is driven by per-element
    hashing (text far slower than numeric) plus the output copy.

    Tier 0 cannot see the duplicate fraction, so it assumes half of the rows survive and spans
    the range 0..100% survivors.
    """

    name = "drop_duplicates"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "drop_duplicates"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        subset = u.literal_columns(u.arg_or_kwarg(op, 0, "subset"))
        n_keys, n_text = u.text_count(df, subset)
        return {
            "n_rows": df.shape[0],
            "n_keys": n_keys,
            "n_text_keys": n_text,
            "input_bytes": df.nbytes,
            "subset_known": subset is not None or op.kwargs.get("subset") is None,
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, k, kt, size = (features[x] for x in ("n_rows", "n_keys", "n_text_keys", "input_bytes"))
        codes = 8 * n * (k + 2)  # per-key codes + combined group ids + mask
        text_tables = 8 * n * kt  # hash-table overhead for text keys
        out = size * OUTPUT_FRACTION_PRIOR
        ram = (codes, codes + text_tables + out, codes + 2 * text_tables + size)
        seconds = (
            n * ((k - kt) * u.machine().num_hash_s + kt * u.machine().text_hash_s)
            + out / u.machine().copy_bps
        )
        return u.build(
            ram,
            u.time_band(seconds),
            0.5,
            tier,
            [
                "factorize key columns (8 B/row/col codes)",
                f"{kt} text key column(s) hashed" if kt else "numeric keys only",
                "output size depends on unknown duplicate fraction",
            ],
        )
