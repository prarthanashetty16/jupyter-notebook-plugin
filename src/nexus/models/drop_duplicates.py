"""Tier 0 model for ``DataFrame.drop_duplicates``."""

from __future__ import annotations

import math
from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models._util import (
    group_ids_overflow,
    khash_presized_bytes,
)
from nexus.models.base import Estimate, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

# Unknown at Tier 0, filled by Tier 1: share of rows that are distinct (over the key columns) and
# share of distinct values per key column. The Tier 0 range spans "all duplicates" to "all unique".
DISTINCT_FRACTIONS = (0.0, 0.5, 1.0)  # (low, expected, high); expected is a prior, not evidence
# Share of the nullable key columns that actually contain nulls (Tier 1 reads it from null counts).
NULL_COLUMN_FRACTIONS = (0.0, 0.5, 1.0)
# Probe-measured error band of the formula (measured / formula): 0.77 .. 1.18 over the probes
# (n = 1M under-predicted by 18%, n = 2M by 5%, a low-cardinality probe over-predicted by 23%).
MODEL_BAND = (0.8, 1.2)


@register_model
class DropDuplicatesModel(OperationModel):
    """Peak RAM and time of ``df.drop_duplicates(subset=...)``.

    RAM, derived from ``DataFrame.duplicated`` / ``drop_duplicates`` in pandas 3.1:

    * Several key columns: each column is run through ``algorithms.factorize`` (an
      ``intp`` code array of 8 B/row, then ``astype("i8")`` makes a second 8 B/row copy that is
      returned; the first is freed) into a hash table whose size follows the number of DISTINCT
      values of that column (``khash_table_bytes``), and the ``k`` code arrays stay alive in
      ``labels`` until ``duplicated`` returns. Pandas allocates each table for
      ``min(n, 2**20 + 7)`` entries up front (``khash_presized_bytes``), whatever the distinct
      count. ``get_group_index`` then fuses them into one int64
      ``ids`` array (8 B/row, plus one transient of the same size) and ``duplicated(ids)`` hashes
      it with a key-only table sized by the distinct ROWS and returns a bool array.
    * One key column (``subset="c"``): ``Series.duplicated`` hashes the values directly: no code
      arrays, one key-only table, one bool array.
    * When the product of the key columns' distinct counts could exceed 2**63, ``get_group_index``
      fuses the columns in chunks and runs ``compress_group_index`` between chunks: one more
      int64 array (the compressed ids), a transient product, and a hash table with 8-byte values
      sized by the distinct rows. Tier 0 cannot rule this out for four or more key columns.
    * Null keys: ``get_group_index(..., xnull=False)`` runs ``maybe_lift`` on every key column that
      contains a null, creating a new ``lab + 1`` int64 array (8 B/row) per such column, alive
      during the ids phase. Tier 0 sees which dtypes CAN hold nulls (float, datetime, text,
      category, nullable extension types; not NumPy int/bool) and spans ``NULL_COLUMN_FRACTIONS``
      of them; Tier 1 knows which ones do. Verified: a 9-column frame with nulls in the 6 nullable
      columns measured 47.9 (n=1M) and 47.8 (n=2M) B/row above the same frame without nulls,
      against 8 x 6 = 48.
    * Then ``self[-mask]``: the negated mask (1 B/row), ``nonzero`` (8 B per surviving row) and a
      ``take`` that copies ``moved_bytes`` of the surviving rows (object columns: pointers only,
      the string objects stay shared).

    The peak is the largest of: the last column's factorize phase, the ``ids`` phase (with the
    compress step when it applies), and the mask/take phase.

    Verified with isolated allocation probes on synthetic 2M-row frames (not benchmark points):
    3-key frames of numeric and of text keys matched this formula within 0.2% (67.1 and 66.9 vs
    67.0 B/row) with all rows distinct; 4+ keys needed the compress step (without it the formula
    was 19-23% low); shared vs unshared strings gave identical peaks. Text and numeric keys cost the same memory (one pointer or value per bucket);
    they differ in time.

    Error band: over the probes measured/formula ranged 0.77..1.18 (the formula under-predicted
    a 9-column frame at n = 1M by 18% and at n = 2M by 5%; cause not identified), so the range
    ends are scaled by ``MODEL_BAND`` = (0.8, 1.2).

    Data dependence (the Tier 1 inputs): the number of distinct values per key column and of
    distinct rows set the table sizes, and the surviving share sets the output. Tier 0 knows
    neither and spans ``DISTINCT_FRACTIONS`` (all duplicates .. all unique); the expected value is
    the middle prior. Nothing here depends on how many string objects are shared: they are never
    copied.
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
            "moved_bytes": df.moved_bytes,
            "subset_known": subset is not None or op.kwargs.get("subset") is None,
            "key_columns": (
                subset
                if subset is not None
                else (list(df.dtypes) if op.kwargs.get("subset") is None and not op.args else None)
            ),
            "n_nullable_keys": (
                sum(u.can_hold_null(d) for d in df.dtypes.values())
                if subset is None
                else sum(u.can_hold_null(df.dtypes.get(c, "")) for c in subset)
            ),
            "null_key_columns": None,  # Tier 1 fills: key columns that contain a null
            "distinct_fraction": None,  # Tier 1 fills: distinct rows / rows
            "key_distinct_fraction": None,  # Tier 1 fills: mean distinct values / rows per key
        }

    @staticmethod
    def ram_at(
        features: dict[str, Any],
        key_frac: float,
        row_frac: float,
        null_keys: float = 0.0,
        log2_shape: float | None = None,
    ) -> float:
        n, k = features["n_rows"], features["n_keys"]
        moved = features.get("moved_bytes", features["input_bytes"])
        table = khash_presized_bytes(key_frac * n, n)
        ids_table = khash_presized_bytes(row_frac * n, n, key_only=True)
        if k <= 1:
            dedup = ids_table + n
        else:
            factorize = 8 * n * (k - 1) + 16 * n + table + 8 * key_frac * n
            ids = 8 * n * k + 16 * n + ids_table + n + 8 * n * null_keys
            compress = 0.0
            if (
                (log2_shape >= 63)
                if log2_shape is not None
                else group_ids_overflow(k, key_frac * n)
            ):
                full_table = khash_presized_bytes(row_frac * n, n)
                compress = 8 * n * k + 24 * n + full_table + 8 * n * null_keys
            dedup = max(factorize, ids, compress)
        take = 2 * n + 8 * row_frac * n + moved * row_frac + 8 * row_frac * n
        return max(dedup, take)

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Distinct rows (survivors), distinct values per key, and null key columns.

        Row/key distinct counts come from a 30k-200k row sample (Chao1 with Good-Turing bounds);
        float/datetime key columns are scanned completely for nulls (one null makes pandas lift
        the column), text columns are judged from the sample (``possible`` if it shows none).
        """
        n = features["n_rows"]
        cols = features.get("key_columns")
        if not cols or n < stats.MIN_SAMPLE_ROWS:
            return None
        df = ctx.obj(op.receiver)
        cols = [c for c in cols if c in df.columns]
        rows = min(stats.DEFAULT_SAMPLE_ROWS, max(30_000, 1_500_000 // len(cols)))
        survivors = stats.distinct_rows(
            [df[c] for c in cols], rows=rows, deadline=ctx.deadline, share=0.45, adaptive=False
        )
        per_key = [
            stats.distinct_count(
                df[c],
                rows=min(rows, 50_000),
                deadline=ctx.deadline,
                share=1.0 / (len(cols) + 1),
                adaptive=False,
            )
            for c in cols
        ]
        nulls = stats.null_profile(df, cols, rows=min(rows, 50_000), deadline=ctx.deadline)
        shape = [math.log2(d.value + 1) for d in per_key]
        lows = [math.log2(d.low + 1) for d in per_key]
        highs = [math.log2(d.high + 1) for d in per_key]
        certain = len(nulls.certain)
        return {
            "distinct_rows_range": (survivors.low / n, survivors.value / n, survivors.high / n),
            "key_fraction_range": (
                max(d.low for d in per_key) / n,
                max(d.value for d in per_key) / n,
                max(d.high for d in per_key) / n,
            ),
            "log2_shape_range": (sum(lows), sum(shape), sum(highs)),
            "null_range": (certain, certain, certain + len(nulls.possible)),
            "tier1": {
                "sample": survivors.sample,
                "confidence": min(survivors.confidence, min(d.confidence for d in per_key)),
                "method": survivors.method,
                "null_certain": certain,
                "null_possible": len(nulls.possible),
            },
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n, k, kt, size = (features[x] for x in ("n_rows", "n_keys", "n_text_keys", "input_bytes"))
        fixed = features.get("distinct_fraction")
        fracs = DISTINCT_FRACTIONS if fixed is None else (fixed, fixed, fixed)
        kfixed = features.get("key_distinct_fraction")
        nullable = features.get("n_nullable_keys", 0)
        known_nulls = features.get("null_key_columns")
        nulls = (
            tuple(known_nulls for _ in fracs)
            if known_nulls is not None
            else tuple(x * nullable for x in NULL_COLUMN_FRACTIONS)
        )
        if "distinct_rows_range" in features:  # Tier 1: estimated survivors, keys and null columns
            fr = features["distinct_rows_range"]
            kr = features["key_fraction_range"]
            ls = features["log2_shape_range"]
            nr = features["null_range"]
            fracs = fr
            ram = [self.ram_at(features, kr[i], fr[i], nr[i], ls[i]) for i in range(3)]
        else:
            ram = [
                self.ram_at(features, kfixed if kfixed is not None else f, f, nl)
                for f, nl in zip(fracs, nulls, strict=True)
            ]
        ram = [ram[0] * MODEL_BAND[0], ram[1], ram[2] * MODEL_BAND[1]]
        out = size * fracs[1]
        seconds = tt.drop_duplicates(features, out)
        return u.build(
            ram,  # type: ignore[arg-type]
            u.time_band_for_tier(seconds, tier),
            0.5,
            tier,
            [
                "factorize each key column (hash table by distinct values, 8 B/row codes kept)",
                f"{kt} text key column(s) hashed" if kt else "numeric keys only",
                "table sizes and output depend on unknown distinct counts (Tier 1 input)",
            ],
        )
