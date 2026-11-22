"""Seeded random-row subsample copies of the real notebook data (Phase 6c item D; DEV data only).

Streams each input file line by line (the originals are only read), keeps the header line and each data
line with probability ``fraction`` (seeded), and writes the copy under ``<out>/<parent dir>/<name>`` so
the notebooks' relative layout is kept. Line-based: a quoted field containing a newline would be split
(the inventory's TSV inputs are plain line records). Writes ``path_map.json`` (notebook literal -> copy)
next to each notebook's results. Nothing is printed except counts.

    python -m benchmarks.realworld.subsample --fraction 0.22 --out benchmarks/results/realworld/subsample
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

INVENTORY = Path("benchmarks/results/realworld/inventory.json")
DATA_SUFFIXES = (".tsv", ".csv", ".txt")


def subsample(src: Path, dst: Path, fraction: float, seed: int) -> tuple[int, int]:
    rng = random.Random(f"{seed}:{src.name}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    kept = total = 0
    with src.open("rb") as fin, dst.open("wb") as fout:
        fout.write(fin.readline())  # header
        for line in fin:
            total += 1
            if rng.random() < fraction:
                fout.write(line)
                kept += 1
    return kept, total


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.realworld.subsample")
    ap.add_argument("--fraction", type=float, default=0.22)
    ap.add_argument("--seed", type=int, default=6)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    books = json.loads(INVENTORY.read_text())
    done: dict[str, Path] = {}
    for b in books:
        pm = {}
        for ref, f in b["files"].items():
            if not f["resolved"] or not ref.lower().endswith(DATA_SUFFIXES):
                continue
            src = Path(f["resolved_path"])
            dst = args.out / src.parent.name / src.name
            if str(src) not in done:
                kept, total = subsample(src, dst, args.fraction, args.seed)
                print(f"{src.parent.name}/{src.name}: kept {kept:,} of {total:,} rows")
                done[str(src)] = dst
            pm[ref] = str(done[str(src)].resolve()).replace(chr(92), "/")
        target = Path("benchmarks/results/realworld") / f"{b['name']}_sub"
        target.mkdir(parents=True, exist_ok=True)
        (target / "path_map.json").write_text(json.dumps(pm, indent=1))


if __name__ == "__main__":
    main()
