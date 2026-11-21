"""The frozen model stack: manifest, and the guard that held-out runs must pass.

``models-frozen-v1`` is a git tag (Phase 6). A held-out run (val-v5 through ``python -m benchmarks
full --splits val-v5``, its ``evaluate --val``, ``evaluate --final`` for test-v2, the Phase 8a
real-notebook evaluation) calls ``require_frozen()``. Since Phase 6b the check is MANIFEST-BASED:
it compares the SHA-256 (LF line endings) of every file that defines the predictions
(``FROZEN_PATTERNS``, resolved against the tag's tree) with the tag's own copy, and aborts if one
differs, is missing, or if a new file matching a frozen pattern exists. Everything else (docs,
benchmark and evaluation scripts, CI, ``.gitignore``, tests, the Phase 8a harness) is outside the
freeze. The scope was narrowed AFTER the tag; the tagged commit is unchanged and no frozen file
changed (``docs/benchmarks/frozen-manifest.md``). Any change to a frozen file invalidates the
held-out status of the runs: a new freeze (new tag, new manifest) and a new held-out group are needed.

    python -m benchmarks.frozen check            # what a held-out run will check
    python -m benchmarks.frozen manifest --out docs/benchmarks/frozen-manifest.md
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FROZEN_TAG = "models-frozen-v1"
ROOT = Path(__file__).resolve().parent.parent

# The files that define the predictions (shell-style patterns relative to the repository root).
FROZEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("src/nexus/models/*.py", "operation models: Tier 0 / Tier 1 RAM and the derived time terms"),
    ("src/nexus/analyzer.py", "which operations a cell contains (what gets estimated)"),
    ("src/nexus/state.py", "state inspection: the descriptors the models read"),
    ("src/nexus/stats.py", "Tier 1 statistics"),
    ("src/nexus/registry.py", "model registry"),
    ("src/nexus/pipeline.py", "analyze -> inspect -> models, policy and time calibration applied"),
    ("src/nexus/failsafe.py", "deadlines: the Tier 1 time budget"),
    ("src/nexus/guard.py", "Tier 1 sanity guard"),
    ("src/nexus/ranges.py", "RAM range policy B"),
    ("src/nexus/controller.py", "Tier 2 controller rules and thresholds"),
    ("src/nexus/dryrun*.py", "Tier 2 dry run: safety, sampling, sandbox I/O, scaling fits"),
    ("src/nexus/_dryrun_child.py", "Tier 2 sandbox child"),
    ("src/nexus/risk.py", "risk-engine classes and thresholds"),
    ("src/nexus/timecal.py", "applies the time calibration artifact (ranges, flags, widening)"),
    ("src/nexus/timebuckets.py", "user-facing time buckets"),
    ("src/nexus/machine.py", "machine profile format 3 and the generic profile"),
    ("src/nexus/calibrate.py", "what the machine profile measures"),
    ("src/nexus/calibration/*.json", "calibration artifact and reference machine profile"),
    ("src/nexus/suggestions/engine.py", "suggestion filter thresholds"),
    # added 2026-11-21 (Phase 6b), after the tag: the measurement instrument and its validation
    ("src/nexus/measure.py", "the measurement instrument (peak RAM, time) of every held-out actual"),
    ("tests/test_measure_validation.py", "the instrument's validation (known allocations within 10%)"),
)  # fmt: skip
ADDED_AFTER_TAG = {
    "src/nexus/measure.py": "2026-11-21",
    "tests/test_measure_validation.py": "2026-11-21",
}
OUTSIDE = (
    "docs/ (reports, access logs, this manifest)",
    "benchmarks/ (harness, evaluation scripts, split.json, which has its own digest checks)",
    "tests/ except tests/test_measure_validation.py, .github/ (CI), .gitignore, pyproject.toml",
    "src/nexus/calfit.py (refits an artifact; the shipped artifact itself is frozen)",
    "UX modules: extension.py, session.py, magics.py, render.py, suggestions/ rules and formatting",
    "the Phase 8a real-notebook harness (not written yet)",
)


class NotFrozenError(RuntimeError):
    """A file that defines the predictions differs from the frozen tag."""


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout


CRLF, LF = bytes((13, 10)), bytes((10,))


def _norm_sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(CRLF, LF)).hexdigest()


def _matches(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pat) for pat, _ in FROZEN_PATTERNS)


def frozen_files(tag: str = FROZEN_TAG) -> list[str]:
    """The frozen files as they exist in the tag's tree."""
    tree = _git("ls-tree", "-r", "--name-only", tag).splitlines()
    return sorted(p for p in tree if _matches(p))


def tag_hashes(tag: str = FROZEN_TAG) -> dict[str, str]:
    return {p: _norm_sha(_git_bytes("show", f"{tag}:{p}")) for p in frozen_files(tag)}


def frozen_state(tag: str = FROZEN_TAG) -> dict[str, Any]:
    """Tag commit, HEAD and the frozen-file differences that would make a held-out run abort."""
    try:
        tag_commit = _git("rev-list", "-n", "1", tag)
    except (OSError, subprocess.CalledProcessError):
        return {"tag": tag, "tag_commit": None, "problems": [f"git tag {tag!r} not found"]}
    head = _git("rev-parse", "HEAD")
    expected = tag_hashes(tag)
    problems = []
    for path, sha in expected.items():
        local = ROOT / path
        if not local.exists():
            problems.append(f"frozen file missing: {path}")
        elif _norm_sha(local.read_bytes()) != sha:
            problems.append(f"frozen file differs from {tag}: {path}")
    for pat, _ in FROZEN_PATTERNS:
        for local in ROOT.glob(pat):
            rel = local.relative_to(ROOT).as_posix()
            if "__pycache__" not in rel and rel not in expected:
                problems.append(f"new file under a frozen pattern: {rel}")
    return {"tag": tag, "tag_commit": tag_commit, "head": head, "files": len(expected),
            "problems": problems}  # fmt: skip


def require_frozen(tag: str = FROZEN_TAG) -> dict[str, Any]:
    """Abort (``NotFrozenError``) unless the working tree is the frozen stack; return its record."""
    return check_state(frozen_state(tag))


def check_state(state: dict[str, Any]) -> dict[str, Any]:
    tag = state["tag"]
    if state["problems"]:
        listed = "\n  ".join(state["problems"][:20])
        raise NotFrozenError(
            f"held-out runs must use the frozen model stack `{tag}`, but the working tree differs:\n"
            f"  {listed}\nCheck out the tag (`git checkout {tag}`) or restore the files; a model "
            "change after the freeze invalidates the held-out status (new freeze + new held-out group)."
        )
    return {"frozen_tag": tag, "frozen_commit": state["tag_commit"], "head": state["head"]}


# -- manifest ----------------------------------------------------------------------------------
def manifest_lines() -> list[str]:
    import numpy as np
    import pandas as pd

    from nexus import calfit, risk, timecal
    from nexus.machine import CURVES, PROFILE_FORMAT, reference_profile
    from nexus.suggestions import engine

    art = json.loads((ROOT / "src/nexus/calibration/calibration-v1.json").read_text())
    hashes = tag_hashes()
    state = frozen_state()
    diff = _git("diff", "--stat", FROZEN_TAG, "--", *hashes)
    roles = {}
    for path in hashes:
        roles[path] = next(r for pat, r in FROZEN_PATTERNS if fnmatch.fnmatchcase(path, pat))
    lines = [
        f"# Frozen model stack `{FROZEN_TAG}`",
        "",
        f"Tag `{FROZEN_TAG}` = commit `{state.get('tag_commit')}` (Phase 6; unchanged). Written by "
        "`python -m benchmarks.frozen manifest`. Held-out runs (val-v5, the Phase 8a real-notebook test, test-v2) "
        "call `benchmarks.frozen.require_frozen()`, which compares the SHA-256 (LF line endings) of every file listed "
        "below with the tag's own copy and **aborts if any of them differs, is missing, or a new file matches a frozen "
        "pattern**. **Any change to a frozen file invalidates their held-out status** (a new freeze, tag and held-out "
        "group would be needed).",
        "",
        "## Scope narrowed after the tag (Phase 6b, 2026-11-21)",
        "",
        "At the tag the guard compared every tracked file outside `docs/` with the tag, so an unrelated `.gitignore` "
        "line, a CI change or a new evaluation harness (Phase 8a) would have aborted the held-out runs or forced a new "
        "freeze. Phase 6b narrowed the check to the files that define the predictions. The tagged commit was not "
        "changed and **no frozen file changed**: at the time this manifest was written,",
        "",
        "```",
        f"git diff --stat {FROZEN_TAG} -- <the {len(hashes)} frozen files below>",
        diff or "(empty: no difference)",
        "```",
        "",
        f"and `python -m benchmarks.frozen check` reported {len(state['problems'])} problems.",
        "",
        "## Scope extended (Phase 6b, 2026-11-21)",
        "",
        "Added to the frozen set after the tag, at the user's request, so that a held-out run also aborts when the "
        "measurement instrument behind its actuals changed: `src/nexus/measure.py` and its validation test "
        "`tests/test_measure_validation.py`. Both are compared with the tag's copies like every other frozen file; "
        "at the time of the extension neither differed from the tag (`git diff models-frozen-v1 -- "
        "src/nexus/measure.py tests/test_measure_validation.py` empty) and the original frozen files were still "
        "unchanged (the `git diff` above).",
        "",
        "## Deliberately outside the freeze",
        "",
        *[f"- {o}" for o in OUTSIDE],
        "",
        "## Versions",
        "",
        f"- python {sys.version.split()[0]}, pandas {pd.__version__}, numpy {np.__version__} (the dev machine)",
        f"- calibration artifact `{art['name']}` format {art['format']}, created {art['created']} at "
        f"commit {art['git_commit']}, selected candidate {art['selected_candidate']}, validated pandas "
        f"{', '.join(art['validated_pandas'])}, data {art['data']['results']} (sha256/16 "
        f"{art['data']['sha256_16']}), {len(art['fitted_parameters'])} fitted parameters",
        f"- machine profile format {PROFILE_FORMAT}; curves {', '.join(sorted(CURVES))}; reference profile id "
        f"{reference_profile().profile_id} (the generic profile is it with every cost x2)",
        "",
        "## Policy and thresholds in force",
        "",
        "- RAM: range policy B (Tier 1 low / expected, Tier 0 high; `nexus/ranges.py`), guard (`nexus/guard.py`)",
        f"- time: calibration artifact, nominal coverage {1 - calfit.ALPHA:.0%} per operation (>= "
        f"{calfit.MIN_CONFIGURATIONS} configurations), generic band {1 - calfit.GENERIC_ALPHA:.0%}; widen x"
        f"{timecal.UNCALIBRATED_MACHINE_WIDEN:g} uncalibrated machine, x{timecal.UNVALIDATED_PANDAS_WIDEN:g} "
        f"unvalidated pandas, x{timecal.NO_ARTIFACT_WIDEN:g} no artifact",
        f"- risk: WARN margin {risk.WARN_MARGIN}, confidence floor {risk.CONFIDENCE_FLOOR}; time shown as buckets",
        f"- suggestions: saving >= {engine.MIN_SAVING_FRAC:.0%} and >= {engine.MIN_SAVING_BYTES >> 20} MiB, "
        "`select_columns` off by default",
        "- Tier 2: opt-in (`Pipeline(tier=2)`), controller rules of docs/benchmarks/phase4d-preregistration.md",
        "",
        f"## Frozen files ({len(hashes)}; hashes of the tag's copies)",
        "",
        "| file | role | sha256 |",
        "|---|---|---|",
    ]
    lines += [
        f"| `{path}` | {roles[path]}"
        + (f" (added {ADDED_AFTER_TAG[path]})" if path in ADDED_AFTER_TAG else "")
        + f" | `{sha}` |"
        for path, sha in hashes.items()
    ]
    return lines


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m benchmarks.frozen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    m = sub.add_parser("manifest")
    m.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    if args.cmd == "check":
        state = frozen_state()
        print(json.dumps(state, indent=1))
        sys.exit(1 if state["problems"] else 0)
    args.out.write_text("\n".join(manifest_lines()) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
