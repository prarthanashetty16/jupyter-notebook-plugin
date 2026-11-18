"""Cells and data of the suggestion benchmark (Phase 5, pre-registration B3).

A *configuration* = (rule family, cell template, data shape). Each has two row counts (the cells).
Data are synthetic and deterministic. The split into dev and held-out is made by
``split.assign`` (sha256 order per family) BEFORE any measurement and frozen in ``split.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

SIZES = (1_000_000, 2_000_000)  # rows of the main frame (the dev machine has ~3 GB free RAM)
CSV_SIZES = (800_000, 1_600_000)

# cell templates: names ``left`` / ``right`` / ``junk`` / ``path`` are bound by the harness
TEMPLATES: dict[str, str] = {
    "G1": 'r = left.groupby("k")["v"].sum()',
    "G2": 'g = left.groupby("k")["v"].mean()\nr = g',
    "M1": 'r = left.merge(right, on="k")["v"]',
    "M2": 'm = left.merge(right, on="k")\nr = m["v"].sum()',
    "S1": 'r = left.sort_values("v").head(10)',
    "D1": 'r = left.drop_duplicates(subset=["k", "c"])["v"].sum()',
    "C_S": 'r = left.copy().sort_values("v").head(10)',
    "C_G": 'r = left.copy().groupby("k")["v"].sum()',
    "C_D": 'r = left.copy().drop_duplicates(subset=["k", "c"])["v"].sum()',
    "C_M": 'r = left.copy().merge(right, on="k")["v"]',
    "R_B": 'df = pd.read_csv(PATH)\nr = df["a"].sum()',
    "R_C": 'r = pd.read_csv(PATH)["a"].sum()',
    "R_K": "df = pd.read_csv(PATH)",
    "X": 'r = left["v"].sum()',  # the cell never touches ``junk`` (delete-unreferenced rule)
}


@dataclass(frozen=True)
class Shape:
    """Synthetic frame: key ``k``, value ``v``, ``c`` (int), extras and low-cardinality text."""

    name: str
    n_float: int = 4  # extra float64 columns
    n_int: int = 1  # extra int64 columns (small range)
    n_text: int = 0
    text_card: int = 100
    text_len: int = 12
    key_card: int = 1000
    right_extra: int = 2
    csv_cols: int = 0  # read_csv shapes only


SHAPES: dict[str, Shape] = {
    "w6": Shape("w6", n_float=3, n_int=1),
    "w12": Shape("w12", n_float=8, n_int=2, n_text=1),
    "w20": Shape("w20", n_float=14, n_int=3, n_text=2),
    "num8": Shape("num8", n_float=5, n_int=2),
    "int8": Shape("int8", n_float=1, n_int=6),
    "t2": Shape("t2", n_float=2, n_int=1, n_text=2, text_card=100),
    "t3long": Shape("t3long", n_float=2, n_int=1, n_text=3, text_card=1000, text_len=24),
    "k_int": Shape("k_int", n_float=3, n_int=1, key_card=5000),
    "k_wide": Shape("k_wide", n_float=6, n_int=2, key_card=200),
    "csv8": Shape("csv8", csv_cols=8),
    "csv16": Shape("csv16", csv_cols=16),
    "junk": Shape("junk", n_float=2, n_int=1),
    "junk_t": Shape("junk_t", n_float=1, n_int=1, n_text=1, text_card=50),
}


@dataclass(frozen=True)
class Config:
    family: str
    template: str
    shape: str
    sizes: tuple[int, ...] = SIZES
    extra: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        return f"{self.family}/{self.template}/{self.shape}"


def _cfgs(family: str, templates: list[str], shapes: list[str], **kw: Any) -> list[Config]:
    return [Config(family, t, s, **kw) for t in templates for s in shapes]


def all_configs() -> list[Config]:
    out: list[Config] = []
    out += _cfgs("select_columns", ["G1", "G2", "M1", "M2"], ["w6", "w12", "w20"])
    out += _cfgs("downcast_numeric", ["G1", "S1", "D1"], ["num8", "int8"])
    out += _cfgs("text_to_category", ["G1", "S1", "D1"], ["t2", "t3long"])
    out += _cfgs("key_dtype", ["M1", "S1"], ["k_int", "k_wide"])
    out += _cfgs("read_csv_options", ["R_B", "R_C", "R_K"], ["csv8", "csv16"], sizes=CSV_SIZES)
    out += _cfgs("avoid_copy", ["C_S", "C_G", "C_D", "C_M"], ["num8"])
    out += _cfgs("delete_unreferenced", ["X"], ["junk", "junk_t"], sizes=(2_000_000,))
    keys = [c.key for c in out]
    assert len(keys) == len(set(keys))
    return out


def build_frames(shape: Shape, n: int, seed: int = 7) -> dict[str, pd.DataFrame]:
    """Deterministic ``left`` / ``right`` (and ``junk``) frames for ``shape`` with ``n`` rows."""
    rng = np.random.default_rng(seed)
    cols: dict[str, Any] = {"k": rng.integers(0, shape.key_card, n), "v": rng.random(n)}
    cols["c"] = rng.integers(0, 100, n)
    for i in range(shape.n_float):
        cols[f"f{i}"] = rng.random(n)
    for i in range(shape.n_int):
        cols[f"i{i}"] = rng.integers(0, 30_000, n)
    for i in range(shape.n_text):
        pool = [f"{j:0{shape.text_len}d}" for j in range(shape.text_card)]
        cols[f"s{i}"] = np.array(pool, dtype=object)[rng.integers(0, shape.text_card, n)]
    left = pd.DataFrame(cols)
    if shape.name.startswith("junk"):  # a small working frame plus a large unreferenced one
        return {"left": left.iloc[:100_000].copy(), "junk": left}
    right = pd.DataFrame({"k": np.arange(shape.key_card), "w": rng.random(shape.key_card)})
    for i in range(shape.right_extra):
        right[f"x{i}"] = rng.random(shape.key_card)
    return {"left": left, "right": right}


def build_csv(shape: Shape, n: int, path: str, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    cols: dict[str, Any] = {"a": rng.random(n)}
    for i in range(1, shape.csv_cols):
        cols[f"col{i}"] = rng.random(n) if i % 2 else rng.integers(0, 100_000, n)
    pd.DataFrame(cols).to_csv(path, index=False)
