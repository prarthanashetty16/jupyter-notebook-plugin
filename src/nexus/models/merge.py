"""Tier 0 model for ``DataFrame.merge`` / ``pandas.merge``."""

from __future__ import annotations

from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models._util import khash_presized_bytes
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

# Tier 0 prior for the OUTPUT row count M, as multiples of max(n_left, n_right). Join fan-out and
# key overlap are not visible without data statistics (Tier 1 replaces it via ``out_rows``).
# 1.0 is the foreign-key case; the 0.1 / 4.0 ends are unchanged first-draft priors, not evidence.
OUTPUT_ROWS_FACTORS = (0.1, 1.0, 4.0)
# Tier 1: dev points under-predicted by up to 14% with fan-out (measured / formula 1.0-1.14)
MODEL_HIGH_BAND = 1.15
MODEL_LOW_BAND = (
    0.8  # probes: measured / formula was 0.82 at the lowest where the elision was right
)


def output_rows_range(nl: int, nr: int, how: str) -> tuple[float, float, float]:
    """Conservative (low, expected, high) output rows when nothing is known about the keys.

    Semantics give hard lower bounds: a left join keeps every left row, a right join every right
    row, an outer join at least the larger side. An inner join has none (no key may match).
    """
    base = float(max(nl, nr))
    lo, mid, hi = (f * base for f in OUTPUT_ROWS_FACTORS)
    floor = {"left": nl, "right": nr, "outer": max(nl, nr)}.get(how, 0)
    return (max(lo, floor), max(mid, floor), max(hi, floor, nl + nr if how == "outer" else 0))


@register_model
class MergeModel(OperationModel):
    """Peak RAM and time of a two-frame merge, as a function of the OUTPUT row count M.

    RAM, derived from ``pandas.core.reshape.merge`` (``get_join_indexers`` / ``_factorize_keys``
    / ``_reindex_and_concat``) in pandas 3.1. Two phases that do not overlap, because the
    factorizer is a local of ``_factorize_keys`` and is freed before the result is assembled:

    1. *Join indexers.* The right keys are factorized into a hash table whose size follows their
       number of DISTINCT values (``khash_table_bytes``; Tier 0 assumes all rows are distinct)
       plus an 8 B/row code array; the left side is looked up or factorized (8 B/row, and a 1 B/row
       mask for the inner join); the result is a left and a right ``intp`` indexer of length M
       (8 B each per output row).
    2. *Result assembly.* The two indexers stay alive while each frame's blocks are taken through
       them: M rows of the left and of the right frame's ``moved_bytes`` (object columns: pointers,
       the string objects are shared). ``pd.concat(axis=1)`` of the two takes moves block
       references, no further copy.

    The hash table is allocated for ``min(max(n_left, n_right), 2**20 + 7)`` entries up front
    (``khash_presized_bytes``), so its size does not shrink with few distinct keys.

    ``how="right"`` builds the hash engine over the left keys (``left.get_indexer``), so the
    table follows ``n_left``; ``how="outer"`` adds three int64 arrays of M for the coalesced key
    (``_maybe_add_join_keys``: two filled takes and the combined copy). Both were found as dev
    under-predictions (right join x0.73, outer x0.62-0.86) and then read from the source.

    peak = max(phase 1, phase 2). Pandas skips the copy of a side whose indexer is a range
    (``is_range_indexer``): a left join against unique right keys, or an inner join in which every
    left row matches exactly once, never copies the left frame. Whether that happens depends on
    key uniqueness and overlap, which Tier 0 cannot see, so ``expected`` and ``high`` charge both
    sides and ``low`` assumes the left copy is elided (Tier 1 can decide it).

    Verified with isolated allocation probes on synthetic 0.4-1.5M-row frames (not benchmark
    points; ``get_join_indexers`` alone and the full merge, ``nexus.measure`` from disk), given
    the true M: the indexer phase alone peaked at 91 MiB for a 1.5M x 1.5M inner join on unique
    keys (formula 98), and the full merge matched ``max(phase 1, phase 2)`` within 0.82-1.05 in
    every case where the left copy was elided exactly when pandas elides it (left joins on unique
    right keys, small unique right side) and within 0.93-0.94 for fan-out and low-overlap joins.
    Without the elision (an inner join in which every left row matches once) pandas copied
    nothing of the left frame and the formula over-predicted by 1.75x (ratio 0.57): that is the
    ``low`` end.

    M is an explicit input: ``features["out_rows"]`` is ``(low, expected, high)``. Tier 0 fills it
    from ``output_rows_range`` (semantic lower bounds plus the prior above) and sets
    ``out_rows_source="tier0_prior"``; Tier 1 will replace it from key statistics (overlap,
    distinct counts, fan-out) and set ``out_rows_source="tier1"``.

    Time: hashing both key columns plus the output copy (complexity class unchanged in Phase 4a).
    """

    name = "merge"

    def matches(self, op: DetectedOp) -> bool:
        return op.name in ("merge", "pandas.merge")

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        if len(op.variables) < 2:
            raise NoEstimateError("merge needs two known frames")
        left, right = u.frame(state, op.variables[0]), u.frame(state, op.variables[1])
        keys = u.literal_columns(op.kwargs.get("on"))
        key_text = bool(keys) and any(u.is_text(left.dtypes.get(c, "")) for c in keys)
        how = op.kwargs.get("how", "inner")
        how = how if isinstance(how, str) else "inner"
        return {
            "n_left": left.shape[0],
            "n_right": right.shape[0],
            "bytes_left": left.nbytes,
            "bytes_right": right.nbytes,
            "moved_left": left.moved_bytes,
            "moved_right": right.moved_bytes,
            "key_text": key_text,
            "key_column": keys[0] if keys and len(keys) == 1 else None,
            "how": how,
            "out_rows": output_rows_range(left.shape[0], right.shape[0], how),
            "out_rows_source": "tier0_prior",
        }

    @staticmethod
    def ram_at(
        features: dict[str, Any],
        m: float,
        left_elided: bool = False,
        right_distinct: float | None = None,
        right_unique: bool = True,
        left_distinct: float | None = None,
        overlap: float | None = None,
    ) -> float:
        nl, nr = features["n_left"], features["n_right"]
        row_l = features.get("moved_left", features["bytes_left"]) / max(nl, 1)
        row_r = features.get("moved_right", features["bytes_right"]) / max(nr, 1)
        how = features.get("how", "inner")
        if how == "right":  # the hash engine is built over the LEFT keys (left.get_indexer)
            table = khash_presized_bytes(nl, max(nl, nr))
        else:
            table = khash_presized_bytes(
                nr if right_distinct is None else right_distinct, max(nl, nr)
            )
        if right_unique:
            phase1 = table + 8 * nr + 8 * nl + nl + 16 * m
        else:
            # Sort-based join: ``_factorize_keys`` runs ONE factorizer over both sides, so the hash
            # table holds the UNION of the left and right keys (not just the right ones), both code
            # arrays stay alive, and the group-sort step adds the sorters and per-group counts.
            # Derived from 27 probes (docs/benchmarks/val-v3-diagnosis/probes/pc3): table over the
            # union + 16 B x (nl + nr) + 8 B x union + 16 B x M, measured/formula 1.02 (0.83-1.17).
            ld = float(nl if left_distinct is None else left_distinct)
            rd = float(nr if right_distinct is None else right_distinct)
            matched = 0.0 if overlap is None else min(rd, overlap * ld)
            union = ld + max(rd - matched, 0.0)
            phase1 = u.khash_table_bytes(union) + 16 * (nl + nr) + 8 * union + 16 * m
        left_copy = 0.0 if left_elided else m * row_l
        phase2 = (8 if left_elided else 16) * m + left_copy + m * row_r
        if how == "outer":  # _maybe_add_join_keys: two filled takes of the key + a combined copy
            phase2 += 24 * m
        return max(phase1, phase2)

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Output rows, overlap, uniqueness and right distinct keys from a coordinated key sample
        (skew-aware; see ``stats.join_profile``). One key column, ``on=`` only."""
        key = features.get("key_column")
        if key is None:
            return None
        left, right = ctx.obj(op.variables[0]), ctx.obj(op.variables[1])
        how = features["how"]
        jp = stats.join_profile(left[key], right[key], how, deadline=ctx.deadline)
        elided = jp.right_keys_unique and (
            how == "left" or (how == "inner" and jp.left_all_matched_once)
        )
        o, d = jp.out_rows, jp.right_distinct
        return {
            "out_rows": (o.low, o.value, o.high),
            "out_rows_source": "tier1",
            "right_distinct": (d.low, d.value, d.high),
            "left_distinct": (jp.left_distinct.low, jp.left_distinct.value, jp.left_distinct.high),
            "overlap": jp.overlap.value,
            "left_elided": bool(elided),
            "right_unique": bool(jp.right_keys_unique),
            "left_elided_certain": bool(o.exact),
            "tier1": {
                "sample": o.sample,
                "confidence": o.confidence,
                "method": o.method,
                "overlap": jp.overlap.value,
                "heavy_keys": jp.heavy_keys,
            },
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        nl, nr = features["n_left"], features["n_right"]
        row_l = features["bytes_left"] / max(nl, 1)
        row_r = features["bytes_right"] / max(nr, 1)
        if "out_rows" in features:
            lo, mid, hi = features["out_rows"]
        else:
            lo, mid, hi = output_rows_range(nl, nr, features.get("how", "inner"))
        base = max(nl, nr)
        hash_s = u.machine().text_hash_s if features["key_text"] else u.machine().num_hash_s
        seconds = (nl + nr) * hash_s + base * (row_l + row_r) / u.machine().copy_bps
        if features.get("out_rows_source") == "tier1":
            el = features.get("left_elided", False)
            rd = features.get("right_distinct") or (nr, nr, nr)
            ru = features.get("right_unique", True)
            ld = features.get("left_distinct") or (nl, nl, nl)
            ov = features.get("overlap")
            ram = (
                self.ram_at(
                    features, lo, left_elided=el, right_distinct=rd[0], right_unique=ru,
                    left_distinct=ld[0], overlap=ov,
                )
                * MODEL_LOW_BAND,
                self.ram_at(
                    features, mid, left_elided=el, right_distinct=rd[1], right_unique=ru,
                    left_distinct=ld[1], overlap=ov,
                ),
                self.ram_at(
                    features,
                    hi,
                    left_elided=el and features.get("left_elided_certain", False),
                    right_distinct=rd[2],
                    right_unique=ru,
                    left_distinct=ld[2],
                    overlap=None,
                )
                * MODEL_HIGH_BAND,
            )  # fmt: skip
        else:
            ram = (
                self.ram_at(features, lo, left_elided=True) * MODEL_LOW_BAND,
                self.ram_at(features, mid),
                max(  # key uniqueness is unknown: the sort-based path may apply
                    self.ram_at(features, hi), self.ram_at(features, hi, right_unique=False)
                ),
            )
        return u.build(
            ram,
            u.time_band_for_tier(seconds, tier),
            0.3,
            tier,
            [
                "hash table + codes over the key columns",
                "two int64 indexers of output length M",
                "output rows copied from both frames (pointers for text)",
                f"M = {int(mid):,} rows ({features.get('out_rows_source', 'tier0_prior')})",
            ],
        )
