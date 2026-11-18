"""Frozen dev / held-out split of the suggestion benchmark (Phase 5).

Assignment is deterministic and made before any measurement: per rule family the configurations are
ordered by ``sha256(SALT + key)`` and the last ``ceil(0.4 * n)`` (at least one) are held out. The
result is stored in ``split.json`` with a digest; ``load`` refuses a file whose digest or content no
longer matches. A new split would be a new version, never an edit.

Only this module and ``run`` may name the held-out part (``tests/test_suggestion_split.py`` scans the
other modules). Reading held-out RESULTS happens only in ``run.evaluate_heldout`` with a reason, which
is appended to ``docs/benchmarks/phase5-heldout-access-log.md``.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from benchmarks.suggestions.cases import all_configs

SALT = "phase5-suggestions-v1:"
HELDOUT_FRACTION = 0.4
SPLIT_FILE = Path(__file__).with_name("split.json")


@dataclass(frozen=True)
class SuggestionSplit:
    version: int
    dev: tuple[str, ...]
    heldout: tuple[str, ...]
    digest: str


def assign(keys_by_family: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    dev: list[str] = []
    held: list[str] = []
    for family in sorted(keys_by_family):
        ordered = sorted(keys_by_family[family], key=lambda k: hashlib.sha256((SALT + k).encode()).hexdigest())
        n_held = max(1, math.ceil(HELDOUT_FRACTION * len(ordered)))
        dev += ordered[:-n_held]
        held += ordered[-n_held:]
    return sorted(dev), sorted(held)


def digest(dev: list[str], held: list[str]) -> str:
    blob = json.dumps({"salt": SALT, "dev": sorted(dev), "heldout": sorted(held)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def _by_family() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for c in all_configs():
        out[c.family].append(c.key)
    return dict(out)


def create(path: Path = SPLIT_FILE) -> SuggestionSplit:
    if path.exists():
        raise FileExistsError(f"{path} exists: create a new version instead of overwriting")
    dev, held = assign(_by_family())
    data = {"version": 1, "salt": SALT, "dev": dev, "heldout": held, "digest": digest(dev, held)}
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return load(path)


def load(path: Path = SPLIT_FILE) -> SuggestionSplit:
    data = json.loads(path.read_text(encoding="utf-8"))
    dev, held = list(data["dev"]), list(data["heldout"])
    if digest(dev, held) != data["digest"]:
        raise ValueError("suggestion split digest mismatch: the frozen split was edited")
    current = {c.key for c in all_configs()}
    if set(dev) | set(held) != current or set(dev) & set(held):
        raise ValueError("suggestion split no longer matches the configurations")
    return SuggestionSplit(int(data["version"]), tuple(dev), tuple(held), data["digest"])


if __name__ == "__main__":
    s = create()
    print(f"created version {s.version}: {len(s.dev)} dev and {len(s.heldout)} held-out configurations, digest {s.digest}")
