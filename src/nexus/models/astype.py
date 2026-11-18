"""Tier 0 model for ``df["col"].astype(dtype)``."""

from __future__ import annotations

import ast
import math
import sys
from typing import Any

import numpy as np

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection

PYMALLOC_ALIGNMENT = 16  # CPython >= 3.8 on 64-bit: small objects are rounded up to 16 bytes
STR_HEADER_BYTES = sys.getsizeof("")  # compact-ASCII str object overhead (41 on CPython 3.12)
INT_OBJECT_BYTES = 32  # a Python int above the small-int cache (fits up to 2**60)
POINTER_BYTES = 8
STR_PROBE_TOLERANCE = 0.02  # probe peaks were within ~1-2% of the formula, below it for datetime
# First-draft figures kept ONLY for the time term, which Phase 4a does not change.

# Characters of the decimal/ISO string form, Tier 0 range by source kind (Tier 1 narrows it).
STR_LEN_RANGE = {"int": (1, 20), "float": (3, 24), "datetime": (10, 29), "bool": (4, 5)}

# Error band of the hash-table model (measured / model over the validation probes, see the class
# docstring) applied to the Tier 1 range ends.
CATEGORY_BAND = (0.92, 1.12)


def str_object_bytes(length: int) -> int:
    """Bytes pymalloc gives a compact-ASCII ``str`` of ``length`` characters."""
    raw = STR_HEADER_BYTES + length
    return -(-raw // PYMALLOC_ALIGNMENT) * PYMALLOC_ALIGNMENT


def _kind(dtype: str) -> str:
    if dtype.startswith(("int", "uint")):
        return "int"
    if dtype.startswith("float"):
        return "float"
    if dtype.startswith("datetime"):
        return "datetime"
    if dtype == "bool":
        return "bool"
    return "other"


def to_str_peak_per_row(kind: str, length: int) -> float:
    """Peak bytes/row of ``astype(str)`` for a source kind and string length.

    Integers go through an object array of Python ints (pointer + int object) that stays alive
    while the result array (pointer) is filled with new ``str`` objects; floats, datetimes and
    bools are converted element by element and have no such temporary.
    """
    final = POINTER_BYTES + str_object_bytes(length)
    if kind == "int":
        return final + POINTER_BYTES + INT_OBJECT_BYTES
    return final


def _column_name(op: DetectedOp) -> str | None:
    """Column from ``df["col"].astype(...)`` read off the call node, if it is a literal."""
    func = getattr(op.node, "func", None)
    value = getattr(func, "value", None)
    if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Constant):
        return value.slice.value if isinstance(value.slice.value, str) else None
    return None


@register_model
class AstypeModel(OperationModel):
    """Peak RAM and time of converting one column (``df["c"].astype(target)``).

    Only the single-column ``df["c"].astype(...)`` form is modelled; whole-frame astype yields no
    estimate. The result is a new array, so the peak depends on the target:

    * numeric -> numeric: ``n * itemsize`` (unchanged; the benchmark and the probes agree).
    * -> ``str`` (pandas ``lib.ensure_string_array``): every value becomes a NEW Python ``str``
      object (``STR_HEADER_BYTES + length`` rounded up to pymalloc's 16-byte class) plus an
      8-byte pointer in the result array. For integer sources pandas first builds an object array
      of the Python ints (8-byte pointer + a 32-byte int object each; small ints are cached) that
      stays alive while the result is filled, adding 40 bytes/row to the peak; float and datetime
      sources have no such temporary. The string length is the unknown: Tier 0 spans
      ``STR_LEN_RANGE`` and puts ``expected`` at the geometric middle of the two ends (the feature
      ``str_len`` lets Tier 1 fix it). Verified with isolated probes on 2M-row columns: int64 with
      1, 3, 5, 7, 9, 12 and 17 digits measured 64.3, 90.8, 96.4, 96.4, 112.5, 112.5, 112.5 B/row
      against 64, 96, 96, 96, 112, 112, 112 from the formula (3 digits: ints below 257 are cached
      objects, so the formula is an upper bound there); floats of 17 and 6 characters measured
      72.4 and 56.3 (formula 72, 56); datetime of 19 characters 72.4 (72). Text -> str copies the
      pointer array only (not probed).
    * -> ``category`` (``Categorical``: ``factorize`` into a hash table, remap of the codes after
      sorting the categories, codes narrowed to int8/16/32): the peak is
      ``base * n + resident table pages + 8 * distinct`` (``_util.factorize_peak_bytes``). The
      table is presized for ``min(n, 2**20 + 7)`` entries whatever the distinct count U, and a
      page of it becomes resident only when a key hashes into it: random keys touch a share
      ``1 - exp(-U / pages)`` of each array, sequential keys (``value_000000123``, ints 0..U-1)
      cluster into few pages, and a table that has to grow is fully resident. Phase 4a had measured
      one curve on 2M-row columns of SEQUENTIAL keys; the diagnosis of the val-v3 failures
      (docs/benchmarks/val-v3-diagnosis.md) found that random strings cost up to 38 MiB more at
      U/n = 0.006 and that the n-dependence is the presize cap, not a 15% effect. The model matches
      22 isolated probes (text, 300k-4M rows, U = 12 .. 2M) within 3%; ``hash_scatter`` (Tier 1)
      replays khash's string / int64 hash over the sampled distinct values to tell random from
      clustered keys. Tier 0 knows neither U nor the layout: ``low`` is few distinct values, ``high``
      all distinct with random keys, ``expected`` their geometric mean.

    Time: unchanged first-draft model (hashing for category, per-element conversion for str).
    """

    name = "astype"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "astype"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        column = _column_name(op)
        target = op.args[0] if op.args else op.kwargs.get("dtype")
        if column is None or column not in df.dtypes or not isinstance(target, str):
            raise NoEstimateError("column or target dtype not statically known")
        if target not in ("str", "object", "category"):
            try:
                np.dtype(target)
            except TypeError as exc:
                raise NoEstimateError(f"unsupported target dtype {target!r}") from exc
        return {
            "n_rows": df.shape[0],
            "source_dtype": df.dtypes[column],
            "target": target,
            "str_len": None,  # Tier 1 fills: characters of the string form
            "distinct_fraction": None,  # Tier 1 fills: distinct values / rows
        }

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Column statistics: distinct count (category) or string-object sizes (str).

        Reads a 200k-row sample of the column; never modifies it.
        """
        col = _column_name(op)
        df = ctx.obj(op.receiver)
        series = df[col]
        n = len(series)
        if n < stats.MIN_SAMPLE_ROWS:
            return None
        target, source = features["target"], features["source_dtype"]
        if target == "category":
            d = stats.distinct_count(series, deadline=ctx.deadline)
            sc = stats.hash_scatter(series, text=u.is_text(source), deadline=ctx.deadline)
            return {
                "distinct_fraction": d.value / n,
                "distinct_fraction_low": d.low / n,
                "distinct_fraction_high": d.high / n,
                "hash_scatter": (sc.low, sc.value, sc.high),
                "tier1": {"sample": d.sample, "confidence": d.confidence, "method": d.method},
            }
        kind = _kind(source)
        if target == "str" and not u.is_text(source) and kind != "other":
            pos = stats.sample_positions(n, 100_000)
            sample = stats.take(series, pos)
            ctx.deadline.check()
            as_str = sample.astype(str)
            present = as_str.notna().to_numpy()  # pandas 3 keeps a null as a null, not as "nan"
            if not present.any():
                return None  # nothing to measure: stay at Tier 0
            lengths = as_str.str.len().to_numpy()[present]
            null_fraction = 1.0 - float(present.mean())
            classes = -(-(STR_HEADER_BYTES + lengths) // PYMALLOC_ALIGNMENT) * PYMALLOC_ALIGNMENT
            mean = float(classes.mean())
            half = stats.Z95 * float(classes.std(ddof=0)) / (len(classes) ** 0.5)
            big = 1.0
            if kind == "int":  # ints in [-5, 256] are cached objects: no 32-byte temporary
                values = sample.to_numpy()
                big = float(((values > 256) | (values < -5)).mean())
            return {
                "str_obj_bytes": mean,
                "str_obj_bytes_low": mean - half,
                "str_obj_bytes_high": mean + half,
                "int_object_fraction": big,
                "null_fraction": null_fraction,
                "tier1": {"sample": len(lengths), "confidence": 1.0 - half / max(mean, 1.0)},
            }
        return None

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        n, source, target = features["n_rows"], features["source_dtype"], features["target"]
        source_text = u.is_text(source)
        ram_range: tuple[float, float, float] | None = None
        out = 0.0
        if target == "category":
            kind = "text" if source_text else "numeric"
            frac = features.get("distinct_fraction")
            if frac is None:  # Tier 0: distinct count and key layout unknown
                lo = u.factorize_peak_bytes(kind, n, 1.0, scatter=0.0)
                hi = u.factorize_peak_bytes(kind, n, n, scatter=1.0)
                ram_range = (lo, math.sqrt(lo * hi), hi)
            else:  # Tier 1: the hash-table model at the estimated distinct count and key scatter
                fl, fh = (
                    features.get("distinct_fraction_low", frac),
                    features.get("distinct_fraction_high", frac),
                )
                sl, sv, sh = features.get("hash_scatter") or (1.0, 1.0, 1.0)
                at = (
                    u.factorize_peak_bytes(kind, n, fl * n, sl),
                    u.factorize_peak_bytes(kind, n, frac * n, sv),
                    u.factorize_peak_bytes(kind, n, fh * n, sh),
                )
                ram_range = (at[0] * CATEGORY_BAND[0], at[1], at[2] * CATEGORY_BAND[1])
            why = "hash every value; peak spans few-distinct .. all-distinct (count unknown)"
        elif target in ("str", "object"):
            kind = _kind(source)
            if target == "str" and not source_text and kind != "other":
                length = features.get("str_len")
                tier1 = features.get("str_obj_bytes")
                lo_len, hi_len = STR_LEN_RANGE[kind]
                if length is None:
                    lens = [lo_len, hi_len]
                else:
                    lens = [length, length]
                low = to_str_peak_per_row(kind, lens[0]) * n
                high = to_str_peak_per_row(kind, lens[1]) * n
                if kind == "int" and length is None:  # smallest values are cached int objects
                    low = (2 * POINTER_BYTES + str_object_bytes(lo_len)) * n
                ram_range = (low * (1 - STR_PROBE_TOLERANCE), math.sqrt(low * high), high)
                if tier1 is not None:  # sampled string-object sizes and cached-int share
                    big = features.get("int_object_fraction", 1.0)
                    fixed = POINTER_BYTES + (
                        POINTER_BYTES + INT_OBJECT_BYTES * big if kind == "int" else 0
                    )
                    present = 1.0 - features.get("null_fraction", 0.0)  # a null has no str object
                    per_row = [
                        fixed + present * features.get(f"str_obj_bytes{k}", tier1)
                        for k in ("_low", "", "_high")
                    ]
                    ram_range = (
                        per_row[0] * n * (1 - STR_PROBE_TOLERANCE),
                        per_row[1] * n,
                        per_row[2] * n * (1 + STR_PROBE_TOLERANCE),
                    )
                out = ram_range[1]
                why = "one new Python str per row (+ int object temporary for integers)"
            else:
                out = n * (POINTER_BYTES if source_text else 40)
                why = "pointer copy for text" if source_text else "one Python object per value"
        else:
            itemsize = np.dtype(target).itemsize
            out = n * itemsize
            why = f"new {target} array of {n} elements"
        if ram_range is None:
            ram_range = (out * 0.5, out, out * 2.5)
        return u.build(
            ram_range,
            u.time_band_for_tier(
                tt.astype({**features, "target_itemsize": out / max(n, 1)}, _kind(source)),
                tier,
            ),
            0.5,
            tier,
            [why],
        )
