"""Tier 0 / Tier 1 model for ``DataFrame.groupby`` (the grouping plus a following aggregation)."""

from __future__ import annotations

import ast
import math
from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

CATEGORY_KEY_BYTES = 9.8  # peak B/row of a categorical key, independent of the group count (probe)
RESULT_BYTES_PER_GROUP = 40.0  # per group: key values, index and sort temporaries (probe: G = n)
COMBO_SCATTER = (0.3, 0.72, 1.0)  # how the combined group ids hash (dense ints measure ~0.72)
COMBO_COEXIST = 0.5  # share of the smaller of (key table, combined-id table) alive with the larger
MODEL_LOW_BAND = 0.92  # measured / model band of the hash-table model (see the class docstring)
MODEL_HIGH_BAND = 1.12
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
       the sorted uniques and a remapped code array). A single key follows the hash-table model of
       ``_util.factorize_peak_bytes`` (the same as ``astype("category")``: ``base * n`` plus the
       RESIDENT pages of a table presized for ``min(n, 2**20 + 7)`` entries, which depend on the
       distinct count and on how uniformly the keys hash; see the ``astype`` docstring). A
       categorical key reuses its codes and costs ~10 B/row at any G. Several keys keep every
       key's codes alive (``base``), the largest key table, two int64 id arrays and a table over the
       combined group ids (``COMBO_SCATTER``); the combined table and the key tables partly coexist
       (``COMBO_COEXIST``, the one constant fitted to four two-key probes of 1M rows: 55.9, 80.4,
       101.5 and 101.9 MiB measured vs 67.6, 84.1, 99.5, 101.3 modelled; docs/benchmarks/
       val-v3-diagnosis/probes/pb8).
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
        kinds = features.get("key_kinds") or ["text"] * len(keys)
        scatter = [
            stats.hash_scatter(df[k], text=(kind == "text"), deadline=ctx.deadline)
            if kind != "category"
            else stats.exact(1.0, n)
            for k, kind in zip(keys, kinds, strict=False)
        ]
        out: dict[str, Any] = {
            "key_scatter": [(sc.low, sc.value, sc.high) for sc in scatter],
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
        scatter: list[float] | None = None,
    ) -> float:
        """Peak bytes for given per-key distinct fractions, group fraction and aggregated columns.

        ``spread`` selects the multi-key assumption: 0 low, 1 expected, 2 high. ``scatter`` is the
        per-key hash scatter (1.0: random keys).
        """
        n = features["n_rows"]
        kinds = features["key_kinds"]
        scatter = scatter or [1.0] * len(kinds)
        if len(kinds) == 1:
            kind = kinds[0]
            phase1 = (
                CATEGORY_KEY_BYTES * n
                if kind == "category"
                else u.factorize_peak_bytes(kind, n, key_fracs[0] * n, scatter[0])
            )
        else:
            bases = tables = 0.0
            for kind, frac, sc in zip(kinds, key_fracs, scatter, strict=False):
                if kind == "category":
                    bases += CATEGORY_KEY_BYTES * n
                    continue
                base = max(u.FACTORIZE_BASE[kind], u.FACTORIZE_FLOOR[kind]) * n
                bases += base
                tables = max(tables, u.factorize_peak_bytes(kind, n, frac * n, sc) - base)
            sc_combo = COMBO_SCATTER[spread]
            combo = u.factorize_peak_bytes("numeric", n, groups_frac * n, sc_combo) - (
                u.FACTORIZE_FLOOR["numeric"] * n
            )
            ids = (8.0 if spread == 0 else 16.0) * n  # group index + compressed ids
            if spread == 2:
                held = tables + combo  # both tables alive: the upper bound
            else:
                held = max(tables, combo) + (COMBO_COEXIST if spread == 1 else 0.0) * min(
                    tables, combo
                )
            phase1 = bases + ids + held
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
            low = self.ram_at(features, [0.0] * len(kinds), 0.0, 1, 0, [0.0] * len(kinds))
            high = self.ram_at(features, [1.0] * len(kinds), 1.0, cols, 2)
            mid = math.sqrt(low * high)
            ram = (low * MODEL_LOW_BAND, mid, high)
            why = "group count unknown: spans one group .. every row distinct"
        else:  # Tier 1: estimated group counts with their bounds
            cols_lo = cols if agg_known else max(1, round(VALUE_COLUMN_FRACTIONS[1] * cols))
            cols_hi = cols
            fr = fr or [gf] * len(kinds)
            sc = features.get("key_scatter") or [(1.0, 1.0, 1.0)] * len(kinds)
            at = [
                self.ram_at(features, [f[0] for f in fr], gf[0], cols_lo, 0, [x[0] for x in sc]),
                self.ram_at(
                    features, [f[1] for f in fr], gf[1], cols if agg_known else cols_lo, 1,
                    [x[1] for x in sc],
                ),
                self.ram_at(features, [f[2] for f in fr], gf[2], cols_hi, 2, [x[2] for x in sc]),
            ]  # fmt: skip
            ram = (at[0] * MODEL_LOW_BAND, at[1], at[2] * MODEL_HIGH_BAND)
            why = f"estimated groups {gf[1] * n:,.0f} of {n:,} rows ({features['tier1']['method']})"
        seconds = tt.groupby(features)
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
