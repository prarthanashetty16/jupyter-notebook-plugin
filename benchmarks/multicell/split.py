"""Frozen dev / held-out split of the multi-statement benchmark (Phase 6c pre-registration A).

Per template, the configuration with the largest ``sha256(SALT + key)`` is held out (both of its sizes),
decided before any measurement and stored with a digest in ``split_v1.json``. ``load`` refuses an edited
file. Only this module and ``run`` name the held-out part; held-out results are read only through
``run.evaluate --heldout --reason``, which is logged in ``docs/benchmarks/phase6c-heldout-access-log.md``.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from benchmarks.multicell.cases import all_configs

SALT = "phase6c-multicell-v1:"
SPLIT_FILE = Path(__file__).with_name("split_v1.json")


@dataclass(frozen=True)
class MulticellSplit:
    version: int
    dev: tuple[str, ...]
    heldout: tuple[str, ...]
    digest: str


def _h(key: str) -> str:
    return hashlib.sha256((SALT + key).encode()).hexdigest()


def assign() -> tuple[list[str], list[str]]:
    by: dict[str, list[str]] = defaultdict(list)
    for c in all_configs():
        by[c.template].append(c.key)
    dev, held = [], []
    for template in sorted(by):
        keys = sorted(by[template], key=_h)
        dev += keys[:-1]
        held.append(keys[-1])
    return sorted(dev), sorted(held)


def digest(dev: list[str], held: list[str]) -> str:
    blob = json.dumps({"salt": SALT, "dev": sorted(dev), "heldout": sorted(held)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def create(path: Path = SPLIT_FILE) -> MulticellSplit:
    if path.exists():
        raise FileExistsError(f"{path} exists: create a new version instead of overwriting")
    dev, held = assign()
    data = {"version": 1, "salt": SALT, "dev": dev, "heldout": held, "digest": digest(dev, held)}
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return load(path)


def load(path: Path = SPLIT_FILE) -> MulticellSplit:
    data = json.loads(path.read_text(encoding="utf-8"))
    dev, held = list(data["dev"]), list(data["heldout"])
    if digest(dev, held) != data["digest"]:
        raise ValueError("multicell split digest mismatch: the frozen split was edited")
    current = {c.key for c in all_configs()}
    if set(dev) | set(held) != current or set(dev) & set(held):
        raise ValueError("multicell split no longer matches the configurations")
    return MulticellSplit(int(data["version"]), tuple(dev), tuple(held), data["digest"])
