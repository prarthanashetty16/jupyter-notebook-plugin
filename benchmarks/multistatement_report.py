"""How much realistic multi-statement code does the Tier 2 safety analyzer accept? (Phase 4d)

Runs ``nexus.dryrun_safety.analyze_safety`` over ``benchmarks.multistatement_cells.CELLS`` and
reports the accepted share, by category, and why the rest are rejected. The analyzer is not changed.

    python -m benchmarks.multistatement_report [--out FILE]
"""

from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from benchmarks.multistatement_cells import CELLS, make_namespace
from nexus.dryrun_safety import analyze_safety

CLASSES = [
    (r"statements \(exactly one", "more than one statement"),
    (r"inplace", "in-place operation"),
    (
        r"assignment target is not a plain name",
        "assignment to a subscript / attribute / tuple (mutation)",
    ),
    (
        r"statement type|shell|magic",
        "other statement type (import, def, for, if, with, ...) or magic",
    ),
    (r"method chain|computed receiver|not a supported call", "method chain or computed receiver"),
    (
        r"argument is not a literal|plain variable that exists|literal",
        "non-literal argument (a variable, expression or call)",
    ),
    (r"allowlist|not in the", "operation or keyword outside the allowlist"),
    (r"does not exist|existing local file", "file not a literal existing path"),
]


def classify(reason: str) -> str:
    for pattern, label in CLASSES:
        if re.search(pattern, reason):
            return label
    return "other: " + reason[:60]


def evaluate() -> list[dict]:
    rows = []
    for name, category, source in CELLS:
        v = analyze_safety(source, make_namespace())
        rows.append({"name": name, "category": category, "source": source, "safe": v.safe,
                     "reason": "" if v.safe else v.reasons[0], "why": "" if v.safe else classify(v.reasons[0])})  # fmt: skip
    return rows


def markdown(rows: list[dict]) -> str:
    n, ok = len(rows), sum(r["safe"] for r in rows)
    lines = [f"# Tier 2 safety analyzer on {n} realistic multi-statement cells (analyzer unchanged)\n",
             f"**Accepted: {ok} of {n} ({ok / n:.0%}):** {', '.join(r['name'] for r in rows if r['safe'])}.\n",
             "## By category\n", "| category | cells | accepted |", "|---|---|---|"]  # fmt: skip
    cats = Counter(r["category"] for r in rows)
    for c in cats:
        k = sum(r["safe"] for r in rows if r["category"] == c)
        lines.append(f"| {c} | {cats[c]} | {k} |")
    lines += ["\n## Why the rest were rejected (first reason)\n", "| reason | cells |", "|---|---|"]
    for why, k in Counter(r["why"] for r in rows if not r["safe"]).most_common():
        lines.append(f"| {why} | {k} |")
    lines += ["\n## Every cell\n", "| cell | category | accepted | reason |", "|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['category']} | {'yes' if r['safe'] else 'no'} | {r['reason'][:90]} |"
        )
    return "\n".join(lines) + "\n" + PROPOSALS


PROPOSALS = """
## Candidate relaxations (PROPOSALS ONLY: nothing below is implemented; each needs its own safety review and a fresh split)

| # | proposal | would accept | risk |
|---|---|---|---|
| P1 | resolve non-literal arguments (`keys`, `col`, `on=keys`, `target`) from the namespace when the value is an immutable literal-like object (str, int, tuple / list of str) | variable-argument cells (8 of 51 here) | a list or frame bound to the name can be mutated between cells, so the value seen at analysis time may differ from the value at run time; an earlier statement of the cell may rebind the name. Mitigation: only names not assigned in the cell |
| P2 | per-statement dry runs: split the cell into statements, accept each that passes alone, dry-run only the one that matches a supported operation | multi-statement cells whose expensive statement is a supported single operation (`clean = df.drop_duplicates()` before `out = clean.merge(...)`) | an earlier statement may have side effects or rebind the operand (`df = df[df.f > 0]`), so the sample is drawn from a different object than the later statement sees; needs a data-flow check that the operand is unchanged |
| P3 | execute short whitelisted chains in the child (`sort_values -> drop_duplicates`, `groupby -> agg -> reset_index`) with the sampling of the first operation | method chains (9 of 51) | the sampling is designed for the first operation (key-hash for merge) and is not valid for later ones; the extrapolation law of a chain is not one operation's |
| P4 | accept pure result wrappers (`.head(n)`, `.reset_index()`) after a supported operation | wrapper cells | `print` and plots are side effects; only pure wrappers should pass |
| P5 | accept boolean-mask / `query` filters before a supported operation | filter cells (6 of 51) | needs evaluating an arbitrary expression in the child (an eval of user code), the largest hole; or restrict to comparisons against literals on a named column |
| P6 | accept aggregation dictionaries / named aggregations in `groupby(...).agg(...)` | groupby cells with `agg` | callables inside the dictionary; literal strings only would be safe |
| P7 | accept `import pandas as pd`-style imports | cells starting with imports | an import runs module code; only `pandas` / `numpy` / `time` could be whitelisted |

Each proposal widens what is executed on SAMPLES in a sandbox; the sandbox bounds the damage (timeout, memory cap, no
shared address space), but a relaxation that lets user code run in the child (P5) gives it the user's data. The mutation
cells in this set (in-place calls, column assignment) must stay rejected under every proposal.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    text = markdown(evaluate())
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
