"""Time is shown as an order-of-magnitude bucket with the measured run-to-run variation."""

from __future__ import annotations

import pandas as pd
import pytest

from nexus.timebuckets import BUCKETS, bucket_index, bucket_label, describe


@pytest.mark.parametrize(
    ("seconds", "label"),
    [(0.0, "under 0.1 s"), (0.099, "under 0.1 s"), (0.1, "0.1-1 s"), (3.2, "1-10 s"),
     (59.9, "10-60 s"), (60.0, "1-10 min"), (599.0, "1-10 min"), (3600.0, "over 10 min")],
)  # fmt: skip
def test_bucket_boundaries(seconds, label):
    assert bucket_label(seconds) == label


def test_buckets_are_ordered_and_cover_everything():
    uppers = [u for u, _ in BUCKETS]
    assert uppers == sorted(uppers) and uppers[-1] == float("inf")
    assert bucket_index(-1.0) == 0 and bucket_index(1e12) == len(BUCKETS) - 1


def test_describe_names_the_bucket_and_the_measured_variation_not_a_number():
    text = describe(1.5, 2.0, 4.0)
    assert text.startswith("about 1-10 s") and "median of 9%" in text and "30%" in text
    assert "2.0 s" not in text  # no false precision
    wide = describe(0.05, 0.5, 20.0)
    assert "most likely 0.1-1 s" in wide and "under 0.1 s" in wide and "10-60 s" in wide


def test_report_formats_time_as_a_bucket():
    from nexus.analyzer import DetectedOp
    from nexus.models.base import Estimate
    from nexus.pipeline import CellReport, OpEstimate
    from nexus.render import format_report

    est = Estimate(ram_low=1, ram_expected=2, ram_high=3, time_low=0.3, time_expected=0.5,
                   time_high=0.9, confidence=0.5, tier=0, drivers=[])  # fmt: skip
    op = DetectedOp(name="sort_values", lineno=1, args=[], kwargs={}, variables=("df",), receiver="df",
                    node=None)  # fmt: skip
    report = CellReport(ops=[op], estimates=[OpEstimate(op=op, model="m", estimate=est)])
    text = format_report(report)
    assert "about 0.1-1 s" in text and "500 ms" not in text


def test_evaluate_reports_a_bucket_agreement_table():
    from benchmarks.evaluate import time_bucket_table

    df = pd.DataFrame(
        {"tier": [1, 1, 1], "op": ["a", "a", "b"], "has_estimate": [True] * 3,
         "time_class": ["valid"] * 3, "time_value": [0.5, 5.0, 50.0], "time_expected": [0.4, 0.5, 40.0],
         "time_low": [0.1, 0.1, 10.0], "time_high": [1.0, 0.9, 60.0], "time_spread": [0.1, 0.1, 0.2]}
    )  # fmt: skip
    t = time_bucket_table(df, 1).set_index("op")
    assert (
        t.loc["a", "same"] == 0.5
        and t.loc["a", "within_one"] == 1.0
        and t.loc["a", "range_hit"] == 0.5
    )
    assert t.loc["b", "same"] == 1.0 and t.loc["ALL", "time_n"] == 3
