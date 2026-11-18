"""Tier 2 safety: which cells may be dry-run. Unknown means unsafe."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.dryrun_safety import analyze_safety


class MyFrame(pd.DataFrame):
    def merge(self, *a, **k):  # a subclass could do anything
        raise RuntimeError("side effect")


class Thing:
    pass


@pytest.fixture
def ns(tmp_path):
    rng = np.random.default_rng(0)
    n = 50
    df = pd.DataFrame({"k": np.arange(n), "j": np.arange(n) % 5, "s": [f"v{i % 7}" for i in range(n)],
                       "f": rng.random(n), "g": rng.random(n), "i": rng.integers(0, 9, n)})  # fmt: skip
    df["c"] = pd.Categorical(df["s"])
    csv = tmp_path / "data.csv"
    df.to_csv(csv, index=False)
    return {
        "pd": pd, "np": np, "df": df, "df2": df.copy(), "left": df, "right": df.copy(), "alias": df,
        "a": rng.random((6, 6)), "b": rng.random((6, 6)), "v": rng.random(10),
        "csv": str(csv).replace("\\", "/"), "mf": MyFrame(df), "obj": pd.DataFrame({"x": [Thing(), Thing()]}),
        "mi": pd.DataFrame(np.zeros((2, 2)), columns=pd.MultiIndex.from_tuples([("a", 1), ("a", 2)])),
        "dup": pd.DataFrame([[1, 2]], columns=["x", "x"]), "num": pd.DataFrame({1: [1, 2]}),
        "mm": np.memmap if False else None,
    }  # fmt: skip


SAFE = [
    'left.merge(right, on="k")',
    'm = left.merge(right, on="k", how="left")',
    'left.merge(right, on=["k", "j"], how="outer", suffixes=("_l", "_r"))',
    'pd.merge(left, right, on="k", how="inner", sort=True)',
    'df.groupby("s")["f"].sum()',
    'df.groupby(["i", "s"])[["f", "g"]].mean()',
    'r = df.groupby("s", sort=False).size()',
    'df.groupby("c", observed=True)["f"].max()',
    'df.sort_values("f")',
    'df.sort_values(["f", "i"], ascending=False, na_position="first")',
    'df.sort_values(by="f", ignore_index=True)',
    "df.drop_duplicates()",
    'df.drop_duplicates(subset=["i", "j"], keep="last")',
    'df.drop_duplicates("i")',
    'df["s"].astype("category")',
    'df["f"].astype(str)',
    'x = df["i"].astype("int32")',
    'df["i"].astype(float)',
    "pd.concat([df, df2], ignore_index=True)",
    "pd.concat([df, df2, left])",
    "np.sort(v)",
    'np.sort(v, kind="stable")',
    "a @ b",
    "np.matmul(a, b)",
    "np.dot(a, b)",
    "%time df.sort_values('f')",
    "%%time\ndf.sort_values('f')",
    "%timeit df.drop_duplicates()",
    "out: object = df.sort_values('f')",
    "alias.sort_values('f')",  # aliasing: only reads
    "left.merge(left, on='k')",  # same object on both sides
]
UNSAFE = [
    # in-place and mutation
    'df.sort_values("f", inplace=True)',
    "df.drop_duplicates(inplace=True)",
    'df["x"] = df["f"].astype(str)',
    "df.x = 1",
    "df.loc[0, 'f'] = 1.0",
    "df += 1",
    "a, b2 = df, df2",
    "del df",
    "global df",
    "a.sort()",
    "np.random.shuffle(v)",
    # aliasing / several statements
    'a2 = df; a2.sort_values("f", inplace=True)',
    'df.sort_values("f"); df.drop_duplicates()',
    'x = 1\ndf.sort_values("f")',
    # imports / calls / evaluation
    'import os\ndf.sort_values("f")',
    '__import__("os").system("echo hi")',
    "eval(\"df.sort_values('f')\")",
    "exec(\"df.sort_values('f')\")",
    "print(df)",
    "open('x.txt', 'w').write('hi')",
    'df.to_csv("out.csv")',
    "df.sample(5)",
    "df.sample(frac=0.1)",
    "np.random.rand(3)",
    "df.fillna(0)",
    "df.apply(len)",
    # lambdas, walrus, comprehensions, control flow
    'df.sort_values("f", key=lambda s: s)',
    'df.groupby("s").agg(lambda x: 1)',
    '(m := left.merge(right, on="k"))',
    "[df.sort_values('f') for _ in range(2)]",
    "for _ in range(2):\n    df.sort_values('f')",
    "if True:\n    df.sort_values('f')",
    "with open('x') as fh:\n    df.sort_values('f')",
    "def g():\n    return df.sort_values('f')",
    # chains and unsupported shapes
    'df.sort_values("f").drop_duplicates()',
    'left.merge(right, on="k").groupby("s")["f"].sum()',
    'df.groupby("s")',
    'df.groupby("s").agg("sum")',
    'df.groupby("s")["f"].apply(sum)',
    'df.sort_values("f").head()',
    # unknown keywords and unsupported options
    'left.merge(right, on="k", copy=False)',
    'left.merge(right, on="k", indicator=True)',
    'left.merge(right, left_on="k", right_on="k")',
    'left.merge(right, how="cross")',
    'left.merge(right, on="nope")',
    "pd.concat([df, df2], axis=1)",
    "pd.concat([df])",
    "pd.concat(frames)",
    'df.sort_values("nope")',
    'df.astype({"f": "int"})',
    'df["f"].astype(lambda v: v)',
    'df["f"].astype("not-a-dtype")',
    'df[["f"]].astype(str)',
    "np.sort(v, order='x')",
    "a @ v",
    "a @ b.T",
    # files and network
    'pd.read_csv("http://example.com/x.csv")',
    'pd.read_csv("s3://bucket/x.csv")',
    'pd.read_csv("does-not-exist.csv")',
    "pd.read_csv(path)",
    # environment identity
    "ghost.merge(right, on='k')",
    "mf.merge(right, on='k')",
    "obj.sort_values('x')",
    "mi.sort_values(('a', 1))",
    "dup.drop_duplicates()",
    "num.sort_values(1)",
    # magics and shell
    "!rm -rf /",
    "%matplotlib inline",
    "%%bash\necho hi",
    # not python / empty / huge
    "df.merge(",
    "",
    "x" * 30_000,
]


@pytest.mark.parametrize("source", SAFE)
def test_safe_cells_are_accepted_with_a_recipe(source, ns):
    verdict = analyze_safety(source, ns)
    assert verdict.safe, verdict.reasons
    assert verdict.recipe is not None and verdict.recipe.kind


@pytest.mark.parametrize("source", UNSAFE)
def test_everything_else_is_rejected_with_a_reason(source, ns):
    verdict = analyze_safety(source, ns)
    assert not verdict.safe and verdict.reasons and verdict.recipe is None


def test_the_snippet_table_is_large_enough():
    assert len(SAFE) >= 25 and len(UNSAFE) >= 60  # the specification asks for at least 40 in all


def test_read_csv_of_a_local_literal_file_is_safe(ns):
    assert analyze_safety(f'pd.read_csv("{ns["csv"]}")', ns).safe
    assert analyze_safety(f'pd.read_csv("{ns["csv"]}", usecols=["k", "f"], sep=",")', ns).safe
    assert not analyze_safety(
        f'pd.read_csv("{ns["csv"]}", nrows=5)', ns
    ).safe  # keyword outside the allowlist


def test_a_shadowed_module_name_is_not_trusted(ns):
    class FakePandas:
        @staticmethod
        def merge(*a, **k):
            raise RuntimeError("side effect")

    assert not analyze_safety('pd.merge(left, right, on="k")', {**ns, "pd": FakePandas()}).safe
    assert not analyze_safety("np.sort(v)", {**ns, "np": FakePandas()}).safe


def test_a_shadowed_builtin_in_astype_is_not_trusted(ns):
    assert analyze_safety('df["f"].astype(str)', ns).safe
    assert not analyze_safety('df["f"].astype(str)', {**ns, "str": lambda x: "boom"}).safe


def test_recipes_are_data_with_the_literal_arguments(ns):
    r = analyze_safety('out = left.merge(right, on=["k", "j"], how="left")', ns).recipe
    assert (r.kind, r.operands, r.target) == ("merge", ("left", "right"), "out")
    assert r.kwargs == {"on": ["k", "j"], "how": "left"}
    g = analyze_safety('df.groupby(["i", "s"])[["f", "g"]].mean()', ns).recipe
    assert g.kind == "groupby_agg" and g.extra == {
        "by": ["i", "s"],
        "cols": ["f", "g"],
        "agg": "mean",
    }
    import json

    json.dumps(g.to_json())  # JSON-serialisable: the child never sees source text


def test_a_cell_is_never_executed_while_it_is_analysed(ns):
    before = ns["df"].copy(deep=True)
    for source in (
        'df.sort_values("f", inplace=True)',
        "del df",
        "df.drop_duplicates(inplace=True)",
    ):
        analyze_safety(source, ns)
    pd.testing.assert_frame_equal(ns["df"], before)
    assert "df" in ns
