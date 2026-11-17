"""Tier 0 model for ``pandas.read_csv``."""

from __future__ import annotations

from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection, candidate_paths

# Peak-RAM structure of ``pd.read_csv(path)`` with the default C engine (pandas 3.1), in bytes. The
# coefficients were measured with isolated probes on synthetic files (see the class docstring), not
# on benchmark points.
FILE_BYTE_FACTOR = 1.6  # per byte of file: tokenizer text and word buffers that live with the parse
FIELD_BYTES = 13.5  # per field (row x column): the parsed 8-byte value plus its token bookkeeping
ROW_BYTES = 6.0  # per row: line bookkeeping
# Formula within +-20% of the probes (low-cardinality text -16%, 16-column floats +19%).
MODEL_BAND = (0.8, 1.2)
FIELD_WIDTH_RANGE = (
    2.0,
    24.0,
)  # file bytes per field incl. separator: 1-digit int .. 17-digit float
PYMALLOC_ALIGNMENT = 16
STR_HEADER_BYTES = 41  # CPython 3.12 compact ASCII str


def string_object_bytes(chars: float) -> float:
    """Bytes pymalloc reserves for one new ``str`` of ``chars`` characters."""
    raw = STR_HEADER_BYTES + chars
    return -(-raw // PYMALLOC_ALIGNMENT) * PYMALLOC_ALIGNMENT


def parse_peak_bytes(
    file_bytes: float,
    rows: float,
    cols: float,
    *,
    text_cols: float = 0.0,
    str_chars: float = 12.0,
    unique_fraction: float = 1.0,
) -> float:
    """Peak bytes of the default read given what Tier 1 can learn from a header/row sample.

    ``unique_fraction`` is the share of text cells that become a NEW ``str`` object (the parser
    reuses an object only for a repeat inside the same chunk of 2**k rows, so even low-cardinality
    columns create many).
    """
    base = FILE_BYTE_FACTOR * file_bytes + FIELD_BYTES * rows * cols + ROW_BYTES * rows
    return base + text_cols * rows * unique_fraction * string_object_bytes(str_chars)


@register_model
class ReadCsvModel(OperationModel):
    """Peak RAM and time of ``pd.read_csv("path")`` from the file size on disk.

    RAM. The peak is NOT the size of the parsed frame: the parse holds the file's tokens and the
    parsed chunks, and ``low_memory`` concatenates the chunks at the end, so values exist twice
    for a moment; text cells also create new ``str`` objects per chunk. Isolated probes on
    synthetic 1M-row files (not benchmark points; ``nexus.measure`` from disk) established the
    structure ``peak ~ 1.6*file_bytes + 13.5*fields + 6*rows (+ new string objects)``:

    * one column, width swept 3..17 bytes/row: +1.56 B of peak per extra file byte;
    * 4-digit ints, 1/4/16/32 columns: 29.2, 88.3, 343.1, 681.4 B/row, i.e. ~21.3 B per field
      (= 1.6*5 file bytes + 13.4);
    * a chunked read (``chunksize=100000``, no concatenation) peaked at only 13-73 B/row against
      71-384 B/row for the default read, so the cost is in holding all chunks and concatenating;
    * strings: 4 columns of 12 characters, all distinct, measured 384 B/row against 401 from
      the formula (a new 64-byte ``str`` object per cell); the same with 5% cardinality measured
      281 against 235 (-16%: the parser's de-duplication works per chunk, not per file).

    Over all probe files the formula is within +-20% except low-cardinality text (-16%) and
    16-column float files (+19%). The attribution to chunk concatenation is partly inferred.

    Tier 0 sees only the file size, so the unknown is the bytes per field ``w``: it spans
    ``FIELD_WIDTH_RANGE`` (``w`` = 24 -> numeric floats, ~2.2x the file; ``w`` = 2 -> one-digit
    integers or very short fields, 11.4x); both ends are then scaled by the +-20% probe error
    band (``MODEL_BAND``). ``expected`` uses the geometric middle width. Tier 1
    knows rows, columns, text columns and string length from a header/row sample and
    ``parse_peak_bytes`` gives the point estimate. Pyarrow, ``usecols``, ``dtype=`` and
    ``chunksize=`` change this and are not modelled.

    Time ~ file size / parse throughput (unchanged in Phase 4a).
    """

    name = "read_csv"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "pandas.read_csv"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        paths = [p for p in candidate_paths(op) if p in state.files]
        if not paths:
            raise NoEstimateError("file path unknown or not found on disk")
        return {
            "file_bytes": state.files[paths[0]].nbytes,
            "n_rows": None,  # Tier 1 fills from a header/row sample
            "n_cols": None,
            "text_cols": None,
            "str_chars": None,
            "unique_fraction": None,
        }

    # options that change what the parser allocates; statistics assume the plain call
    _PLAIN_KWARGS = frozenset({"filepath_or_buffer", "encoding", "low_memory"})

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Rows, columns, text columns, string length and per-chunk string uniqueness from the
        head of the file plus three seeked chunks (at most 1.75 MiB read)."""
        if any(k not in self._PLAIN_KWARGS for k in op.kwargs) or len(op.args) > 1:
            return None
        paths = candidate_paths(op)
        if not paths:
            return None
        cp = stats.csv_profile(paths[0], features["file_bytes"], deadline=ctx.deadline)
        r, uq = cp.rows, cp.unique_fraction
        return {
            "n_rows": r.value,
            "rows_range": (r.low, r.value, r.high),
            "n_cols": cp.cols,
            "text_cols": cp.text_cols,
            "str_chars": cp.str_chars,
            "unique_fraction": uq.value,
            "unique_range": (uq.low, uq.value, uq.high),
            "bytes_per_field": cp.bytes_per_field,
            "tier1": {
                "sample": r.sample,
                "confidence": min(r.confidence, uq.confidence),
                "method": r.method,
                "bytes_read": cp.bytes_read,
                "exact": cp.exact,
            },
        }

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        size = features["file_bytes"]
        rows, cols = features.get("n_rows"), features.get("n_cols")
        if rows and cols:  # Tier 1 values present: a point estimate with the sampling band
            rr = features.get("rows_range") or (rows, rows, rows)
            ur = features.get("unique_range") or (features.get("unique_fraction") or 1.0,) * 3

            def peak_at(i: int) -> float:
                return parse_peak_bytes(
                    size,
                    rr[i],
                    cols,
                    text_cols=features.get("text_cols") or 0,
                    str_chars=features.get("str_chars") or 12.0,
                    unique_fraction=ur[i],
                )

            ram = (peak_at(0) * MODEL_BAND[0], peak_at(1), peak_at(2) * MODEL_BAND[1])
        else:
            w_lo, w_hi = FIELD_WIDTH_RANGE
            w_mid = (w_lo * w_hi) ** 0.5

            def at(width: float) -> float:
                fields = size / width
                return FILE_BYTE_FACTOR * size + (FIELD_BYTES + ROW_BYTES) * fields

            ram = (at(w_hi) * MODEL_BAND[0], at(w_mid), at(w_lo) * MODEL_BAND[1])
        return u.build(
            ram,
            u.time_band_for_tier(size / u.machine().csv_parse_bps, tier),
            0.4,
            tier,
            [
                "tokenizer text + per-field buffers and chunk concatenation (not just the frame)",
                "bytes per field unknown at Tier 0 (spans 2..24); text cells add new str objects",
            ],
        )
