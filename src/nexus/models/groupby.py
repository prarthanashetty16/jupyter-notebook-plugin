"""Tier 0 / Tier 1 model for ``DataFrame.groupby`` (the grouping plus a following aggregation)."""

from __future__ import annotations

import ast
import math
from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

CATEGORY_KEY_BYTES = 9.8  # peak B/row of a categorical key, independent of the group count (probe)
RESULT_BYTES_PER_GROUP = 40.0  # per group: key values, index and sort temporaries (probe: G = n)
MULTI_KEY_EXTRA = (0.0, 8.0, 16.0)  # B/row per additional key beyond the sum of the key curves
MODEL_LOW_BAND = 0.8  # probes at n = 1M/3M/6M: measured / curve between 0.78 and 1.5
MODEL_HIGH_BAND = 1.25  # same probes: up to +50% at one (n, G/n); +25% covers 6 of 7 cells
VALUE_COLUMN_FRACTIONS = (0.0, 0.3, 1.0)  # share of value columns aggregated (Tier 0 prior)

NUMERIC_KINDS = ("int", "uint", "float", "bool")


def _key_kind(dtype: str) -> str:
    if dtype == "category":
        return "category"
    return "text" if u.is_text(dtype) else "numeric"


@register_model
class GroupByModel(OperationModel):
    """Peak RAM and time of ``df.groupby(keys)`` followed by an aggregation.

    RAM, derived from ``pandas.core.groupby`` (pandas 3.1) and isolated probes on 2M-row frames
    (``docs/benchmarks/tier0-v2/probes/p_gb.py``, ``p_gb2.py``, ``p_gb3.py``). Two phases that do
    not overlap, because the factorize temporaries are freed before the result is built:

    1. *Factorizing the keys.* Each key column is run through ``factorize`` (codes, a hash table,
       the sorted uniques and a remapped code array). The peak depends only on the key's dtype and
       its number of distinct values G, and follows the same curve as ``astype("category")``
       (``_util.FACTORIZE_KNOTS``: text 24 -> 83 B/row, numeric 16 -> 58 as G/n goes 0 -> 1). A
       categorical key reuses its codes and costs ~10 B/row at any G. Several keys add roughly
       8-16 B/row per additional key for combining the codes (measured +0.9 .. +16.6 over the sum of
       the single-key curves, and -17 at G = n, hence the 0.85 low band).
    2. *Building the result.* The codes (8 B/row) stay alive while the result has G rows with the
       aggregated columns (8 B each) and ~40 B/group of key and index storage (probe at G = n: peak
       = 48.4 + 8 x columns B/row: 57.5, 80.4, 128.4 for 1, 4 and 10 columns).

    The value columns do not matter in phase 1 (1 vs 3 columns measured identical) and matter only
    at high G in phase 2. The number of groups G and the aggregated columns are the data-dependent
    inputs. Tier 0 spans G/n = 0..1 (the geometric middle of the RAM extremes is ``expected``) and
    0..100% of the value columns. Tier 1 estimates G per key and for the key combination
    (``stats.distinct_count`` / ``distinct_rows``: Chao1 with Good-Turing bounds) and reads the
    aggregated columns off the cell (``df.groupby(k)["v"]`` / ``[["a","b"]]``; else every numeric
    non-key column).

    Time: unchanged first-draft model (hashing keys + aggregation); its error is data-dependent
    (group count) and not addressed here.
    """

    name = "groupby"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "groupby"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        keys = u.literal_columns(u.arg_or_kwarg(op, 0, "by"))
        n_keys, n_text = u.text_count(df, keys)
        kinds = [_key_kind(df.dtypes.get(c, "object")) for c in keys] if keys else ["text"]
        value_cols = [
            c
            for c, d in df.dtypes.items()
            if (not keys or c not in keys) and d.startswith(NUMERIC_KINDS)
        ]
        return {
            "n_rows": df.shape[0],
            "n_cols": df.shape[1],
            "n_keys": n_keys if keys else 1,
            "n_text_keys": n_text if keys else 0,
            "key_columns": keys,
            "key_kinds": kinds,
            "n_value_cols": max(len(value_cols), 1),
            "input_bytes": df.nbytes,
            "groups_fraction": None,  # Tier 1 fills: groups / rows (low, value, high) below
        }

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        keys = features.get("key_columns")
        n = features["n_rows"]
        if not keys or n < stats.MIN_SAMPLE_ROWS:
            return None
        df = ctx.obj(op.receiver)
        per_key = [
            stats.distinct_count(df[k], deadline=ctx.deadline, share=0.5 / len(keys)) for k in keys
        ]
        if len(keys) > 1:
            combined = stats.distinct_rows([df[k] for k in keys], deadline=ctx.deadline, share=0.8)
        else:
            combined = per_key[0]
        agg = _aggregated_columns(ctx.source, op, df, keys)
        out: dict[str, Any] = {
            "key_fractions": [(d.low / n, d.value / n, d.high / n) for d in per_key],
            "groups_fraction": (combined.low / n, combined.value / n, combined.high / n),
            "tier1": {
                "sample": min(s.sample for s in per_key),
                "confidence": min(s.confidence for s in per_key + [combined]),
                "method": combined.method,
            },
        }
        if agg is not None:
            out["n_value_cols"] = max(len(agg), 1)
            out["aggregated_columns"] = agg
        return out

    @staticmethod
    def ram_at(
        features: dict[str, Any],
        key_fracs: list[float],
        groups_frac: float,
        cols: int,
        spread: int = 1,
    ) -> float:
        """Peak bytes for given per-key distinct fractions, group fraction and aggregated columns."""
        n = features["n_rows"]
        kinds = features["key_kinds"]
        per_key = 0.0
        for kind, frac in zip(kinds, key_fracs, strict=False):
            per_key += (
                CATEGORY_KEY_BYTES if kind == "category" else u.factorize_peak_per_row(kind, frac)
            )
        phase1 = (per_key + MULTI_KEY_EXTRA[spread] * (len(kinds) - 1)) * n
        phase2 = 8 * n + groups_frac * n * (RESULT_BYTES_PER_GROUP + 8 * cols)
        return max(phase1, phase2)

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n, k, kt, cols = (features[x] for x in ("n_rows", "n_keys", "n_text_keys", "n_value_cols"))
        kinds = features.get("key_kinds") or ["text"] * k
        features = {**features, "key_kinds": kinds}
        fr = features.get("key_fractions")
        gf = features.get("groups_fraction")
        agg_known = "aggregated_columns" in features
        if gf is None:  # Tier 0: G unknown, spans none-repeated .. all-distinct
            low = self.ram_at(features, [0.0] * len(kinds), 0.0, 1, 0)
            high = self.ram_at(features, [1.0] * len(kinds), 1.0, cols, 2)
            mid = math.sqrt(low * high)
            ram = (low * MODEL_LOW_BAND, mid, high)
            why = "group count unknown: spans one group .. every row distinct"
        else:  # Tier 1: estimated group counts with their bounds
            cols_lo = cols if agg_known else max(1, round(VALUE_COLUMN_FRACTIONS[1] * cols))
            cols_hi = cols
            fr = fr or [gf] * len(kinds)
            at = [
                self.ram_at(features, [f[0] for f in fr], gf[0], cols_lo, 0),
                self.ram_at(features, [f[1] for f in fr], gf[1], cols if agg_known else cols_lo, 1),
                self.ram_at(features, [f[2] for f in fr], gf[2], cols_hi, 2),
            ]
            ram = (at[0] * MODEL_LOW_BAND, at[1], at[2] * MODEL_HIGH_BAND)
            why = f"estimated groups {gf[1] * n:,.0f} of {n:,} rows ({features['tier1']['method']})"
        seconds = (
            n * ((k - kt) * u.machine().num_hash_s + kt * u.machine().text_hash_s)
            + n * cols * u.machine().agg_s
        )
        return u.build(
            ram,  # type: ignore[arg-type]
            u.time_band_for_tier(seconds, tier),
            0.4 if gf is None else 0.7,
            tier,
            [
                "factorize key columns (cost follows the number of groups)",
                f"{kt} text key column(s) hashed" if kt else "numeric keys only",
                why,
            ],
        )


def _aggregated_columns(source: str, op: DetectedOp, df: Any, keys: list[str]) -> list[str] | None:
    """Columns selected after the groupby call in the cell (``["v"]`` / ``[["a", "b"]]``), else
    every numeric non-key column; None when the source cannot be matched to the call."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    call = getattr(op, "node", None)
    target = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "groupby"
            and node.lineno == getattr(call, "lineno", -1)
            and node.col_offset == getattr(call, "col_offset", -1)
        ):
            target = node
            break
    if target is None:
        return None
    for parent in ast.walk(tree):
        if isinstance(parent, ast.Subscript) and parent.value is target:
            sel = parent.slice
            names = []
            if isinstance(sel, ast.Constant) and isinstance(sel.value, str):
                names = [sel.value]
            elif isinstance(sel, ast.List):
                names = [e.value for e in sel.elts if isinstance(e, ast.Constant)]
            return [c for c in names if c in df.columns] or None
    numeric = [
        c for c in df.columns if c not in keys and str(df[c].dtype).startswith(NUMERIC_KINDS)
    ]
    return numeric or None
