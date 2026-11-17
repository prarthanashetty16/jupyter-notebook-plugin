"""Wall time as an order-of-magnitude bucket, not a number.

Why: the time models are first drafts. On the development split their median bias is 1.1x but
individual points are off by 0.3x-8x (read_csv under-predicted, groupby / astype / float32 matmul
over-predicted), far more than the run-to-run noise of the measurement (repeats of the same point
spread by a median of 9% and a 90th percentile of 30% of the median). A figure such as "1.3 s"
would imply a precision the models do not have; a decade bucket is what they can support. Phase 6
calibrates the models; until then the user-facing output and the benchmark report use buckets.
"""

from __future__ import annotations

import math

# (upper bound in seconds, label); the last bucket is open-ended
BUCKETS: tuple[tuple[float, str], ...] = (
    (0.1, "under 0.1 s"),
    (1.0, "0.1-1 s"),
    (10.0, "1-10 s"),
    (60.0, "10-60 s"),
    (600.0, "1-10 min"),
    (math.inf, "over 10 min"),
)
REPEAT_SPREAD_MEDIAN = 0.09  # (max - min) / median of repeated runs, development points >= 0.1 s
REPEAT_SPREAD_P90 = 0.30


def bucket_index(seconds: float) -> int:
    """Index of the bucket that contains ``seconds`` (negative values count as the first)."""
    for i, (upper, _) in enumerate(BUCKETS):
        if seconds < upper:
            return i
    return len(BUCKETS) - 1


def bucket_label(seconds: float) -> str:
    return BUCKETS[bucket_index(seconds)][1]


def describe(low: float, expected: float, high: float) -> str:
    """User-facing time statement for an estimate: the bucket, and a wider one if the range spans it."""
    lo, mid, hi = bucket_index(low), bucket_index(expected), bucket_index(high)
    if lo == hi:
        text = f"about {BUCKETS[mid][1]}"
    else:
        text = f"most likely {BUCKETS[mid][1]} (could be {BUCKETS[lo][1]} .. {BUCKETS[hi][1]})"
    return (
        f"{text}; coarse: repeated runs of one cell varied by a median of {REPEAT_SPREAD_MEDIAN:.0%} "
        f"(90th percentile {REPEAT_SPREAD_P90:.0%}), the models are less exact than that"
    )
