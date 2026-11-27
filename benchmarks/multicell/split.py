"""Frozen dev / held-out split of the multi-statement benchmark (Phase 6c pre-registration A).

Per template, the configuration with the largest ``sha256(SALT + key)`` is held out (both of its sizes),
(v1: ``split_v1.json``, Phase 6c; v2: ``split_v2.json`` with ``cases_v2``, the Phase 7 group for freeze v3),
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

from benchmarks.multicell import cases, cases_v2, cases_v3, cases_v4

SALT = "phase6c-multicell-v1:"
SPLIT_FILE = Path(__file__).with_name("split_v1.json")
# v2 (Phase 7 pre-registration): the fresh held-out group for freeze v3; same rule, own salt and file
SALT_V2 = "phase7-multicell-v2:"
SPLIT_FILE_V2 = Path(__file__).with_name("split_v2.json")
# v3 (Phase 7c, amendment 1 of the Phase 7 pre-registration): the ENLARGED group, TWO held out per template
SALT_V3 = "phase7c-multicell-v3:"
SPLIT_FILE_V3 = Path(__file__).with_name("split_v3.json")
# v4 (Phase 8c Amendment 7): new pre-registered group with two held-out configurations per template
SALT_V4 = "phase8c-multicell-v4:"
SPLIT_FILE_V4 = Path(__file__).with_name("split_v4.json")
_VERSIONS = {
    1: (SALT, SPLIT_FILE, cases),
    2: (SALT_V2, SPLIT_FILE_V2, cases_v2),
    3: (SALT_V3, SPLIT_FILE_V3, cases_v3),
    4: (SALT_V4, SPLIT_FILE_V4, cases_v4),
}
HELD_PER_TEMPLATE = {1: 1, 2: 1, 3: 2, 4: 2}


def all_configs(version: int = 1) -> list:
    return _VERSIONS[version][2].all_configs()


@dataclass(frozen=True)
class MulticellSplit:
    version: int
    dev: tuple[str, ...]
    heldout: tuple[str, ...]
    digest: str


def _h(key: str, salt: str = SALT) -> str:
    return hashlib.sha256((salt + key).encode()).hexdigest()


def assign(version: int = 1) -> tuple[list[str], list[str]]:
    salt = _VERSIONS[version][0]
    by: dict[str, list[str]] = defaultdict(list)
    for c in all_configs(version):
        by[c.template].append(c.key)
    dev, held = [], []
    k_held = HELD_PER_TEMPLATE[version]
    for template in sorted(by):
        keys = sorted(by[template], key=lambda k: _h(k, salt))
        dev += keys[:-k_held]
        held += keys[-k_held:]
    return sorted(dev), sorted(held)


def digest(dev: list[str], held: list[str], salt: str = SALT) -> str:
    blob = json.dumps({"salt": salt, "dev": sorted(dev), "heldout": sorted(held)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def create(path: Path | None = None, version: int = 1) -> MulticellSplit:
    salt, default, _ = _VERSIONS[version]
    path = path or default
    if path.exists():
        raise FileExistsError(f"{path} exists: create a new version instead of overwriting")
    dev, held = assign(version)
    data = {
        "version": version,
        "salt": salt,
        "dev": dev,
        "heldout": held,
        "digest": digest(dev, held, salt),
    }
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    return load(path, version)


def load(path: Path | None = None, version: int = 1) -> MulticellSplit:
    salt, default, _ = _VERSIONS[version]
    data = json.loads((path or default).read_text(encoding="utf-8"))
    dev, held = list(data["dev"]), list(data["heldout"])
    if int(data["version"]) != version or digest(dev, held, salt) != data["digest"]:
        raise ValueError("multicell split digest mismatch: the frozen split was edited")
    current = {c.key for c in all_configs(version)}
    if set(dev) | set(held) != current or set(dev) & set(held):
        raise ValueError("multicell split no longer matches the configurations")
    return MulticellSplit(int(data["version"]), tuple(dev), tuple(held), data["digest"])


# Held-out parts whose one evaluation is done and that are dev data since (PROGRESS, Test-split access log):
# v1 since 2026-11-22, v2 and v3 since 2026-11-24. A future group is NOT listed here until its evaluation is done.
CONSUMED = (1, 2, 3)


def consumed_heldout_results(version: int, reason: str) -> Path:
    """Path of a CONSUMED held-out part's results, for dev tooling; every call is logged in the group's access log.

    Refuses a group that is not consumed, so dev tools never read a protected held-out part.
    """
    if version not in CONSUMED:
        raise PermissionError(f"multicell v{version} held-out part is not consumed: protected")
    from benchmarks.multicell.run import SUITES, _log_access

    _mod, results, _cache, log = SUITES[version]
    _log_access(
        f"READ consumed held-out multicell v{version} rows (dev data) | reason: {reason}", log
    )
    return results / "heldout" / "results.jsonl"
