"""Tier 0 model for ``df["col"].astype(dtype)``."""

from __future__ import annotations

import ast
import math
import sys
from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection

PYMALLOC_ALIGNMENT = 16  # CPython >= 3.8 on 64-bit: small objects are rounded up to 16 bytes
STR_HEADER_BYTES = sys.getsizeof("")  # compact-ASCII str object overhead (41 on CPython 3.12)
INT_OBJECT_BYTES = 32  # a Python int above the small-int cache (fits up to 2**60)
POINTER_BYTES = 8
STR_PROBE_TOLERANCE = 0.02  # probe peaks were within ~1-2% of the formula, below it for datetime
# First-draft figures kept ONLY for the time term, which Phase 4a does not change.
LEGACY_STR_BYTES = 60
LEGACY_CATEGORY_FRACTION = 0.1

# Characters of the decimal/ISO string form, Tier 0 range by source kind (Tier 1 narrows it).
STR_LEN_RANGE = {"int": (1, 20), "float": (3, 24), "datetime": (10, 29), "bool": (4, 5)}

# Peak bytes/row of ``astype("category")`` at the two extremes of the distinct count, measured with
# isolated probes at n = 1M, 2M and 4M rows (constant across n; see the class docstring).
CATEGORY_PEAK = {"text": (24.0, 83.0), "numeric": (16.0, 59.0)}


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
      sorting the categories, codes narrowed to int8/16/32): the peak depends on the number of
      distinct values U, which Tier 0 cannot see. At the extremes it is constant per row,
      independent of n (measured at 1M, 2M and 4M rows): few distinct values need about 24 (text)
      or 16 (numeric) B/row, all-distinct about 83 / 59. In between the cost is not linear in U/n
      (measured at U/n = 0.05..0.5), so Tier 0 reports the two extremes as ``low`` and ``high``
      and the geometric middle as ``expected``; ``distinct_fraction`` (Tier 1) interpolates
      linearly, which under-predicts mid fractions (by up to ~30% around U/n = 0.05-0.1): a known
      approximation.

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

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier0(tier)
        n, source, target = features["n_rows"], features["source_dtype"], features["target"]
        source_text = u.is_text(source)
        ram_range: tuple[float, float, float] | None = None
        out = 0.0
        time_out = 0.0  # bytes in the (unchanged) time term
        if target == "category":
            lo, hi = CATEGORY_PEAK["text" if source_text else "numeric"]
            frac = features.get("distinct_fraction")
            mid = math.sqrt(lo * hi) if frac is None else lo + (hi - lo) * min(max(frac, 0), 1)
            ram_range = (lo * n, mid * n, hi * n)
            hash_s = u.machine().text_hash_s if source_text else u.machine().num_hash_s
            seconds = n * hash_s
            time_out = 4 * n + LEGACY_CATEGORY_FRACTION * n * (
                LEGACY_STR_BYTES if source_text else 8
            )
            why = "hash every value; peak spans few-distinct .. all-distinct (count unknown)"
        elif target in ("str", "object"):
            kind = _kind(source)
            seconds = 0.0 if source_text else n * u.machine().to_str_s
            if target == "str" and not source_text and kind != "other":
                length = features.get("str_len")
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
                out = ram_range[1]
                time_out = n * LEGACY_STR_BYTES
                why = "one new Python str per row (+ int object temporary for integers)"
            else:
                out = n * (POINTER_BYTES if source_text else 40)
                time_out = n * (POINTER_BYTES if source_text else LEGACY_STR_BYTES)
                why = "pointer copy for text" if source_text else "one Python object per value"
        else:
            itemsize = np.dtype(target).itemsize
            out, seconds = n * itemsize, n * u.machine().cast_s
            time_out = out
            why = f"new {target} array of {n} elements"
        if ram_range is None:
            ram_range = (out * 0.5, out, out * 2.5)
        return u.build(
            ram_range,
            u.time_band(seconds + time_out / u.machine().copy_bps),
            0.5,
            tier,
            [why],
        )
