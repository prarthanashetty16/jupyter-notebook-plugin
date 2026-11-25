"""Tier 1 data statistics: cheap, bounded, read-only estimators with honest intervals.

Every function reads the user's objects without mutating them (positions are drawn, small slices
are copied, nothing is written back), polls a hard ``Deadline`` and fixed row/byte caps, and returns a
``Bounded`` estimate: ``value`` with a ``low``/``high`` interval, the sample size it rests on, a
``confidence`` in [0, 1] (how tight the interval is relative to what could be known: 1 = exact)
and the method used. Callers fall back to Tier 0 when the sample is too small
(``MIN_SAMPLE_ROWS``); expiry of the interceptor's hard deadline aborts analysis instead of
selecting a different tier.

Intervals are analytic:

* distinct counts: lower bound = distinct values seen; upper bound = seen + the unseen rows allowed
  by the Good-Turing missing-mass bound of McAllester & Schapire (95%); point estimate = the
  bias-corrected Chao1 estimator when there are enough doubletons, else a stated fallback;
* proportions: Wilson interval with the finite-population correction;
* join sizes: coordinated (key-hash) sampling of both sides, so the sampled keys have complete
  groups on both sides; variance of the Horvitz-Thompson sum;
* CSV files: line-length statistics of the head and of a few seeked chunks.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import io
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from nexus.failsafe import Deadline

DEFAULT_SAMPLE_ROWS = 200_000
MIN_SAMPLE_ROWS = 1_000  # below this a sample says too little about a large population
Z95 = 1.96
MCALLESTER_SCHAPIRE = 2 * math.sqrt(2) + math.sqrt(3)  # missing-mass deviation coefficient
LOG_3_OVER_DELTA = math.log(3 / 0.05)
CHUNK = 1 << 18  # rows per block when a whole column is scanned (bounds temporary memory)


@dataclass(frozen=True)
class Bounded:
    """An estimate with an interval, its sample size and a confidence in [0, 1]."""

    value: float
    low: float
    high: float
    sample: int
    population: int
    confidence: float
    method: str
    exact: bool = False

    def scaled(self, factor: float) -> Bounded:
        return Bounded(
            self.value * factor,
            self.low * factor,
            self.high * factor,
            self.sample,
            self.population,
            self.confidence,
            self.method,
            self.exact,
        )


def exact(value: float, population: int, method: str = "exact") -> Bounded:
    return Bounded(value, value, value, population, population, 1.0, method, True)


def _confidence(low: float, high: float, weak: bool = False) -> float:
    c = 1.0 if high <= 0 else max(0.0, min(1.0, (low + 1.0) / (high + 1.0)))
    return c * 0.5 if weak else c


# -- sampling -------------------------------------------------------------------------------------
# Phase 7b (determinism): the sampler's random stream is seeded from the CELL SOURCE as well as the call's
# own seed, so the same cell on the same data draws the same rows, and different cells draw independently.
_CELL_SALT: contextvars.ContextVar[int] = contextvars.ContextVar("nexus_cell_salt", default=0)


def cell_salt_of(source: str) -> int:
    return int(hashlib.sha256(source.encode("utf-8", "replace")).hexdigest()[:12], 16)


@contextlib.contextmanager
def cell_seed(source: str):  # noqa: ANN201
    """Seed every sample drawn inside the block from ``source`` (the cell being analysed)."""
    token = _CELL_SALT.set(cell_salt_of(source))
    try:
        yield
    finally:
        _CELL_SALT.reset(token)


def sample_positions(n: int, m: int, seed: int = 0) -> np.ndarray:
    """Sorted positions of ``m`` distinct rows out of ``n`` (all rows if ``m >= n``).

    Stratified: one uniformly random row inside each of ``m`` equal strata. O(m), no sort, and the
    random offset inside a stratum keeps periodic or clustered data from aliasing with the step. The
    stream is seeded by ``(seed, cell salt)`` (``cell_seed``).
    """
    if m >= n:
        return np.arange(n)
    rng = np.random.default_rng([seed, _CELL_SALT.get()])
    if n < 2 * m:  # tiny strata: plain sampling without replacement is as cheap
        return np.sort(rng.choice(n, size=m, replace=False))
    idx = np.arange(m, dtype=np.int64)
    lo = (idx * n) // m  # integer stratum boundaries: strata are disjoint by construction
    hi = ((idx + 1) * n) // m
    return lo + (rng.random(m) * (hi - lo)).astype(np.int64)


def _column(obj: Any, name: str | None = None) -> Any:
    return obj[name] if name is not None else obj


def take(obj: Any, positions: np.ndarray) -> pd.Series:
    """Copy of the rows at ``positions`` of a Series / ndarray / Index (never a view)."""
    if isinstance(obj, np.ndarray):
        return pd.Series(obj[positions])
    if isinstance(obj, pd.Index):
        return pd.Series(obj.take(positions))
    if isinstance(obj.dtype, pd.CategoricalDtype):
        # equal values <=> equal codes, and hashing the codes avoids re-hashing every category
        return pd.Series(obj.cat.codes.to_numpy()[positions])
    return obj.iloc[positions].reset_index(drop=True)


# -- distinct counts --------------------------------------------------------------------------------
def distinct_from_counts(counts: np.ndarray, population: int) -> Bounded:
    """Distinct values in a population of ``population`` rows, from the value counts of a sample.

    ``counts[i]`` is how often distinct value ``i`` occurs in the sample (sum = sample size r).
    """
    r = int(counts.sum())
    d = len(counts)
    if r >= population:
        return exact(d, population, "complete")
    f1 = int((counts == 1).sum())
    f2 = int((counts == 2).sum())
    if f1 == 0:  # every value was seen at least twice: coverage is (almost) complete
        missing = MCALLESTER_SCHAPIRE * math.sqrt(LOG_3_OVER_DELTA / r)
        high = d + min(population - r, missing * population)
        return Bounded(float(d), float(d), float(high), r, population, _confidence(d, high), "seen")
    missing = min(1.0, f1 / r + MCALLESTER_SCHAPIRE * math.sqrt(LOG_3_OVER_DELTA / r))
    high = float(min(population, d + min(population - r, missing * population)))
    chao = d + (f1 * f1 / (2.0 * f2) if f2 > 0 else f1 * (f1 - 1) / 2.0)
    value = float(min(max(chao, d), high))
    weak = f2 < 10  # too few doubletons: Chao1 is unstable
    return Bounded(value, float(d), high, r, population, _confidence(d, high, weak), "chao1", False)


PILOT_ROWS = 4096
MIN_AFFORDABLE_ROWS = 2_000


def affordable_rows(rows: int, budget_s: float | None, pilot: Any) -> int:
    """Sample size that fits ``budget_s``, from the timed ``pilot(m)`` (seconds for ``m`` rows).

    Raises TimeoutError when even ``MIN_AFFORDABLE_ROWS`` would not fit: a sample that small says
    too little, so the caller falls back to Tier 0 instead of reporting a meaningless interval.

    Phase 7b: a deterministic variant (profile-predicted cost against a fixed budget share, no
    shrinking to the live time left) was implemented and NOT adopted: on 2 contended CPUs the hard
    deadline fired after it had admitted the statistics on 12 of 29 dev inputs (41%), far above the
    pre-registered 10% failure bar (docs/benchmarks/phase7b/determinism_cores2.md). This v2 timed gate
    remains available only to callers opting into adaptive sampling; pipeline Tier 1 uses fixed samples.
    """
    if budget_s is None:
        return rows
    m0 = min(rows, PILOT_ROWS)
    per_row = max(pilot(m0) / m0, 1e-9)
    fit = int(budget_s / per_row)
    if fit < MIN_AFFORDABLE_ROWS and fit < rows:
        raise TimeoutError("time budget too small for a useful sample")
    return min(rows, fit)


def _budget(deadline: Deadline | None, share: float) -> float | None:
    return None if deadline is None else deadline.remaining() * share


def distinct_count(
    values: Any,
    *,
    rows: int = DEFAULT_SAMPLE_ROWS,
    deadline: Deadline | None = None,
    seed: int = 0,
    share: float = 0.5,
    adaptive: bool = True,
) -> Bounded:
    """Distinct values of a Series/array/Index (NaN counts as one value).

    ``adaptive=False`` keeps the registered sample size fixed; ``deadline`` then only aborts work
    when the interceptor's hard limit expires.
    """
    n = len(values)
    if n == 0:
        return exact(0, 0)

    def pilot(m: int) -> float:
        t0 = time.perf_counter()
        pd.factorize(take(values, sample_positions(n, m, seed + 1)), use_na_sentinel=False)
        return time.perf_counter() - t0

    sample_rows = min(rows, n)
    if adaptive:
        sample_rows = affordable_rows(sample_rows, _budget(deadline, share), pilot)
    pos = sample_positions(n, sample_rows, seed)
    if deadline is not None:
        deadline.check()
    sample = take(values, pos)
    codes, _ = pd.factorize(sample, use_na_sentinel=False)
    counts = np.bincount(codes)
    return distinct_from_counts(counts, n)


# -- how uniformly keys hash over a table ------------------------------------------------------------
SCATTER_REFERENCE_BUCKETS = 1 << 21
SCATTER_SAMPLE_ROWS = 20_000
SCATTER_MAX_DISTINCT = 8_000  # distinct values replayed through the hash replica
SCATTER_MARGIN = 0.15  # sampling noise allowance on both sides of the point estimate
_PAGE = 4096


def _x31(strings: list[str]) -> np.ndarray:
    """khash's X31 string hash (``h = 31 * h + byte``) as pandas' ``StringHashTable`` uses it."""
    raw = [s.encode("utf-8", "surrogatepass")[:256] for s in strings]
    width = max((len(b) for b in raw), default=1) or 1
    mat = np.zeros((len(raw), width), dtype=np.uint64)
    lens = np.fromiter((len(b) for b in raw), dtype=np.int64, count=len(raw))
    for i, b in enumerate(raw):
        mat[i, : len(b)] = np.frombuffer(b, dtype=np.uint8)
    h = mat[:, 0].copy()
    for j in range(1, width):
        nxt = (h * np.uint64(31) + mat[:, j]) & np.uint64(0xFFFFFFFF)
        h = np.where(j < lens, nxt, h)
    return h


def _int64_hash(values: np.ndarray) -> np.ndarray:
    """khash's int64 hash ``(k >> 33) ^ k ^ (k << 11)`` (low 32 bits)."""
    k = values.astype(np.uint64)
    return ((k >> np.uint64(33)) ^ k ^ (k << np.uint64(11))) & np.uint64(0xFFFFFFFF)


def hash_scatter(
    values: Any, *, text: bool, deadline: Deadline | None = None, seed: int = 0
) -> Bounded:
    """How uniformly the distinct values of a column hash over a presized pandas hash table.

    Returns the share of table pages the sampled distinct values touch relative to what the same
    number of RANDOMLY hashed keys would touch (1.0: random keys; ~0.05: sequential strings such as
    ``user_000123``; ~0.7: dense integers 0..U-1). The pandas tables only make a page resident when
    a key lands in it, so this share scales the resident size of a presized table. The hash
    functions are replicas of khash's (validated against measured resident growth:
    docs/benchmarks/val-v3-diagnosis/probes/pb6, pb7). Non-numeric, non-string objects hash through
    Python's randomised ``hash``: reported as 1.0.
    """
    n = len(values)
    if n == 0:
        return exact(1.0, 0, "empty")
    sample = take(values, sample_positions(n, min(SCATTER_SAMPLE_ROWS, n), seed))
    if deadline is not None:
        deadline.check()
    uniq = pd.unique(sample.to_numpy())
    uniq = uniq[: SCATTER_MAX_DISTINCT * 4]
    uniq = uniq[~pd.isna(uniq)] if uniq.dtype == object or uniq.dtype.kind == "f" else uniq
    uniq = uniq[:SCATTER_MAX_DISTINCT]
    m = len(uniq)
    if m < 200:  # a small table: its pages hardly matter
        return Bounded(1.0, 1.0, 1.0, m, n, 1.0, "few-distinct")
    kind = uniq.dtype.kind
    if text:
        if not all(isinstance(v, str) for v in uniq):
            return Bounded(1.0, 1.0, 1.0, m, n, 0.5, "non-string-objects")
        h = _x31(list(uniq))
        strides = (16, 8)
    elif kind in "iub":
        h, strides = _int64_hash(uniq.astype(np.int64)), (8, 8)
    elif kind in "fM":
        bits = uniq.astype(np.float64).view(np.int64) if kind == "f" else uniq.view(np.int64)
        h, strides = _int64_hash(bits), (8, 8)
    else:
        return Bounded(1.0, 1.0, 1.0, m, n, 0.5, "unhashed-kind")
    idx = (h & np.uint64(SCATTER_REFERENCE_BUCKETS - 1)).astype(np.int64)
    seen = expect = 0.0
    for stride in strides:
        per_page = _PAGE // stride
        pages = SCATTER_REFERENCE_BUCKETS / per_page
        seen += len(np.unique(idx // per_page))
        expect += pages * (1.0 - math.exp(-m / pages))
    value = min(1.0, seen / expect)
    return Bounded(
        value, max(0.0, value - SCATTER_MARGIN), min(1.0, value + SCATTER_MARGIN), m, n, 0.9,
        "khash-replica",
    )  # fmt: skip


def distinct_rows(
    columns: list[Any],
    *,
    rows: int = DEFAULT_SAMPLE_ROWS,
    deadline: Deadline | None = None,
    seed: int = 0,
    share: float = 0.5,
    adaptive: bool = True,
) -> Bounded:
    """Distinct combinations of several equal-length columns (a null equals a null).

    ``adaptive=False`` keeps the registered sample size fixed; ``deadline`` then only aborts work
    when the interceptor's hard limit expires.
    """
    n = len(columns[0])
    if n == 0:
        return exact(0, 0)

    def hashed_sample(m: int) -> np.ndarray:
        pos = sample_positions(n, m, seed)
        frame = pd.DataFrame({i: take(c, pos) for i, c in enumerate(columns)})
        return pd.util.hash_pandas_object(frame, index=False).to_numpy()

    def pilot(m: int) -> float:
        t0 = time.perf_counter()
        hashed_sample(m)
        return time.perf_counter() - t0

    sample_rows = min(rows, n)
    if adaptive:
        sample_rows = affordable_rows(sample_rows, _budget(deadline, share), pilot)
    if deadline is not None:
        deadline.check()
    _, counts = np.unique(hashed_sample(sample_rows), return_counts=True)
    return distinct_from_counts(counts, n)


# -- proportions and nulls -------------------------------------------------------------------------
def proportion(k: int, r: int, population: int | None = None) -> Bounded:
    """Share of rows with a property: ``k`` of the ``r`` sampled; Wilson 95% interval, fpc."""
    if r == 0:
        return Bounded(math.nan, 0.0, 1.0, 0, population or 0, 0.0, "none")
    p = k / r
    z2 = Z95 * Z95
    centre = (p + z2 / (2 * r)) / (1 + z2 / r)
    half = Z95 * math.sqrt(p * (1 - p) / r + z2 / (4 * r * r)) / (1 + z2 / r)
    if population is not None and population > r:
        half *= math.sqrt((population - r) / (population - 1))
    low, high = max(0.0, centre - half), min(1.0, centre + half)
    if population is not None and r >= population:
        return exact(p, population, "complete")
    return Bounded(p, low, high, r, population or r, _confidence(low, high), "wilson")


@dataclass(frozen=True)
class NullProfile:
    """Which columns contain nulls: ``certain`` hold at least one, ``possible`` cannot be ruled out."""

    certain: tuple[str, ...]
    possible: tuple[str, ...]  # undecided (text columns not fully scanned, none seen in the sample)
    fraction: dict[str, Bounded] = field(default_factory=dict)
    scanned_rows: int = 0


def _has_null_scan(values: Any, deadline: Deadline | None) -> bool:
    """Exact 'contains a null?' of a numpy-backed column, in blocks (1 byte/row temporaries)."""
    arr = values.to_numpy(copy=False) if hasattr(values, "to_numpy") else np.asarray(values)
    if arr.dtype.kind not in "fMm":
        return bool(pd.isna(arr).any())
    for start in range(0, len(arr), CHUNK):
        if deadline is not None:
            deadline.check()
        block = arr[start : start + CHUNK]
        if np.isnat(block).any() if block.dtype.kind in "Mm" else np.isnan(block).any():
            return True
    return False


def null_profile(
    df: Any,
    columns: list[str],
    *,
    rows: int = DEFAULT_SAMPLE_ROWS,
    deadline: Deadline | None = None,
) -> NullProfile:
    """Null presence per column. Float/datetime columns are scanned completely (a single null
    matters to pandas: ``get_group_index`` lifts any column that has one); other columns are
    judged from a row sample, and when it shows none they stay ``possible``."""
    n = len(df)
    pos = sample_positions(n, rows)
    certain, possible = [], []
    fraction: dict[str, Bounded] = {}
    for name in columns:
        if deadline is not None:
            deadline.check()
        col = df[name]
        kind = getattr(col.dtype, "kind", "O")
        if isinstance(col.dtype, np.dtype) and kind in "iub":
            fraction[name] = exact(0.0, n, "integer")
            continue
        if isinstance(col.dtype, np.dtype) and kind in "fMm":
            has = _has_null_scan(col, deadline)
            if has:
                certain.append(name)
            fraction[name] = proportion(int(col.iloc[pos].isna().sum()), len(pos), n)
            continue
        sampled = take(col, pos).isna()
        k = int(sampled.sum())
        fraction[name] = proportion(k, len(pos), n)
        if k > 0:
            certain.append(name)
        elif len(pos) < n:
            possible.append(name)
    return NullProfile(tuple(certain), tuple(possible), fraction, n)


# -- text columns ------------------------------------------------------------------------------------
@dataclass(frozen=True)
class TextProfile:
    mean_chars: Bounded
    shared_fraction: float | None  # share of repeated values that reuse one str object
    sample: int


def text_profile(
    values: Any, *, rows: int = 50_000, deadline: Deadline | None = None
) -> TextProfile:
    """Average string length and how many repeated values share one Python object.

    ``shared_fraction`` = 1 - (extra distinct objects)/(extra rows): 1.0 when every repeat of a
    value is the same object (the read_csv / categorical case), 0.0 when none is. None if the
    sample has no repeated value. Object ids are read, never modified.
    """
    n = len(values)
    pos = sample_positions(n, rows)
    sample = take(values, pos)
    if deadline is not None:
        deadline.check()
    present = sample.dropna()
    if present.empty:
        return TextProfile(exact(0.0, n, "empty"), None, 0)
    lengths = present.astype(str).str.len().to_numpy(dtype=float)
    mean = float(lengths.mean())
    half = Z95 * float(lengths.std(ddof=0)) / math.sqrt(len(lengths)) if len(lengths) > 1 else 0.0
    mean_b = Bounded(
        mean,
        mean - half,
        mean + half,
        len(lengths),
        n,
        _confidence(mean - half, mean + half),
        "mean",
    )
    shared = None
    if present.dtype == object or str(present.dtype) == "str":
        distinct_values = present.nunique()
        repeats = len(present) - distinct_values
        if repeats > 0:
            distinct_ids = len({id(v) for v in present.to_numpy()})
            shared = float(min(1.0, max(0.0, 1.0 - (distinct_ids - distinct_values) / repeats)))
    return TextProfile(mean_b, shared, len(present))


# -- merge: coordinated key sampling ------------------------------------------------------------------
class UnsupportedError(Exception):
    """The statistic does not apply (dtype, size or form); the caller falls back to Tier 0."""


_MIX = np.uint64(0x9E3779B97F4A7C15)
_TEXT_ROWS_LIMIT = 400_000  # hashing object keys costs ~0.2 us/row: scan them only up to this


def _key_bits(block: np.ndarray) -> np.ndarray:
    """Equality-preserving uint64 image of a block of key values."""
    kind = block.dtype.kind
    if kind in "iub":
        return block.astype(np.uint64, copy=False)
    if kind == "f":
        return np.ascontiguousarray(block, dtype=np.float64).view(np.uint64)
    if kind in "Mm":
        return block.view(np.int64).astype(np.uint64, copy=False)
    return pd.util.hash_array(block)


def _as_array(keys: Any) -> np.ndarray:
    arr = keys.to_numpy(copy=False) if hasattr(keys, "to_numpy") else np.asarray(keys)
    if arr.dtype.kind not in "iubfMm" and len(arr) > _TEXT_ROWS_LIMIT:
        raise UnsupportedError("text keys too large to scan within the budget")
    return arr


HEAVY_MIN_COUNT = 5  # a key seen this often in a 100k-row sample is "heavy" (>= 5e-5 of the rows)
MAX_HEAVY = 64


def scan_keys(
    arr: np.ndarray, shift: int, heavy: np.ndarray, deadline: Deadline | None
) -> tuple[np.ndarray, np.ndarray]:
    """One read-only pass over a key column, in blocks.

    Returns (key images whose multiplicative hash falls in the lowest 2**-shift of the hash space,
    exact counts of the ``heavy`` key images). Heavy keys are excluded from the hash sample: they
    are counted exactly instead, which removes the variance that a few very frequent keys would
    otherwise add. Both sides of a join use the same ``shift`` so each sampled key appears with
    all of its rows on both sides.
    """
    picked = []
    counts = np.zeros(len(heavy), dtype=np.int64)
    lookup = pd.Index(heavy) if len(heavy) else None
    for start in range(0, len(arr), CHUNK):
        if deadline is not None:
            deadline.check()
        bits = _key_bits(arr[start : start + CHUNK])
        if lookup is not None:
            where = lookup.get_indexer(bits)  # hash lookup, -1 for light keys
            hit = where >= 0
            if hit.any():
                counts += np.bincount(where[hit], minlength=len(heavy))
                bits = bits[~hit]
        if shift == 0:
            picked.append(bits.copy())
        else:
            sel = ((bits * _MIX) >> np.uint64(64 - shift)) == 0
            picked.append(bits[sel])
    sample = np.concatenate(picked) if picked else np.empty(0, np.uint64)
    return sample, counts


@dataclass(frozen=True)
class JoinProfile:
    """Merge statistics from skew-aware coordinated key sampling (scaled to the full frames)."""

    out_rows: Bounded
    overlap: Bounded  # share of left rows whose key exists on the right
    right_unique: Bounded  # share of right keys that occur once
    right_distinct: Bounded  # distinct right keys
    left_distinct: Bounded  # distinct left keys (the merge's factorizer sees both sides)
    left_all_matched_once: bool  # every sampled left row matched exactly one right row
    right_keys_unique: bool  # no sampled right key repeats (the sample cannot see rare repeats)
    heavy_keys: int
    keys_sampled: int
    fraction: float  # sampling fraction of the light key space


def _contribution(a: np.ndarray, b: np.ndarray, how: str) -> np.ndarray:
    if how == "inner":
        return a * b
    if how == "left":
        return a * np.maximum(b, 1.0)
    if how == "right":
        return np.maximum(a, 1.0) * b
    if how == "outer":
        return np.where(a > 0, a * np.maximum(b, 1.0), b)
    raise UnsupportedError(f"how={how!r}")


def join_profile(  # noqa: C901
    left_keys: Any,
    right_keys: Any,
    how: str,
    *,
    rows: int = DEFAULT_SAMPLE_ROWS,
    deadline: Deadline | None = None,
) -> JoinProfile:
    """Output rows, overlap, fan-out and uniqueness of ``left.merge(right, on=key, how=how)``.

    Heavy keys (frequent in a 100k-row sample) are counted exactly; the other keys are estimated
    by coordinated hash sampling (Horvitz-Thompson), so both the uniform and the zipf fan-out case
    get a valid interval.
    """
    al, ar = _as_array(left_keys), _as_array(right_keys)
    nl, nr = len(al), len(ar)
    if min(nl, nr) == 0:
        raise UnsupportedError("empty side")
    shift = max(0, math.ceil(math.log2(max(nl, nr) / rows))) if max(nl, nr) > rows else 0
    p = 2.0**-shift
    m = min(100_000, nl, nr)
    lrow = _key_bits(al[sample_positions(nl, m)])
    rrow = _key_bits(ar[sample_positions(nr, m)])
    seen = pd.concat([pd.Series(lrow).value_counts(), pd.Series(rrow).value_counts()], axis=1)
    top = seen.fillna(0).max(axis=1)
    top = top[top >= HEAVY_MIN_COUNT].sort_values(ascending=False).head(MAX_HEAVY)
    heavy = np.sort(top.index.to_numpy(dtype=np.uint64))
    lk, ha = scan_keys(al, shift, heavy, deadline)
    rk, hb = scan_keys(ar, shift, heavy, deadline)
    if len(lk) + len(rk) < MIN_SAMPLE_ROWS and shift > 0:
        raise UnsupportedError("key sample too small")
    cl = pd.Series(lk).value_counts(sort=False)
    cr = pd.Series(rk).value_counts(sort=False)
    joined = pd.concat([cl.rename("l"), cr.rename("r")], axis=1).fillna(0)
    a, b = joined["l"].to_numpy(dtype=float), joined["r"].to_numpy(dtype=float)
    x = _contribution(a, b, how)
    xh = _contribution(ha.astype(float), hb.astype(float), how)
    m_hat = float(x.sum() / p + xh.sum())
    se = math.sqrt(float((x * x).sum()) * (1 - p)) / p
    floor = {"left": nl, "right": nr, "outer": max(nl, nr)}.get(how, 0)
    low = max(float(floor), m_hat - Z95 * se)
    high = m_hat + Z95 * se
    if len(x):  # light keys that were not sampled could carry the heaviest light weight (rule of 3)
        high = max(high, m_hat + 3.0 * float(x.max()) / p)
    out_rows = Bounded(
        max(m_hat, float(floor)), low, max(high, float(floor)), len(lk) + len(rk), nl + nr,
        _confidence(low, high), "coordinated+heavy", p == 1.0,
    )  # fmt: skip
    matched_rows = float(a[b > 0].sum() / p + ha[hb > 0].sum())
    overlap_r = int(a.sum())
    if overlap_r:
        w = proportion(int(a[b > 0].sum()), overlap_r)
        overlap = Bounded(
            matched_rows / nl, w.low, w.high, overlap_r, nl, w.confidence, "coordinated+heavy"
        )
    else:
        overlap = proportion(0, 0, nl)
    keys_r_light = int((b > 0).sum())
    d_r = keys_r_light / p + float((hb > 0).sum())
    se_d = math.sqrt(keys_r_light * (1 - p)) / p
    right_distinct = Bounded(
        d_r, max(float(keys_r_light + (hb > 0).sum()), d_r - Z95 * se_d), min(float(nr), d_r + Z95 * se_d),
        keys_r_light, nr, _confidence(d_r - Z95 * se_d, d_r + Z95 * se_d), "coordinated+heavy", p == 1.0,
    )  # fmt: skip
    keys_l_light = int((a > 0).sum())
    d_l = keys_l_light / p + float((ha > 0).sum())
    se_l = math.sqrt(keys_l_light * (1 - p)) / p
    left_distinct = Bounded(
        d_l, max(float(keys_l_light + (ha > 0).sum()), d_l - Z95 * se_l), min(float(nl), d_l + Z95 * se_l),
        keys_l_light, nl, _confidence(d_l - Z95 * se_l, d_l + Z95 * se_l), "coordinated+heavy", p == 1.0,
    )  # fmt: skip
    right_unique = (
        proportion(int((b == 1).sum()), keys_r_light, None) if keys_r_light else proportion(0, 0)
    )
    heavy_ok = bool(((ha == 0) | (hb == 1)).all()) if len(heavy) else True
    once = bool(len(a) and (b[a > 0] == 1).all() and (a[a > 0] > 0).all() and heavy_ok)
    unique = bool((b <= 1).all() and (hb <= 1).all())
    return JoinProfile(
        out_rows, overlap, right_unique, right_distinct, left_distinct, once, unique,
        len(heavy), len(joined), p,
    )  # fmt: skip


# -- read_csv -----------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CsvProfile:
    """Shape of a CSV file estimated from its head and a few seeked chunks."""

    rows: Bounded
    cols: int
    text_cols: int
    str_chars: float
    unique_fraction: Bounded  # share of text cells that become a NEW str object (per parser chunk)
    bytes_per_field: float
    bytes_read: int
    exact: bool
    total_cols: int = 0  # columns in the file (``cols`` = the columns kept, e.g. by ``usecols``)
    value_bytes_per_row: float = 0.0  # parsed value bytes of one row of the kept columns
    dtypes: dict[str, str] = field(default_factory=dict)  # kept column -> parsed dtype (Phase 7b)


def _parse_chunk(
    raw: bytes, names: list[Any] | None, kw: dict[str, Any] | None = None, *, first: bool = False
) -> pd.DataFrame:
    """Parse sampled bytes with the call's own tokenizing / conversion arguments (Phase 6c)."""
    kw = kw or {}
    header = kw.get("header", 0) if first else None
    extra = {k: kw[k] for k in ("sep", "dtype", "usecols", "na_values") if k in kw}
    return pd.read_csv(io.BytesIO(raw), header=header, names=None if first else names, **extra)


def _value_bytes(frame: pd.DataFrame) -> float:
    total = 0.0
    for c in frame.columns:
        dt = frame[c].dtype
        text = str(dt) in ("object", "str", "string")
        total += 8.0 if text else float(getattr(dt, "itemsize", 8))
    return total


def csv_profile(  # noqa: C901
    path: str,
    file_bytes: int,
    *,
    head_bytes: int = 1 << 20,
    chunks: int = 3,
    chunk_bytes: int = 256 << 10,
    deadline: Deadline | None = None,
    read_kwargs: dict[str, Any] | None = None,
) -> CsvProfile:
    """Rows, columns, text columns, string length and per-chunk string uniqueness of a CSV.

    Reads at most ``head_bytes + chunks * chunk_bytes`` (1.75 MiB by default). A file that fits in
    the head is read completely and the profile is exact in rows. The parser's chunk length is
    ``2**floor(log2(2**20 / columns))`` rows (pandas ``buffer_lines``): string objects are shared
    only within such a chunk, so uniqueness is estimated at that scale. ``read_kwargs`` (Phase 6c):
    the call's own ``sep``, ``header`` (0 or None), ``dtype`` and ``usecols``, applied to the sampled
    bytes so the profile describes the columns the call keeps, with the dtypes it converts to.
    """
    kw = dict(read_kwargs or {})
    has_header = kw.get("header", 0) == 0
    path = os.path.expanduser(path)
    with open(path, "rb") as fh:
        head = fh.read(head_bytes)
        whole = len(head) >= file_bytes
        if not whole:
            cut = head.rfind(b"\n")
            if cut <= 0:
                raise UnsupportedError("no newline in the head")
            head = head[: cut + 1]
        if deadline is not None:
            deadline.check()
        first = _parse_chunk(head, None, kw, first=True)
        first_line = head[: head.index(b"\n") + 1]
        all_cols = pd.read_csv(io.BytesIO(first_line), header=None, sep=kw.get("sep", ","))
        total_cols = int(all_cols.shape[1])
        if "usecols" in kw or not has_header:  # the seeked chunks need the FILE's column names
            names: list[Any] | None = (
                [str(c) for c in all_cols.iloc[0].tolist()] if has_header else None
            )
        else:
            names = [str(c) for c in first.columns]
        header_bytes = len(first_line) if has_header else 0
        parts, sampled_lines, sampled_bytes = (
            [first],
            head.count(b"\n") - (1 if has_header else 0),
            len(head) - header_bytes,
        )
        line_means = [sampled_bytes / max(sampled_lines, 1)]
        read = len(head)
        if not whole:
            for i in range(chunks):
                if deadline is not None:
                    deadline.check()
                span = max(file_bytes - head_bytes - chunk_bytes, 1)
                fh.seek(head_bytes + int(span * (i + 0.5) / chunks))
                raw = fh.read(chunk_bytes)
                start, end = raw.find(b"\n"), raw.rfind(b"\n")
                if start < 0 or end <= start:
                    continue
                raw = raw[start + 1 : end + 1]
                lines = raw.count(b"\n")
                if lines == 0:
                    continue
                parts.append(_parse_chunk(raw, names, kw))
                line_means.append(len(raw) / lines)
                sampled_lines += lines
                sampled_bytes += len(raw)
                read += len(raw)
    if sampled_lines < 20 and not whole:
        raise UnsupportedError("too few lines sampled")
    cols = int(first.shape[1])  # the columns the call keeps (all of them by default)
    if whole:
        rows = exact(float(sampled_lines), sampled_lines, "whole file")
    else:
        mean_line = sampled_bytes / sampled_lines
        lo_line = min(line_means) - 1.0
        hi_line = max(line_means) + 1.0
        body = file_bytes - header_bytes
        est = body / mean_line
        rows = Bounded(
            est, body / hi_line, body / max(lo_line, 1.0), sampled_lines, int(est),
            _confidence(body / hi_line, body / max(lo_line, 1.0)), "line lengths", False,
        )  # fmt: skip
    sample = pd.concat(parts, ignore_index=True)
    text_cols = [
        c for c in sample.columns if sample[c].dtype == object or str(sample[c].dtype) == "str"
    ]
    chars = []
    uniques = []
    chunk_rows = 2 ** int(math.floor(math.log2(max(2**20 // max(total_cols, 1), 2))))
    for c in text_cols:
        s = sample[c].dropna()
        if s.empty:
            continue
        chars.append(float(s.astype(str).str.len().mean()))
        codes, _ = pd.factorize(s)
        counts = np.bincount(codes)
        est = distinct_from_counts(counts, max(chunk_rows, len(s)))
        total = max(chunk_rows, len(s))
        uniques.append((est.low / total, est.value / total, est.high / total))
    if uniques:
        arr = np.array(uniques)
        unique_fraction = Bounded(
            float(arr[:, 1].mean()), float(arr[:, 0].mean()), float(arr[:, 2].mean()),
            len(sample), chunk_rows, _confidence(arr[:, 0].mean(), arr[:, 2].mean()), "per-chunk chao1",
        )  # fmt: skip
    else:
        unique_fraction = exact(0.0, chunk_rows, "no text")
    return CsvProfile(
        rows, cols, len(text_cols), float(np.mean(chars)) if chars else 0.0, unique_fraction,
        (sampled_bytes / max(sampled_lines, 1)) / max(total_cols, 1), read, whole,
        total_cols, _value_bytes(first), {str(c): str(first[c].dtype) for c in first.columns},
    )  # fmt: skip
