"""Tier 0 / Tier 1 model for ``pandas.read_csv``."""

from __future__ import annotations

import math
from typing import Any

from nexus import stats
from nexus.analyzer import DetectedOp, Expr
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel, Tier1Context
from nexus.registry import register_model
from nexus.state import Inspection, candidate_paths

# Peak-RAM structure of ``pd.read_csv(path)`` with the default C engine (pandas 3.1), in bytes. The
# coefficients were measured with isolated probes on synthetic files (see the class docstring), not
# on benchmark points. Since Phase 7b used for Tier 0 and for text files on the parallel reader only.
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

# -- pandas 3.1 reader paths (Phase 7b; docs/benchmarks/phase7a/probes/p1a_*, phase7b/probes/) ---------
# ``readers._read_csv_parallel`` reads a local, uncompressed file >= 5 MiB with threads when
# ``_can_parallelize_csv`` holds and ``_default_n_workers()`` > 1. Derived peaks (F = file bytes,
# V = rows x the kept columns' itemsizes, S = new str objects, T = one serial tokenizer chunk,
# W = the workers' parser buffers):
#   "parallel":      F + 2V   the mmapped file + per-chunk column arrays + the final blocks (1.003-1.018)
#   "parallel_wrap": F + V + W  a ``dtype`` dict: the mmap closes before the per-column concat (1.008)
#   "serial":        [V + S, V + S + T]  low_memory chunks; the point term was contradicted (0.71-0.92)
#   "unknown":       this pandas has no parallel reader helpers: a range over both paths
PARALLEL_MIN_BYTES = 5 * 1024 * 1024  # pandas _PARALLEL_READ_MIN_BYTES
PARALLEL_CHUNK_BYTES = 4 * 1024 * 1024  # pandas _PARALLEL_CHUNK_BYTES
TOKEN_BYTES_PER_FIELD = 16.0  # tokenizer word pointer + word start per field
COMPRESSED_SUFFIXES = (".gz", ".bz2", ".zip", ".xz", ".zst", ".tar")
TEXT_DTYPES = frozenset({"str", "string", "object", "O"})
READER_DRIVERS = {
    "parallel": "parallel reader: mmapped file + per-chunk values + final blocks",
    "parallel_wrap": "parallel reader (dtype dict): mmapped file + values + worker buffers",
    "serial": "serial reader: values + one tokenizer chunk",
    "unknown": "reader path unknown (parallel or serial): range over both",
}


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
    """Peak bytes of the default read given what Tier 1 can learn from a header/row sample (v2 formula).

    ``unique_fraction`` is the share of text cells that become a NEW ``str`` object (the parser
    reuses an object only for a repeat inside the same chunk of 2**k rows, so even low-cardinality
    columns create many).
    """
    base = FILE_BYTE_FACTOR * file_bytes + FIELD_BYTES * rows * cols + ROW_BYTES * rows
    return base + text_cols * rows * unique_fraction * string_object_bytes(str_chars)


def parallel_workers() -> int | None:
    """pandas' own worker count for a parallel read (``mode.max_threads``, else min(cpu_count, 6, the
    CPUs the process may use: affinity and cgroup quota where pandas probes them, i.e. Linux)); None
    if this pandas has no parallel reader (the reader path is then unknown)."""
    try:
        from pandas.io.parsers.readers import _default_n_workers, _read_csv_parallel  # noqa: F401

        return int(_default_n_workers())
    except Exception:
        return None


def reader_path(path: str, file_bytes: float, kw: dict[str, Any]) -> tuple[str, int | None]:
    """(reader path, workers) pandas takes for ``read_csv(path, **kw)``, ``kw`` = understood arguments."""
    workers = parallel_workers()
    if "usecols" in kw or "nrows" in kw:
        return "serial", workers
    if file_bytes < PARALLEL_MIN_BYTES or str(path).lower().endswith(COMPRESSED_SUFFIXES):
        return "serial", workers
    if workers is None:
        return "unknown", None
    if workers <= 1:
        return "serial", workers
    return ("parallel_wrap" if isinstance(kw.get("dtype"), dict) else "parallel"), workers


def serial_chunk_bytes(total_cols: int, bytes_per_field: float, rows: float) -> float:
    """One low_memory tokenizer chunk: ``2**floor(log2(2**20 / columns))`` rows of ALL file columns."""
    lines = min(2 ** int(math.floor(math.log2(max(2**20 / max(total_cols, 1), 2)))), max(rows, 1.0))
    return lines * total_cols * (bytes_per_field + TOKEN_BYTES_PER_FIELD)


def worker_buffer_bytes(workers: int, bytes_per_field: float) -> float:
    """The parallel workers' parser buffers: one chunk's text + word pointer / start per field each."""
    return (
        workers * PARALLEL_CHUNK_BYTES * (1.0 + TOKEN_BYTES_PER_FIELD / max(bytes_per_field, 1.0))
    )


def _numeric(dtype: str) -> bool:
    try:
        import numpy as np

        return np.dtype(dtype).kind in "iufb"
    except TypeError:
        return False


@register_model
class ReadCsvModel(OperationModel):
    """Peak RAM and time of ``pd.read_csv("path", ...)``.

    RAM, Tier 1 (Phase 7b, derived from pandas 3.1.1 ``io/parsers/readers.py`` and confirmed by
    isolated probes, ``docs/benchmarks/phase7a/probes/p1a_*`` and ``docs/benchmarks/phase7b/probes/``):
    which reader runs decides the structure (``reader_path``, module comment above). All-numeric files
    get the derived terms. Files with text columns on the parallel path keep the v2 formula
    ``parse_peak_bytes`` (Phase 2 probes): the text term of the new structure was not confirmed
    (1.05-1.26) and is out of scope. The serial path (``usecols``, ``nrows``, files < 5 MiB, one
    worker) is a range, since its derived chunk term over-estimated the measured one. ``dtype`` with
    numeric targets changes the kept itemsizes (the sample is parsed with the call's own arguments);
    ``na_values`` changes only tokenizing. ``parse_dates``, text ``dtype`` targets,
    ``low_memory=False``, ``chunksize`` and other arguments keep Tier 0 (not derived).

    Tier 0 sees only the file size (unchanged from v2): the bytes per field ``w`` span
    ``FIELD_WIDTH_RANGE``, scaled by the +-20% band; ``expected`` uses the geometric middle width.

    Time ~ file size / parse throughput (unchanged in Phase 4a).
    """

    name = "read_csv"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "pandas.read_csv"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        paths = [p for p in candidate_paths(op) if p in state.files]
        if not paths:
            raise NoEstimateError("file path unknown or not found on disk")
        size = state.files[paths[0]].nbytes
        kw = self.read_kwargs(op)
        path, workers = reader_path(paths[0], size, kw) if kw is not None else ("unsupported", None)
        return {
            "file_bytes": size,
            "n_rows": None,  # Tier 1 fills from a header/row sample
            "n_cols": None,
            "text_cols": None,
            "str_chars": None,
            "unique_fraction": None,
            "reader_path": path,
            "workers": workers,
            "subset_read": bool(kw) and ("nrows" in kw or "usecols" in kw),
            "parse_dates": kw.get("parse_dates") if kw else None,
        }

    # options that change what the parser allocates; statistics assume the plain call
    _PLAIN_KWARGS = frozenset({"filepath_or_buffer", "encoding", "low_memory"})
    # Phase 6c: tokenizing only (one-character ``sep`` / ``delimiter``, ``header`` 0 / None); Phase 7b:
    # ``na_values`` (tokenizing only, probe 1.006), ``usecols`` / ``nrows`` (serial reader) and
    # ``dtype`` with numeric targets (kept itemsizes; a dict takes the parallel series-wrap branch).
    _TOKENIZING_KWARGS = frozenset({"sep", "delimiter", "header", "na_values"})
    _SHAPE_KWARGS = frozenset({"usecols", "nrows", "dtype"})

    @classmethod
    def read_kwargs(cls, op: DetectedOp) -> dict[str, Any] | None:  # noqa: C901
        """The understood arguments for the sampler, or None if any argument is not understood."""
        kw = op.kwargs
        allowed = cls._PLAIN_KWARGS | cls._TOKENIZING_KWARGS | cls._SHAPE_KWARGS
        if len(op.args) > 1 or any(k not in allowed for k in kw):
            return None
        if "sep" in kw and "delimiter" in kw:
            return None
        if any(isinstance(v, Expr) for v in kw.values()):
            return None  # a computed argument: its value is unknown
        if kw.get("low_memory", True) is not True:
            return None  # low_memory=False reads in one piece: not derived
        enc = kw.get("encoding")
        if enc is not None and str(enc).lower().replace("_", "-") not in (
            "utf-8",
            "utf8",
            "utf-8-sig",
        ):
            return None
        out: dict[str, Any] = {}
        if "parse_dates" in kw:
            parsed = kw["parse_dates"]
            if not (isinstance(parsed, (bool, list, tuple))):
                return None
            out["parse_dates"] = parsed
        sep = kw.get("sep", kw.get("delimiter", ","))
        if not isinstance(sep, str) or len(sep) != 1 or ord(sep) > 127:
            return None  # sniffing (None), regex or multi-character separators: the python engine
        if sep != ",":
            out["sep"] = sep
        if "header" in kw:
            if kw["header"] not in (0, None, "infer"):
                return None
            if kw["header"] is None:
                out["header"] = None
        if "na_values" in kw:
            na = kw["na_values"]
            if not (
                isinstance(na, str)
                or (isinstance(na, list) and all(isinstance(x, str) for x in na))
            ):
                return None
            out["na_values"] = na
        if "usecols" in kw:
            cols = kw["usecols"]
            if not (
                isinstance(cols, list) and cols and all(isinstance(c, (str, int)) for c in cols)
            ):
                return None
            out["usecols"] = cols
        if "nrows" in kw:
            n = kw["nrows"]
            if not isinstance(n, int) or isinstance(n, bool) or n < 0:
                return None
            out["nrows"] = n
        if "dtype" in kw:
            dt = kw["dtype"]
            targets = list(dt.values()) if isinstance(dt, dict) else [dt]
            if not all(
                isinstance(t, str) and t not in TEXT_DTYPES and _numeric(t) for t in targets
            ):
                return None  # text / extension targets: not derived
            out["dtype"] = dt
        return out

    def tier1_features(
        self, op: DetectedOp, features: dict[str, Any], ctx: Tier1Context
    ) -> dict[str, Any] | None:
        """Rows, kept columns and their itemsizes, text columns, string length and per-chunk string
        uniqueness from the head of the file plus three seeked chunks (at most 1.75 MiB read), parsed
        with the call's own arguments; ``nrows`` caps the row estimate."""
        kw = self.read_kwargs(op)
        if kw is None or features.get("reader_path") == "unsupported":
            return None
        paths = candidate_paths(op)
        if not paths:
            return None
        sample_kw = {k: v for k, v in kw.items() if k != "nrows"}
        cp = stats.csv_profile(
            paths[0], features["file_bytes"], deadline=ctx.deadline, read_kwargs=sample_kw or None
        )
        r, uq = cp.rows, cp.unique_fraction
        rows = (r.low, r.value, r.high)
        if "nrows" in kw:
            rows = tuple(min(float(kw["nrows"]), x) for x in rows)
        return {
            "n_rows": rows[1],
            "rows_range": rows,
            "n_cols": cp.cols,
            "total_cols": cp.total_cols,
            "text_cols": cp.text_cols,
            "str_chars": cp.str_chars,
            "unique_fraction": uq.value,
            "unique_range": (uq.low, uq.value, uq.high),
            "bytes_per_field": cp.bytes_per_field,
            "value_bytes_per_row": cp.value_bytes_per_row,
            "dtypes": cp.dtypes,  # for a frame created in the cell (nexus.cellframes)
            "tier1": {
                "sample": r.sample,
                "confidence": min(r.confidence, uq.confidence),
                "method": r.method,
                "bytes_read": cp.bytes_read,
                "exact": cp.exact,
            },
        }

    @staticmethod
    def tier1_ram(features: dict[str, Any]) -> tuple[float, float, float]:
        """(low, expected, high) of the Tier 1 estimate for the features' reader path."""
        size = float(features["file_bytes"])
        rows, cols = features["n_rows"], features["n_cols"]
        rr = features.get("rows_range") or (rows, rows, rows)
        ur = features.get("unique_range") or (features.get("unique_fraction") or 1.0,) * 3
        text = features.get("text_cols") or 0
        chars = features.get("str_chars") or 12.0
        path = features.get("reader_path", "parallel")
        vbr = features.get("value_bytes_per_row") or 8.0 * cols
        bpf = features.get("bytes_per_field") or 18.0
        total = features.get("total_cols") or cols

        def frozen(i: int) -> float:
            return parse_peak_bytes(
                size, rr[i], cols, text_cols=text, str_chars=chars, unique_fraction=ur[i]
            )

        def strings(i: int) -> float:
            return text * rr[i] * ur[i] * string_object_bytes(chars)

        values = [rr[i] * vbr for i in range(3)]
        serial = (
            values[0] + strings(0),
            values[1] + strings(1) + serial_chunk_bytes(total, bpf, rr[1]) / 2.0,
            (values[2] + strings(2) + serial_chunk_bytes(total, bpf, rr[2])) * MODEL_BAND[1],
        )
        if path == "serial":
            return serial
        if text:  # the parallel text term is not derived: the v2 formula (pre-registered)
            par = (frozen(0) * MODEL_BAND[0], frozen(1), frozen(2) * MODEL_BAND[1])
        elif path == "parallel_wrap":
            w = worker_buffer_bytes(int(features.get("workers") or 1), bpf)
            par = (
                (size + values[0] + w) * MODEL_BAND[0],
                size + values[1] + w,
                (size + values[2] + w) * MODEL_BAND[1],
            )
        else:
            par = (
                (size + 2 * values[0]) * MODEL_BAND[0],
                size + 2 * values[1],
                (size + 2 * values[2]) * MODEL_BAND[1],
            )
        if path == "unknown":  # either reader may run
            return (min(serial[0], par[0]), par[1], max(serial[2], par[2]))
        return par

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        size = features["file_bytes"]
        rows, cols = features.get("n_rows"), features.get("n_cols")
        if rows and cols:  # Tier 1 values present
            ram = self.tier1_ram(features)
            driver = READER_DRIVERS.get(features.get("reader_path", "parallel"), "parser")
        else:
            w_lo, w_hi = FIELD_WIDTH_RANGE
            w_mid = (w_lo * w_hi) ** 0.5

            def at(width: float) -> float:
                fields = size / width
                return FILE_BYTE_FACTOR * size + (FIELD_BYTES + ROW_BYTES) * fields

            ram = (at(w_hi) * MODEL_BAND[0], at(w_mid), at(w_lo) * MODEL_BAND[1])
            if features.get("subset_read"):
                # nrows / usecols read part of the file: any cost from ~0 up to the whole read
                ram = (0.0, ram[1], ram[2])
            elif features.get("reader_path") == "serial":
                # the serial reader holds the values plus one chunk: at least 8 B per field of the whole
                # file (fields >= size / 24); probe A (max_threads=1): 144 MiB for a 296 MiB file
                ram = (8.0 * size / w_hi, ram[1], ram[2])
            driver = (
                "tokenizer text + per-field buffers and chunk concatenation (not just the frame)"
            )
        parsed = features.get("parse_dates")
        if parsed is not None:
            count = len(parsed) if isinstance(parsed, (list, tuple)) else 1
            rows = features.get("n_rows") or 0.0
            extra = count * rows * 8.0
            ram = (ram[0] + extra * 0.85, ram[1] + extra, ram[2] + extra * 1.15)
            driver = f"{driver}; parse_dates datetime arrays ({count} columns)"
        return u.build(
            ram,
            u.time_band_for_tier(tt.read_csv(features), tier),
            0.4,
            tier,
            [
                driver,
                "bytes per field unknown at Tier 0 (spans 2..24); text cells add new str objects",
            ],
        )
