"""Realistic multi-statement notebook cells for measuring how much of real code the Tier 2 safety
analyzer accepts (Phase 4d). The analyzer is NOT loosened in this phase; this is the baseline.

Each entry: (name, category, source). Names used by the cells (see ``make_namespace``): frames ``df``,
``orders``, ``customers``, ``left``, ``right``, ``parts`` (a list), ``a``/``b`` arrays, ``keys`` (a list),
``col`` (a str), ``path`` (a str), plus ``pd`` / ``np``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CELLS: list[tuple[str, str, str]] = [
    # -- controls: the single supported operation -----------------------------------------------------
    ("control merge", "control", 'left.merge(right, on="k")'),
    ("control groupby", "control", 'df.groupby("s")["f"].sum()'),
    ("control sort", "control", 'df.sort_values("f")'),
    ("control astype", "control", 'df["s"].astype("category")'),
    ("control matmul", "control", "a @ b"),
    # -- variables as arguments -------------------------------------------------------------------------------
    ("keys variable in groupby", "variable argument", 'df.groupby(keys)["f"].sum()'),
    ("on= variable in merge", "variable argument", "left.merge(right, on=keys)"),
    ("column variable in sort", "variable argument", "df.sort_values(col)"),
    ("target dtype variable", "variable argument", 'df["s"].astype(target)'),
    ("keys defined in the cell", "variable argument", 'keys = ["s"]\ndf.groupby(keys)["f"].sum()'),
    ("subset variable", "variable argument", "df.drop_duplicates(subset=keys)"),
    ("frames list variable in concat", "variable argument", "pd.concat(parts, ignore_index=True)"),
    ("path variable in read_csv", "variable argument", "pd.read_csv(path)"),
    # -- intermediate assignments ---------------------------------------------------------------------------
    (
        "merge then groupby",
        "intermediate",
        'm = left.merge(right, on="k")\nr = m.groupby("s")["f"].sum()',
    ),
    (
        "sort then dedup",
        "intermediate",
        'x = df.sort_values("f")\nx = x.drop_duplicates(subset=["i"])',
    ),
    (
        "clean then merge",
        "intermediate",
        'clean = df.drop_duplicates()\nout = clean.merge(right, on="k")',
    ),
    (
        "several results",
        "intermediate",
        'a1 = df.groupby("s")["f"].sum()\na2 = df.groupby("i")["f"].mean()',
    ),
    ("copy then sort", "intermediate", 'tmp = df.copy()\ntmp.sort_values("f")'),
    ("alias then op", "intermediate", 'd2 = df\nd2.sort_values("f")'),
    ("result printed", "intermediate", 'r = df.groupby("s")["f"].sum()\nprint(r.head())'),
    # -- method chains ----------------------------------------------------------------------------------------
    ("sort then head", "method chain", 'df.sort_values("f").head(10)'),
    (
        "merge then groupby chain",
        "method chain",
        'left.merge(right, on="k").groupby("s")["f"].sum()',
    ),
    (
        "sort drop_duplicates chain",
        "method chain",
        'df.sort_values("f").drop_duplicates(subset=["i"])',
    ),
    ("groupby reset_index", "method chain", 'df.groupby("s")["f"].sum().reset_index()'),
    ("groupby agg dict", "method chain", 'df.groupby("s").agg({"f": "sum", "g": "mean"})'),
    ("groupby named agg", "method chain", 'df.groupby("s").agg(total=("f", "sum"))'),
    ("astype chain", "method chain", 'df["s"].astype("category").cat.codes'),
    ("merge then sort", "method chain", 'left.merge(right, on="k").sort_values("f")'),
    ("assign then groupby", "method chain", 'df.assign(h=df.f * 2).groupby("s")["h"].sum()'),
    # -- filters and expressions --------------------------------------------------------------------------------
    ("filter then groupby", "filter / expression", 'df[df.f > 0.5].groupby("s")["g"].sum()'),
    ("query then sort", "filter / expression", 'df.query("f > 0.5").sort_values("g")'),
    ("loc then merge", "filter / expression", 'df.loc[df.i > 3].merge(right, on="k")'),
    ("column arithmetic", "filter / expression", 'df["h"] = df["f"] * df["g"]'),
    ("dropna then dedup", "filter / expression", "df.dropna().drop_duplicates()"),
    (
        "rename then merge",
        "filter / expression",
        'df.rename(columns={"f": "x"}).merge(right, on="k")',
    ),
    # -- several operations / pipelines ---------------------------------------------------------------------------
    ("read then groupby", "pipeline", 'data = pd.read_csv("x.csv")\ndata.groupby("s")["f"].sum()'),
    (
        "merge, filter, groupby",
        "pipeline",
        'm = left.merge(right, on="k")\nm = m[m.f > 0]\nm.groupby("s")["f"].sum()',
    ),
    ("two independent ops", "pipeline", 'df.sort_values("f")\ndf.drop_duplicates()'),
    (
        "concat then dedup",
        "pipeline",
        "all_ = pd.concat([df, left])\nall_ = all_.drop_duplicates()",
    ),
    ("matmul then sum", "pipeline", "c = a @ b\nc.sum()"),
    # -- imports, display, control flow, functions ------------------------------------------------------------------
    ("import then op", "imports / display", 'import pandas as pd\ndf.sort_values("f")'),
    ("time then op", "imports / display", '%time df.sort_values("f")'),
    ("plot after groupby", "imports / display", 'r = df.groupby("s")["f"].sum()\nr.plot.bar()'),
    (
        "for loop over keys",
        "control flow / functions",
        'for k in keys:\n    df.groupby(k)["f"].sum()',
    ),
    (
        "list comprehension",
        "control flow / functions",
        'res = [df.groupby(k)["f"].sum() for k in keys]',
    ),
    (
        "function definition",
        "control flow / functions",
        'def agg(d):\n    return d.groupby("s")["f"].sum()\nagg(df)',
    ),
    ("if branch", "control flow / functions", 'if len(df) > 10:\n    df.sort_values("f")'),
    (
        "with timer",
        "control flow / functions",
        'with open("log.txt", "w") as fh:\n    df.sort_values("f")',
    ),
    # -- in-place / mutation ------------------------------------------------------------------------------------------
    ("inplace sort", "mutation", 'df.sort_values("f", inplace=True)'),
    ("assign column then sort", "mutation", 'df["z"] = df["f"] + 1\ndf.sort_values("z")'),
    ("drop columns inplace", "mutation", 'df.drop(columns=["g"], inplace=True)'),
]


def make_namespace(path: str = "") -> dict:
    rng = np.random.default_rng(0)
    n = 60
    df = pd.DataFrame({"k": np.arange(n), "s": [f"v{i % 7}" for i in range(n)], "f": rng.random(n),
                       "g": rng.random(n), "i": rng.integers(0, 9, n)})  # fmt: skip
    right = pd.DataFrame({"k": np.arange(0, n, 2), "c": rng.random(n // 2)})
    return {
        "pd": pd, "np": np, "df": df, "left": df, "right": right, "orders": df, "customers": right,
        "parts": [df, df.copy()], "a": rng.random((6, 6)), "b": rng.random((6, 6)),
        "keys": ["s"], "col": "f", "path": path, "target": "category",
    }  # fmt: skip
