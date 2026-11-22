"""Templates, shapes and sizes of the multi-statement benchmark v2 (Phase 7 pre-registration, held-out design).

Fixed in Phase 7a BEFORE any v3 model change. It exercises what freeze v3 is scoped to: read_csv arguments
(``usecols``, ``dtype``, ``nrows``, ``na_values``, ``sep`` / ``header``), the coverage candidates (set_index,
value_counts, apply, explode, fillna on text columns), operations on a frame CREATED EARLIER IN THE SAME CELL
(the v1 "uncovered frame" gap) and the non-load templates whose bias v1 left unexplained (chains, copy,
rebinding, del). Operations that end up out of v3's scope stay in: they test the "no estimate" path.

Nothing is shared with v1 (``cases.py``): other sizes, other generator seeds (11 / 12 / 13), two new
shapes (``text``: pandas-3 ``str`` columns with missing values; ``lists``: a list column for explode).
A configuration = (template, shape); each runs at both sizes.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from benchmarks.multicell.cases import KEYS, make_frame

TAB = chr(9)
SIZES = (1_500_000, 3_000_000)
SEEDS = (11, 12, 13)  # df, df2, right (v1: 1, 2, 3)

# template -> (source, shapes it applies to)
TEMPLATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "loads_usecols_dtype": ("a = pd.read_csv({P1}, usecols=['k', 'v', 'f0'])\nb = pd.read_csv({P2}, dtype={{'v': 'float32'}})",
                            ("num", "wide", "mixed")),
    "load_nrows_merge": ("a = pd.read_csv({P1}, nrows={HALF})\nm = a.merge(right, on='k')", ("num", "wide", "mixed")),
    "load_fillna": ("a = pd.read_csv({P1})\nb = a.fillna(0)", ("num", "wide", "text")),
    "concat_reads_groupby": ("parts = pd.concat([pd.read_csv({P1}), pd.read_csv({P2})])\ng = parts.groupby('k')['v'].sum()",
                             ("num", "wide", "mixed")),
    "loads_tsv_na": ("a = pd.read_csv({T1}, sep={TAB}, na_values=['NA'])\nb = pd.read_csv({P2}, header=0)",
                     ("num", "wide", "mixed")),
    "set_index_copy": ("s = df.set_index('k')\nc = s.copy()", ("num", "mixed", "text")),
    "value_counts_dedup": ("vc = df['k'].value_counts()\nd = df.drop_duplicates(subset=['k'])", ("num", "mixed", "text")),
    "explode_groupby": ("e = df['l'].explode()\ng = df.groupby('k')['v'].sum()", ("lists", "lists_long")),
    "apply_forms": ("a = df['v'].apply(np.sqrt)\nb = df['f0'].apply(lambda x: x * 2)", ("num", "wide", "mixed")),
    "text_fillna": ("z = df['s0'].fillna('missing')\ny = df[['s0', 's1']].fillna('z')", ("text", "mixed")),
    "chain_copy": ("r = df.sort_values('v').drop_duplicates(subset=['k']).copy()", ("num", "mixed", "wide")),
    "copy_astype": ("x = df.copy()\nc = x['k'].astype('category')", ("num", "mixed", "text")),
    "merge_del_groupby": ("m = df.merge(right, on='k')\ndel m\ng = df.groupby('k')['v'].mean()", ("num", "mixed", "wide")),
    "sort_then_groupby": ("s = df.sort_values('v')\ng = s.groupby('k')['v'].sum()", ("num", "mixed", "wide")),
    "concat_then_dedup": ("c = pd.concat([df, df2])\nd = c.drop_duplicates(subset=['k'])", ("num", "mixed", "text")),
}  # fmt: skip
CSV_SHAPES = ("num", "wide", "mixed", "text")


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
        return f"v2:{self.config.key}@{self.rows}"


def all_configs() -> list[Config]:
    return [Config(t, s) for t, (_, shapes) in TEMPLATES.items() for s in shapes]


def all_cells(keys: set[str] | None = None) -> list[Cell]:
    return [Cell(c, n) for c in all_configs() if keys is None or c.key in keys for n in SIZES]


def make_frame_v2(shape: str, rows: int, seed: int) -> pd.DataFrame:
    """v1 shapes with v2 seeds, plus ``text`` and ``lists``."""
    if shape in ("num", "mixed", "wide"):
        return make_frame(shape, rows, seed)
    rng = np.random.default_rng(seed)
    cols: dict[str, object] = {"k": rng.integers(0, KEYS, rows), "v": rng.random(rows)}
    if shape == "text":
        f0 = rng.random(rows)
        f0[::50] = np.nan
        cols["f0"] = f0
        cols["i0"] = rng.integers(0, 10**6, rows)
        vocab = np.array([f"t{x:09d}" for x in range(20_000)], dtype=object)
        for i in range(2):
            s = vocab[rng.integers(0, len(vocab), rows)]
            s[rng.random(rows) < 0.05] = None
            cols[f"s{i}"] = pd.array(s, dtype="str")
    else:  # lists / lists_long: a list column of small (cached) ints
        mean = 4 if shape == "lists" else 12
        small = list(range(256))
        cols["l"] = pd.Series([small[: int(n)] for n in rng.poisson(mean, rows)], dtype=object)
    return pd.DataFrame(cols)


def prepare(cache: Path, shape: str, rows: int) -> dict[str, str]:
    """Write the inputs of one (shape, size) once; returns the paths (CSV files only for CSV shapes)."""
    d = cache / f"v2_{shape}_{rows}"
    paths = {"df": d / "df.pkl", "df2": d / "df2.pkl", "right": d / "right.pkl",
             "P1": d / "p1.csv", "P2": d / "p2.csv", "T1": d / "t1.tsv"}  # fmt: skip
    if not (d / "DONE").exists():
        d.mkdir(parents=True, exist_ok=True)
        df, df2 = make_frame_v2(shape, rows, SEEDS[0]), make_frame_v2(shape, rows, SEEDS[1])
        df.to_pickle(paths["df"])
        df2.to_pickle(paths["df2"])
        right = pd.DataFrame(
            {"k": np.arange(KEYS), "w": np.random.default_rng(SEEDS[2]).random(KEYS)}
        )
        right.to_pickle(paths["right"])
        if shape in CSV_SHAPES:
            df.to_csv(paths["P1"], index=False, na_rep="NA")
            df2.to_csv(paths["P2"], index=False, na_rep="NA")
            df.to_csv(paths["T1"], index=False, sep=TAB, na_rep="NA")
        del df, df2
        gc.collect()
        (d / "DONE").write_text("ok")
    return {k: str(v) for k, v in paths.items()}


def source(cell: Cell, paths: dict[str, str]) -> str:
    src, _ = TEMPLATES[cell.config.template]
    return src.format(P1=repr(paths["P1"]), P2=repr(paths["P2"]), T1=repr(paths["T1"]), TAB=repr(TAB),
                      HALF=cell.rows // 2)  # fmt: skip
