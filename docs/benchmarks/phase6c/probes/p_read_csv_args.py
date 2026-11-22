"""Probe (RAM >= 200 MiB, OS peak, fresh process): read_csv with sep / dtype / usecols / header / nrows.

HYPOTHESES (pandas 3.1 C parser, ``pandas/_libs/parsers.pyx`` / ``io/parsers/c_parser_wrapper.py``):
* ``sep`` (one character) only changes the tokenizer's delimiter: same structure as the default read
  (the frozen model: 1.6 x file bytes + 13.5 B per field + 6 B per row + new str objects).
* the 13.5 B per field = the parsed value (8 B for int64 / float64 / object pointers) + ~5.5 B of token
  bookkeeping; ``dtype=`` changes the value size (float32 / int32: 4 B) and, for ``str``/``object`` on a
  numeric column, creates a new str object per field (like a text column).
* ``usecols``: the tokenizer still holds the whole file (1.6 x file bytes) but only kept columns are
  converted (per-field and string terms for kept columns only).
* ``nrows``: the parser stops after ``nrows`` rows: every term scales with the rows read.
* ``header=None``: the first line is data: no change in cost.

Files: 3M rows x (4 float, 3 int, 2 short text) written as CSV and TSV.

    python docs/benchmarks/phase6c/probes/p_read_csv_args.py
"""

from __future__ import annotations

import gc
import os
import tempfile

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
ROWS = 3_000_000
FIELD_BOOK = 5.5
FILE_FACTOR, ROW_BYTES = 1.6, 6.0


def write(tmp: str, sep: str, header: bool = True) -> tuple[str, list[str]]:
    rng = np.random.default_rng(3)
    cols = {f"f{i}": np.round(rng.random(ROWS) * 1000, 4) for i in range(4)}
    cols.update({f"i{i}": rng.integers(0, 10**6, ROWS) for i in range(3)})
    vocab = np.array([f"w{x:07d}" for x in range(5_000)], dtype=object)
    cols.update({f"s{i}": vocab[rng.integers(0, len(vocab), ROWS)] for i in range(2)})
    df = pd.DataFrame(cols)
    path = os.path.join(tmp, ("data" if header else "nohead") + (".tsv" if sep == "\t" else ".csv"))
    df.to_csv(path, index=False, sep=sep, header=header)
    return path, list(df.columns)


def run(args: tuple[str, dict]) -> int:
    path, kw = args
    return len(pd.read_csv(path, **kw))


def setup(path: str, kw: dict) -> tuple[str, dict]:
    gc.collect()
    return path, kw


def derived(path: str, file_bytes: int, kw: dict) -> float:
    """1.6 x bytes read + per kept field (value itemsize + 5.5) + 6 per row + new str objects, where the
    value size and which columns are text come from parsing one parser chunk with the same arguments."""
    from nexus.models.read_csv import string_object_bytes

    rows = kw.get("nrows", ROWS)
    head = pd.read_csv(path, **{**kw, "nrows": min(rows, 2**17)})
    chunk_rows = 2 ** int(np.floor(np.log2(2**20 // max(head.shape[1], 1))))
    total = FILE_FACTOR * file_bytes * rows / ROWS + ROW_BYTES * rows
    for c in head.columns:
        s = head[c]
        text = s.dtype == object or str(s.dtype) == "str"
        item = 8 if text else s.dtype.itemsize
        total += rows * (item + FIELD_BOOK)
        if text:
            part = s.iloc[:chunk_rows].dropna()
            uq = part.nunique() / max(len(part), 1)
            total += rows * uq * string_object_bytes(float(part.astype(str).str.len().mean()))
    return total


def main() -> None:
    print(f"pandas {pd.__version__}")
    with tempfile.TemporaryDirectory() as tmp:
        csv, _ = write(tmp, ",")
        tsv, _ = write(tmp, "\t")
        nohead, _ = write(tmp, "\t", header=False)
        variants = [
            ("csv default", csv, {}),
            ("tsv sep=tab", tsv, {"sep": "\t"}),
            ("tsv header=None", nohead, {"sep": "\t", "header": None}),
            ("csv dtype float32", csv, {"dtype": {f"f{i}": "float32" for i in range(4)}}),
            ("csv dtype str (all)", csv, {"dtype": str}),
            ("csv usecols 3 of 9", csv, {"usecols": ["f0", "i0", "s0"]}),
            ("csv nrows 1M", csv, {"nrows": 1_000_000}),
        ]
        print("variant              file MiB  measured MiB  derived MiB  ratio  time s")
        for name, path, kw in variants:
            size = os.path.getsize(path)
            m = measure_call(run, setup=setup, setup_args=(path, kw), repeats=3)
            want = derived(path, size, kw)
            got = m.delta_bytes
            g = "censored" if got is None else f"{got / MIB:9.0f}"
            ratio = "-" if got is None else f"{got / want:5.2f}"
            print(f"{name:20} {size / MIB:8.0f}  {g:>12}  {want / MIB:11.0f}  {ratio}  {m.time_s:6.2f}")


if __name__ == "__main__":
    main()
