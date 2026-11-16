"""Frozen dev/test split of benchmark *configurations* and the guard around the test split.

Unit of split = a *case* (operation + source + dataset configuration; all sizes of a case stay
together). ``split.json`` was frozen by ``freeze_from_docs``: **dev** = every case that already
appeared in a committed report under ``docs/benchmarks`` (the project has seen and discussed
those results); **test** = every other case, never run or evaluated before the freeze. The test
cases deliberately use configurations the dev cases never use (null rates, zipfian value
distributions, datetime keys, other join types and shapes), so the test split measures
generalisation, not memorisation.

Guard: only ``evaluate --final`` may read the test split. It requires a reason and appends a
line to the "Test-split access log" in ``docs/PROGRESS.md``. Test-split measurements are written
by the runner to ``<results>/sealed/`` and are never read by dev tooling (``load_joined``,
tuning, calibration, notebooks). ``split.json`` carries SHA-256 digests; the loader refuses a
file whose lists no longer match them.
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


class SealedAccessError(RuntimeError):
    """Raised when something other than ``evaluate --final`` tries to read the test split."""


@dataclass(frozen=True)
class Split:
    dev: frozenset[str]
    test: frozenset[str]
    meta: dict

    def of(self, case: str) -> str:
        if case in self.dev:
            return "dev"
        if case in self.test:
            return "test"
        raise ValueError(f"case {case!r} is not classified in split.json (dev or test)")


def digest(names: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(names)).encode()).hexdigest()


def load_split(path: Path = SPLIT_PATH) -> Split:
    """Load and verify the frozen split (digests, disjointness)."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    dev, test = set(raw["dev"]), set(raw["test"])
    if dev & test:
        raise ValueError(f"split.json: cases in both dev and test: {sorted(dev & test)}")
    if digest(dev) != raw["sha256"]["dev"] or digest(test) != raw["sha256"]["test"]:
        raise ValueError("split.json was modified after freezing (digest mismatch)")
    return Split(frozenset(dev), frozenset(test), raw.get("meta", {}))


def split_of(case: str) -> str:
    return load_split().of(case)


def seen_cases(docs_dir: Path = DOCS_BENCHMARKS) -> set[str]:
    """Case names that appear in any committed report's actuals.csv."""
    import csv

    seen: set[str] = set()
    for actuals in docs_dir.glob("*/actuals.csv"):
        with actuals.open(newline="", encoding="utf-8") as fh:
            seen.update(row["case"] for row in csv.DictReader(fh))
    return seen


def freeze_from_docs(all_cases: Iterable[str], path: Path = SPLIT_PATH) -> Path:
    """Write split.json once: seen cases -> dev, unseen -> test. Refuses to overwrite."""
    if path.exists():
        raise FileExistsError(f"{path} already exists; the split is frozen")
    names = sorted(set(all_cases))
    seen = seen_cases()
    dev = [n for n in names if n in seen]
    test = [n for n in names if n not in seen]
    if not dev or not test:
        raise ValueError("need both dev and test cases")
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "frozen": time.strftime("%Y-%m-%d"),
                "rule": "dev = cases present in committed reports under docs/benchmarks; "
                "test = all other cases (never measured or evaluated before the freeze)",
                "meta": {"n_dev": len(dev), "n_test": len(test)},
                "dev": dev,
                "test": test,
                "sha256": {"dev": digest(dev), "test": digest(test)},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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


def open_test_split(
    reason: str,
    *,
    results_dir: Path,
    command: str,
    n_points: int,
    progress_path: Path = PROGRESS_PATH,
) -> SealedAccessToken:
    """Log one use of the test split in PROGRESS.md and return the access token."""
    if not reason.strip():
        raise SealedAccessError("evaluate --final requires a non-empty --reason")
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"- {stamp} | git `{_git_commit()}` | results `{results_dir.as_posix()}` | "
        f"{n_points} test points | reason: {reason.strip()} | `{command}`"
    )
    text = progress_path.read_text(encoding="utf-8") if progress_path.exists() else ""
    if LOG_HEADING not in text:
        text = text.rstrip() + f"\n\n{LOG_HEADING}\n\n{line}\n"
    else:
        head, _, tail = text.partition(LOG_HEADING)
        nxt = tail.find("\n## ")
        body, rest = (tail, "") if nxt == -1 else (tail[:nxt], tail[nxt:])
        text = head + LOG_HEADING + body.rstrip() + "\n" + line + "\n" + rest
    progress_path.write_text(text, encoding="utf-8")
    return SealedAccessToken(reason.strip(), stamp, command)


def require_token(token: object) -> None:
    if not isinstance(token, SealedAccessToken):
        raise SealedAccessError(
            "the test split can only be read through `evaluate --final` (see split.py)"
        )
