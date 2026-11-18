"""Pilot run: time the first N points (priority order) and extrapolate the rest.

``python -m benchmarks full ... --pilot N`` runs only the first N points of the grid (for val-v5 the
grid is in priority order: merge, groupby, astype, drop_duplicates, read_csv; then concat, sort_values;
then np.sort, matmul) and writes ``pilot.json`` next to the results with the seconds each point took
(measurement + prediction + one-off input generation) and a total estimate for the points that were
NOT run. Method: the mean seconds of the pilot points of the same size; a size the pilot did not reach
is scaled from the nearest size it did (linear in rows; quadratic in the dimension for matmul). The low
/ high figures use the fastest / slowest pilot point of that size (+-50% when there is only one).
It is an estimate to size the VM budget, not a promise: large sizes are extrapolated from small ones.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DIM_OPS = frozenset({"operator.matmul"})


def _exponent(op: str) -> float:
    return 2.0 if op in DIM_OPS else 1.0


def extrapolate(timed: list[dict[str, Any]], remaining: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate the seconds for ``remaining`` points ({id, op, size}) from ``timed`` pilot points."""
    by_size: dict[tuple[bool, int], list[float]] = {}
    for t in timed:
        by_size.setdefault((t["op"] in DIM_OPS, int(t["size"])), []).append(float(t["seconds"]))
    if not by_size:
        return {"ok": False, "reason": "no timed pilot point"}
    low = exp = high = 0.0
    scaled = 0
    for r in remaining:
        dim = r["op"] in DIM_OPS
        size = int(r["size"])
        seen = {s: v for (d, s), v in by_size.items() if d == dim}
        if (
            not seen
        ):  # no pilot point of this kind (e.g. matmul): scale from the other kind's largest
            seen = {s: v for (_, s), v in by_size.items()}
            ref = max(seen)
            vals = [x * (size / ref) ** _exponent(r["op"]) for x in seen[ref]] if dim else seen[ref]
            scaled += 1
        elif size in seen:
            vals = seen[size]
        else:
            ref = min(seen, key=lambda s: abs(s - size))
            vals = [x * (size / ref) ** _exponent(r["op"]) for x in seen[ref]]
            scaled += 1
        mean = sum(vals) / len(vals)
        lo, hi = (min(vals), max(vals)) if len(vals) > 1 else (0.5 * mean, 1.5 * mean)
        low, exp, high = low + lo, exp + mean, high + hi
    return {"ok": True, "points_remaining": len(remaining), "points_scaled": scaled,
            "seconds_low": low, "seconds_expected": exp, "seconds_high": high,
            "hours_expected": exp / 3600, "hours_low": low / 3600, "hours_high": high / 3600}  # fmt: skip


def write(
    out_dir: Path,
    pilot_n: int,
    timed: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
    elapsed_s: float,
) -> dict[str, Any]:
    est = extrapolate(timed, remaining)
    report = {"pilot_points": pilot_n, "measured_points": len(timed), "pilot_seconds": elapsed_s,
              "seconds_per_point_mean": (sum(t["seconds"] for t in timed) / len(timed)) if timed else None,
              "points": timed, "estimate_remaining": est}  # fmt: skip
    (out_dir / "pilot.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def summary(report: dict[str, Any]) -> str:
    e = report["estimate_remaining"]
    if not e.get("ok"):
        return f"pilot: no estimate ({e.get('reason')})"
    return (f"pilot: {report['measured_points']} points took {report['pilot_seconds'] / 60:.1f} min "
            f"({report['seconds_per_point_mean']:.0f} s/point); the remaining {e['points_remaining']} points: "
            f"~{e['hours_expected']:.1f} h (range {e['hours_low']:.1f}-{e['hours_high']:.1f} h; "
            f"{e['points_scaled']} scaled from other sizes). Full run ~{(e['seconds_expected'] + report['pilot_seconds']) / 3600:.1f} h")  # fmt: skip
