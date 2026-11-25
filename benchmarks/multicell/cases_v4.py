"""Phase 8c multicell v4: fresh templates and inputs for the next frozen evaluation."""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.multicell.cases import KEYS

TAB = chr(9)
SIZES = (1_500_000, 3_000_000)
SEEDS = (41, 42, 43)
SHAPES = ("balanced", "nullable", "textwide", "narrow", "indexheavy", "skewed")

TEMPLATES: dict[str, str] = {
    "loads_args": "a = pd.read_csv({P1}, usecols=['k', 'v', 'f0'])\nb = pd.read_csv({P2}, nrows={HALF})",
    "load_fillna_text": "a = pd.read_csv({P1})\nb = a.fillna('missing')",
    "text_fillna_cols": "z = df[['k', 'v']].copy()\ny = df.fillna(0)",
    "load_then_merge_left": "a = pd.read_csv({P1})\nm = a.merge(right, on='k', how='left')",
    "concat_then_sort": "c = pd.concat([df, df2])\ns = c.sort_values('v')",
    "copy_then_fillna": "x = df.copy()\ny = x.fillna(0)",
    "set_index_ops": "s = df.set_index('k')\nt = df.set_index('v', drop=False)",
    "apply_ufunc": "a = df['v'].apply(np.sqrt)\nb = df['k'].apply(np.log1p)",
    "deletes_v4": "m = df.merge(right, on='k')\ndel m\ns = df.sort_values('v')\ndel s\nd = df.drop_duplicates(subset=['k'])\nc = df.corr()",
    "rebinding_v4": "x = df.sort_values('v')\nx = df.copy()\nx = df.sort_values('k')\nc = pd.concat([df, df2])\nc.to_csv({P3}, index=False)",
    "rebinding_alias": "x = df.sort_values('v')\ny = x\nx = df.copy()\nz = x.drop_duplicates(subset=['k'])\nj = df.join(right.set_index('k'), on='k')",
    "chain_v4": "r = df.sort_values('k').drop_duplicates(subset=['k']).merge(right, on='k')",
    "groupby_on_created": "s = df.sort_values('v')\ng = s.groupby('k')['v'].sum()\nvc = df['k'].value_counts()",
    "astype_on_created": "x = df.copy()\nc = x['k'].astype('category')\nd = x.drop_duplicates(subset=['k'])\na = df['v'].apply(lambda value: value + 1)",
    "partial_map": "s = df['v'].map(lambda value: value + 1)\ng = df.groupby('k')['v'].mean()",
    "partial_get_dummies": "d = df.dropna(subset=['f0'])\no = pd.get_dummies(df['cat'])",
}  # fmt: skip


@dataclass(frozen=True)
class Config:
    template: str
    shape: str

    @property
    def key(self) -> str:
        return f"{self.template}/{self.shape}"


@dataclass(frozen=True)
class Cell:
    config: Config
    rows: int

    @property
    def id(self) -> str:
        return f"v4:{self.config.key}@{self.rows}"


def all_configs() -> list[Config]:
    return [Config(template, shape) for template in TEMPLATES for shape in SHAPES]


def all_cells(keys: set[str] | None = None) -> list[Cell]:
    return [
        Cell(config, rows)
        for config in all_configs()
        if keys is None or config.key in keys
        for rows in SIZES
    ]


def make_frame_v4(shape: str, rows: int, seed: int) -> pd.DataFrame:
    """Create new Phase 8c input shapes with bounded text and category vocabularies."""
    rng = np.random.default_rng(seed)
    if shape == "skewed":
        keys = (rng.zipf(1.7, rows) % KEYS).astype(np.int64)
    else:
        keys = rng.integers(0, KEYS, rows, dtype=np.int64)

    values = rng.random(rows)
    values[::37] = np.nan
    text_vocab = np.array([f"v{x:06d}" for x in range(20_000)], dtype=object)

    def text_col(offset: int) -> pd.arrays.StringArray:
        values = text_vocab[rng.integers(0, len(text_vocab), rows)].copy()
        values[offset::29] = None
        return pd.array(values, dtype="str")

    columns: dict[str, object] = {
        "k": keys,
        "v": values,
        "f0": rng.random(rows),
        "i0": rng.integers(0, 50_000, rows, dtype=np.int64),
        "s0": text_col(3),
        "cat": pd.Categorical(rng.integers(0, 4, rows), categories=range(4)),
    }
    if shape == "nullable":
        columns["k"] = pd.array(keys, dtype="Int64")
        columns["k"][::41] = pd.NA
        columns["f0"] = pd.array(columns["f0"], dtype="Float64")
        columns["f0"][::43] = pd.NA
    elif shape == "textwide":
        columns.update({f"s{i}": text_col(i + 5) for i in range(1, 5)})
    elif shape == "narrow":
        columns["k"] = keys.astype(np.int32)
        columns["v"] = values.astype(np.float32)
        columns["i0"] = rng.integers(0, 30_000, rows, dtype=np.int16)
    elif shape == "indexheavy":
        frame = pd.DataFrame(columns)
        frame.index = pd.Index(rng.permutation(rows), name="row_id")
        return frame
    elif shape != "balanced" and shape != "skewed":
        raise ValueError(f"unknown v4 frame shape: {shape}")
    return pd.DataFrame(columns)


def prepare(cache: Path, shape: str, rows: int) -> dict[str, str]:
    """Write a shape/size input set once and return its file paths."""
    directory = cache / f"v4_{shape}_{rows}"
    paths = {
        "df": directory / "df.pkl",
        "df2": directory / "df2.pkl",
        "right": directory / "right.pkl",
        "P1": directory / "p1.csv",
        "P2": directory / "p2.csv",
        "P3": directory / "out.csv",
        "T1": directory / "t1.tsv",
    }
    if not (directory / "DONE").exists():
        directory.mkdir(parents=True, exist_ok=True)
        df = make_frame_v4(shape, rows, SEEDS[0])
        df2 = make_frame_v4(shape, rows, SEEDS[1])
        right = pd.DataFrame(
            {"k": np.arange(KEYS), "w": np.random.default_rng(SEEDS[2]).random(KEYS)}
        )
        df.to_pickle(paths["df"])
        df2.to_pickle(paths["df2"])
        right.to_pickle(paths["right"])
        df.to_csv(paths["P1"], index=False, na_rep="NA")
        df2.to_csv(paths["P2"], index=False, na_rep="NA")
        df.to_csv(paths["T1"], index=False, sep=TAB, na_rep="NA")
        del df, df2, right
        gc.collect()
        (directory / "DONE").write_text("ok", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}


def source(cell: Cell, paths: dict[str, str]) -> str:
    return TEMPLATES[cell.config.template].format(
        P1=repr(paths["P1"]),
        P2=repr(paths["P2"]),
        P3=repr(paths["P3"]),
        T1=repr(paths["T1"]),
        TAB=repr(TAB),
        HALF=cell.rows // 2,
    )
