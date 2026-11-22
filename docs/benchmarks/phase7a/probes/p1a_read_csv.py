# ruff: noqa: N806  (F, V, S, T, W, M: the derivation's notation)
"""Phase 7a probe 1a (information only): what the peak of ``pd.read_csv`` scales with.

Isolated (``nexus.measure.measure_call``: fresh spawned process, file on disk, incremental OS peak,
median of 3), mains power required, every variant's peak >= 200 MiB unless stated.

HYPOTHESIS (derived from pandas 3.1.1 source before measuring; not fitted):
``c_parser_wrapper.CParserWrapper.read`` (low_memory=True) -> ``TextReader.read_low_memory`` parses
the file in chunks of ``buffer_lines`` rows and keeps every chunk's converted column arrays; then
``_concatenate_chunks`` pops one column at a time from all chunks and concatenates it (peak during
this step: all values once + one column twice), and ``DataFrame(dict, copy=False)`` consolidates the
same-dtype columns into 2-D blocks (``np.vstack``: a second copy of the numeric values while the dict
still holds the columns). So

    peak ~= R + V2 + T

* R  = the retained frame (``memory_usage(deep=True)``: values + pointers + new str objects),
* V2 = the second copy made by consolidation: the numeric value bytes of dtype groups with more than
       one column (a single-column group is not copied) plus 8 B per text field (pointer array);
       str objects themselves are not copied,
* T  = per-chunk tokenizer state (raw chunk text + word pointers / starts), bounded by one chunk:
       independent of the number of rows, small against 200 MiB.

Consequences to check: the peak scales with the KEPT, CONVERTED columns (not the file bytes);
``usecols`` keeps the scaling to the kept columns, ``dtype=float32`` halves V2 and R, ``nrows`` scales
everything by the rows read; ``sep`` / ``header`` change nothing; ``na_values`` adds nothing beyond a
float column instead of an int one; ``parse_dates`` converts after the read (an extra object->datetime
pass: + the string column's objects until it is replaced).

    python docs/benchmarks/phase7a/probes/p1a_read_csv.py <scratch dir> > docs/benchmarks/phase7a/probes/p1a_read_csv.out
"""

from __future__ import annotations

import gc
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call
from nexus.models.read_csv import parse_peak_bytes
from nexus.power import power_state

MIB = 2**20


def make(
    path: Path, rows: int, spec: str, *, sep: str = ",", header: bool = True, seed: int = 7
) -> None:
    if path.exists():
        return
    rng = np.random.default_rng(seed)
    cols: dict[str, object] = {}
    for part in spec.split("+"):
        kind, n = part[0], int(part[1:])
        for i in range(n):
            name = f"{kind}{i}"
            if kind == "F":
                cols[name] = rng.random(rows)
            elif kind == "I":
                cols[name] = rng.integers(0, 10**6, rows)
            elif kind == "L":  # low-cardinality text, 8 chars
                vocab = np.array([f"w{x:07d}" for x in range(1000)], dtype=object)
                cols[name] = vocab[rng.integers(0, len(vocab), rows)]
            elif kind == "U":  # unique text, 12 chars
                cols[name] = np.char.add(
                    "u", np.char.zfill((rng.permutation(rows)).astype(str), 11)
                ).astype(object)
            elif kind == "N":  # float with 10% missing, written as "NA"
                v = rng.random(rows)
                v[rng.random(rows) < 0.1] = np.nan
                cols[name] = v
            elif kind == "D":  # ISO dates
                base = np.datetime64("2000-01-01")
                cols[name] = (base + rng.integers(0, 9000, rows)).astype(str).astype(object)
    df = pd.DataFrame(cols)
    df.to_csv(path, index=False, sep=sep, header=header, na_rep="NA")
    del df
    gc.collect()


def run(args: tuple[str, dict]) -> pd.DataFrame:
    path, kw = args
    return pd.read_csv(path, **kw)


def setup(path: str, kw: dict) -> tuple[str, dict]:
    gc.collect()
    return path, kw


def summarize(df: pd.DataFrame) -> dict:
    mu = df.memory_usage(deep=True)
    text = [c for c in df.columns if df[c].dtype == object or str(df[c].dtype) == "str"]
    groups: dict[str, int] = {}
    for c in df.columns:
        if c not in text:
            groups[str(df[c].dtype)] = groups.get(str(df[c].dtype), 0) + 1
    num_multi = sum(int(df[c].memory_usage(index=False, deep=False)) for c in df.columns
                    if c not in text and groups[str(df[c].dtype)] > 1)  # fmt: skip
    return {"rows": len(df), "cols": df.shape[1], "retained": int(mu.sum()), "text_cols": len(text),
            "num_multi_bytes": num_multi, "text_ptr_bytes": 8 * len(df) * len(text),
            "dtypes": sorted({str(t) for t in df.dtypes})}  # fmt: skip


def main() -> None:
    if power_state() == "battery":
        raise SystemExit("on battery power: plug in first")
    tmp = Path(sys.argv[1])
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"pandas {pd.__version__} numpy {np.__version__} power {power_state()}")
    M = 1_000_000
    files = {
        "F8_1M": (M, "F8", ","), "F8_2M": (2 * M, "F8", ","), "F8_4M": (4 * M, "F8", ","),
        "F4_2M": (2 * M, "F4", ","), "F16_2M": (2 * M, "F16", ","), "I8_2M": (2 * M, "I8", ","),
        "L8_2M": (2 * M, "L8", ","), "U4_1M": (M, "U4", ","), "MIX_2M": (2 * M, "F4+I2+L2", ","),
        "F8_2M_tsv": (2 * M, "F8", "\t"), "N8_2M": (2 * M, "N8", ","), "D1F4_2M": (2 * M, "D1+F4", ","),
    }  # fmt: skip
    for name, (rows, spec, sep) in files.items():
        make(tmp / f"{name}.csv", rows, spec, sep=sep)
    make(tmp / "F8_2M_nohead.csv", 2 * M, "F8", header=False)
    f16 = [f"F{i}" for i in range(16)]
    variants = [
        ("rows 1M  8 float", "F8_1M", {}), ("rows 2M  8 float", "F8_2M", {}), ("rows 4M  8 float", "F8_4M", {}),
        ("cols 4 float 2M", "F4_2M", {}), ("cols 16 float 2M", "F16_2M", {}),
        ("8 int 2M", "I8_2M", {}), ("8 lowcard text 2M", "L8_2M", {}), ("4 unique text 1M", "U4_1M", {}),
        ("mix 4F 2I 2L 2M", "MIX_2M", {}),
        ("usecols 2 of 16", "F16_2M", {"usecols": f16[:2]}), ("usecols 8 of 16", "F16_2M", {"usecols": f16[:8]}),
        ("dtype float32 all 16", "F16_2M", {"dtype": "float32"}),
        ("dtype float32 half", "F16_2M", {"dtype": dict.fromkeys(f16[:8], "float32")}),
        ("nrows 500k of 2M x16", "F16_2M", {"nrows": 500_000}), ("nrows 1M of 2M x16", "F16_2M", {"nrows": 1_000_000}),
        ("sep tab 8 float", "F8_2M_tsv", {"sep": "\t"}), ("header None 8 float", "F8_2M_nohead", {"header": None}),
        ("8 float 10% NA", "N8_2M", {}), ("8 float NA na_values", "N8_2M", {"na_values": ["NA", "-"]}),
        ("date+4F no parse", "D1F4_2M", {}), ("date+4F parse_dates", "D1F4_2M", {"parse_dates": ["D0"]}),
    ]  # fmt: skip
    out = []
    for label, fname, kw in variants:
        path = str(tmp / (fname + ".csv"))
        size = os.path.getsize(path)
        m = measure_call(run, setup=setup, setup_args=(path, kw), summarize=summarize, repeats=3)
        info = m.info.get("summary", m.info)
        rec = {"variant": label, "file": fname, "kwargs": {k: str(v)[:40] for k, v in kw.items()},
               "file_bytes": size, "status": m.status, "peak": m.delta_bytes, "spread": m.ram_spread,
               "time_s": m.time_s, "power": power_state(), **info}  # fmt: skip
        out.append(rec)
        print(json.dumps(rec), flush=True)
    # frozen-model comparison for the plain reads (Tier 1 formula with the true shape)
    for r in out:
        if not r.get("peak") or r["kwargs"]:
            continue
        frozen = parse_peak_bytes(r["file_bytes"], r["rows"], r["cols"], text_cols=r["text_cols"])
        print(
            json.dumps(
                {
                    "frozen_formula_true_shape": r["variant"],
                    "frozen": frozen,
                    "ratio": r["peak"] / frozen,
                }
            )
        )


if __name__ == "__main__":
    main()
