"""Declarative benchmark grid: (operation case) x (dataset configuration) x (size).

A *case* fixes the cell source and how its inputs scale with size. A *grid point* is one case at
one size. The same source string is executed (to measure) and analysed by NEXUS (to predict).
Point ids are stable so interrupted runs can resume.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.datasets import DatasetConfig, estimate_frame_bytes, make_frame, make_join_pair

BASE = DatasetConfig(n_rows=1, n_int=2, n_float=2, n_object=2, n_category=1, n_datetime=1)
NUMERIC = {"n_int": 3, "n_float": 3, "n_object": 0, "n_category": 0, "n_datetime": 0}
STRINGS = {"n_int": 0, "n_float": 0, "n_object": 4, "n_category": 0, "n_datetime": 0, "str_len": 24}


# -- inputs --------------------------------------------------------------------------------
@dataclass(frozen=True)
class FrameInput:
    """One DataFrame bound to ``var``."""

    cfg: DatasetConfig
    var: str = "df"

    def build(self, cache_dir: str) -> dict[str, Any]:
        return {self.var: make_frame(self.cfg)}

    def est_bytes(self) -> int:
        return estimate_frame_bytes(self.cfg)


@dataclass(frozen=True)
class JoinInput:
    """Two frames bound to ``df`` and ``right``."""

    left: DatasetConfig
    right_rows: int
    overlap: float = 1.0
    fanout: float = 1.0

    def build(self, cache_dir: str) -> dict[str, Any]:
        left, right = make_join_pair(
            self.left, self.right_rows, overlap=self.overlap, fanout=self.fanout
        )
        return {"df": left, "right": right}

    def est_bytes(self) -> int:
        right = DatasetConfig(
            n_rows=self.right_rows, n_int=1, n_float=2, n_object=1, n_category=0, n_datetime=0
        )
        return estimate_frame_bytes(self.left) + estimate_frame_bytes(right)


@dataclass(frozen=True)
class ArrayInput:
    """A float64 array bound to ``var``: random ('random') or already sorted ('sorted')."""

    shape: tuple[int, ...]
    var: str = "a"
    pattern: str = "random"
    seed: int = 0

    def build(self, cache_dir: str) -> dict[str, Any]:
        rng = np.random.default_rng(self.seed)
        size = int(np.prod(self.shape))
        arr = np.arange(size, dtype=np.float64) if self.pattern == "sorted" else rng.random(size)
        return {self.var: arr.reshape(self.shape)}

    def est_bytes(self) -> int:
        return int(np.prod(self.shape)) * 8


@dataclass(frozen=True)
class CsvInput:
    """A CSV file on disk (written once, cached); binds its path to ``path``."""

    cfg: DatasetConfig

    def file_path(self, cache_dir: str) -> str:
        digest = hashlib.sha1(repr(self.cfg).encode()).hexdigest()[:16]
        return str(Path(cache_dir) / f"data_{digest}.csv")

    def build(self, cache_dir: str) -> dict[str, Any]:
        return {"path": self.file_path(cache_dir)}

    def est_bytes(self) -> int:
        return estimate_frame_bytes(self.cfg)


InputSpec = FrameInput | JoinInput | ArrayInput | CsvInput


# -- grid ----------------------------------------------------------------------------------
@dataclass(frozen=True)
class GridPoint:
    id: str
    case: str
    op: str  # operation name the analyzer is expected to report (matched against predictions)
    source: str  # may contain ``{csv}``, replaced with the csv path by the runner
    size: int
    inputs: tuple[InputSpec, ...]
    repeats: int
    footprint_factor: float  # worst-case child RSS as a multiple of estimated input bytes
    meta: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def est_input_bytes(self) -> int:
        return sum(spec.est_bytes() for spec in self.inputs)

    def est_footprint_bytes(self) -> int:
        return int(self.est_input_bytes() * self.footprint_factor)

    def describe(self) -> str:
        return json.dumps({"case": self.case, "size": self.size, "meta": self.meta}, default=str)


@dataclass(frozen=True)
class Case:
    name: str
    op: str
    source: str
    make_inputs: Callable[[int], tuple[InputSpec, ...]]
    footprint_factor: float = 3.0
    size_kind: str = "rows"  # "rows" or "dim" (square matrix side)
    max_size: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _frame(n: int, **kw: Any) -> tuple[InputSpec, ...]:
    return (FrameInput(BASE.with_(n_rows=n, **kw)),)


def _join(n: int, overlap: float = 1.0, fanout: float = 1.0, **kw: Any) -> tuple[InputSpec, ...]:
    return (
        JoinInput(
            BASE.with_(n_rows=n, **kw), right_rows=max(1, n // 2), overlap=overlap, fanout=fanout
        ),
    )


def _concat(n: int, **kw: Any) -> tuple[InputSpec, ...]:
    half = max(1, n // 2)
    return (
        FrameInput(BASE.with_(n_rows=half, seed=0, **kw), "df"),
        FrameInput(BASE.with_(n_rows=half, seed=1, **kw), "df2"),
    )


def _cases() -> list[Case]:
    c: list[Case] = []
    add = c.append
    # drop_duplicates: dtype mix and duplicate fraction are the claimed drivers
    for name, kw in (
        ("mixed_dup0", {"dup_rate": 0.0}),
        ("mixed_dup50", {"dup_rate": 0.5}),
        ("numeric_dup50", {**NUMERIC, "dup_rate": 0.5}),
        ("strings_dup50", {**STRINGS, "dup_rate": 0.5}),
    ):
        add(
            Case(
                f"drop_duplicates/{name}",
                "drop_duplicates",
                "df.drop_duplicates()",
                lambda n, kw=kw: _frame(n, **kw),
                3.0,
                meta=kw,
            )
        )
    add(
        Case(
            "drop_duplicates/subset_s0_lowcard",
            "drop_duplicates",
            'df.drop_duplicates(subset=["s0"])',
            lambda n: _frame(n, cardinality=0.01),
            3.0,
        )
    )
    # merge: overlap, fan-out and many-to-many drive output size
    merge = 'df.merge(right, on="k", how="{how}")'
    for name, how, kw in (
        ("inner_1to1", "inner", {}),
        ("inner_overlap10", "inner", {"overlap": 0.1}),
        ("inner_fanout3", "inner", {"fanout": 3.0}),
        ("inner_manymany", "inner", {"fanout": 3.0, "dup_rate": 0.5}),
        ("left_1to1", "left", {}),
    ):
        add(
            Case(
                f"merge/{name}",
                "merge",
                merge.format(how=how),
                lambda n, kw=kw: _join(n, **kw),
                5.0,
                meta=kw,
            )
        )
    # groupby
    add(
        Case(
            "groupby/str_lowcard_sum_f0",
            "groupby",
            'df.groupby("s0")["f0"].sum()',
            lambda n: _frame(n, cardinality=0.001),
            3.0,
        )
    )
    add(
        Case(
            "groupby/str_highcard_sum_f0",
            "groupby",
            'df.groupby("s0")["f0"].sum()',
            lambda n: _frame(n, cardinality=0.5),
            3.0,
        )
    )
    add(
        Case(
            "groupby/int_sum_numeric",
            "groupby",
            'df.groupby("i0").sum(numeric_only=True)',
            lambda n: _frame(n, cardinality=0.001),
            3.0,
        )
    )
    # sort_values
    add(Case("sort_values/by_int", "sort_values", 'df.sort_values("i0")', lambda n: _frame(n), 3.0))
    add(Case("sort_values/by_str", "sort_values", 'df.sort_values("s0")', lambda n: _frame(n), 3.0))
    add(
        Case(
            "sort_values/by_int_float",
            "sort_values",
            'df.sort_values(["i0", "f0"])',
            lambda n: _frame(n),
            3.0,
        )
    )
    # read_csv
    for name, kw in (("mixed", {}), ("numeric", NUMERIC), ("strings", STRINGS)):
        add(
            Case(
                f"read_csv/{name}",
                "pandas.read_csv",
                "pd.read_csv({csv!r})",
                lambda n, kw=kw: (CsvInput(BASE.with_(n_rows=n, **kw)),),
                4.0,
                max_size=3_000_000,
                meta=kw,
            )
        )
    # astype (single column)
    for name, src, kw in (
        ("str_to_category_lowcard", 'df["s0"].astype("category")', {"cardinality": 0.001}),
        ("str_to_category_highcard", 'df["s0"].astype("category")', {"cardinality": 0.5}),
        ("int_to_float64", 'df["i0"].astype("float64")', {}),
        ("float_to_float32", 'df["f0"].astype("float32")', {}),
        ("int_to_str", 'df["i0"].astype(str)', {}),
    ):
        add(Case(f"astype/{name}", "astype", src, lambda n, kw=kw: _frame(n, **kw), 3.0))
    # concat
    add(Case("concat/mixed", "pandas.concat", "pd.concat([df, df2])", lambda n: _concat(n), 3.0))
    add(
        Case(
            "concat/numeric",
            "pandas.concat",
            "pd.concat([df, df2])",
            lambda n: _concat(n, **NUMERIC),
            3.0,
        )
    )
    # numpy
    add(
        Case(
            "matmul/square_f64",
            "operator.matmul",
            "a @ b",
            lambda d: (ArrayInput((d, d), "a", seed=0), ArrayInput((d, d), "b", seed=1)),
            4.0,
            size_kind="dim",
        )
    )
    add(Case("np_sort/random", "numpy.sort", "np.sort(a)", lambda n: (ArrayInput((n,)),), 3.0))
    add(
        Case(
            "np_sort/sorted",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="sorted"),),
            3.0,
        )
    )
    return c


CASES: tuple[Case, ...] = tuple(_cases())


@dataclass(frozen=True)
class SuiteSpec:
    name: str
    row_sizes: tuple[int, ...]
    dim_sizes: tuple[int, ...]
    repeats: int
    large_rows: int = 3_000_000  # at or above this size use ``large_repeats``
    large_repeats: int = 2


SUITES: dict[str, SuiteSpec] = {
    "small": SuiteSpec("small", (10_000, 100_000, 500_000), (200, 500, 1000), repeats=3),
    "full": SuiteSpec(
        "full",
        (10_000, 100_000, 1_000_000, 3_000_000, 10_000_000),
        (200, 500, 1000, 2000, 3000),
        repeats=3,
    ),
}


def build_grid(suite: str = "small", *, ops: set[str] | None = None) -> list[GridPoint]:
    """All grid points of ``suite`` (optionally only cases whose op or case name is in ``ops``)."""
    spec = SUITES[suite]
    points: list[GridPoint] = []
    for case in CASES:
        if ops and case.op not in ops and case.name.split("/")[0] not in ops:
            continue
        sizes = spec.dim_sizes if case.size_kind == "dim" else spec.row_sizes
        for size in sizes:
            if case.max_size is not None and size > case.max_size:
                continue
            repeats = spec.large_repeats if size >= spec.large_rows else spec.repeats
            points.append(
                GridPoint(
                    id=f"{case.name}|n={size}",
                    case=case.name,
                    op=case.op,
                    source=case.source,
                    size=size,
                    inputs=case.make_inputs(size),
                    repeats=repeats,
                    footprint_factor=case.footprint_factor,
                    meta=dict(case.meta),
                )
            )
    return points
