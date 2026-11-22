"""Bytes of an operation's RESULT object (Phase 6c), for the cell-level peak model (``nexus.cellpeak``).

The cell model needs what an operation leaves behind when its result is bound to a name, which is
smaller than its incremental peak (the peak also holds transients: hash tables, indexers, tokenizer
buffers). Each formula is the output term of the model's own RAM derivation, so it needs no new
constant:

* read_csv: the parsed frame: rows x (value bytes of every kept column) + the new str objects of
  text cells (the model's per-field term without its 5.5 B of token bookkeeping, nor the tokenizer);
* merge: the output rows' copies (left side only when not elided) of ``MergeModel.ram_at``'s phase 2;
* groupby: G x (40 B of key / index + 8 B per aggregated column) of ``GroupByModel.ram_at``'s phase 2;
* sort_values: every moved column + the int64 index of the result;
* drop_duplicates: the surviving share of the moved bytes;
* astype: the new column (codes for category; for str / object and numeric targets the model's
  range is already the new column);
* concat, copy, fillna: the model's range IS the result (no transient beyond it);
* matmul: the m x p result; numpy.sort: the sorted copy.

Any other model: ``None`` -> the cell model keeps the whole peak as retained (conservative).
Returns ``(low, expected, high)``, each clipped to the operation's own ``(low, expected, high)``.
"""

from __future__ import annotations

import math
from typing import Any

from nexus.models.base import Estimate

Triple = tuple[float, float, float]


def _mid(v: Any, default: float) -> Triple:
    if v is None:
        return (default, default, default)
    if isinstance(v, (list, tuple)) and len(v) == 3:
        return (float(v[0]), float(v[1]), float(v[2]))
    return (float(v), float(v), float(v))


def _read_csv(f: dict[str, Any], e: Estimate) -> Triple:
    from nexus.models.read_csv import FIELD_WIDTH_RANGE, string_object_bytes

    rows, cols = f.get("n_rows"), f.get("n_cols")
    if rows and cols:
        rr = _mid(f.get("rows_range"), rows)
        ur = _mid(f.get("unique_range"), f.get("unique_fraction") or 1.0)
        values = f.get("value_bytes_per_row") or 8.0 * cols
        strings = (f.get("text_cols") or 0) * string_object_bytes(f.get("str_chars") or 12.0)
        return tuple(rr[i] * (values + strings * ur[i]) for i in range(3))  # type: ignore[return-value]
    size = f["file_bytes"]
    w_lo, w_hi = FIELD_WIDTH_RANGE
    w_mid = math.sqrt(w_lo * w_hi)
    return (
        8.0 * size / w_hi,
        8.0 * size / w_mid,
        float(e.ram_high),
    )  # text share unknown at Tier 0


def _merge(f: dict[str, Any], e: Estimate) -> Triple:
    """Phase 7b (``_reindex_and_concat`` in pandas 3.1): the result has a new RangeIndex (no bytes) and
    the ``on=`` keys only once, from the left side, so the right side contributes its NON-key columns;
    the left columns are new only when the left indexer is not a range (``left_elided`` False). v2
    charged 8 B x M for an index and the right key columns (probe: 30.5 MiB retained vs 91.8)."""
    nl, nr = f["n_left"], f["n_right"]
    row_l = f.get("moved_left", f["bytes_left"]) / max(nl, 1)
    right_key = float(f.get("right_key_bytes", 0.0))
    row_r = max(f.get("moved_right", f["bytes_right"]) - right_key, 0.0) / max(nr, 1)
    lo, mid, hi = _mid(f.get("out_rows"), max(nl, nr))
    elided = bool(f.get("left_elided", False))
    certain = bool(f.get("left_elided_certain", False))

    def at(m: float, el: bool) -> float:
        return (0.0 if el else m * row_l) + m * row_r

    if f.get("out_rows_source") == "tier1":
        return (at(lo, elided), at(mid, elided), at(hi, elided and certain))
    return (at(lo, True), at(mid, False), at(hi, False))


def _groupby(f: dict[str, Any], e: Estimate) -> Triple:
    from nexus.models.groupby import RESULT_BYTES_PER_GROUP

    n = float(f["n_rows"])
    cols = len(f["aggregated_columns"]) if f.get("aggregated_columns") else f["n_value_cols"]
    g = _mid(f.get("groups_fraction"), math.nan)
    if math.isnan(g[0]):
        g = (1.0 / max(n, 1.0), 1.0 / math.sqrt(max(n, 1.0)), 1.0)
    return tuple(gi * n * (RESULT_BYTES_PER_GROUP + 8.0 * cols) for gi in g)  # type: ignore[return-value]


def _sort_values(f: dict[str, Any], e: Estimate) -> Triple:
    out = float(f.get("moved_bytes", f["input_bytes"])) + 8.0 * f["n_rows"]
    return (out, out, out)


def _drop_duplicates(f: dict[str, Any], e: Estimate) -> Triple:
    from nexus.models.drop_duplicates import DISTINCT_FRACTIONS

    moved = float(f.get("moved_bytes", f["input_bytes"]))
    if f.get("distinct_rows_range") is not None:
        fr = _mid(f["distinct_rows_range"], 1.0)
    elif f.get("distinct_fraction") is not None:
        fr = _mid(f["distinct_fraction"], 1.0)
    else:
        fr = DISTINCT_FRACTIONS
    rows = float(f["n_rows"])
    return tuple(x * (moved + 8.0 * rows) for x in fr)  # type: ignore[return-value]


def _astype(f: dict[str, Any], e: Estimate) -> Triple:
    n = float(f["n_rows"])
    if f.get("target") == "category":
        frac = _mid(f.get("distinct_fraction"), math.nan)
        if math.isnan(frac[0]):
            return (n * 1.0, n * 2.0, n * 4.0)  # int8 .. int32 codes: distinct count unknown
        width = [1.0 if x * n < 128 else 2.0 if x * n < 32768 else 4.0 for x in frac]
        return (n * width[0], n * width[1], n * width[2])
    return (float(e.ram_low), float(e.ram_expected), float(e.ram_high))


def _whole(f: dict[str, Any], e: Estimate) -> Triple:
    return (float(e.ram_low), float(e.ram_expected), float(e.ram_high))


def _matmul(f: dict[str, Any], e: Estimate) -> Triple:
    out = float(f["m"] * f["p"] * f["itemsize"])
    return (out, out, out)


def _np_sort(f: dict[str, Any], e: Estimate) -> Triple:
    out = float(f["nbytes"])
    return (out, out, out)


FORMULAS = {
    "read_csv": _read_csv, "merge": _merge, "groupby": _groupby, "sort_values": _sort_values,
    "drop_duplicates": _drop_duplicates, "astype": _astype, "concat": _whole, "copy": _whole,
    "fillna": _whole, "matmul": _matmul, "np_sort": _np_sort,
}  # fmt: skip


def output_range(model: str, features: dict[str, Any], estimate: Estimate) -> Triple | None:
    """Result bytes (low, expected, high) of an operation, or None when not derived for ``model``."""
    fn = FORMULAS.get(model)
    if fn is None:
        return None
    try:
        lo, mid, hi = fn(features, estimate)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    caps = (estimate.ram_low, estimate.ram_expected, estimate.ram_high)
    vals = [min(max(float(v), 0.0), float(c)) for v, c in zip((lo, mid, hi), caps, strict=True)]
    vals = sorted(vals)
    return (vals[0], vals[1], vals[2])
