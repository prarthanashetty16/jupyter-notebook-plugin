"""One-off repairs after the version-1 test split was exposed.

``migrate-exposed``: move the exposed-v1 rows from ``<results>/sealed/`` into the development
files (``actuals.csv``/``predictions.csv``) with ``split=exposed-v1``, so the sealed directory is
left for test-v2 only. ``scrub-logs``: rewrite every log line that names an exposed-v1 or test-v2
point so that it keeps only the timestamp, index, point id, status and elapsed time.

    python -m benchmarks.maintenance migrate-exposed benchmarks/results/full
    python -m benchmarks.maintenance scrub-logs      benchmarks/results/full
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from benchmarks.runner import ACTUAL_FIELDS, PREDICTION_FIELDS, ResultStore, upgrade_header
from benchmarks.split import EXPOSED, SEALED_DIR, load_split

_STATUS = re.compile(
    r":\s+(?P<status>ok|error|timeout|memory_limit|died|actual kept \(\w+\)|already done \(\w+\)"
    r"|skipped(?: \([^)]*\))?)"
)
_ELAPSED = re.compile(r"\[(?P<s>\d+)s(?: elapsed)?\]\s*$")
_PREFIX = re.compile(r"^(?P<ts>\d\d:\d\d:\d\d\s+)?(?P<idx>\[\d+/\d+\]\s+)?")


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def migrate_exposed(results_dir: Path) -> dict[str, int]:
    """Move exposed-v1 rows out of ``sealed/`` into the development files. Idempotent."""
    exposed = load_split().exposed
    sealed = results_dir / SEALED_DIR
    moved = {"actuals": 0, "predictions": 0, "left_sealed": 0}
    for name, fields, key in (
        ("actuals", ACTUAL_FIELDS, ("point_id",)),
        ("predictions", PREDICTION_FIELDS, ("point_id", "tier")),
    ):
        src = sealed / f"{name}.csv"
        rows = _read(src)
        if not rows:
            continue
        case_of = {r["point_id"]: r["point_id"].split("|n=")[0] for r in rows}
        keep, move = [], []
        for r in rows:
            (move if case_of[r["point_id"]] in exposed else keep).append(r)
        upgrade_header(results_dir / f"{name}.csv", fields)
        dst = ResultStore(results_dir / f"{name}.csv", fields, key)
        for r in move:
            r = {**r, "split": EXPOSED}
            if dst.has(**{k: r[k] for k in key}) is None:
                dst.add(r)
                moved[name] += 1
        if keep:  # rows of other groups stay sealed
            tmp = src.with_suffix(".csv.tmp")
            with tmp.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields)
                writer.writeheader()
                writer.writerows({f: r.get(f, "") for f in fields} for r in keep)
            tmp.replace(src)
            moved["left_sealed"] += len(keep)
        else:
            src.unlink()
    for name, fields in (("actuals", ACTUAL_FIELDS), ("predictions", PREDICTION_FIELDS)):
        upgrade_header(results_dir / f"{name}.csv", fields)
    return moved


def redact_line(line: str) -> str:
    """Keep timestamp, index, point id, status and elapsed time of a point log line."""
    head = _PREFIX.match(line)
    rest = line[head.end() :] if head else line
    point_id = rest.split(":", 1)[0].strip()
    status = _STATUS.search(rest)
    elapsed = _ELAPSED.search(line.rstrip())
    out = (head.group(0) if head else "") + point_id
    out += f": {status.group('status')}" if status else ": (status removed)"
    out += f" [{elapsed.group('s')}s]" if elapsed else ""
    return out


def scrub_logs(results_dir: Path) -> int:
    """Redact point lines of exposed-v1 and test-v2 cases in every ``*.log`` of the directory."""
    sp = load_split()
    names = sorted(sp.exposed | sp.test, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(n) + r"\|n=\d+" for n in names))
    changed = 0
    for log in results_dir.rglob("*.log"):
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        out = []
        for line in lines:
            if pattern.search(line):
                new = redact_line(line)
                changed += new != line
                out.append(new)
            else:
                out.append(line)
        log.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


def main() -> None:
    if len(sys.argv) != 3 or sys.argv[1] not in ("migrate-exposed", "scrub-logs"):
        raise SystemExit(__doc__)
    results = Path(sys.argv[2])
    if not results.exists():
        raise SystemExit(f"{results} does not exist")
    if sys.argv[1] == "migrate-exposed":
        print(migrate_exposed(results))
    else:
        print(f"redacted {scrub_logs(results)} log line(s)")


if __name__ == "__main__":
    main()
