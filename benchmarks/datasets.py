"""Seeded, reproducible synthetic dataset generators for the benchmark.

Columns of ``make_frame`` (each group present only if its count is > 0):
``k`` (row identity of the *unique* base row; duplicated rows repeat it), ``i0..`` int64,
``f0..`` float64, ``s0..`` text, ``c0..`` category, ``d0..`` datetime.

Knobs added for the test-v2 configurations (defaults reproduce the earlier datasets bit for bit):
``zipf_exponent``, ``null_pattern`` ("uniform" or "clustered" runs), ``str_len_dist`` ("fixed" or
"variable" lognormal lengths) and ``ordering`` ("random" or "block_sorted").

Knobs: row count, per-dtype column counts, string length, cardinality, null rate, duplicate rate
(share of rows that exactly repeat an earlier row), distribution ("uniform" or "real_like":
zipfian categories/ints and lognormal floats), whether repeated strings share one Python object.
Null rates apply to float, text, category and datetime columns (int64 cannot hold nulls).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace
from typing import Any

import numpy as np
import pandas as pd

_CHUNK = 1_000_000
ZIPF_EXPONENT = 1.2
_DISTRIBUTIONS = ("uniform", "real_like")
_NULL_PATTERNS = ("uniform", "clustered")
_STR_LEN_DISTS = ("fixed", "variable")
_ORDERINGS = ("random", "block_sorted")
NULL_RUN_LENGTH = 64
SORT_BLOCK = 4096
_NEW_FIELDS = {
    "zipf_exponent": ZIPF_EXPONENT,
    "null_pattern": "uniform",
    "str_len_dist": "fixed",
    "ordering": "random",
}


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
    zipf_exponent: float = ZIPF_EXPONENT
    null_pattern: str = "uniform"
    str_len_dist: str = "fixed"
    ordering: str = "random"

    def __repr__(self) -> str:
        """Like the dataclass repr, but omits the newer knobs at their defaults so existing
        configs keep the same repr (and therefore the same on-disk cache keys)."""
        parts = [
            f"{f.name}={getattr(self, f.name)!r}"
            for f in fields(self)
            if f.name not in _NEW_FIELDS or getattr(self, f.name) != _NEW_FIELDS[f.name]
        ]
        return f"DatasetConfig({', '.join(parts)})"

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
        if self.null_pattern not in _NULL_PATTERNS:
            raise ValueError(f"null_pattern must be one of {_NULL_PATTERNS}")
        if self.str_len_dist not in _STR_LEN_DISTS:
            raise ValueError(f"str_len_dist must be one of {_STR_LEN_DISTS}")
        if self.ordering not in _ORDERINGS:
            raise ValueError(f"ordering must be one of {_ORDERINGS}")
        if self.zipf_exponent <= 0:
            raise ValueError("zipf_exponent must be > 0")

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


def _codes(
    rng: np.random.Generator,
    card: int,
    n: int,
    distribution: str,
    exponent: float = ZIPF_EXPONENT,
) -> np.ndarray:
    if distribution == "uniform" or card == 1:
        return rng.integers(0, card, n)
    weights = 1.0 / np.arange(1, card + 1) ** exponent
    cdf = np.cumsum(weights)
    cdf /= cdf[-1]
    return np.minimum(np.searchsorted(cdf, rng.random(n)), card - 1)


def _vocab(rng: np.random.Generator, card: int, length: int, variable: bool = False) -> np.ndarray:
    """``card`` distinct lowercase strings; the id is encoded in the prefix.

    Fixed: every string has ``length`` characters. Variable: lengths are lognormal around
    ``length`` (sigma 0.6), clipped to [needed, 4 * length].
    """
    needed = max(1, math.ceil(math.log(card, 26) + 1e-9)) if card > 1 else 1
    if length < needed:
        raise ValueError(f"str_len={length} cannot hold {card} distinct strings")
    width = length
    lengths = None
    if variable:
        lengths = np.clip(np.rint(rng.lognormal(math.log(length), 0.6, card)), needed, 4 * length)
        lengths = lengths.astype(np.int64)
        width = int(lengths.max())
    ids = np.arange(card)
    chars = np.empty((card, width), dtype=np.uint8)
    for j in range(needed - 1, -1, -1):
        chars[:, j] = 97 + ids % 26
        ids = ids // 26
    if width > needed:
        chars[:, needed:] = rng.integers(97, 123, size=(card, width - needed), dtype=np.uint8)
    if lengths is not None:
        chars[np.arange(width)[None, :] >= lengths[:, None]] = 0  # NUL padding is stripped by 'S'
    return chars.view(f"S{width}").ravel().astype(f"U{width}")


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


def _clustered_mask(rng: np.random.Generator, n: int, rate: float) -> np.ndarray:
    """Nulls in contiguous runs of ~NULL_RUN_LENGTH rows (about ``rate`` of all rows)."""
    n_runs = max(1, round(n * rate / NULL_RUN_LENGTH))
    starts = rng.integers(0, n, n_runs)
    diff = np.zeros(n + 1, dtype=np.int64)
    np.add.at(diff, starts, 1)
    np.add.at(diff, np.minimum(starts + NULL_RUN_LENGTH, n), -1)
    return np.cumsum(diff[:-1]) > 0


def _block_sorted_order(key: np.ndarray, block: int = SORT_BLOCK) -> np.ndarray:
    """Row order that sorts ``key`` within consecutive blocks (nearly-sorted-by-runs data)."""
    n = len(key)
    order = np.empty(n, dtype=np.int64)
    for start in range(0, n, block):
        sl = slice(start, min(start + block, n))
        order[sl] = start + np.argsort(key[sl], kind="stable")
    return order


def _base_columns(cfg: DatasetConfig, rng: np.random.Generator) -> dict[str, Any]:  # noqa: C901
    nu, card, dist, exp = cfg.n_unique, cfg.card, cfg.distribution, cfg.zipf_exponent
    variable = cfg.str_len_dist == "variable"
    cols: dict[str, Any] = {}

    def null_mask() -> np.ndarray | None:
        if cfg.null_rate <= 0:
            return None
        if cfg.null_pattern == "clustered":
            return _clustered_mask(rng, nu, cfg.null_rate)
        return rng.random(nu) < cfg.null_rate

    if cfg.with_key:
        cols["k"] = rng.permutation(nu).astype(np.int64)
    for j in range(cfg.n_int):
        cols[f"i{j}"] = _codes(rng, card, nu, dist, exp).astype(np.int64)
    for j in range(cfg.n_float):
        values = rng.lognormal(0.0, 1.5, nu) if dist == "real_like" else rng.random(nu)
        mask = null_mask()
        if mask is not None:
            values[mask] = np.nan
        cols[f"f{j}"] = values
    for j in range(cfg.n_object):
        vocab = _vocab(rng, card, cfg.str_len, variable).astype(object)
        arr = vocab[_codes(rng, card, nu, dist, exp)]
        mask = null_mask()
        if mask is not None:
            arr[mask] = None
        cols[f"s{j}"] = arr
    for j in range(cfg.n_category):
        codes = _codes(rng, card, nu, dist, exp).astype(np.int64)
        mask = null_mask()
        if mask is not None:
            codes[mask] = -1
        cols[f"c{j}"] = ("category", codes, _vocab(rng, card, cfg.str_len, variable))
    for j in range(cfg.n_datetime):
        seconds = 1_500_000_000 + rng.integers(0, 157_680_000, nu)
        stamps = seconds.astype("datetime64[s]")
        mask = null_mask()
        if mask is not None:
            stamps[mask] = np.datetime64("NaT", "s")
        cols[f"d{j}"] = stamps
    if cfg.ordering == "block_sorted":
        sort_key = cols.get("i0", cols.get("f0", cols.get("k")))
        if sort_key is not None:
            order = _block_sorted_order(sort_key)
            cols = {
                name: ((col[0], col[1][order], col[2]) if isinstance(col, tuple) else col[order])
                for name, col in cols.items()
            }
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
    right_key_dist: str = "uniform",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two frames joinable on ``k``.

    ``overlap``: share of the right side's distinct keys that exist in the left frame.
    ``fanout``: right rows per distinct right key. With unique left keys the inner join has
    about ``right_rows * overlap`` rows; repeated left keys (``left.dup_rate``) multiply that.
    ``right_key_dist="zipf"`` draws the right rows' keys with a zipfian weight over the right keys
    (a few keys get most of the rows: skewed fan-out) instead of an even round-robin.
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
    if right_key_dist == "zipf":
        row_keys = keys[_codes(rng, len(keys), right_rows, "real_like", 1.5)]
    else:
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
        zipf_exponent=left.zipf_exponent,
        str_len_dist=left.str_len_dist,
        seed=seed,
    )
    right_df = make_frame(payload)
    right_df.insert(0, "k", row_keys)
    return left_df, right_df
