"""Seeded, reproducible synthetic dataset generators for the benchmark.

Columns of ``make_frame`` (each group present only if its count is > 0):
``k`` (row identity of the *unique* base row; duplicated rows repeat it), ``i0..`` int64,
``f0..`` float64, ``s0..`` text, ``c0..`` category, ``d0..`` datetime.

Knobs: row count, per-dtype column counts, string length, cardinality, null rate, duplicate rate
(share of rows that exactly repeat an earlier row), distribution ("uniform" or "real_like":
zipfian categories/ints and lognormal floats), whether repeated strings share one Python object.
Null rates apply to float, text, category and datetime columns (int64 cannot hold nulls).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

_CHUNK = 1_000_000
ZIPF_EXPONENT = 1.2
_DISTRIBUTIONS = ("uniform", "real_like")


@dataclass(frozen=True)
class DatasetConfig:
    n_rows: int
    n_int: int = 2
    n_float: int = 2
    n_object: int = 2
    n_category: int = 1
    n_datetime: int = 1
    str_len: int = 12
    cardinality: float = (
        0.1  # distinct values: <= 1 means a fraction of rows, > 1 an absolute count
    )
    null_rate: float = 0.0
    dup_rate: float = 0.0
    distribution: str = "uniform"
    with_key: bool = True
    share_strings: bool = True  # repeated strings reuse one object (like read_csv) vs distinct
    str_dtype: str = "object"  # "object" or "str" (pandas >= 3)
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_rows < 1:
            raise ValueError("n_rows must be >= 1")
        if not 0 <= self.dup_rate < 1:
            raise ValueError("dup_rate must be in [0, 1)")
        if not 0 <= self.null_rate <= 1:
            raise ValueError("null_rate must be in [0, 1]")
        if self.distribution not in _DISTRIBUTIONS:
            raise ValueError(f"distribution must be one of {_DISTRIBUTIONS}")
        if self.cardinality <= 0:
            raise ValueError("cardinality must be > 0")

    def with_(self, **changes: Any) -> DatasetConfig:
        return replace(self, **changes)

    @property
    def n_unique(self) -> int:
        """Number of distinct base rows."""
        return max(1, round(self.n_rows * (1 - self.dup_rate)))

    @property
    def card(self) -> int:
        """Distinct values per int/text/category column."""
        c = self.cardinality
        value = int(c * self.n_rows) if c <= 1 else int(c)
        return max(1, min(value, self.n_unique))


def estimate_frame_bytes(cfg: DatasetConfig) -> int:
    """Rough resident size of ``make_frame(cfg)`` (used to cap runs, not as ground truth)."""
    n, card = cfg.n_rows, cfg.card
    per_row = 8 * (1 if cfg.with_key else 0) + 8 * (cfg.n_int + cfg.n_float + cfg.n_datetime)
    per_row += cfg.n_object * 8 + cfg.n_category * (1 if card < 128 else 2 if card < 32768 else 4)
    distinct_str = (49 + cfg.str_len) * card * (cfg.n_object + cfg.n_category)
    if not cfg.share_strings:
        distinct_str = (49 + cfg.str_len) * n * cfg.n_object
    return int(n * per_row + distinct_str)


def _codes(rng: np.random.Generator, card: int, n: int, distribution: str) -> np.ndarray:
    if distribution == "uniform" or card == 1:
        return rng.integers(0, card, n)
    weights = 1.0 / np.arange(1, card + 1) ** ZIPF_EXPONENT
    cdf = np.cumsum(weights)
    cdf /= cdf[-1]
    return np.minimum(np.searchsorted(cdf, rng.random(n)), card - 1)


def _vocab(rng: np.random.Generator, card: int, length: int) -> np.ndarray:
    """``card`` distinct lowercase strings of ``length``; the id is encoded in the prefix."""
    needed = max(1, math.ceil(math.log(card, 26) + 1e-9)) if card > 1 else 1
    if length < needed:
        raise ValueError(f"str_len={length} cannot hold {card} distinct strings")
    ids = np.arange(card)
    chars = np.empty((card, length), dtype=np.uint8)
    for j in range(needed - 1, -1, -1):
        chars[:, j] = 97 + ids % 26
        ids = ids // 26
    if length > needed:
        chars[:, needed:] = rng.integers(97, 123, size=(card, length - needed), dtype=np.uint8)
    return chars.view(f"S{length}").ravel().astype(f"U{length}")


def _unshare(arr: np.ndarray) -> np.ndarray:
    """Give every element its own Python str object (chunked to bound the temporary)."""
    out = np.empty(len(arr), dtype=object)
    for start in range(0, len(arr), _CHUNK):
        chunk = arr[start : start + _CHUNK]
        has_null = np.array([x is None for x in chunk])
        fresh = np.where(has_null, "", chunk).astype("U").astype(object)
        fresh[has_null] = None
        out[start : start + _CHUNK] = fresh
    return out


def _base_columns(cfg: DatasetConfig, rng: np.random.Generator) -> dict[str, Any]:  # noqa: C901
    nu, card, dist = cfg.n_unique, cfg.card, cfg.distribution
    cols: dict[str, Any] = {}

    def null_mask() -> np.ndarray | None:
        return rng.random(nu) < cfg.null_rate if cfg.null_rate > 0 else None

    if cfg.with_key:
        cols["k"] = rng.permutation(nu).astype(np.int64)
    for j in range(cfg.n_int):
        cols[f"i{j}"] = _codes(rng, card, nu, dist).astype(np.int64)
    for j in range(cfg.n_float):
        values = rng.lognormal(0.0, 1.5, nu) if dist == "real_like" else rng.random(nu)
        mask = null_mask()
        if mask is not None:
            values[mask] = np.nan
        cols[f"f{j}"] = values
    for j in range(cfg.n_object):
        arr = _vocab(rng, card, cfg.str_len).astype(object)[_codes(rng, card, nu, dist)]
        mask = null_mask()
        if mask is not None:
            arr[mask] = None
        cols[f"s{j}"] = arr
    for j in range(cfg.n_category):
        codes = _codes(rng, card, nu, dist).astype(np.int64)
        mask = null_mask()
        if mask is not None:
            codes[mask] = -1
        cols[f"c{j}"] = ("category", codes, _vocab(rng, card, cfg.str_len))
    for j in range(cfg.n_datetime):
        seconds = 1_500_000_000 + rng.integers(0, 157_680_000, nu)
        stamps = seconds.astype("datetime64[s]")
        mask = null_mask()
        if mask is not None:
            stamps[mask] = np.datetime64("NaT", "s")
        cols[f"d{j}"] = stamps
    return cols


def make_frame(cfg: DatasetConfig) -> pd.DataFrame:
    """Build the DataFrame for ``cfg``; identical for identical configs."""
    rng = np.random.default_rng(cfg.seed)
    base = _base_columns(cfg, rng)
    n, nu = cfg.n_rows, cfg.n_unique
    idx = None
    if nu < n:
        idx = np.concatenate([np.arange(nu), rng.integers(0, nu, n - nu)])
        rng.shuffle(idx)
    out: dict[str, Any] = {}
    for name, col in base.items():
        if isinstance(col, tuple):
            _, codes, vocab = col
            codes = codes if idx is None else codes[idx]
            out[name] = pd.Categorical.from_codes(codes, categories=pd.Index(vocab))
            continue
        col = col if idx is None else col[idx]
        if col.dtype == object:
            if not cfg.share_strings:
                col = _unshare(col)
            out[name] = pd.Series(col, dtype=object if cfg.str_dtype == "object" else cfg.str_dtype)
        else:
            out[name] = col
    return pd.DataFrame(out)


def make_join_pair(
    left: DatasetConfig,
    right_rows: int,
    *,
    overlap: float = 1.0,
    fanout: float = 1.0,
    right_n_float: int = 2,
    right_n_object: int = 1,
    seed: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two frames joinable on ``k``.

    ``overlap``: share of the right side's distinct keys that exist in the left frame.
    ``fanout``: right rows per distinct right key. With unique left keys the inner join has
    about ``right_rows * overlap`` rows; repeated left keys (``left.dup_rate``) multiply that.
    """
    if not left.with_key:
        raise ValueError("left config needs with_key=True")
    if not 0 <= overlap <= 1 or fanout < 1:
        raise ValueError("overlap must be in [0, 1] and fanout >= 1")
    left_df = make_frame(left)
    rng = np.random.default_rng(seed)
    n_keys = max(1, math.ceil(right_rows / fanout))
    n_match = min(round(n_keys * overlap), left.n_unique)
    matched = rng.choice(left.n_unique, n_match, replace=False)
    unmatched = left.n_unique + np.arange(n_keys - n_match)
    keys = np.concatenate([matched, unmatched]).astype(np.int64)
    row_keys = keys[np.arange(right_rows) % len(keys)]
    rng.shuffle(row_keys)
    payload = DatasetConfig(
        n_rows=right_rows,
        n_int=0,
        n_float=right_n_float,
        n_object=right_n_object,
        n_category=0,
        n_datetime=0,
        str_len=left.str_len,
        cardinality=left.cardinality,
        with_key=False,
        distribution=left.distribution,
        seed=seed,
    )
    right_df = make_frame(payload)
    right_df.insert(0, "k", row_keys)
    return left_df, right_df
