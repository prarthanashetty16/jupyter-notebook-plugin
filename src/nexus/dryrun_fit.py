"""Scaling fits for Tier 2: peak RAM / time of a cell at several sample sizes -> the full size.

Three laws, each with a fixed cost: ``y = a + b * f(n)`` with ``f`` linear, ``n log n`` or
quadratic, ``a >= 0`` and ``b >= 0`` (a cost cannot shrink as the input grows). They are compared by
FORWARD cross-validation: fit on the smaller samples, predict the next larger one. Plain
leave-one-out would let a law interpolate between its neighbours; the job here is extrapolation, so
the validation extrapolates too. The extrapolation range carries (a) the cross-validation error of
the candidate laws (model-selection uncertainty: every law whose error is close to the best one is a
candidate and the range spans all of them) and (b) the distance travelled: a wrong exponent costs a
constant factor per doubling, so the standard deviation grows with ``log2(target / largest sample)``.

The fit refuses to answer (``ok=False`` with a reason) when fewer than three points are usable, the
measurement does not grow with the size (it is a fixed cost or noise), or no law predicts the next
sample within ``CV_MAX``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

LAWS: dict[str, Callable[[float], float]] = {
    "linear": lambda n: n,
    "nlogn": lambda n: n * math.log2(max(n, 2.0)),
    "quadratic": lambda n: n * n,
}
CV_MAX = 0.25  # best forward-CV error (rms of log(pred / actual)) above which no estimate is given
MIN_POINTS = 3
MIN_GROWTH = 1.3  # largest / smallest usable measurement: below this it is a fixed cost or noise
CV_FLOOR = 0.02  # a perfect fit on three points says little; never claim less than 2%
SELECTION_SLACK = (2.0, 0.05)  # laws within max(2 x best, best + 0.05) are candidates
Z_HIGH, Z_LOW = 1.64, 1.28  # one-sided 95% / 90%: under-prediction is the dangerous side


@dataclass(frozen=True)
class FitResult:
    """Outcome of one scaling fit (RAM or time)."""

    ok: bool
    reason: str = ""
    expected: float = math.nan
    low: float = math.nan
    high: float = math.nan
    best: str = ""
    laws: dict[str, dict[str, float]] = field(default_factory=dict)
    sizes: tuple[float, ...] = ()
    values: tuple[float, ...] = ()
    target: float = math.nan
    ratio: float = math.nan  # target / largest sample

    def diagnostics(self) -> dict[str, Any]:
        """JSON-friendly summary recorded in the Estimate."""
        return {
            "ok": self.ok, "reason": self.reason, "best_law": self.best, "target": self.target,
            "extrapolation_ratio": self.ratio, "sizes": list(self.sizes), "values": list(self.values),
            "laws": self.laws,
        }  # fmt: skip


def fit_law(xs: Sequence[float], ys: Sequence[float], law: str) -> tuple[float, float]:
    """Least squares ``y = a + b * f(x)`` with ``a, b >= 0`` (``f`` normalised at the largest x)."""
    f = LAWS[law]
    scale = f(max(xs)) or 1.0
    u = np.array([f(x) / scale for x in xs])
    y = np.asarray(ys, dtype=float)
    a_mat = np.vstack([np.ones_like(u), u]).T
    a, b = np.linalg.lstsq(a_mat, y, rcond=None)[0]
    if b < 0:
        a, b = float(np.mean(y)), 0.0
    elif a < 0:
        a, b = 0.0, float((u @ y) / (u @ u))
    return float(a), float(b / scale)


def predict(a: float, b: float, law: str, x: float) -> float:
    return a + b * LAWS[law](x)


def _forward_cv(xs: Sequence[float], ys: Sequence[float], law: str) -> float:
    errors = []
    for j in range(max(2, len(xs) - 2), len(xs)):
        a, b = fit_law(xs[:j], ys[:j], law)
        pred = max(predict(a, b, law, xs[j]), 1e-12)
        errors.append(math.log(pred / ys[j]))
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def fit_scaling(xs: Sequence[float], ys: Sequence[float], target: float) -> FitResult:
    """Fit the three laws to ``(size, value)`` pairs and extrapolate to ``target`` size."""
    pts = sorted((float(x), float(y)) for x, y in zip(xs, ys, strict=True) if y > 0 and x > 0)
    if len(pts) < MIN_POINTS:
        return FitResult(False, f"only {len(pts)} usable sample sizes (need {MIN_POINTS})")
    sizes, values = tuple(p[0] for p in pts), tuple(p[1] for p in pts)
    base = {"sizes": sizes, "values": values, "target": float(target)}
    if target <= sizes[-1]:
        return FitResult(False, "target is not larger than the largest sample", **base)
    if values[-1] / values[0] < MIN_GROWTH:
        return FitResult(False, "no growth with sample size (fixed cost or noise)", **base)
    ratio = target / sizes[-1]
    laws: dict[str, dict[str, float]] = {}
    for law in LAWS:
        a, b = fit_law(sizes, values, law)
        laws[law] = {"intercept": a, "slope": b, "cv": _forward_cv(sizes, values, law),
                     "extrapolated": predict(a, b, law, target)}  # fmt: skip
    best = min(laws, key=lambda k: (laws[k]["cv"], list(LAWS).index(k)))
    best_cv = laws[best]["cv"]
    if best_cv > CV_MAX:
        return FitResult(False, f"no law predicts the next sample (best CV error {best_cv:.2f})",
                         best=best, laws=laws, ratio=ratio, **base)  # fmt: skip
    cutoff = max(SELECTION_SLACK[0] * best_cv, best_cv + SELECTION_SLACK[1])
    lows, highs = [], []
    for d in laws.values():
        if d["cv"] > cutoff:
            continue
        sigma = max(d["cv"], CV_FLOOR) * max(1.0, math.log2(ratio))
        lows.append(d["extrapolated"] * math.exp(-Z_LOW * sigma))
        highs.append(d["extrapolated"] * math.exp(Z_HIGH * sigma))
    expected = laws[best]["extrapolated"]
    return FitResult(True, "", expected, min(lows + [expected]), max(highs + [expected]), best, laws,
                     ratio=ratio, **base)  # fmt: skip
