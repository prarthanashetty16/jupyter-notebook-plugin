import pandas as pd

from benchmarks.phase8_verdict import width_criteria


def test_width_b_counts_v4_points_not_estimated_by_v3():
    point_ids = [f"point-{index}" for index in range(35)]
    current = pd.DataFrame(
        {
            "point_id": point_ids,
            "tier": 1,
            "has_estimate": True,
            "ram_class": "valid",
            "ram_expected": 100.0,
            "ram_high": 150.0,
        }
    )
    baseline = pd.DataFrame(
        {
            "point_id": point_ids,
            "v3_has_estimate": False,
            "v3_ram_expected": float("nan"),
            "v3_ram_high": float("nan"),
        }
    )

    width = width_criteria(current, baseline)

    assert width["W(b)"]["n"] == 35
    assert width["W(b)"]["median"] == 1.5
    assert width["W(b)"]["verdict"] == "MET"
