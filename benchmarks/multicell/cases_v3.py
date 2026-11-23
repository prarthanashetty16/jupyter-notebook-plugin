"""Multi-statement benchmark v3 (Phase 7c): the ENLARGED held-out group for freeze v3 (designed, never run).

Designed from the pre-registered rules (``docs/benchmarks/phase7-preregistration.md``, amendment 1), not from
measured values. It is fixed before ``models-frozen-v3`` is tagged. It exercises the v3 scope and the cell patterns
v3 must handle conservatively:
* fillna on pandas-3 text columns (uncovered: must give UNKNOWN or a class that is never OK when the actual exceeds
  the headroom);
* frames created earlier in the cell;
* set_index;
* apply(np.<ufunc>);
* del / rebinding, including an alias;
* chains;
* read_csv arguments;
* an uncovered value_counts.

Nothing is shared with v1 / v2: sizes 1.25M / 2.5M (v1 1M / 2M, v2 1.5M / 3M), seeds 21 / 22 / 23, two new shapes
(``narrow``: 32- / 16-bit columns and one short text column; ``textwide``: four ``str`` columns with missing values).
Every template applies to all six shapes; ``split.py`` holds out TWO configurations per template (16 templates ->
32 held-out configurations, 64 cells).
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.multicell.cases import KEYS
from benchmarks.multicell.cases_v2 import make_frame_v2

TAB = chr(9)
SIZES = (1_250_000, 2_500_000)
SEEDS = (21, 22, 23)  # df, df2, right (v1: 1-3, v2: 11-13)
SHAPES = ("num", "mixed", "wide", "text", "narrow", "textwide")

TEMPLATES: dict[str, str] = {
    "loads_args": "a = pd.read_csv({P1}, usecols=['k', 'v', 'f0'])\nb = pd.read_csv({P2}, nrows={HALF})",
    "load_fillna_text": "a = pd.read_csv({P1})\nb = a.fillna('missing')",
    "text_fillna_cols": "z = df[['k', 'v']].copy()\ny = df.fillna(0)",
    "load_then_merge_left": "a = pd.read_csv({P1})\nm = a.merge(right, on='k', how='left')",
    "concat_then_sort": "c = pd.concat([df, df2])\ns = c.sort_values('v')",
    "copy_then_fillna": "x = df.copy()\ny = x.fillna(0)",
    "set_index_ops": "s = df.set_index('k')\nt = df.set_index('v', drop=False)",
    "apply_ufunc": "a = df['v'].apply(np.sqrt)\nb = df['k'].apply(np.log1p)",
    "deletes_v3": "m = df.merge(right, on='k')\ndel m\ns = df.sort_values('v')\ndel s\nd = df.drop_duplicates(subset=['k'])",
    "rebinding_v3": "x = df.sort_values('v')\nx = df.copy()\nx = df.sort_values('k')\nc = pd.concat([df, df2])",
    "rebinding_alias": "x = df.sort_values('v')\ny = x\nx = df.copy()\nz = x.drop_duplicates(subset=['k'])",
    "chain_v3": "r = df.sort_values('k').drop_duplicates(subset=['k']).merge(right, on='k')",
    "groupby_on_created": "s = df.sort_values('v')\ng = s.groupby('k')['v'].sum()",
    "astype_on_created": "x = df.copy()\nc = x['k'].astype('category')\nd = x.drop_duplicates(subset=['k'])",
    "loads_tsv_dtype": "a = pd.read_csv({T1}, sep={TAB}, dtype={{'v': 'float32'}})\nb = pd.read_csv({P2}, na_values=['NA'])",
    "value_counts_mix": "vc = df['k'].value_counts()\ng = df.groupby('k')['v'].mean()",
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
        return f"v3:{self.config.key}@{self.rows}"


def all_configs() -> list[Config]:
    return [Config(t, s) for t in TEMPLATES for s in SHAPES]


def all_cells(keys: set[str] | None = None) -> list[Cell]:
    return [Cell(c, n) for c in all_configs() if keys is None or c.key in keys for n in SIZES]


def make_frame_v3(shape: str, rows: int, seed: int) -> pd.DataFrame:
    """v2 shapes with v3 seeds, plus ``narrow`` and ``textwide``."""
    if shape in ("num", "mixed", "wide", "text"):
        return make_frame_v2(shape, rows, seed)
    rng = np.random.default_rng(seed)
    vocab = np.array([f"x{x:07d}" for x in range(30_000)], dtype=object)

    def text_col() -> pd.arrays.StringArray:
        s = vocab[rng.integers(0, len(vocab), rows)]
        s[rng.random(rows) < 0.05] = None
        return pd.array(s, dtype="str")

    f0 = rng.random(rows)
    f0[::40] = np.nan
    if shape == "narrow":
        cols = {"k": rng.integers(0, KEYS, rows).astype("int32"), "v": rng.random(rows).astype("float32"),
                "f0": f0.astype("float32"), "i0": rng.integers(0, 30_000, rows).astype("int16"), "s0": text_col()}  # fmt: skip
    else:  # textwide
        cols = {"k": rng.integers(0, KEYS, rows), "v": rng.random(rows), "f0": f0,
                **{f"s{i}": text_col() for i in range(4)}}  # fmt: skip
    return pd.DataFrame(cols)


def prepare(cache: Path, shape: str, rows: int) -> dict[str, str]:
    """Write the inputs of one (shape, size) once; returns the paths."""
    d = cache / f"v3_{shape}_{rows}"
    paths = {"df": d / "df.pkl", "df2": d / "df2.pkl", "right": d / "right.pkl",
             "P1": d / "p1.csv", "P2": d / "p2.csv", "T1": d / "t1.tsv"}  # fmt: skip
    if not (d / "DONE").exists():
        d.mkdir(parents=True, exist_ok=True)
        df, df2 = make_frame_v3(shape, rows, SEEDS[0]), make_frame_v3(shape, rows, SEEDS[1])
        df.to_pickle(paths["df"])
        df2.to_pickle(paths["df2"])
        pd.DataFrame(
            {"k": np.arange(KEYS), "w": np.random.default_rng(SEEDS[2]).random(KEYS)}
        ).to_pickle(paths["right"])
        df.to_csv(paths["P1"], index=False, na_rep="NA")
        df2.to_csv(paths["P2"], index=False, na_rep="NA")
        df.to_csv(paths["T1"], index=False, sep=TAB, na_rep="NA")
        del df, df2
        gc.collect()
        (d / "DONE").write_text("ok")
    return {k: str(v) for k, v in paths.items()}


def source(cell: Cell, paths: dict[str, str]) -> str:
    return TEMPLATES[cell.config.template].format(
        P1=repr(paths["P1"]),
        P2=repr(paths["P2"]),
        T1=repr(paths["T1"]),
        TAB=repr(TAB),
        HALF=cell.rows // 2,
    )
