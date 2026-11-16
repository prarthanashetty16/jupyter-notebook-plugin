"""Declarative benchmark grid: (operation case) x (dataset configuration) x (size).

A *case* fixes the cell source and how its inputs scale with size. A *grid point* is one case at
one size. The same source string is executed (to measure) and analysed by NEXUS (to predict).
Point ids are stable so interrupted runs can resume.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks import store
from benchmarks.datasets import DatasetConfig, estimate_frame_bytes, make_frame, make_join_pair
from benchmarks.split import load_split

BASE = DatasetConfig(n_rows=1, n_int=2, n_float=2, n_object=2, n_category=1, n_datetime=1)
NP_SORT_SIZES = (5_000_000, 10_000_000, 30_000_000, 100_000_000)
MATMUL_FULL_DIMS = (2000, 3000, 4000, 6000, 8000)
NUMERIC = {"n_int": 3, "n_float": 3, "n_object": 0, "n_category": 0, "n_datetime": 0}
STRINGS = {"n_int": 0, "n_float": 0, "n_object": 4, "n_category": 0, "n_datetime": 0, "str_len": 24}


# -- inputs --------------------------------------------------------------------------------
class _Stored:
    """Mixin: inputs are generated once into ``<cache>/ds_<hash>/<var>/`` and loaded by workers."""

    def key(self) -> str:
        return hashlib.sha1(repr(self).encode()).hexdigest()[:16]

    def directory(self, cache_dir: str) -> Path:
        return Path(cache_dir) / f"ds_{self.key()}"

    def generate(self) -> dict[str, Any]:
        raise NotImplementedError

    def ensure(self, cache_dir: str) -> None:
        """Generate and save the inputs unless already cached (runs in a spawned prep process)."""
        d = self.directory(cache_dir)
        if (d / "DONE").exists():
            return
        for var, obj in self.generate().items():
            store.save(obj, d / var)
        (d / "DONE").write_text("ok")

    def load(self, cache_dir: str) -> dict[str, Any]:
        d = self.directory(cache_dir)
        return {sub.name: store.load(sub) for sub in sorted(d.iterdir()) if sub.is_dir()}


@dataclass(frozen=True)
class FrameInput(_Stored):
    """One DataFrame bound to ``var``."""

    cfg: DatasetConfig
    var: str = "df"

    def generate(self) -> dict[str, Any]:
        return {self.var: make_frame(self.cfg)}

    def est_bytes(self) -> int:
        return estimate_frame_bytes(self.cfg)


@dataclass(frozen=True)
class JoinInput(_Stored):
    """Two frames bound to ``df`` and ``right``."""

    left: DatasetConfig
    right_rows: int
    overlap: float = 1.0
    fanout: float = 1.0

    def generate(self) -> dict[str, Any]:
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
class ArrayInput(_Stored):
    """A 1-D/2-D array bound to ``var``: pattern 'random', 'sorted' or 'reverse'."""

    shape: tuple[int, ...]
    var: str = "a"
    pattern: str = "random"
    seed: int = 0
    dtype: str = "float64"

    def generate(self) -> dict[str, Any]:
        rng = np.random.default_rng(self.seed)
        size = int(np.prod(self.shape))
        if self.pattern == "sorted":
            arr = np.arange(size, dtype=np.float64)
        elif self.pattern == "reverse":
            arr = np.arange(size, 0, -1, dtype=np.float64)
        else:
            arr = rng.random(size)
        return {self.var: arr.astype(self.dtype).reshape(self.shape)}

    def est_bytes(self) -> int:
        return int(np.prod(self.shape)) * np.dtype(self.dtype).itemsize


@dataclass(frozen=True)
class CsvInput:
    """A CSV file on disk (written once, cached); binds its path to ``path``."""

    cfg: DatasetConfig

    def file_path(self, cache_dir: str) -> str:
        digest = hashlib.sha1(repr(self.cfg).encode()).hexdigest()[:16]
        return str(Path(cache_dir) / f"data_{digest}.csv")

    def ensure(self, cache_dir: str) -> None:
        path = self.file_path(cache_dir)
        if not Path(path).exists():
            tmp = path + ".part"
            make_frame(self.cfg).to_csv(tmp, index=False)
            os.replace(tmp, path)

    def load(self, cache_dir: str) -> dict[str, Any]:
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
    split: str = "dev"

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
    full_sizes: tuple[int, ...] | None = None  # overrides the suite sizes for the full suite


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


def _concat3(n: int, **kw: Any) -> tuple[InputSpec, ...]:
    third = max(1, n // 3)
    return tuple(
        FrameInput(BASE.with_(n_rows=third, seed=i, **kw), v)
        for i, v in enumerate(("df", "df2", "df3"))
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
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "np_sort/random",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,)),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    add(
        Case(
            "np_sort/sorted",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="sorted"),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    # ---- configurations added at the dev/test split (never measured before the freeze) ----
    real = {"distribution": "real_like", "null_rate": 0.05, "str_len": 20}
    add(
        Case(
            "drop_duplicates/realistic_nulls_dup30",
            "drop_duplicates",
            "df.drop_duplicates()",
            lambda n: _frame(n, dup_rate=0.3, cardinality=0.2, **real),
            3.0,
            meta=real,
        )
    )
    add(
        Case(
            "drop_duplicates/subset_i0_s0_lowcard",
            "drop_duplicates",
            'df.drop_duplicates(subset=["i0", "s0"])',
            lambda n: _frame(n, cardinality=0.002),
            3.0,
        )
    )
    add(
        Case(
            "merge/outer_overlap50_realistic",
            "merge",
            'df.merge(right, on="k", how="outer")',
            lambda n: _join(n, overlap=0.5, fanout=2.0, **real),
            5.0,
        )
    )
    add(
        Case(
            "merge/right_fanout4_strings",
            "merge",
            'df.merge(right, on="k", how="right")',
            lambda n: _join(n, fanout=4.0, **STRINGS),
            5.0,
        )
    )
    add(
        Case(
            "groupby/two_keys_mean_realistic",
            "groupby",
            'df.groupby(["s0", "i0"])["f0"].mean()',
            lambda n: _frame(n, cardinality=0.01, **real),
            3.0,
        )
    )
    add(
        Case(
            "groupby/cat_key_zipf_sum",
            "groupby",
            'df.groupby("c0")["f0"].sum()',
            lambda n: _frame(n, cardinality=100, distribution="real_like"),
            3.0,
        )
    )
    add(
        Case(
            "sort_values/by_datetime",
            "sort_values",
            'df.sort_values("d0")',
            lambda n: _frame(n),
            3.0,
        )
    )
    add(
        Case(
            "sort_values/by_str_desc_nulls",
            "sort_values",
            'df.sort_values("s0", ascending=False)',
            lambda n: _frame(n, null_rate=0.1, str_len=24),
            3.0,
        )
    )
    add(
        Case(
            "read_csv/realistic_nulls",
            "pandas.read_csv",
            "pd.read_csv({csv!r})",
            lambda n: (
                CsvInput(BASE.with_(n_rows=n, null_rate=0.1, distribution="real_like", str_len=16)),
            ),
            4.0,
            max_size=3_000_000,
        )
    )
    add(
        Case(
            "read_csv/wide_numeric",
            "pandas.read_csv",
            "pd.read_csv({csv!r})",
            lambda n: (
                CsvInput(
                    BASE.with_(
                        n_rows=n, n_int=4, n_float=12, n_object=0, n_category=0, n_datetime=0
                    )
                ),
            ),
            4.0,
            max_size=3_000_000,
        )
    )
    add(
        Case(
            "astype/str_to_category_zipf",
            "astype",
            'df["s0"].astype("category")',
            lambda n: _frame(n, cardinality=0.01, distribution="real_like"),
            3.0,
        )
    )
    add(Case("astype/int_to_int32", "astype", 'df["i0"].astype("int32")', lambda n: _frame(n), 3.0))
    add(Case("astype/datetime_to_str", "astype", 'df["d0"].astype(str)', lambda n: _frame(n), 3.0))
    add(
        Case(
            "concat/realistic_nulls",
            "pandas.concat",
            "pd.concat([df, df2])",
            lambda n: _concat(n, **real),
            3.0,
        )
    )
    add(
        Case(
            "concat/three_frames",
            "pandas.concat",
            "pd.concat([df, df2, df3])",
            lambda n: _concat3(n),
            3.0,
        )
    )
    add(
        Case(
            "matmul/rect_f64",
            "operator.matmul",
            "a @ b",
            lambda d: (ArrayInput((d, d // 2), "a", seed=0), ArrayInput((d // 2, d), "b", seed=1)),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "np_sort/reverse",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="reverse"),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    add(
        Case(
            "np_sort/float32_random",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), dtype="float32"),),
            3.0,
            full_sizes=NP_SORT_SIZES,
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
    large_repeats: int = 3


SUITES: dict[str, SuiteSpec] = {
    "small": SuiteSpec("small", (300_000, 1_000_000, 3_000_000), (1000, 2000, 3000), repeats=3),
    "full": SuiteSpec(
        "full",
        (1_000_000, 3_000_000, 10_000_000, 30_000_000),
        (2000, 3000, 4000, 6000),
        repeats=3,
        large_repeats=3,
    ),
}


def build_grid(
    suite: str = "small",
    *,
    ops: set[str] | None = None,
    splits: tuple[str, ...] = ("dev", "test"),
    max_size: int | None = None,
) -> list[GridPoint]:
    """All grid points of ``suite``, dev split first, then test.

    ``ops`` keeps cases whose op or case-group name is in it; ``max_size`` drops larger points.
    """
    spec = SUITES[suite]
    sp = load_split()
    points: list[GridPoint] = []
    for case in CASES:
        if ops and case.op not in ops and case.name.split("/")[0] not in ops:
            continue
        which = sp.of(case.name)
        if which not in splits:
            continue
        sizes = spec.dim_sizes if case.size_kind == "dim" else spec.row_sizes
        if suite == "full" and case.full_sizes:
            sizes = case.full_sizes
        for size in sizes:
            if case.max_size is not None and size > case.max_size:
                continue
            if max_size is not None and size > max_size:
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
                    split=which,
                )
            )
    return sorted(points, key=lambda pt: pt.split != "dev")  # stable: dev first, then test
