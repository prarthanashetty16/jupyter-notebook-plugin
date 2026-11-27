"""Synthetic fixtures used by the headless notebook demo."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_measure_frame(rows: int = 1_000_000) -> pd.DataFrame:
    """Create a deterministic frame for the drop_duplicates measurement."""
    values = np.arange(rows, dtype=np.int64)
    return pd.DataFrame({"key": values, "value": values % 10})


def drop_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    """Run the measured operation in a fresh child process."""
    return frame.drop_duplicates()


def make_merge_frames(rows: int = 1_000_000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build wide one-to-one join inputs that make column pruning visible."""
    keys = np.arange(rows, dtype=np.int64)
    left = pd.DataFrame({"key": keys, "left_value": keys % 100})
    right = pd.DataFrame({"key": keys.copy(), "right_value": keys % 200})
    for i in range(8):
        left[f"left_extra{i}"] = keys + i
        right[f"right_extra{i}"] = keys + i
    return left, right
