"""Samples for Tier 2: what is sampled how, and why.

All samples are NESTED (each smaller sample is a subset of the next), so the sizes differ only in
how much of the same data is included, and every one is a COPY: the user's objects are only read.

| operation              | sampling                                             | why |
|------------------------|------------------------------------------------------|-----|
| merge                  | coordinated KEY-HASH sample of both frames           | a sampled key keeps ALL its rows on both sides, so fan-out, overlap and skew survive; a row sample would thin both sides independently and destroy matches |
| groupby + aggregation  | key-hash sample                                      | whole groups are kept: the number of groups scales with the sampling fraction, group sizes do not change |
| drop_duplicates        | hash of the subset (or of the most distinct columns) | duplicates are equal rows, so they hash alike and are kept together; the duplicate rate is preserved |
| astype, sort_values,   | uniform ROW sample, original order kept              | cost is row-wise (or sort-order dependent: an ordered column stays ordered) |
| concat, np.sort        |                                                      |     |
| matmul ``a @ b``       | the first ``x`` of the rows of ``a`` and of the columns of ``b`` | work ~ x^2, output ~ x^2, operands ~ x; inner dimension kept so BLAS blocking matches |
| read_csv               | lines from 8 evenly spread byte offsets (+ header)   | local order is kept, the file's head is not the only region seen |

Sample sizes follow one principle (not tuned): the largest sample is 4% of the rows, but at least
``MIN_LARGEST`` and at most ``ROW_CAP`` rows (a bigger sample costs more than it teaches), then
1/2, 1/4, 1/8 of it. An input smaller than ``MIN_RATIO`` x the largest sample is not worth
extrapolating from: just run the cell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.dryrun_io import save_array, save_frame
from nexus.failsafe import Deadline
from nexus.stats import _key_bits

LARGEST_FRACTION = 0.04
MIN_LARGEST = 40_000
ROW_CAP = 250_000
LEVELS = (0.125, 0.25, 0.5, 1.0)
MIN_RATIO = 5.0
MATMUL_MIN_DIM = 400
TEXT_HASH_LIMIT = 6_000_000  # rows of text keys that may be hashed (about 0.2 us/row)
_MIX = np.uint64(0x9E3779B97F4A7C15)


class NoSampleError(Exception):
    """The cell cannot be sampled (reason in the message): no Tier 2 estimate."""


@dataclass
class Level:
    n_eff: float  # the size variable of the scaling fit
    objects: list[str]
    rows: dict[str, int]
    csv: bool = False


@dataclass
class SamplePlan:
    levels: list[Level]
    target: float  # the size the fit extrapolates to
    sampling: str
    notes: list[str] = field(default_factory=list)


def largest_sample(n_rows: float) -> int:
    """Rows of the largest sample for an input of ``n_rows``; raises NoSampleError if too small."""
    m = int(min(ROW_CAP, max(MIN_LARGEST, LARGEST_FRACTION * n_rows)))
    if n_rows < MIN_RATIO * m:
        raise NoSampleError(
            f"input of {int(n_rows):,} rows is under {MIN_RATIO:g}x the smallest useful sample: run the cell"
        )
    return m


# -- hashing -------------------------------------------------------------------------------------------
def _mix(h: np.ndarray) -> np.ndarray:
    h = h * _MIX
    return h ^ (h >> np.uint64(29))


def hash01(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    """Per-row hash of ``columns`` as floats in [0, 1): equal key values give equal hashes."""
    acc = np.zeros(len(df), dtype=np.uint64)
    for c in columns:
        col = df[c]
        if isinstance(col.dtype, pd.CategoricalDtype):
            col = col.astype(object)
        arr = col.to_numpy()
        if arr.dtype.kind not in "iubfMm" and len(arr) > TEXT_HASH_LIMIT:
            raise NoSampleError("text keys too large to hash within the budget")
        bits = _key_bits(arr)
        with np.errstate(over="ignore"):
            acc = _mix(acc ^ _mix(bits.astype(np.uint64, copy=False)))
    return (acc >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def choose_hash_columns(df: pd.DataFrame, columns: list[str], limit: int = 2) -> list[str]:
    """For whole-row duplicates any column works; take the most distinct ones (cheap, from 20k rows)."""
    probe = df[columns].iloc[:: max(1, len(df) // 20_000)]
    ranked = sorted(columns, key=lambda c: -probe[c].nunique())
    return ranked[:limit]


def _threshold(hashes: list[np.ndarray], target_rows: int, deadline: Deadline | None) -> float:
    """Hash threshold t so the LARGEST frame keeps about ``target_rows`` rows (skew-corrected once)."""
    big = max(hashes, key=len)
    t = min(1.0, target_rows / max(len(big), 1))
    for _ in range(2):
        if deadline is not None:
            deadline.check()
        kept = int((big < t).sum())
        if kept == 0:
            t = min(1.0, t * 4)
        elif not 0.5 * target_rows <= kept <= 2.0 * target_rows:
            t = min(1.0, t * target_rows / kept)
        else:
            break
    return t


def _write(plan_dir: Path, k: int, objs: dict[str, Any]) -> list[str]:
    root = plan_dir / f"level{k}"
    for name, obj in objs.items():
        (save_array if isinstance(obj, np.ndarray) else save_frame)(obj, root / name)
    return list(objs)


# -- per kind -----------------------------------------------------------------------------------------
def build_samples(  # noqa: C901
    recipe: Any, ns: Any, plan_dir: Path, deadline: Deadline | None = None, seed: int = 20260101
) -> SamplePlan:
    kind = recipe.kind
    if kind in ("merge", "groupby_agg", "drop_duplicates"):
        return _hash_samples(recipe, ns, plan_dir, deadline)
    if kind == "matmul":
        return _matmul_samples(recipe, ns, plan_dir)
    if kind == "read_csv":
        return _csv_samples(recipe, plan_dir, deadline)
    rng = np.random.default_rng(seed)
    if kind in ("astype", "sort_values"):
        df = ns[recipe.operands[0]]
        cols = [recipe.extra["column"]] if kind == "astype" else None
        n = len(df)
        m = largest_sample(n)
        pos, u = _row_levels(n, m, rng)
        levels = []
        for k, f in enumerate(LEVELS):
            sel = pos[u < f]
            sub = df.iloc[sel] if cols is None else df[cols].iloc[sel]
            name = recipe.operands[0]
            levels.append(
                Level(float(len(sel)), _write(plan_dir, k, {name: sub}), {name: len(sel)})
            )
        return SamplePlan(levels, float(n), "uniform row sample (order kept)")
    if kind == "concat":
        frames = [ns[name] for name in recipe.operands]
        total = sum(len(f) for f in frames)
        m = largest_sample(total)
        parts = [_row_levels(len(f), max(1, int(round(m * len(f) / total))), rng) for f in frames]
        levels = []
        for k, f in enumerate(LEVELS):
            objs = {
                name: fr.iloc[pos[u < f]]
                for name, fr, (pos, u) in zip(recipe.operands, frames, parts, strict=True)
            }
            levels.append(Level(float(sum(len(o) for o in objs.values())), _write(plan_dir, k, objs),
                                {n: len(o) for n, o in objs.items()}))  # fmt: skip
        return SamplePlan(levels, float(total), "uniform row sample of every frame (order kept)")
    if kind == "np_sort":
        arr = ns[recipe.operands[0]]
        if arr.ndim != 1:
            raise NoSampleError("np.sort of a 2-D array is not sampled")
        n = len(arr)
        m = largest_sample(n)
        pos, u = _row_levels(n, m, rng)
        levels = []
        for k, f in enumerate(LEVELS):
            sel = pos[u < f]
            levels.append(
                Level(
                    float(len(sel)),
                    _write(plan_dir, k, {recipe.operands[0]: arr[sel]}),
                    {recipe.operands[0]: len(sel)},
                )
            )
        return SamplePlan(levels, float(n), "uniform row sample (order kept)")
    raise NoSampleError(f"no sampling defined for {kind}")


def _row_levels(n: int, m: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Positions of the largest sample (sorted) and a uniform draw per position for the nesting."""
    pos = np.sort(rng.choice(n, size=min(m, n), replace=False))
    return pos, rng.random(len(pos))


def _hash_samples(recipe: Any, ns: Any, plan_dir: Path, deadline: Deadline | None) -> SamplePlan:
    kind = recipe.kind
    if kind == "merge":
        names = recipe.operands
        keys = (
            recipe.kwargs["on"] if isinstance(recipe.kwargs["on"], list) else [recipe.kwargs["on"]]
        )
        cols = dict.fromkeys(names, keys)
        why = "coordinated key-hash sample of both frames (a sampled key keeps all its rows on both sides)"
    elif kind == "groupby_agg":
        names = recipe.operands
        cols = {names[0]: recipe.extra["by"]}
        why = "key-hash sample (whole groups kept)"
    else:
        names = recipe.operands
        subset = recipe.kwargs.get("subset")
        base = ns[names[0]]
        subset = (
            (subset if isinstance(subset, list) else [subset])
            if subset is not None
            else list(base.columns)
        )
        cols = {names[0]: choose_hash_columns(base, subset) if len(subset) > 2 else subset}
        why = "hash sample of the duplicate key (equal rows are kept together)"
    frames = {n: ns[n] for n in dict.fromkeys(names)}
    primary = frames[names[0]]
    total_big = max(len(f) for f in frames.values())
    m = largest_sample(total_big)
    hashes = {n: hash01(frames[n], cols.get(n, cols[names[0]])) for n in frames}
    t_max = _threshold(list(hashes.values()), m, deadline)
    levels = []
    for k, f in enumerate(LEVELS):
        objs, rows = {}, {}
        for n, fr in frames.items():
            sel = np.flatnonzero(hashes[n] < t_max * f)
            objs[n], rows[n] = fr.iloc[sel], len(sel)
        levels.append(Level(t_max * f * len(primary), _write(plan_dir, k, objs), rows))
    return SamplePlan(levels, float(len(primary)), why, [f"hash threshold {t_max:.4g}"])


def _matmul_samples(recipe: Any, ns: Any, plan_dir: Path) -> SamplePlan:
    a, b = ns[recipe.operands[0]], ns[recipe.operands[1]]
    rows, cols = a.shape[0], b.shape[1]
    if min(rows, cols) < MATMUL_MIN_DIM:
        raise NoSampleError(f"matrices under {MATMUL_MIN_DIM} rows / columns: run the cell")
    x_max = 0.25
    levels = []
    for k, f in enumerate(LEVELS):
        x = x_max * f
        r, c = max(2, int(round(rows * x))), max(2, int(round(cols * x)))
        objs = {"L": np.ascontiguousarray(a[:r]), "R": np.ascontiguousarray(b[:, :c])}
        levels.append(
            Level(x * rows, _write(plan_dir, k, objs), {n: o.shape[0] for n, o in objs.items()})
        )
    return SamplePlan(
        levels,
        float(rows),
        "leading rows of a and leading columns of b, scale x in both (work ~ x^2)",
    )


def _csv_samples(recipe: Any, plan_dir: Path, deadline: Deadline | None) -> SamplePlan:
    from nexus import stats

    path = recipe.extra["path"]
    size = os.path.getsize(path)
    prof = stats.csv_profile(path, size, deadline=deadline)
    n_rows = prof.rows.value
    m = largest_sample(n_rows)
    blocks = 8
    per_block = max(1, m // blocks)
    with open(path, "rb") as fh:
        header = fh.readline()
        start = fh.tell()
        chunks: list[list[bytes]] = []
        for i in range(blocks):
            fh.seek(start + int((size - start) * i / blocks))
            if i:
                fh.readline()  # land on a line boundary
            chunks.append(
                [ln for _, ln in zip(range(per_block), iter(fh.readline, b""), strict=False)]
            )
    levels = []
    for k, f in enumerate(LEVELS):
        keep = max(1, int(per_block * f))
        lines = [ln for chunk in chunks for ln in chunk[:keep]]
        root = plan_dir / f"level{k}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "sample.csv").write_bytes(header + b"".join(lines))
        levels.append(Level(float(len(lines)), [], {"csv": len(lines)}, csv=True))
    notes = [
        f"rows from the file profile: {n_rows:,.0f} ({'exact' if prof.rows.exact else 'estimated'})"
    ]
    return SamplePlan(
        levels, float(n_rows), "lines from 8 evenly spread byte offsets (+ header)", notes
    )
