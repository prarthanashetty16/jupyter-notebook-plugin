"""The frozen model stack (Phase 6): manifest, and the guard that held-out runs must pass.

``models-frozen-v1`` is a git tag. A held-out run (val-v5 through ``python -m benchmarks full
--splits val-v5``, its ``evaluate --val``, ``evaluate --final`` for test-v2, and the Phase 8a
real-notebook evaluation) calls ``require_frozen()``: it aborts unless the tracked files that
affect predictions or their scoring are byte-identical to the tag (everything except ``docs/``,
which the held-out runs themselves append to: access logs and reports) and nothing untracked lies
under ``src/`` or ``benchmarks/`` (``benchmarks/results/`` is git-ignored). The commit is recorded
in the run's ``meta.json`` / report. Any model change after the freeze invalidates the held-out
status of these runs: a new freeze (new tag, new manifest) and a new held-out group are needed.

    python -m benchmarks.frozen check            # what a held-out run will check
    python -m benchmarks.frozen manifest --out docs/benchmarks/frozen-manifest.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

FROZEN_TAG = "models-frozen-v1"
ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = ("docs",)  # appended to by the held-out runs themselves


class NotFrozenError(RuntimeError):
    """The working tree is not the frozen model stack."""


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def frozen_state(tag: str = FROZEN_TAG) -> dict[str, Any]:
    """Tag commit, HEAD and the differences that would make a held-out run abort."""
    try:
        tag_commit = _git("rev-list", "-n", "1", tag)
    except (OSError, subprocess.CalledProcessError):
        return {"tag": tag, "tag_commit": None, "problems": [f"git tag {tag!r} not found"]}
    head = _git("rev-parse", "HEAD")
    excludes = [f":(exclude){e}" for e in EXCLUDED]
    diff = _git("diff", "--name-only", tag, "--", ".", *excludes).splitlines()
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", "src", "benchmarks")
    problems = [f"differs from {tag}: {p}" for p in diff if p]
    problems += [f"untracked file: {p}" for p in untracked.splitlines() if p]
    return {"tag": tag, "tag_commit": tag_commit, "head": head, "problems": problems}


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
MODEL_FILES = (
    "src/nexus/models/*.py", "src/nexus/machine.py", "src/nexus/calibrate.py",
    "src/nexus/timecal.py", "src/nexus/calfit.py", "src/nexus/ranges.py", "src/nexus/guard.py",
    "src/nexus/risk.py", "src/nexus/controller.py", "src/nexus/pipeline.py", "src/nexus/stats.py",
    "src/nexus/state.py", "src/nexus/analyzer.py", "src/nexus/dryrun*.py", "src/nexus/_dryrun_child.py",
    "src/nexus/timebuckets.py", "src/nexus/suggestions/**/*.py", "src/nexus/measure.py",
    "src/nexus/calibration/*.json", "benchmarks/split.json",
)  # fmt: skip


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def manifest_lines() -> list[str]:
    import numpy as np
    import pandas as pd

    from nexus import calfit, risk, timecal
    from nexus.machine import CURVES, PROFILE_FORMAT, reference_profile
    from nexus.suggestions import engine

    art = json.loads((ROOT / "src/nexus/calibration/calibration-v1.json").read_text())
    files = sorted(
        {p for pat in MODEL_FILES for p in ROOT.glob(pat) if "__pycache__" not in p.parts}
    )
    lines = [
        f"# Frozen model stack `{FROZEN_TAG}`",
        "",
        "Written by `python -m benchmarks.frozen manifest` at the freeze. Held-out runs (val-v5, the Phase 8a "
        "real-notebook test, test-v2) check out this tag and abort if the tracked files outside `docs/` "
        "differ from it (`benchmarks/frozen.py`). **Any model change after the freeze invalidates their "
        "held-out status.** Hashes are SHA-256 of the file with LF line endings.",
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
        "## File hashes",
        "",
        "| file | sha256 |",
        "|---|---|",
    ]
    lines += [f"| `{p.relative_to(ROOT).as_posix()}` | `{_sha(p)}` |" for p in files]
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
