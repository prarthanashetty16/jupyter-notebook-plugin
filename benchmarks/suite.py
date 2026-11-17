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
from benchmarks.split import GROUPS, load_split

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
    right_key_dist: str = "uniform"  # "zipf": skewed fan-out over the right keys
    right_seed: int = 1

    def __repr__(self) -> str:
        """Omit the newer knobs at their defaults so existing cache keys stay valid."""
        extra = ""
        if self.right_key_dist != "uniform":
            extra += f", right_key_dist={self.right_key_dist!r}"
        if self.right_seed != 1:
            extra += f", right_seed={self.right_seed!r}"
        return (
            f"JoinInput(left={self.left!r}, right_rows={self.right_rows!r}, "
            f"overlap={self.overlap!r}, fanout={self.fanout!r}{extra})"
        )

    def generate(self) -> dict[str, Any]:
        left, right = make_join_pair(
            self.left,
            self.right_rows,
            overlap=self.overlap,
            fanout=self.fanout,
            seed=self.right_seed,
            right_key_dist=self.right_key_dist,
        )
        return {"df": left, "right": right}

    def est_bytes(self) -> int:
        right = DatasetConfig(
            n_rows=self.right_rows, n_int=1, n_float=2, n_object=1, n_category=0, n_datetime=0
        )
        return estimate_frame_bytes(self.left) + estimate_frame_bytes(right)


@dataclass(frozen=True)
class ArrayInput(_Stored):
    """A 1-D/2-D array bound to ``var``: random, sorted, reverse, nearly_sorted or few_unique."""

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
        elif self.pattern == "nearly_sorted":  # sorted, then ~1% of positions swapped at random
            arr = np.arange(size, dtype=np.float64)
            k = max(1, size // 100)
            i, j = rng.integers(0, size, k), rng.integers(0, size, k)
            arr[i], arr[j] = arr[j].copy(), arr[i].copy()
        elif self.pattern == "few_unique":  # 1000 distinct values, random order
            arr = rng.integers(0, 1000, size).astype(np.float64)
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


def _join(
    n: int,
    overlap: float = 1.0,
    fanout: float = 1.0,
    right_ratio: float = 0.5,
    right_key_dist: str = "uniform",
    right_seed: int = 1,
    **kw: Any,
) -> tuple[InputSpec, ...]:
    return (
        JoinInput(
            BASE.with_(n_rows=n, **kw),
            right_rows=max(1, int(n * right_ratio)),
            overlap=overlap,
            fanout=fanout,
            right_key_dist=right_key_dist,
            right_seed=right_seed,
        ),
    )


def _concat_parts(
    n: int, fractions: tuple[float, ...], seeds: tuple[int, ...], **kw: Any
) -> tuple[InputSpec, ...]:
    names = ["df"] + [f"df{i}" for i in range(2, len(fractions) + 1)]
    return tuple(
        FrameInput(BASE.with_(n_rows=max(1, int(n * f)), seed=s, **kw), v)
        for f, s, v in zip(fractions, seeds, names, strict=True)
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


def _add_val_v4(add: Callable[[Case], None]) -> None:
    """The val-v4 configurations (kept apart from ``_cases`` for readability)."""
    merge = 'df.merge(right, on="k", how="{how}")'
    # ---- val-v4: held-out validation after Phase 4b.2 (seeds >= 401; every non-default generator
    # value, join ratio and array dtype/pattern is new relative to dev (incl. the former val-v3) and
    # test-v2). Targets the families that failed on val-v3 (high-cardinality category conversion,
    # low-cardinality text and two-key groupby, moderate-overlap high-fan-out merges, null-heavy
    # drop_duplicates) and repeats the families that worked, so regressions show. ----
    for name, src, kw in (
        ("str_to_category_card6000", 'df["s0"].astype("category")', {"cardinality": 6000, "seed": 401}),
        ("str_to_category_card40000", 'df["s0"].astype("category")', {"cardinality": 40000, "seed": 402}),
        ("str_to_category_card150000", 'df["s0"].astype("category")',
         {"cardinality": 150000, "seed": 403}),
        ("str_to_category_card0p12", 'df["s0"].astype("category")', {"cardinality": 0.12, "seed": 404}),
        ("str_to_category_card400_long", 'df["s0"].astype("category")',
         {"cardinality": 400, "str_len": 22, "seed": 405}),
        ("int_to_category_card15000", 'df["i0"].astype("category")', {"cardinality": 15000, "seed": 406}),
        ("float_to_str_nulls", 'df["f0"].astype(str)',
         {"distribution": "real_like", "null_rate": 0.04, "seed": 407}),
        ("int_to_str_card1500", 'df["i0"].astype(str)', {"cardinality": 1500, "seed": 408}),
    ):  # fmt: skip
        add(Case(f"v4/astype/{name}", "astype", src, lambda n, kw=kw: _frame(n, **kw), 3.0))
    for name, src, kw in (
        ("str_card3_sum", 'df.groupby("s0")["f0"].sum()', {"cardinality": 3, "seed": 409}),
        ("str_card0p003_two_values", 'df.groupby("s0")[["f0", "f1"]].sum()',
         {"cardinality": 0.003, "seed": 410}),
        ("two_keys_card60", 'df.groupby(["i0", "s0"])["f0"].sum()', {"cardinality": 60, "seed": 411}),
        ("two_keys_card6000", 'df.groupby(["i0", "s0"])["f0"].sum()',
         {"cardinality": 6000, "seed": 412}),
        ("int_card40000_mean", 'df.groupby("i0")["f0"].mean()', {"cardinality": 40000, "seed": 413}),
        ("zipf_int_card0p006", 'df.groupby("i0")["f0"].sum()',
         {"cardinality": 0.006, "distribution": "real_like", "zipf_exponent": 1.5, "seed": 414}),
        ("str_card0p9_mean", 'df.groupby("s0")["f0"].mean()', {"cardinality": 0.9, "seed": 415}),
    ):  # fmt: skip
        add(Case(f"v4/groupby/{name}", "groupby", src, lambda n, kw=kw: _frame(n, **kw), 3.0))
    for name, how, kw in (
        ("inner_overlap35_fanout7", "inner",
         {"overlap": 0.35, "fanout": 7.0, "right_ratio": 0.4, "right_seed": 2416, "seed": 416}),
        ("inner_overlap20_fanout10", "inner",
         {"overlap": 0.2, "fanout": 10.0, "right_ratio": 0.15, "right_seed": 2417, "seed": 417}),
        ("inner_overlap55_fanout4p5", "inner",
         {"overlap": 0.55, "fanout": 4.5, "right_ratio": 0.9, "right_seed": 2418, "seed": 418}),
        ("left_overlap40_fanout9", "left",
         {"overlap": 0.4, "fanout": 9.0, "right_ratio": 0.45, "right_seed": 2419, "seed": 419}),
        ("outer_overlap70_zipf1p5", "outer",
         {"overlap": 0.7, "fanout": 3.5, "right_key_dist": "zipf", "right_seed": 2420,
          "right_ratio": 1.2, "zipf_exponent": 1.5, "seed": 420}),
        ("right_overlap15_text", "right",
         {"overlap": 0.15, "fanout": 1.8, "right_seed": 2421, "right_ratio": 3.0, "seed": 421,
          "n_object": 3, "str_len": 28}),
        ("inner_overlap95_fanout1p1", "inner",
         {"overlap": 0.95, "fanout": 1.1, "right_ratio": 0.65, "right_seed": 2422, "seed": 422}),
    ):  # fmt: skip
        add(
            Case(
                f"v4/merge/{name}",
                "merge",
                merge.format(how=how),
                lambda n, kw=kw: _join(n, **kw),
                5.0,
                meta={"how": how},
            )
        )
    for name, src, kw in (
        ("null_heavy_full", "df.drop_duplicates()",
         {"dup_rate": 0.1, "cardinality": 0.12, "null_rate": 0.45, "str_len": 15, "seed": 423}),
        ("null_subset_floats", 'df.drop_duplicates(subset=["f0", "f1"])',
         {"dup_rate": 0.35, "cardinality": 0.6, "null_rate": 0.28, "seed": 424}),
        ("null_subset_texts", 'df.drop_duplicates(subset=["s0", "s1"])',
         {"dup_rate": 0.25, "cardinality": 8000, "null_rate": 0.55, "str_len": 22, "seed": 425}),
        ("null_subset_cat_date", 'df.drop_duplicates(subset=["c0", "d0"])',
         {"dup_rate": 0.2, "cardinality": 1500, "null_rate": 0.18, "seed": 426}),
        ("numeric_wide_nulls12", "df.drop_duplicates()",
         {"n_int": 4, "n_float": 8, "n_object": 0, "n_category": 0, "n_datetime": 0,
          "dup_rate": 0.45, "null_rate": 0.12, "cardinality": 0.15, "seed": 427}),
        ("no_nulls_full", "df.drop_duplicates()",
         {"dup_rate": 0.55, "cardinality": 0.6, "str_len": 13, "seed": 428}),
        ("int_subset_lowdup", 'df.drop_duplicates(subset=["i0"])',
         {"dup_rate": 0.05, "cardinality": 6000, "seed": 429}),
    ):  # fmt: skip
        add(Case(f"v4/drop_duplicates/{name}", "drop_duplicates", src,
                 lambda n, kw=kw: _frame(n, **kw), 3.0))  # fmt: skip
    add(
        Case(
            "v4/sort_values/str_desc_nulls",
            "sort_values",
            'df.sort_values("s0", ascending=False)',
            lambda n: _frame(n, null_rate=0.04, str_len=13, seed=430),
            3.0,
        )
    )
    add(
        Case(
            "v4/sort_values/float_int_lowcard",
            "sort_values",
            'df.sort_values(["f0", "i0"])',
            lambda n: _frame(n, cardinality=0.003, seed=431),
            3.0,
        )
    )
    add(
        Case(
            "v4/concat/three_uneven",
            "pandas.concat",
            "pd.concat([df, df2, df3])",
            lambda n: _concat_parts(
                n, (0.5, 0.3, 0.2), (432, 433, 434), null_rate=0.01, str_len=13
            ),
            3.0,
        )
    )
    add(
        Case(
            "v4/concat/two_category_heavy",
            "pandas.concat",
            "pd.concat([df, df2], ignore_index=True)",
            lambda n: _concat_parts(n, (0.5, 0.5), (435, 436), n_category=3, n_object=0),
            3.0,
        )
    )
    for name, kw in (
        ("wide_floats", {"n_int": 1, "n_float": 14, "n_object": 0, "n_category": 0,
                         "n_datetime": 0, "seed": 437}),
        ("text_nulls", {"n_int": 1, "n_float": 1, "n_object": 3, "n_category": 0,
                        "n_datetime": 0, "str_len": 13, "null_rate": 0.12, "cardinality": 0.15,
                        "seed": 438}),
        ("dates_ints", {"n_int": 4, "n_float": 0, "n_object": 0, "n_category": 0,
                        "n_datetime": 3, "seed": 439}),
    ):  # fmt: skip
        add(
            Case(
                f"v4/read_csv/{name}",
                "pandas.read_csv",
                "pd.read_csv({csv!r})",
                lambda n, kw=kw: (CsvInput(BASE.with_(n_rows=n, **kw)),),
                4.0,
                max_size=3_000_000,
            )
        )
    add(
        Case(
            "v4/matmul/three_quarter_rect",
            "operator.matmul",
            "a @ b",
            lambda d: (
                ArrayInput((d, 3 * d // 4), "a", seed=452),
                ArrayInput((3 * d // 4, d // 2), "b", seed=453),
            ),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "v4/matmul/float32_thin",
            "operator.matmul",
            "a @ b",
            lambda d: (
                ArrayInput((d, d // 4), "a", seed=454, dtype="float32"),
                ArrayInput((d // 4, d), "b", seed=455, dtype="float32"),
            ),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "v4/np_sort/int64_random",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), dtype="int64", seed=450),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    add(
        Case(
            "v4/np_sort/float32_nearly_sorted",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="nearly_sorted", dtype="float32", seed=451),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
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
    # ---- test-v2: fresh sealed configurations (new generators/parameters/seeds >= 100) ----
    vs = {"str_len_dist": "variable", "null_pattern": "clustered"}
    add(
        Case(
            "v2/drop_duplicates/clustered_nulls_varstr_dup60",
            "drop_duplicates",
            "df.drop_duplicates()",
            lambda n: _frame(
                n,
                dup_rate=0.6,
                cardinality=0.07,
                null_rate=0.15,
                str_len=10,
                n_int=1,
                n_float=1,
                n_object=3,
                n_category=0,
                n_datetime=2,
                seed=101,
                **vs,
            ),
            3.0,
            meta=vs,
        )
    )
    add(
        Case(
            "v2/drop_duplicates/subset_f0_d0_wide_floats",
            "drop_duplicates",
            'df.drop_duplicates(subset=["f0", "d0"])',
            lambda n: _frame(
                n,
                n_float=8,
                n_int=1,
                n_object=1,
                n_category=0,
                n_datetime=1,
                dup_rate=0.4,
                seed=102,
            ),
            3.0,
        )
    )
    add(
        Case(
            "v2/merge/zipf_right_left_join",
            "merge",
            'df.merge(right, on="k", how="left")',
            lambda n: _join(
                n,
                overlap=0.8,
                fanout=5.0,
                right_ratio=0.25,
                right_key_dist="zipf",
                right_seed=1103,
                cardinality=0.3,
                distribution="real_like",
                zipf_exponent=1.8,
                seed=103,
            ),
            5.0,
        )
    )
    add(
        Case(
            "v2/merge/big_right_low_overlap",
            "merge",
            'df.merge(right, on="k", how="inner")',
            lambda n: _join(
                n,
                overlap=0.3,
                fanout=1.5,
                right_ratio=1.5,
                right_seed=1104,
                str_len_dist="variable",
                str_len=14,
                seed=104,
            ),
            5.0,
        )
    )
    add(
        Case(
            "v2/groupby/two_str_keys_multi_agg",
            "groupby",
            'df.groupby(["s0", "s1"])[["f0", "f1"]].sum()',
            lambda n: _frame(
                n, n_object=3, cardinality=300, str_len=9, str_len_dist="variable", seed=105
            ),
            3.0,
        )
    )
    add(
        Case(
            "v2/groupby/int_key_heavy_zipf_mean",
            "groupby",
            'df.groupby("i0")["f0"].mean()',
            lambda n: _frame(
                n, cardinality=5000, distribution="real_like", zipf_exponent=1.8, seed=106
            ),
            3.0,
        )
    )
    add(
        Case(
            "v2/sort_values/block_sorted_int",
            "sort_values",
            'df.sort_values("i0")',
            lambda n: _frame(n, ordering="block_sorted", cardinality=0.3, seed=107),
            3.0,
        )
    )
    add(
        Case(
            "v2/sort_values/multikey_str_float_desc",
            "sort_values",
            'df.sort_values(["s0", "f0"], ascending=[True, False])',
            lambda n: _frame(n, str_len=11, null_rate=0.05, cardinality=0.25, seed=108, **vs),
            3.0,
        )
    )
    add(
        Case(
            "v2/read_csv/variable_strings_clustered_nulls",
            "pandas.read_csv",
            "pd.read_csv({csv!r})",
            lambda n: (
                CsvInput(
                    BASE.with_(
                        n_rows=n,
                        n_object=3,
                        str_len=14,
                        null_rate=0.1,
                        cardinality=0.3,
                        seed=109,
                        **vs,
                    )
                ),
            ),
            4.0,
            max_size=3_000_000,
        )
    )
    add(
        Case(
            "v2/read_csv/category_heavy_dates",
            "pandas.read_csv",
            "pd.read_csv({csv!r})",
            lambda n: (
                CsvInput(
                    BASE.with_(
                        n_rows=n,
                        n_int=1,
                        n_float=1,
                        n_object=0,
                        n_category=4,
                        n_datetime=3,
                        cardinality=0.02,
                        seed=110,
                    )
                ),
            ),
            4.0,
            max_size=3_000_000,
        )
    )
    add(
        Case(
            "v2/astype/int_to_category_lowcard",
            "astype",
            'df["i0"].astype("category")',
            lambda n: _frame(n, cardinality=50, seed=111),
            3.0,
        )
    )
    add(
        Case(
            "v2/astype/float_to_int64",
            "astype",
            'df["f0"].astype("int64")',
            lambda n: _frame(n, distribution="real_like", seed=112),
            3.0,
        )
    )
    add(
        Case(
            "v2/concat/unequal_variable_strings",
            "pandas.concat",
            "pd.concat([df, df2], ignore_index=True)",
            lambda n: _concat_parts(n, (0.7, 0.3), (113, 114), str_len=12, str_len_dist="variable"),
            3.0,
        )
    )
    add(
        Case(
            "v2/concat/five_small_frames",
            "pandas.concat",
            "pd.concat([df, df2, df3, df4, df5])",
            lambda n: _concat_parts(
                n, (0.2,) * 5, (115, 116, 117, 118, 119), null_rate=0.03, null_pattern="clustered"
            ),
            3.0,
        )
    )
    add(
        Case(
            "v2/matmul/tall_skinny",
            "operator.matmul",
            "a @ b",
            lambda d: (
                ArrayInput((2 * d, d // 4), "a", seed=120),
                ArrayInput((d // 4, d), "b", seed=121),
            ),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "v2/np_sort/nearly_sorted",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="nearly_sorted", seed=122),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    add(
        Case(
            "v2/np_sort/int64_few_unique",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="few_unique", dtype="int64", seed=123),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )

    # ---- val-v3: held-out validation configurations (seeds >= 301; parameter values, join ratios
    # and array dtype/pattern combinations not used by any dev or test-v2 case; frozen in
    # split.json, measured but never displayed; see benchmarks/split.py) ----
    add(
        Case(
            "v3/drop_duplicates/null_heavy_full",
            "drop_duplicates",
            "df.drop_duplicates()",
            lambda n: _frame(
                n, dup_rate=0.15, cardinality=0.04, null_rate=0.35, str_len=18, seed=301
            ),
            3.0,
        )
    )
    add(
        Case(
            "v3/drop_duplicates/null_subset_f0_s0",
            "drop_duplicates",
            'df.drop_duplicates(subset=["f0", "s0"])',
            lambda n: _frame(n, dup_rate=0.7, cardinality=0.35, null_rate=0.22, seed=302),
            3.0,
        )
    )
    add(
        Case(
            "v3/drop_duplicates/high_survivor_subset_i0_d0",
            "drop_duplicates",
            'df.drop_duplicates(subset=["i0", "d0"])',
            lambda n: _frame(n, dup_rate=0.02, cardinality=800, seed=303),
            3.0,
        )
    )
    add(
        Case(
            "v3/drop_duplicates/numeric_wide_nulls",
            "drop_duplicates",
            "df.drop_duplicates()",
            lambda n: _frame(
                n, n_int=6, n_float=6, n_object=0, n_category=0, n_datetime=0,
                dup_rate=0.85, null_rate=0.08, cardinality=0.0007, seed=304,
            ),
            3.0,
        )
    )  # fmt: skip
    merge = 'df.merge(right, on="k", how="{how}")'
    for name, how, kw in (
        ("inner_overlap25_fanout6", "inner",
         {"overlap": 0.25, "fanout": 6.0, "right_ratio": 0.35, "right_seed": 1301, "seed": 305}),
        ("left_overlap90_fanout1p2", "left",
         {"overlap": 0.9, "fanout": 1.2, "right_ratio": 0.8, "right_seed": 1302, "seed": 306}),
        ("outer_overlap65_zipf", "outer",
         {"overlap": 0.65, "fanout": 2.5, "right_key_dist": "zipf", "right_seed": 1303, "right_ratio": 0.6,
          "zipf_exponent": 2.4, "seed": 307}),
        ("inner_bigright_fanout8", "inner",
         {"overlap": 0.45, "fanout": 8.0, "right_ratio": 2.0, "right_seed": 1304, "seed": 308}),
        ("right_overlap05_text", "right",
         {"overlap": 0.05, "fanout": 1.2, "right_seed": 1305, "right_ratio": 0.7, "seed": 309,
          "n_object": 4, "str_len": 30}),
    ):  # fmt: skip
        add(
            Case(
                f"v3/merge/{name}",
                "merge",
                merge.format(how=how),
                lambda n, kw=kw: _join(n, **kw),
                5.0,
                meta={"how": how},
            )
        )
    for name, src, kw in (
        ("str_card12_sum", 'df.groupby("s0")["f0"].sum()', {"cardinality": 12, "seed": 310}),
        ("int_card20000_mean", 'df.groupby("i0")["f0"].mean()', {"cardinality": 20000, "seed": 311}),
        ("str_card0p04_two_values", 'df.groupby("s0")[["f0", "f1"]].sum()',
         {"cardinality": 0.04, "seed": 312}),
        ("two_keys_card800", 'df.groupby(["i0", "s0"])["f0"].sum()', {"cardinality": 800, "seed": 313}),
        ("zipf_int_card0p0004", 'df.groupby("i0")["f0"].sum()',
         {"cardinality": 0.0004, "distribution": "real_like", "zipf_exponent": 1.3, "seed": 314}),
        ("str_card0p75_sum", 'df.groupby("s0")["f0"].sum()', {"cardinality": 0.75, "seed": 315}),
    ):  # fmt: skip
        add(Case(f"v3/groupby/{name}", "groupby", src, lambda n, kw=kw: _frame(n, **kw), 3.0))
    for name, src, kw in (
        ("str_to_category_card25", 'df["s0"].astype("category")', {"cardinality": 25, "seed": 316}),
        ("str_to_category_card12000", 'df["s0"].astype("category")',
         {"cardinality": 12000, "seed": 317}),
        ("str_to_category_card0p75", 'df["s0"].astype("category")',
         {"cardinality": 0.75, "seed": 318}),
        ("int_to_category_card0p04", 'df["i0"].astype("category")',
         {"cardinality": 0.04, "seed": 319}),
        ("float_to_str", 'df["f0"].astype(str)', {"distribution": "real_like", "seed": 320}),
        ("int_to_int16", 'df["i0"].astype("int16")', {"cardinality": 30000, "seed": 321}),
    ):  # fmt: skip
        add(Case(f"v3/astype/{name}", "astype", src, lambda n, kw=kw: _frame(n, **kw), 3.0))
    add(
        Case(
            "v3/sort_values/float_desc_nulls",
            "sort_values",
            'df.sort_values("f0", ascending=False)',
            lambda n: _frame(n, null_rate=0.08, seed=322),
            3.0,
        )
    )
    add(
        Case(
            "v3/sort_values/two_str_keys",
            "sort_values",
            'df.sort_values(["s0", "s1"])',
            lambda n: _frame(n, str_len=7, cardinality=0.04, seed=323),
            3.0,
        )
    )
    add(
        Case(
            "v3/sort_values/int_datetime_lowcard",
            "sort_values",
            'df.sort_values(["i0", "d0"])',
            lambda n: _frame(n, cardinality=0.0004, seed=324),
            3.0,
        )
    )
    add(
        Case(
            "v3/concat/four_frames_light_nulls",
            "pandas.concat",
            "pd.concat([df, df2, df3, df4])",
            lambda n: _concat_parts(n, (0.25,) * 4, (325, 326, 327, 328), null_rate=0.02),
            3.0,
        )
    )
    add(
        Case(
            "v3/concat/two_numeric_unequal",
            "pandas.concat",
            "pd.concat([df, df2], ignore_index=True)",
            lambda n: _concat_parts(n, (0.55, 0.45), (329, 330), n_object=0, n_category=0),
            3.0,
        )
    )
    add(
        Case(
            "v3/concat/two_strings_long",
            "pandas.concat",
            "pd.concat([df, df2])",
            lambda n: _concat_parts(
                n, (0.5, 0.5), (331, 332), n_int=0, n_float=0, n_object=3, str_len=40
            ),
            3.0,
        )
    )
    for name, kw in (
        ("float_heavy", {"n_int": 2, "n_float": 10, "n_object": 0, "n_category": 0,
                         "n_datetime": 0, "seed": 333}),
        ("short_ints", {"n_int": 12, "n_float": 0, "n_object": 0, "n_category": 0,
                        "n_datetime": 0, "cardinality": 12, "seed": 334}),
        ("long_distinct_strings", {"n_int": 1, "n_float": 0, "n_object": 3, "n_category": 0,
                                   "n_datetime": 0, "str_len": 40, "cardinality": 0.75,
                                   "seed": 335}),
        ("mixed_nulls_dates", {"n_int": 2, "n_float": 3, "n_object": 2, "n_category": 0,
                               "n_datetime": 2, "str_len": 6, "null_rate": 0.22, "seed": 336}),
        ("two_columns", {"n_int": 1, "n_float": 1, "n_object": 0, "n_category": 0,
                         "n_datetime": 0, "seed": 337}),
    ):  # fmt: skip
        add(
            Case(
                f"v3/read_csv/{name}",
                "pandas.read_csv",
                "pd.read_csv({csv!r})",
                lambda n, kw=kw: (CsvInput(BASE.with_(n_rows=n, **kw)),),
                4.0,
                max_size=3_000_000,
            )
        )
    add(
        Case(
            "v3/matmul/wide_rect",
            "operator.matmul",
            "a @ b",
            lambda d: (
                ArrayInput((d // 3, d), "a", seed=340),
                ArrayInput((d, 2 * d // 3), "b", seed=341),
            ),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "v3/matmul/float32_square",
            "operator.matmul",
            "a @ b",
            lambda d: (
                ArrayInput((d, d), "a", seed=342, dtype="float32"),
                ArrayInput((d, d), "b", seed=343, dtype="float32"),
            ),
            4.0,
            size_kind="dim",
            full_sizes=MATMUL_FULL_DIMS,
        )
    )
    add(
        Case(
            "v3/np_sort/int32_random",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), dtype="int32", seed=350),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )
    add(
        Case(
            "v3/np_sort/float32_reverse",
            "numpy.sort",
            "np.sort(a)",
            lambda n: (ArrayInput((n,), pattern="reverse", dtype="float32", seed=351),),
            3.0,
            full_sizes=NP_SORT_SIZES,
        )
    )

    _add_val_v4(add)
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
    splits: tuple[str, ...] = ("dev",),
    max_size: int | None = None,
) -> list[GridPoint]:
    """All grid points of ``suite`` in the requested groups (dev first, then test-v2, val-v3).

    The protected groups (``test-v2``, ``val-v3``) are opt-in: never part of the default selection.

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
    return sorted(points, key=lambda pt: GROUPS.index(pt.split))  # stable group order
