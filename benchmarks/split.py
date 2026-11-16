"""Frozen split of benchmark *configurations* into dev / exposed-v1 / test-v2, and the test guard.

Unit of split = a *case* (operation + source + dataset configuration; all sizes of a case stay
together).

- ``dev``: cases examined during Phases 3 and 3b (committed reports under ``docs/benchmarks``).
- ``exposed-v1``: the original sealed test split (frozen 2026-11-16). Its measured and predicted
  values were printed by the runner to the console and ``run.log`` during the first full run, so it
  is **exposed**: usable for development and diagnosis, never for final claims.
- ``test-v2``: a fresh sealed split of configurations that differ from every dev and exposed-v1
  configuration (new generators/parameters/seeds). Never run or evaluated so far.

Guard: only ``evaluate --final`` may read ``test-v2``. It requires a reason and appends a line to
the "Test-split access log" in ``docs/PROGRESS.md``. ``test-v2`` measurements are written by the
runner to ``<results>/sealed/``; no log, console line, status output or normal report shows their
values (only point id, status and elapsed time). ``split.json`` carries SHA-256 digests per group
and a history of earlier freezes; the loader refuses a file whose lists no longer match.
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
SEALED_DIR = "sealed"

DEV = "dev"
EXPOSED = "exposed-v1"
TEST = "test-v2"
DEVELOPMENT_GROUPS = (DEV, EXPOSED)  # may be read by development tooling
SEALED_GROUPS = (TEST,)  # read only by ``evaluate --final``
GROUPS = (DEV, EXPOSED, TEST)


class SealedAccessError(RuntimeError):
    """Raised when something other than ``evaluate --final`` tries to read the sealed split."""


@dataclass(frozen=True)
class Split:
    dev: frozenset[str]
    exposed: frozenset[str]
    test: frozenset[str]  # sealed: test-v2
    meta: dict

    def of(self, case: str) -> str:
        if case in self.dev:
            return DEV
        if case in self.exposed:
            return EXPOSED
        if case in self.test:
            return TEST
        raise ValueError(f"case {case!r} is not classified in split.json")

    def group(self, name: str) -> frozenset[str]:
        return {DEV: self.dev, EXPOSED: self.exposed, TEST: self.test}[name]


def digest(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()


def load_split(path: Path = SPLIT_PATH) -> Split:
    """Load and verify the frozen split (digests, disjointness)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    groups = {}
    for name in GROUPS:
        entry = raw["groups"][name]
        cases = set(entry["cases"])
        if digest(cases) != entry["sha256"]:
            raise ValueError(f"split.json was modified after freezing (digest mismatch: {name})")
        groups[name] = frozenset(cases)
    overlaps = [
        (a, b, sorted(groups[a] & groups[b]))
        for i, a in enumerate(GROUPS)
        for b in GROUPS[i + 1 :]
        if groups[a] & groups[b]
    ]
    if overlaps:
        raise ValueError(f"split.json: cases in two groups (both dev and test...): {overlaps}")
    meta = {k: v for k, v in raw.items() if k != "groups"}
    return Split(groups[DEV], groups[EXPOSED], groups[TEST], meta)


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


def supersede_to_v2(new_test_cases: Iterable[str], note: str, path: Path = SPLIT_PATH) -> Path:
    """One-off: turn the version-1 file (dev/test) into version 2.

    The old ``test`` list becomes ``exposed-v1`` (same digest, recorded in ``history``) and
    ``new_test_cases`` become the sealed ``test-v2``. Refuses to run on a version-2 file.
    """
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


@dataclass(frozen=True)
class SealedAccessToken:
    """Proof that a test-split access was logged; only ``open_test_split`` makes one."""

    reason: str
    timestamp: str
    command: str


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


def open_test_split(
    reason: str,
    *,
    results_dir: Path,
    command: str,
    n_points: int,
    progress_path: Path = PROGRESS_PATH,
) -> SealedAccessToken:
    """Log one use of the sealed test split in PROGRESS.md and return the access token."""
    if not reason.strip():
        raise SealedAccessError("evaluate --final requires a non-empty --reason")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"- {stamp} | git `{_git_commit()}` | {TEST} | results `{results_dir.as_posix()}` | "
        f"{n_points} test points | reason: {reason.strip()} | `{command}`"
    )
    append_access_log(line, progress_path)
    return SealedAccessToken(reason.strip(), stamp, command)


def require_token(token: object) -> None:
    if not isinstance(token, SealedAccessToken):
        raise SealedAccessError(
            "the sealed test split can only be read through `evaluate --final` (see split.py)"
        )
