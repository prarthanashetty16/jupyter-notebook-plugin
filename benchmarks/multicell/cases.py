"""Templates, data shapes and sizes of the multi-statement benchmark (Phase 6c pre-registration A).

A configuration = (template, shape); each runs at two sizes. Paths are written into the cell source as
literals (``{P1}`` / ``{P2}`` CSV, ``{T1}`` TSV); ``df``, ``df2`` and ``right`` are loaded from disk
before the cell. The templates exercise what the cell model must handle: several retained loads,
load arguments, an operation on a frame created inside the cell (no estimate possible: a known
coverage gap), chains with temporaries, ``del``, copy / fillna, expression statements, rebinding.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

TAB = chr(9)
SIZES = (1_000_000, 2_000_000)
KEYS = 50_000

TEMPLATES: dict[str, str] = {
    "loads2": "a = pd.read_csv({P1})\nb = pd.read_csv({P2})",
    "loads3_tsv": "a = pd.read_csv({T1}, sep={TAB})\nb = pd.read_csv({T1}, sep={TAB}, usecols=['k', 'v'])\n"
    "c = pd.read_csv({P2})",
    "load_dtype_nrows": "a = pd.read_csv({P1}, dtype={{'f0': 'float32', 'v': 'float32'}})\n"
    "b = pd.read_csv({P2}, nrows={HALF})",
    "load_then_merge": "a = pd.read_csv({P2})\nm = a.merge(right, on='k')",
    "chain": "r = df.merge(right, on='k').sort_values('v').drop_duplicates(subset=['k'])",
    "deletes": "s = df.sort_values('v')\ndel s\nd = df.drop_duplicates(subset=['k'])\n"
    "g = df.groupby('k')['v'].sum()",
    "copy_fillna": "x = df.copy()\ny = df.fillna(0)\nz = df.fillna({{'f0': 0.0}})",
    "expressions": "df.sort_values('v')\ndf.merge(right, on='k')\nx = df.copy()",
    "rebinding": "m = df.merge(right, on='k')\nm = df.sort_values('v')\nc = pd.concat([df, df2])",
    "concat_loads": "parts = pd.concat([pd.read_csv({P1}), pd.read_csv({P2})])",
    "astype_groupby": "c = df['k'].astype('category')\ng = df.groupby('k')['v'].mean()",
}  # fmt: skip
SHAPES = ("num", "mixed", "wide")


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
        return f"{self.config.key}@{self.rows}"


def all_configs() -> list[Config]:
    return [Config(t, s) for t in TEMPLATES for s in SHAPES]


def all_cells(keys: set[str] | None = None) -> list[Cell]:
    return [Cell(c, n) for c in all_configs() if keys is None or c.key in keys for n in SIZES]


def make_frame(shape: str, rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols: dict[str, np.ndarray] = {"k": rng.integers(0, KEYS, rows), "v": rng.random(rows)}
    if shape == "num":
        cols.update({f"f{i}": rng.random(rows) for i in range(4)})
        cols.update({f"i{i}": rng.integers(0, 10**6, rows) for i in range(2)})
    elif shape == "mixed":
        cols.update({f"f{i}": rng.random(rows) for i in range(2)})
        cols["i0"] = rng.integers(0, 10**6, rows)
        vocab = np.array([f"w{x:011d}" for x in range(5_000)], dtype=object)
        cols.update({f"s{i}": vocab[rng.integers(0, len(vocab), rows)] for i in range(2)})
    else:  # wide
        cols.update({f"f{i}": rng.random(rows) for i in range(10)})
    df = pd.DataFrame(cols)
    df.loc[df.index[::100], "f0"] = np.nan  # a missing value for fillna
    return df


def prepare(cache: Path, shape: str, rows: int) -> dict[str, str]:
    """Write the inputs of one (shape, size) once; returns the paths."""
    d = cache / f"{shape}_{rows}"
    paths = {"df": d / "df.pkl", "df2": d / "df2.pkl", "right": d / "right.pkl",
             "P1": d / "p1.csv", "P2": d / "p2.csv", "T1": d / "t1.tsv"}  # fmt: skip
    if not (d / "DONE").exists():
        d.mkdir(parents=True, exist_ok=True)
        df, df2 = make_frame(shape, rows, 1), make_frame(shape, rows, 2)
        df.to_pickle(paths["df"])
        df2.to_pickle(paths["df2"])
        pd.DataFrame({"k": np.arange(KEYS), "w": np.random.default_rng(3).random(KEYS)}).to_pickle(
            paths["right"]
        )
        df.to_csv(paths["P1"], index=False)
        df2.to_csv(paths["P2"], index=False)
        df.to_csv(paths["T1"], index=False, sep=TAB)
        del df, df2
        gc.collect()
        (d / "DONE").write_text("ok")
    return {k: str(v) for k, v in paths.items()}


def source(cell: Cell, paths: dict[str, str]) -> str:
    return TEMPLATES[cell.config.template].format(
        P1=repr(paths["P1"]), P2=repr(paths["P2"]), T1=repr(paths["T1"]), TAB=repr(TAB),
        HALF=cell.rows // 2,
    )  # fmt: skip
