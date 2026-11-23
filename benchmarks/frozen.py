"""The frozen model stack: manifest, and the guard that held-out runs must pass.

The current freeze is ``FROZEN_TAG`` (``models-frozen-v3``, Phase 7d; the tag name lives ONLY here: the guard and
every held-out entry point use this constant). ``models-frozen-v2`` (Phase 6c) and ``models-frozen-v1`` (Phase 6) are
kept and documented in ``docs/benchmarks/frozen-manifest-v2.md`` / ``-v1.md``. A held-out run (val-v5 through ``python -m benchmarks
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

FROZEN_TAG = "models-frozen-v3"
PREVIOUS_TAG = "models-frozen-v2"
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
    ("src/nexus/cellpeak.py", "cell-level peak model (Phase 6c)"),
    ("src/nexus/cellframes.py", "frames created earlier in the cell: shape propagation / shadowing (Phase 7b)"),
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
    "UX modules: extension.py, session.py, magics.py, render.py (fallback wording), suggestions/ rules and formatting",
    "the real-notebook harness (benchmarks/realworld/), the multicell runner and splits (benchmarks/multicell/)",
    "benchmarks/childproc.py, benchmarks/powerguard.py (--allow-battery: dev-only, refused for held-out runs), "
    "benchmarks/repredict.py, benchmarks/risk_eval.py (the R1-R3 replay of evaluate --val)",
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


def frozen_files(
    tag: str = FROZEN_TAG,
) -> list[str]:  # ``tag``: any git ref (a tag, or HEAD before tagging)
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
HISTORY = (
    ("models-frozen-v1", "Phase 6", "time calibration, ranges, the measurement instrument (manifest: "
     "`docs/benchmarks/frozen-manifest-v1.md`)"),
    ("models-frozen-v2", "Phase 6c", "cell-level peak model, read_csv Tier 1 with sep / header, copy and fillna models, "
     "Tier 1 as the extension default (manifest: `docs/benchmarks/frozen-manifest-v2.md`)"),
    ("models-frozen-v3", "Phase 7d", "read_csv reader paths and arguments, merge output term, consolidation check, "
     "conservative rebinding release, frames created in the cell, apply(np.<ufunc>), set_index, cell-seeded sampler, "
     "risk v2 (C3) and named UNKNOWN (`docs/benchmarks/phase7b/README.md`)"),
)  # fmt: skip
LIMITATIONS = (
    "**Determinism NOT achieved on contended machines**: the deterministic statistics gate failed its pre-registered rule "
    "(the deadline fired after admission on 12 of 29 2-core inputs, 41% > 10%) and was **reverted** to v2's adaptive gate; "
    "final code: 12 of 28 inputs flip Tier 1 / Tier 0 on 2 contended CPUs, 0 of 28 on 16 CPUs; same-tier spreads remain "
    "(drop_duplicates strings 10M ~22%, groupby 10M 0.05%).",
    "**Item (2) dev criterion FAILED**: 2 of 66 v1 multi-statement cells above the v3 high (copy_fillna/mixed, 88 vs 65 and "
    "176 vs 130 MiB; an uncovered fillna on text columns); risk UNKNOWN or HIGH_RISK, never OK.",
    "**Uncovered**: value_counts, explode, apply with Python functions, set_index with text / several keys / append, "
    "fillna on text columns, parse_dates, text columns on the parallel read_csv path (v2 term), operations on merge / "
    "groupby / drop_duplicates results made in the cell; no column statistics carried between statements.",
    "**CPU-dependent read_csv path**: parallel (file >= 5 MiB and pandas' worker count > 1; affinity / cgroup on Linux "
    "only) or serial; the same call can get another estimate on another machine.",
    "**One laptop, synthetic data**: every probe and dev figure comes from one Windows 11 laptop and synthetic frames "
    "(plus two dev notebooks); Linux only through the planned val-v5 VM run.",
    "**Supported environment**: pandas >= 3.1 (Python >= 3.11) on Windows and Linux. Models and the instrument's "
    "validation assume pandas 3 copy-on-write (Python 3.10 resolves pandas 2.x: unsupported, report-only in CI); on "
    "macOS the instrument cannot isolate an operation's peak (report-only in CI). Derived from pandas 3.1.1 only.",
    "**R2 is a dev selection**: risk v2 (C3) was selected on dev by a rule written beforehand (dev R2 pooled 17.1%, merge "
    "9.4%, read_csv 39.0%); it is a claim only if val-v5 confirms it.",
)  # fmt: skip


def manifest_lines(ref: str = FROZEN_TAG) -> list[str]:  # noqa: C901
    """The manifest of ``FROZEN_TAG``; frozen-file hashes read from ``ref`` (HEAD before the tag exists)."""
    import numpy as np
    import pandas as pd

    from nexus import calfit, risk, timecal
    from nexus.machine import CURVES, PROFILE_FORMAT, reference_profile
    from nexus.session import DEFAULT_TIER
    from nexus.suggestions import engine

    art = json.loads((ROOT / "src/nexus/calibration/calibration-v1.json").read_text())
    hashes = tag_hashes(ref)
    previous = tag_hashes(PREVIOUS_TAG)
    roles = {
        p: next(r for pat, r in FROZEN_PATTERNS if fnmatch.fnmatchcase(p, pat)) for p in hashes
    }
    changed = sorted(p for p in hashes if p in previous and previous[p] != hashes[p])
    added = sorted(p for p in hashes if p not in previous)
    unchanged = sorted(p for p in hashes if p in previous and previous[p] == hashes[p])
    removed = sorted(p for p in previous if p not in hashes)
    lines = [
        f"# Frozen model stack `{FROZEN_TAG}`",
        "",
        f"Written by `python -m benchmarks.frozen manifest` from `{ref}` (commit `{_git('rev-parse', ref)[:12]}`); the "
        f"annotated tag `{FROZEN_TAG}` is created on the commit that adds this file, whose frozen files are byte-identical "
        "to these. Held-out runs (multicell v2 / v3, val-v5, test-v2, Phase 8b) call `benchmarks.frozen.require_frozen()`, "
        "which compares the SHA-256 (LF line endings) of every frozen file with the tag's own copy and **aborts if any "
        f"differs, is missing, or a new file matches a frozen pattern**. **Any change to a frozen file after `{FROZEN_TAG}` "
        "invalidates the held-out status of those runs** (a new freeze, tag and held-out groups would be needed).",
        "",
        "## History",
        "",
        *[f"- `{t}` ({ph}): {what}" for t, ph, what in HISTORY],
        "",
        f"## Frozen files: {len(changed)} changed, {len(added)} added, {len(unchanged)} unchanged since `{PREVIOUS_TAG}`"
        + (f", {len(removed)} removed" if removed else ""),
        "",
        f"| file | status | role | sha256 {PREVIOUS_TAG} | sha256 {FROZEN_TAG} |",
        "|---|---|---|---|---|",
    ]  # fmt: skip
    for group, status in ((changed, "changed"), (added, "added"), (unchanged, "unchanged")):
        for path in group:
            lines.append(
                f"| `{path}` | {status} | {roles[path]} | `{previous.get(path, '-')[:16]}` | `{hashes[path][:16]}` |"
            )
    for path in removed:
        lines.append(f"| `{path}` | removed | - | `{previous[path][:16]}` | - |")
    lines += [
        "",
        "The table shows the first 16 hex digits; the guard recomputes full hashes from the tag on every check.",
        "",
        "## Deliberately outside the freeze",
        "",
        *[f"- {o}" for o in OUTSIDE],
        "",
        f"## Known limitations of `{FROZEN_TAG}`",
        "",
        *[f"- {x}" for x in LIMITATIONS],
        "",
        "## Versions",
        "",
        f"- python {sys.version.split()[0]}, pandas {pd.__version__}, numpy {np.__version__} (the dev machine)",
        f"- calibration artifact `{art['name']}` format {art['format']} (unchanged since v1), selected candidate "
        f"{art['selected_candidate']}, validated pandas {', '.join(art['validated_pandas'])}, "
        f"{len(art['fitted_parameters'])} fitted parameters",
        f"- machine profile format {PROFILE_FORMAT}; curves {', '.join(sorted(CURVES))}; reference profile id "
        f"{reference_profile().profile_id} (the generic profile is it with every cost x2)",
        "",
        "## Policy and thresholds in force",
        "",
        "- RAM: range policy B (Tier 1 low / expected, Tier 0 high; `nexus/ranges.py`, unchanged), guard (`nexus/guard.py`,"
        " unchanged); cell level: `nexus/cellpeak.py` (retained outputs + current peak, conservative rebinding release)",
        f"- time: calibration artifact, nominal coverage {1 - calfit.ALPHA:.0%} per operation (>= "
        f"{calfit.MIN_CONFIGURATIONS} configurations), generic band {1 - calfit.GENERIC_ALPHA:.0%}; widen x"
        f"{timecal.UNCALIBRATED_MACHINE_WIDEN:g} uncalibrated machine, x{timecal.UNVALIDATED_PANDAS_WIDEN:g} "
        f"unvalidated pandas, x{timecal.NO_ARTIFACT_WIDEN:g} no artifact",
        f"- risk: WARN margin {risk.WARN_MARGIN}, confidence floor {risk.CONFIDENCE_FLOOR} (unchanged); risk v2: WARN on the "
        f"own Tier 1 high for {', '.join(sorted(risk.OWN_TIER1_HIGH_FOR_WARN))} when statistics ran; time shown as buckets",
        f"- suggestions: saving >= {engine.MIN_SAVING_FRAC:.0%} and >= {engine.MIN_SAVING_BYTES >> 20} MiB, "
        "`select_columns` off by default",
        f"- extension default: Tier {DEFAULT_TIER} (Tier 2 dry runs opt-in with `%nexus tier 2`)",
    ]  # fmt: skip
    return lines


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m benchmarks.frozen")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    m = sub.add_parser("manifest")
    m.add_argument("--out", type=Path, required=True)
    m.add_argument(
        "--ref", default=FROZEN_TAG, help="git ref of the frozen files (HEAD before the tag exists)"
    )
    args = p.parse_args(argv)
    if args.cmd == "check":
        state = frozen_state()
        print(json.dumps(state, indent=1))
        sys.exit(1 if state["problems"] else 0)
    args.out.write_text("\n".join(manifest_lines(args.ref)) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
