"""Read-only inventory of notebooks for Phase 8a (never executes, never modifies a notebook).

Per notebook: code-cell count, imported top-level modules (flags for GPU / deep-learning stacks,
gradient-boosting libraries, multiprocessing; whether each is installed here), referenced data
files (string literals with a data extension) with their size on disk and whether the path
resolves, magic / shell cells, and cells that look expensive. The report holds no cell code and
no data values: only counts, module names, file names, sizes and cell hashes.

    python -m benchmarks.realworld.inventory C:/dev/nb_corpus --search C:/dev C:/Users/<you>/Downloads \
        --out docs/benchmarks/phase8a/inventory.md --json benchmarks/results/realworld/inventory.json
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any

DATA_EXT = (".csv", ".parquet", ".pq", ".feather", ".pkl", ".pickle", ".npy", ".npz", ".json",
            ".jsonl", ".zip", ".gz", ".tsv", ".xlsx", ".h5", ".hdf5", ".txt", ".joblib")  # fmt: skip
GPU_DL = {"torch", "tensorflow", "keras", "transformers", "jax", "cupy", "cudf", "sentence_transformers",
          "timm", "torchvision", "accelerate"}  # fmt: skip
BOOSTING = {"xgboost", "lightgbm", "catboost"}
PARALLEL = {"multiprocessing", "joblib", "concurrent", "dask", "ray"}
SHELL = re.compile(r"^\s*(!|%pip|%conda|%%bash|%%sh|%system|%%script|%%cmd|%%powershell)", re.M)
MAGIC = re.compile(r"^\s*%", re.M)
EXPENSIVE_CALLS = {"fit", "fit_transform", "train", "cross_val_score", "GridSearchCV", "apply", "explode",
                   "transform", "predict", "merge", "groupby", "read_csv", "read_parquet", "concat",
                   "TfidfVectorizer", "encode"}  # fmt: skip


def cell_hash(src: str) -> str:
    return hashlib.sha256(src.encode("utf-8")).hexdigest()[:12]


def _source(cell: dict[str, Any]) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else str(s)


def _strip_magics(src: str) -> str:
    return "\n".join(
        "" if line.lstrip().startswith(("%", "!")) else line for line in src.splitlines()
    )


def analyse_cell(src: str) -> dict[str, Any]:
    out: dict[str, Any] = {"imports": set(), "files": set(), "calls": set(), "loops": 0,
                           "parses": True, "shell": bool(SHELL.search(src)),
                           "magic": bool(MAGIC.search(src))}  # fmt: skip
    try:
        tree = ast.parse(_strip_magics(src))
    except SyntaxError:
        out["parses"] = False
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out["imports"].update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out["imports"].add(node.module.split(".")[0])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.strip()
            if v.lower().endswith(DATA_EXT) and len(v) < 300 and "\n" not in v:
                out["files"].add(v)
        elif isinstance(node, ast.Call):
            f = node.func
            name = (
                f.attr
                if isinstance(f, ast.Attribute)
                else f.id
                if isinstance(f, ast.Name)
                else None
            )
            if name:
                out["calls"].add(name)
        elif isinstance(node, (ast.For, ast.While)):
            out["loops"] += 1
    return out


def resolve(
    ref: str, nb_dir: Path, search: list[Path], index: dict[str, list[Path]]
) -> Path | None:
    p = Path(ref)
    for cand in [p] if p.is_absolute() else [nb_dir / p, *[s / p for s in search]]:
        if cand.exists():
            return cand
    hits = index.get(p.name.lower(), [])
    return hits[0] if len(hits) == 1 else None


def build_index(search: list[Path], names: set[str], max_depth: int = 6) -> dict[str, list[Path]]:
    wanted = {n.lower() for n in names}
    index: dict[str, list[Path]] = {}
    for root in search:
        root_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = len(Path(dirpath).parts) - root_depth
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in
                           ("node_modules", "__pycache__", ".git", ".cache", "site-packages")]  # fmt: skip
            if depth >= max_depth:
                dirnames[:] = []
            for f in filenames:
                if f.lower() in wanted:
                    index.setdefault(f.lower(), []).append(Path(dirpath) / f)
    return index


def installed(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def inventory(folder: Path, search: list[Path]) -> list[dict[str, Any]]:
    books = []
    for nb in sorted(folder.glob("*.ipynb"), key=lambda p: p.stat().st_size):
        raw = json.loads(nb.read_text(encoding="utf-8"))
        cells = [c for c in raw.get("cells", []) if c.get("cell_type") == "code"]
        per = [analyse_cell(_source(c)) | {"hash": cell_hash(_source(c)), "index": i}
               for i, c in enumerate(cells)]  # fmt: skip
        books.append({"name": nb.stem, "path": nb, "bytes": nb.stat().st_size, "cells": per})
    all_files = {Path(f).name for b in books for c in b["cells"] for f in c["files"]}
    index = build_index(search, all_files) if search else {}
    for b in books:
        imports = sorted({m for c in b["cells"] for m in c["imports"]})
        b["imports"] = {m: installed(m) for m in imports}
        files = {}
        for c in b["cells"]:
            for ref in c["files"]:
                hit = resolve(ref, b["path"].parent, search, index)
                files[ref] = {"resolved": hit is not None, "bytes": hit.stat().st_size if hit else None,
                              "resolved_path": str(hit) if hit else None,
                              "candidates": len(index.get(Path(ref).name.lower(), []))}  # fmt: skip
        b["files"] = files
    return books


def report(books: list[dict[str, Any]]) -> str:
    lines = ["# Phase 8a inventory (read-only; nothing executed; no cell code or data values)", ""]
    for b in books:
        cells = b["cells"]
        flags = []
        for label, group in (("GPU / deep learning", GPU_DL), ("gradient boosting", BOOSTING),
                             ("parallelism", PARALLEL)):  # fmt: skip
            hit = sorted(set(b["imports"]) & group)
            if hit:
                flags.append(f"{label}: {', '.join(hit)}")
        missing = sorted(m for m, ok in b["imports"].items() if not ok)
        expensive = [
            c
            for c in cells
            if (c["calls"] & EXPENSIVE_CALLS and c["loops"]) or {"fit", "train"} & c["calls"]
        ]
        lines += [
            f"## {b['name']} ({b['bytes'] / 2**20:.1f} MiB on disk)",
            "",
            f"* code cells: {len(cells)}; not parseable: {sum(not c['parses'] for c in cells)}; with magics: "
            f"{sum(c['magic'] for c in cells)}; shell / package cells (never executed): {sum(c['shell'] for c in cells)}",
            f"* imports ({len(b['imports'])}): {', '.join(b['imports'])}",
            f"* flags: {'; '.join(flags) or 'none'}",
            f"* **not installed here: {', '.join(missing) or 'none'}**",
            f"* cells that look expensive (model fit / train, or a loop around apply / merge / groupby / IO): "
            f"{len(expensive)} (hashes: {', '.join(c['hash'] for c in expensive[:12])}{' ...' if len(expensive) > 12 else ''})",
            "",
            "| data file (name only) | resolves | size on disk | candidates found |",
            "|---|---|---|---|",
        ]
        for ref, f in sorted(b["files"].items(), key=lambda kv: Path(kv[0]).name):
            size = f"{f['bytes'] / 2**20:,.1f} MiB" if f["bytes"] is not None else "-"
            lines.append(
                f"| `{Path(ref).name}` | {'yes' if f['resolved'] else '**NO**'} | {size} | {f['candidates']} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.realworld.inventory")
    ap.add_argument("folder", type=Path)
    ap.add_argument("--search", type=Path, nargs="*", default=[])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--json", type=Path, help="full inventory incl. resolved paths (keep under results/)"
    )
    args = ap.parse_args(argv)
    books = inventory(args.folder, args.search)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report(books), encoding="utf-8")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        slim = [{"name": b["name"], "imports": b["imports"], "files": b["files"],
                 "cells": [{"index": c["index"], "hash": c["hash"], "shell": c["shell"], "magic": c["magic"],
                            "parses": c["parses"]} for c in b["cells"]]} for b in books]  # fmt: skip
        args.json.write_text(json.dumps(slim, indent=1, default=str))
    print(report(books))


if __name__ == "__main__":
    main()
