# ruff: noqa: N806  (F, V, S, T, W, M: the derivation's notation)
"""Phase 7a probe 1a, analysis: candidate read_csv formulas (derived from pandas 3.1.1 ``io/parsers/readers.py``
after the first run contradicted the low_memory hypothesis) against the measured peaks of ``p1a_read_csv.out``.

pandas 3.1.1 reads a local, uncompressed file >= 5 MiB with the C engine through ``_read_csv_parallel``
when ``_can_parallelize_csv`` holds (no ``usecols``, ``nrows``, ``parse_dates``, ``index_col``,
``chunksize`` / iterator, comment / escapechar / dialect, list header, skipfooter, non-int skiprows,
``low_memory=False``, multi-character separators other than ``\\s+``, encodings other than UTF-8) and
``_default_n_workers()`` = min(cpu_count, 6, CPUs available to the process) > 1. Otherwise the serial
low_memory reader runs. Derived terms:

* parallel, direct block assembly (dtype None / a non-text scalar dtype):
  ``F + 2 V + S``: the mmapped file's pages (resident while the workers parse), the per-chunk column
  arrays (V) and the final blocks they are copied into (V); the workers' parser buffers are freed in
  parallel with the copy. Text columns take the "leftover" path after the mmap is closed (S below).
* parallel, ``dtype`` dict or str/object ("series wrap"): the mmap is closed BEFORE the per-column
  concatenation, and the readers are closed after the parse: ``max(F + V + W, V + V_col)``
  with W = workers x parser buffers of one chunk (``chunk_bytes x (1 + 16 / bytes_per_field)``: the
  chunk's text plus an 8 B word pointer and an 8 B word start per field).
* serial: ``V + S + T`` with T = one low_memory chunk of the tokenizer: ``buffer_lines`` rows of ALL
  file columns (``2**floor(log2(2**20 / columns))``) x (line bytes + 16 B per field).
* S (text): 8 B pointer per text field + new ``str`` objects (``string_object_bytes`` x the per-chunk
  unique share that ``stats.csv_profile`` estimates; the Tier 1 statistic as frozen).

V = rows x the kept columns' itemsizes (numeric) - exactly what Tier 1's ``value_bytes_per_row`` gives.

    python docs/benchmarks/phase7a/probes/p1a_analysis.py <scratch dir of p1a> > docs/benchmarks/phase7a/probes/p1a_analysis.out
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from nexus.models.read_csv import parse_peak_bytes, string_object_bytes
from nexus.stats import csv_profile

MIB = 2**20
WORKERS = 6  # min(16 logical CPUs, 6) on the probe machine
CHUNK = 4 * 1024 * 1024


def kept_itemsizes(r: dict) -> list[int]:
    cols, text = r["cols"], r["text_cols"]
    if r["variant"] == "dtype float32 all 16":
        return [4] * 16
    if r["variant"] == "dtype float32 half":
        return [4] * 8 + [8] * 8
    return [8] * (cols - text)


def main() -> None:
    tmp = Path(sys.argv[1])
    rows = [json.loads(x) for x in Path("docs/benchmarks/phase7a/probes/p1a_read_csv.out").read_text().splitlines()
            if x.startswith('{"variant"')]  # fmt: skip
    print("variant | path | measured MiB | candidate MiB | ratio | frozen Tier 1 formula ratio")
    out = []
    for r in rows:
        kw = r["kwargs"]
        n, F = r["rows"], r["file_bytes"]
        V = n * sum(kept_itemsizes(r))
        prof = csv_profile(
            str(tmp / (r["file"] + ".csv")),
            F,
            read_kwargs={"sep": "\t"} if "tsv" in r["file"] else None,
        )
        total_cols = prof.total_cols
        bpf = prof.bytes_per_field
        S = 0.0
        if r["text_cols"]:
            S = (
                n
                * r["text_cols"]
                * (8 + prof.unique_fraction.value * string_object_bytes(prof.str_chars))
            )
        serial = any(k in kw for k in ("usecols", "nrows", "parse_dates"))
        if serial:
            lines = 2 ** int(math.floor(math.log2(2**20 / total_cols)))
            T = lines * (bpf * total_cols + 16 * total_cols)
            cand, path = V + S + T, "serial"
        elif "dtype" in kw and kw["dtype"].startswith("{"):
            W = WORKERS * CHUNK * (1 + 16 / bpf)
            cand, path = (
                max(F + V + W, V + V / max(len(kept_itemsizes(r)), 1)) + S,
                "parallel, series wrap",
            )
        else:
            cand, path = F + 2 * V + S, "parallel, direct"
        frozen = parse_peak_bytes(F, n, r["cols"], text_cols=r["text_cols"], str_chars=prof.str_chars or 12.0,
                                  unique_fraction=prof.unique_fraction.value)  # fmt: skip
        out.append({"variant": r["variant"], "path": path, "measured": r["peak"], "candidate": cand,
                    "ratio": r["peak"] / cand, "frozen_ratio": r["peak"] / frozen})  # fmt: skip
        print(
            f"{r['variant']} | {path} | {r['peak'] / MIB:.0f} | {cand / MIB:.0f} | {r['peak'] / cand:.3f} | {r['peak'] / frozen:.3f}"
        )
    for path in sorted({o["path"] for o in out}):
        rs = [o["ratio"] for o in out if o["path"] == path]
        print(json.dumps({"path": path, "n": len(rs), "min_ratio": min(rs), "max_ratio": max(rs)}))
    fr = [o["frozen_ratio"] for o in out]
    print(json.dumps({"frozen_formula_with_true_shape": {"min": min(fr), "max": max(fr)}}))


if __name__ == "__main__":
    main()
