"""Frozen split of benchmark *configurations* into dev / test-v2 / val-v4, and the access guards.

Unit of split = a *case* (operation + source + dataset configuration; all sizes of a case stay
together).

- ``dev``: everything development tooling may read. It includes the cases examined in Phases 3-3b
  and the former ``exposed-v1`` group (the version-1 test split, whose values were printed to the
  console in the first full run and which influenced a Phase 4a model change). Version 3 of the
  split file reclassified exposed-v1 as dev; its case list is kept as ``provenance`` so reports can
  still say where a case came from.
- ``test-v2``: sealed configurations for the final claim. Never run or evaluated so far.
- ``val-v3``: was the held-out validation split of Phase 4b. Its report was read by the developer
  and a reviewer, so split version 4 reclassified it as dev (list kept as ``provenance``).
- ``val-v4``: the held-out validation split after Phase 4b.2 (new configurations, no generator
  parameter or seed shared with dev, val-v3 or test-v2). It is measured by the runner into
  ``<results>/validation/`` with the same log redaction as test-v2 (id, status, elapsed only) and
  is read only by ``evaluate --val --reason "..."``, which logs each use in docs/PROGRESS.md.

``split.json`` carries SHA-256 digests per group and a history of earlier freezes; the loader
refuses a file whose lists no longer match.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
SPLIT_PATH = HERE / "split.json"
PROGRESS_PATH = HERE.parent / "docs" / "PROGRESS.md"
DOCS_BENCHMARKS = HERE.parent / "docs" / "benchmarks"
LOG_HEADING = "## Test-split access log"
SEALED_DIR = "sealed"  # test-v2 results
VAL_DIR = "validation"  # val-v3 results

DEV = "dev"
EXPOSED = "exposed-v1"  # provenance label only: these cases are dev since split version 3
TEST = "test-v2"
VAL = "val-v5"  # the current held-out validation group
VAL3 = "val-v3"  # val-v3 / val-v4: group names of older split versions, provenance labels now
VAL4 = "val-v4"
DEVELOPMENT_GROUPS = (DEV,)  # may be read by development tooling
SEALED_GROUPS = (TEST, VAL)  # values never shown by logs, status or normal reports
GROUPS = (DEV, TEST, VAL)


def group_dir(group: str) -> str | None:
    """Subdirectory of a results directory that holds ``group`` (None: the top level)."""
    return {DEV: None, TEST: SEALED_DIR, VAL: VAL_DIR}[group]


class SealedAccessError(RuntimeError):
    """Raised when something other than ``evaluate --final`` tries to read the sealed split."""


@dataclass(frozen=True)
class Split:
    dev: frozenset[str]  # includes the former exposed-v1 cases
    test: frozenset[str]  # sealed: test-v2
    val: frozenset[str]  # held-out validation: val-v3
    exposed: frozenset[str]  # provenance: the former exposed-v1 cases (a subset of dev)
    meta: dict
    val3: frozenset[str] = frozenset()  # provenance: the former val-v3 cases (a subset of dev)
    val4: frozenset[str] = frozenset()  # provenance: the former val-v4 cases (dev since version 5)

    def of(self, case: str) -> str:
        if case in self.dev:
            return DEV
        if case in self.test:
            return TEST
        if case in self.val:
            return VAL
        raise ValueError(f"case {case!r} is not classified in split.json")

    def group(self, name: str) -> frozenset[str]:
        return {DEV: self.dev, TEST: self.test, VAL: self.val}[name]


def digest(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()


def load_split(path: Path | None = None) -> Split:
    """Load and verify the frozen split (digests, disjointness). Reads versions 2 and 3."""
    path = path or SPLIT_PATH  # resolved per call so tests can point it elsewhere
    raw = json.loads(path.read_text(encoding="utf-8"))
    groups: dict[str, frozenset[str]] = {}
    in_file = raw["groups"]
    held_out = next(
        (g for g in (VAL, VAL4, VAL3) if g in in_file), VAL
    )  # older files name theirs val-v3 / val-v4
    for name in (DEV, EXPOSED, TEST, held_out):
        entry = in_file.get(name)
        if entry is None:
            if name in (EXPOSED, held_out):  # absent in newer / older files
                groups[name] = frozenset()
                continue
            raise ValueError(f"split.json has no group {name!r}")
        cases = set(entry["cases"])
        if digest(cases) != entry["sha256"]:
            raise ValueError(f"split.json was modified after freezing (digest mismatch: {name})")
        groups[name] = frozenset(cases)
    exposed = groups[EXPOSED]  # a version-2 file lists it as a group of its own: it is dev now
    dev = groups[DEV] | exposed
    provenance: dict[str, frozenset[str]] = {}
    for label in (EXPOSED, VAL3, VAL4):
        entry = raw.get("provenance", {}).get(label)
        if entry is not None:
            prov = set(entry["cases"])
            if digest(prov) != entry["sha256"]:
                raise ValueError(
                    "split.json was modified after freezing (digest mismatch: provenance)"
                )
            provenance[label] = frozenset(prov)
    exposed = provenance.get(EXPOSED, exposed)
    val3 = provenance.get(VAL3, frozenset())
    val4 = provenance.get(VAL4, frozenset())
    merged = {DEV: dev, TEST: groups[TEST], VAL: groups[held_out]}
    named = tuple(merged)
    overlaps = [
        (a, b, sorted(merged[a] & merged[b]))
        for i, a in enumerate(named)
        for b in named[i + 1 :]
        if merged[a] & merged[b]
    ]
    if overlaps:
        raise ValueError(f"split.json: cases in two groups (both dev and test...): {overlaps}")
    if not (exposed <= dev and val3 <= dev and val4 <= dev):
        raise ValueError("split.json: provenance cases must belong to dev")
    meta = {k: v for k, v in raw.items() if k != "groups"}
    return Split(dev, merged[TEST], merged[VAL], exposed, meta, val3, val4)


def split_of(case: str) -> str:
    return load_split().of(case)


def group_of(case: str, default: str = DEV) -> str:
    """Group of ``case``; unclassified cases (test fixtures) fall back to ``default``."""
    try:
        return load_split().of(case)
    except ValueError:
        return default


def seen_cases(docs_dir: Path = DOCS_BENCHMARKS) -> set[str]:
    """Case names that appear in any committed report's top-level actuals.csv."""
    import csv

    seen: set[str] = set()
    for actuals in docs_dir.glob("*/actuals.csv"):
        with actuals.open(newline="", encoding="utf-8") as fh:
            seen.update(row["case"] for row in csv.DictReader(fh))
    return seen


def supersede_to_v2(new_test_cases: Iterable[str], note: str, path: Path | None = None) -> Path:
    """One-off: turn the version-1 file (dev/test) into version 2.

    The old ``test`` list becomes ``exposed-v1`` (same digest, recorded in ``history``) and
    ``new_test_cases`` become the sealed ``test-v2``. Refuses to run on a version-2 file.
    """
    path = path or SPLIT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("split.json is not a version-1 file; nothing to supersede")
    dev, old_test = set(raw["dev"]), set(raw["test"])
    if digest(dev) != raw["sha256"]["dev"] or digest(old_test) != raw["sha256"]["test"]:
        raise ValueError("version-1 split.json digest mismatch")
    new = set(new_test_cases)
    if new & (dev | old_test):
        raise ValueError(f"test-v2 reuses existing cases: {sorted(new & (dev | old_test))}")
    out = {
        "version": 2,
        "frozen": time.strftime("%Y-%m-%d"),
        "rule": "dev = cases examined in Phases 3/3b; exposed-v1 = the version-1 test split, whose "
        "values were printed to console/run.log (development use only, never final claims); "
        "test-v2 = new sealed configurations, never run or evaluated",
        "history": [
            {
                "version": 1,
                "frozen": raw["frozen"],
                "event": "frozen: dev = seen cases, test = unseen cases",
                "sha256": raw["sha256"],
            },
            {"version": 2, "frozen": time.strftime("%Y-%m-%d"), "event": note},
        ],
        "groups": {
            DEV: {"cases": sorted(dev), "sha256": digest(dev), "status": "development"},
            EXPOSED: {
                "cases": sorted(old_test),
                "sha256": digest(old_test),
                "status": "exposed: development and diagnosis only, never final claims",
            },
            TEST: {"cases": sorted(new), "sha256": digest(new), "status": "sealed"},
        },
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


def supersede_to_v3(val_cases: Iterable[str], note: str, path: Path | None = None) -> Path:
    """One-off: turn the version-2 file (dev / exposed-v1 / test-v2) into version 3.

    ``exposed-v1`` is merged into ``dev`` (its list is kept under ``provenance``) and
    ``val_cases`` become the held-out ``val-v3``. The version-2 digests stay in ``history``.
    Refuses to run on anything but a version-2 file.
    """
    path = path or SPLIT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 2:
        raise ValueError("split.json is not a version-2 file; nothing to supersede")
    old = load_split(path)
    new = set(val_cases)
    if new & (old.dev | old.test):
        raise ValueError(f"val-v3 reuses existing cases: {sorted(new & (old.dev | old.test))}")
    out = {
        "version": 3,
        "frozen": time.strftime("%Y-%m-%d"),
        "rule": "dev = every case development tooling may read (Phases 3-3b cases plus the former "
        "exposed-v1, which influenced a Phase 4a model change); test-v2 = sealed, never run; "
        "val-v3 = held-out validation for Phases 4b-4d, new configurations, evaluated only by "
        "`evaluate --val` (logged)",
        "history": [
            *raw["history"],
            {
                "version": 3,
                "frozen": time.strftime("%Y-%m-%d"),
                "event": note,
                "sha256_v2": {k: v["sha256"] for k, v in raw["groups"].items()},
            },
        ],
        "provenance": {
            EXPOSED: {
                "cases": sorted(old.exposed),
                "sha256": digest(old.exposed),
                "status": "former exposed-v1 (version-1 test split); dev since version 3",
            }
        },
        "groups": {
            DEV: {"cases": sorted(old.dev), "sha256": digest(old.dev), "status": "development"},
            TEST: {"cases": sorted(old.test), "sha256": digest(old.test), "status": "sealed"},
            VAL3: {
                "cases": sorted(new),
                "sha256": digest(new),
                "status": "held-out validation (values hidden; `evaluate --val` logs each use)",
            },
        },
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


def supersede_to_v4(val_cases: Iterable[str], note: str, path: Path | None = None) -> Path:
    """One-off: turn the version-3 file into version 4.

    The old held-out group ``val-v3`` (read by the developer and a reviewer) is merged into dev and
    kept under ``provenance``; ``val_cases`` become the new held-out ``val-v4``. Version-3 digests
    stay in ``history``. Refuses anything but a version-3 file.
    """
    path = path or SPLIT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 3:
        raise ValueError("split.json is not a version-3 file; nothing to supersede")
    old = load_split(path)
    new = set(val_cases)
    if new & (old.dev | old.test | old.val):
        raise ValueError(
            f"val-v4 reuses existing cases: {sorted(new & (old.dev | old.test | old.val))}"
        )
    dev = set(old.dev | old.val)
    out = {
        "version": 4,
        "frozen": time.strftime("%Y-%m-%d"),
        "rule": "dev = every case development tooling may read (Phases 3-3b cases, the former "
        "exposed-v1 and the former val-v3, whose report was read); test-v2 = sealed, never run; "
        "val-v4 = held-out validation after Phase 4b.2, new configurations, evaluated only by "
        "`evaluate --val` (logged)",
        "history": [
            *raw["history"],
            {
                "version": 4,
                "frozen": time.strftime("%Y-%m-%d"),
                "event": note,
                "sha256_v3": {k: v["sha256"] for k, v in raw["groups"].items()},
            },
        ],
        "provenance": {
            **raw.get("provenance", {}),
            VAL3: {
                "cases": sorted(old.val),
                "sha256": digest(old.val),
                "status": "former val-v3 (held-out in Phase 4b); dev since version 4",
            },
        },
        "groups": {
            DEV: {"cases": sorted(dev), "sha256": digest(dev), "status": "development"},
            TEST: {"cases": sorted(old.test), "sha256": digest(old.test), "status": "sealed"},
            VAL4: {
                "cases": sorted(new),
                "sha256": digest(new),
                "status": "held-out validation (values hidden; `evaluate --val` logs each use)",
            },
        },
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


def supersede_to_v5(note: str, path: Path | None = None) -> Path:
    """One-off: turn the version-4 file into version 5.

    The held-out group ``val-v4`` (its report was read after it failed its pre-registered
    criterion) is merged into dev and kept under ``provenance``; there is NO held-out validation
    group in version 5 (a new one is created in a later phase, before it is run). Refuses anything
    but a version-4 file.
    """
    path = path or SPLIT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 4:
        raise ValueError("split.json is not a version-4 file; nothing to supersede")
    old = load_split(path)
    dev = set(old.dev | old.val)
    out = {
        "version": 5,
        "frozen": time.strftime("%Y-%m-%d"),
        "rule": "dev = every case development tooling may read (Phases 3-3b cases, the former "
        "exposed-v1, val-v3 and val-v4, whose reports were read); test-v2 = sealed, never run; "
        "no held-out validation group exists in this version",
        "history": [
            *raw["history"],
            {
                "version": 5,
                "frozen": time.strftime("%Y-%m-%d"),
                "event": note,
                "sha256_v4": {k: v["sha256"] for k, v in raw["groups"].items()},
            },
        ],
        "provenance": {
            **raw.get("provenance", {}),
            VAL4: {
                "cases": sorted(old.val),
                "sha256": digest(old.val),
                "status": "former val-v4 (held-out in Phase 4b.2; failed its criterion); dev since version 5",
            },
        },
        "groups": {
            DEV: {"cases": sorted(dev), "sha256": digest(dev), "status": "development"},
            TEST: {"cases": sorted(old.test), "sha256": digest(old.test), "status": "sealed"},
        },
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


def supersede_to_v6(val_cases: Iterable[str], note: str, path: Path | None = None) -> Path:
    """One-off: turn the version-5 file (no held-out group) into version 6 with ``val-v5``.

    ``val_cases`` become the new held-out group; dev, test-v2 and the provenance lists are kept.
    Refuses anything but a version-5 file and any case already classified.
    """
    path = path or SPLIT_PATH
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 5:
        raise ValueError("split.json is not a version-5 file; nothing to supersede")
    old = load_split(path)
    new = set(val_cases)
    if new & (old.dev | old.test):
        raise ValueError(f"val-v5 reuses existing cases: {sorted(new & (old.dev | old.test))}")
    out = {
        "version": 6,
        "frozen": time.strftime("%Y-%m-%d"),
        "rule": "dev = every case development tooling may read (Phases 3-4c: the former exposed-v1, "
        "val-v3 and val-v4 included); test-v2 = sealed, never run; val-v5 = held-out validation for "
        "a Linux machine with >= 32 GB RAM, frozen before it is run, evaluated only by "
        "`evaluate --val` (logged)",
        "history": [
            *raw["history"],
            {
                "version": 6,
                "frozen": time.strftime("%Y-%m-%d"),
                "event": note,
                "sha256_v5": {k: v["sha256"] for k, v in raw["groups"].items()},
            },
        ],
        "provenance": raw.get("provenance", {}),
        "groups": {
            DEV: {"cases": sorted(old.dev), "sha256": digest(old.dev), "status": "development"},
            TEST: {"cases": sorted(old.test), "sha256": digest(old.test), "status": "sealed"},
            VAL: {
                "cases": sorted(new),
                "sha256": digest(new),
                "status": "held-out validation (values hidden; `evaluate --val` logs each use)",
            },
        },
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass(frozen=True)
class SealedAccessToken:
    """Proof that a test-split access was logged; only ``open_test_split`` makes one."""

    reason: str
    timestamp: str
    command: str
    group: str = TEST


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=HERE,
        ).stdout.strip()
    except Exception:
        return "unknown"


def append_access_log(line: str, progress_path: Path = PROGRESS_PATH) -> None:
    """Append one line inside the "Test-split access log" section of PROGRESS.md."""
    text = progress_path.read_text(encoding="utf-8") if progress_path.exists() else ""
    if LOG_HEADING not in text:
        text = text.rstrip() + f"\n\n{LOG_HEADING}\n\n{line}\n"
    else:
        head, _, tail = text.partition(LOG_HEADING)
        nxt = tail.find("\n## ")
        body, rest = (tail, "") if nxt == -1 else (tail[:nxt], tail[nxt:])
        text = head + LOG_HEADING + body.rstrip() + "\n" + line + "\n" + rest
    progress_path.write_text(text, encoding="utf-8")


def open_sealed_group(
    group: str,
    reason: str,
    *,
    results_dir: Path,
    command: str,
    n_points: int,
    progress_path: Path = PROGRESS_PATH,
) -> SealedAccessToken:
    """Log one use of a protected group (test-v2 or val-v3) in PROGRESS.md; return the token."""
    if group not in SEALED_GROUPS:
        raise SealedAccessError(f"{group!r} is not a protected group")
    if not reason.strip():
        raise SealedAccessError("a non-empty --reason is required to read a protected group")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"- {stamp} | git `{_git_commit()}` | {group} | results `{results_dir.as_posix()}` | "
        f"{n_points} {group} points | reason: {reason.strip()} | `{command}`"
    )
    append_access_log(line, progress_path)
    return SealedAccessToken(reason.strip(), stamp, command, group)


def open_test_split(
    reason: str,
    *,
    results_dir: Path,
    command: str,
    n_points: int,
    progress_path: Path = PROGRESS_PATH,
) -> SealedAccessToken:
    """Log one use of the sealed test split (``evaluate --final``)."""
    return open_sealed_group(
        TEST, reason, results_dir=results_dir, command=command, n_points=n_points,
        progress_path=progress_path,
    )  # fmt: skip


def open_validation_split(
    reason: str,
    *,
    results_dir: Path,
    command: str,
    n_points: int,
    progress_path: Path = PROGRESS_PATH,
) -> SealedAccessToken:
    """Log one use of the held-out validation split (``evaluate --val``)."""
    return open_sealed_group(
        VAL, reason, results_dir=results_dir, command=command, n_points=n_points,
        progress_path=progress_path,
    )  # fmt: skip


def require_token(token: object, group: str = TEST) -> None:
    if not isinstance(token, SealedAccessToken) or token.group != group:
        flag = "--final" if group == TEST else "--val"
        raise SealedAccessError(
            f"the {group} split can only be read through `evaluate {flag}` (see split.py)"
        )
