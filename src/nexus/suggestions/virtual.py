"""Column profiles of a live frame and virtual descriptors for the estimator.

Profiles read the live data (read-only, bounded by a deadline); virtual descriptors are what the
frozen models see after a suggestion's modification. Nothing is copied or mutated.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from nexus import stats
from nexus.failsafe import Deadline
from nexus.state import FrameDescriptor

SAMPLE_ROWS = 50_000
POINTER = 8


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    dtype: str
    n_rows: int
    bytes_per_row: float  # deep, sampled for text
    distinct: float | None = None  # estimated distinct values (text / category candidates)
    lo: float | None = None  # exact min / max of integer columns (None otherwise)
    hi: float | None = None
    is_text: bool = False
    is_float: bool = False
    is_int: bool = False
    nulls: bool = False


def _is_text(dtype: Any) -> bool:
    return bool(pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype))


def profile_frame(
    df: pd.DataFrame, columns: list[str] | None = None, deadline: Deadline | None = None
) -> dict[str, ColumnProfile]:
    """Profiles of ``columns`` (default all); raises TimeoutError if ``deadline`` expires."""
    n = len(df)
    out: dict[str, ColumnProfile] = {}
    for col in columns if columns is not None else list(df.columns):
        if deadline is not None:
            deadline.check()
        s = df[col]
        if not isinstance(s, pd.Series):  # duplicate column names: not provable
            continue
        dt = s.dtype
        text = _is_text(dt)
        if text:
            step = max(1, n // SAMPLE_ROWS)
            sample = s.iloc[::step]
            bpr = float(sample.memory_usage(index=False, deep=True)) / max(len(sample), 1)
            d = stats.distinct_count(s, deadline=deadline, share=0.2).value if n else 0.0
            out[col] = ColumnProfile(col, str(dt), n, bpr, distinct=float(d), is_text=True,
                                     nulls=bool(sample.isna().any()))  # fmt: skip
        elif pd.api.types.is_integer_dtype(dt) and not pd.api.types.is_extension_array_dtype(dt):
            lo, hi = (int(s.min()), int(s.max())) if n else (0, 0)
            out[col] = ColumnProfile(col, str(dt), n, float(dt.itemsize), lo=lo, hi=hi, is_int=True)
        elif pd.api.types.is_float_dtype(dt) and not pd.api.types.is_extension_array_dtype(dt):
            out[col] = ColumnProfile(col, str(dt), n, float(dt.itemsize), is_float=True,
                                     nulls=bool(s.isna().any()))  # fmt: skip
        else:
            bpr = float(s.memory_usage(index=False, deep=False)) / max(n, 1)
            out[col] = ColumnProfile(col, str(dt), n, bpr)
    return out


def smallest_signed_int(lo: int, hi: int) -> str | None:
    for name, info in (("int8", np.iinfo(np.int8)), ("int16", np.iinfo(np.int16)),
                       ("int32", np.iinfo(np.int32))):  # fmt: skip
        if info.min <= lo and hi <= info.max:
            return name
    return None


def category_bytes_per_row(p: ColumnProfile) -> float:
    """Codes (smallest int that holds the categories) plus the distinct values once."""
    d = max(p.distinct or 1.0, 1.0)
    code = 1 if d < 2**7 else 2 if d < 2**15 else 4
    per_value = max(p.bytes_per_row, POINTER)
    return code + d * per_value / max(p.n_rows, 1)


def dtype_bytes_per_row(p: ColumnProfile, target: str) -> float:
    if target == "category":
        return category_bytes_per_row(p)
    return float(np.dtype(target).itemsize)


def virtual_frame(
    desc: FrameDescriptor,
    profiles: Mapping[str, ColumnProfile],
    *,
    keep: list[str] | None = None,
    retype: Mapping[str, str] | None = None,
) -> FrameDescriptor:
    """``desc`` after keeping only ``keep`` and giving ``retype`` columns new dtypes."""
    retype = dict(retype or {})
    cols = [c for c in desc.dtypes if keep is None or c in keep]
    n = desc.shape[0]
    removed = 0.0
    added = 0.0
    shallow_removed = 0.0
    shallow_added = 0.0
    dtypes: dict[str, str] = {}
    for c, dt in desc.dtypes.items():
        p = profiles.get(c)
        if c not in cols:
            if p is None:
                return desc  # not profiled: cannot build a faithful virtual descriptor
            removed += p.bytes_per_row * n
            shallow_removed += (POINTER if p.is_text else p.bytes_per_row) * n
            continue
        if c in retype and p is not None:
            new = dtype_bytes_per_row(p, retype[c])
            removed += p.bytes_per_row * n
            added += new * n
            shallow_removed += (POINTER if p.is_text else p.bytes_per_row) * n
            shallow_added += (new if retype[c] == "category" else new) * n
            dtypes[c] = retype[c]
        else:
            dtypes[c] = dt
    counts: dict[str, int] = {}
    for dt in dtypes.values():
        counts[dt] = counts.get(dt, 0) + 1
    shallow = (
        None
        if desc.shallow_bytes is None
        else int(max(0.0, desc.shallow_bytes - shallow_removed + shallow_added))
    )
    return replace(
        desc,
        shape=(n, len(cols)),
        dtypes=dtypes,
        dtype_counts=counts,
        nbytes=int(max(0.0, desc.nbytes - removed + added)),
        shallow_bytes=shallow,
        text_columns=sum(
            1
            for c in cols
            if profiles.get(c) is not None and profiles[c].is_text and c not in retype
        ),
        n_blocks=None,
        consolidated=None,
    )


def finite(x: float) -> bool:
    return math.isfinite(x)
