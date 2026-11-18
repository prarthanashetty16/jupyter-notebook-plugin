"""Suggestion rules: refusal battery (liveness), positive battery, labels, filters (Phase 5 S5)."""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd
import pytest

from nexus.analyzer import analyze_cell
from nexus.failsafe import Deadline
from nexus.state import StateInspector
from nexus.suggestions import suggest
from nexus.suggestions.base import Context
from nexus.suggestions.engine import _in_tree
from nexus.suggestions.rules.dtypes import CategoryRule, DowncastRule, KeyDtypeRule
from nexus.suggestions.rules.select_columns import SelectColumnsRule
from nexus.suggestions.rules.variables import CopyAvoidRule


def _ns(n=2000):
    rng = np.random.default_rng(1)
    left = pd.DataFrame(
        {"k": rng.integers(0, 50, n), "a": rng.random(n), "b": rng.random(n),
         "c": rng.integers(0, 100, n), "s": rng.choice(["x", "y", "z"], n)}
    )  # fmt: skip
    right = pd.DataFrame({"k": np.arange(50), "w": rng.random(50), "z": rng.random(50)})
    return {
        "left": left,
        "right": right,
        "pd": pd,
        "np": np,
        "cols": ["a"],
        "keys": ["k"],
        "f": print,
    }


def propose(rule, src, ns=None, op_name=None):
    ns = ns if ns is not None else _ns()
    ops = analyze_cell(src, ns)
    tree = ast.parse(src)
    ops = [m for m in (_in_tree(tree, o) for o in ops) if m]
    op = next((o for o in ops if op_name is None or o.name == op_name), None)
    if op is None:
        return None
    state = StateInspector().inspect([v for o in ops for v in o.variables], ns)
    ctx = Context(source=src, tree=tree, op=op, inspection=state, namespace=ns,
                  deadline=Deadline(10), all_ops=ops)  # fmt: skip
    return rule.propose(ctx)


def value_of(src, ns):
    """Run a cell on a copy of the namespace and return the value of its last statement."""
    env = dict(ns)
    tree = ast.parse(src)
    *body, last = tree.body
    exec(compile(ast.Module(body, []), "c", "exec"), env)  # noqa: S102
    node = last.value if isinstance(last, ast.Expr | ast.Assign) else None
    return eval(compile(ast.Expression(node), "c", "eval"), env)  # noqa: S307


SELECT = SelectColumnsRule()

REFUSED = [  # every one must be refused: the unused-column claim cannot be proven
    'left.groupby("k").sum()',  # whole-frame aggregation
    'left.groupby("k")[["a", "zzz"]].sum()',  # unknown column
    'left.groupby("k")[cols].sum()',  # non-literal selection
    'g = left.groupby("k")\ng["a"].sum()',  # not consumed by a literal selection
    'left.groupby("k").agg({"a": "sum"})',
    'left.groupby("k").a.sum()',  # attribute access
    'left.groupby(keys)["a"].sum()',  # non-literal key
    'm = left.merge(right, on="k")\nm',  # result used as a whole
    'm = left.merge(right, on="k")\nprint(m)',
    'm = left.merge(right, on="k")\nm.a.sum()',
    'm = left.merge(right, on="k")\nm[cols]',
    'm = left.merge(right, on="k")\nm["new"] = 1\nm["a"].sum()',  # assigned column
    'm = left.merge(right, on="k")\nm = m.head()\nm["a"].sum()',  # rebound
    'm = left.merge(right, on="k")\nn = m\nn["a"].sum()',  # alias
    'm = left.merge(right, on="k")\nlocals()["m"]["a"]',  # dynamic
    'm = left.merge(right, on="k")\neval("m[0]")',
    'm = left.merge(right, on="k")\nm.eval("a + b")',
    'm = left.merge(right, on="k")\nf(**{"m": m})',
    'm = left.merge(right, on="k")\ndel m',
    'm = left.merge(right, on="k")\n[m[c] for c in cols]',
    'm = left.merge(right, on="k")\nm.loc[:, "a"]',
    'm = left.merge(right, on="k")\nm[["a"]].join(m)',
    'left.merge(right, on="k")',  # displayed whole
    'left.merge(right, left_on="k", right_on="k")["a"]',
    'left.merge(right, on="k", suffixes=("_l", "_r"))["a"]',
    'left.merge(right, on="k", indicator=True)["_merge"]',
    'left.merge(right, on="k")[0:5]',  # slice, not a column
    'm = left.merge(right, on="k")\nglobals()',
    'from numpy import *\nm = left.merge(right, on="k")\nm["a"]',
    'm = left.merge(right, on="k")\nm["a"], m',
]
ACCEPTED = [  # (source, expected semantics)
    ('left.groupby("k")["a"].sum()', "preserving"),
    ('left.groupby("k")["a"].mean()', "preserving"),
    ('x = left.groupby("k")["a"].sum()', "preserving"),
    ('left.groupby("k")[["a", "b"]].sum()', "preserving"),
    ('left.groupby(["k", "c"])["a"].sum()', "preserving"),
    ('left.groupby(by="k")["a"].max()', "preserving"),
    ('left.merge(right, on="k")["a"]', "preserving"),
    ('left.merge(right, on="k")["w"]', "preserving"),
    ('left.merge(right, on="k")[["a", "w"]]', "preserving"),
    ('left.merge(right, how="left", on="k")["a"]', "preserving"),
    ('m = left.merge(right, on="k")\nm["a"].sum()', "changes_results"),
    ('m = left.merge(right, on="k")\nm["a"].sum()\nm["w"].sum()', "changes_results"),
    ('m = left.merge(right, on="k")\nx = m["a"] + m["w"]', "changes_results"),
    ('# note\nm = left.merge(right, on="k")  # join\nm["a"].sum()', "changes_results"),
    ('m = pd.merge(left, right, on="k")\nm["a"].sum()', "changes_results"),
]


def test_batteries_are_large_enough():
    assert len(REFUSED) >= 25 and len(ACCEPTED) >= 15


@pytest.mark.parametrize("src", REFUSED)
def test_select_columns_refuses_what_it_cannot_prove(src):
    ns = _ns()
    try:
        names = [o.name for o in analyze_cell(src, ns)]
    except Exception:
        names = []
    for name in ("groupby", "merge", "pandas.merge"):
        if name in names:
            assert propose(SELECT, src, ns, name) is None, src


@pytest.mark.parametrize("src,label", ACCEPTED)
def test_select_columns_accepts_provable_cells_with_the_right_label(src, label):
    s = propose(SELECT, src)
    assert s is not None and s.semantics == label, src
    ast.parse(s.modified_source)
    assert s.modified_source != src


def test_select_columns_preserving_results_are_really_equal():
    ns = _ns()
    checked = 0
    for src, _ in ACCEPTED:
        s = propose(SELECT, src, ns)
        if s.semantics != "preserving":
            continue
        a, b = value_of(src, ns), value_of(s.modified_source, ns)
        if isinstance(a, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b)
        else:
            pd.testing.assert_series_equal(a, b)
        checked += 1
    assert checked >= 8


def test_downcast_labels_and_proves_integer_range():
    s = propose(DowncastRule(), 'left.groupby("k")["a"].sum()')
    assert s.semantics == "changes_precision" and "'c': 'int8'" in s.modified_source
    ns = _ns()
    ns["left"]["c"] = np.arange(len(ns["left"])) * 10_000_000  # exceeds int32: not narrowed
    s = propose(DowncastRule(), 'left.groupby("k")["a"].sum()', ns)
    assert "'c'" not in s.modified_source


def test_downcast_int_only_frame_is_changes_dtype_never_preserving():
    ns = {"left": pd.DataFrame({"k": np.arange(100), "c": np.arange(100) % 7})}
    s = propose(DowncastRule(), 'left.sort_values("k")', ns)
    assert s is not None and s.semantics == "changes_dtype"


def test_category_rule_skips_keys_and_high_cardinality():
    s = propose(CategoryRule(), 'left.groupby("k")["a"].sum()')
    assert s.semantics == "changes_dtype" and "'s': 'category'" in s.modified_source
    ns = _ns()
    ns["left"]["s"] = [str(i) for i in range(len(ns["left"]))]
    assert propose(CategoryRule(), 'left.groupby("k")["a"].sum()', ns) is None


def test_key_dtype_rule_uses_one_dtype_for_both_merge_sides():
    s = propose(KeyDtypeRule(), 'left.merge(right, on="k")["a"]')
    assert s is not None and s.modified_source.count("'k': 'int8'") == 2


def test_copy_avoid_only_for_temporaries_with_fresh_results():
    r = CopyAvoidRule()
    s = propose(r, 'x = left.copy().sort_values("a")')
    assert s.semantics == "preserving" and s.modified_source == 'x = left.sort_values("a")'
    assert propose(r, "y = left.copy()") is None  # a bound copy may be mutated later
    assert propose(r, "left.copy().head()") is None  # head returns a view-like result
    assert propose(r, 'left.copy().sort_values("a", inplace=True)') is None
    assert propose(r, "left.copy(deep=False).sum()") is None


def test_engine_never_shows_a_suggestion_below_the_saving_threshold():
    ns = _ns()  # tiny frames: every saving is far below 64 MiB
    src = 'left.merge(right, on="k")["a"]'
    state = StateInspector().inspect(["left", "right"], ns)
    assert suggest(src, ns, state, analyze_cell(src, ns)) == []


def test_magic_cells_are_not_rewritten():
    ns = _ns()
    src = '%time left.merge(right, on="k")["a"]'
    state = StateInspector().inspect(["left", "right"], ns)
    assert suggest(src, ns, state, analyze_cell(src, ns)) == []


def test_patch_keeps_comments_and_non_ascii():
    src = '# é comment\nm = left.merge(right, on="k")  # keep\nm["a"].sum()'
    s = propose(SELECT, src)
    assert "# é comment" in s.modified_source and "# keep" in s.modified_source
