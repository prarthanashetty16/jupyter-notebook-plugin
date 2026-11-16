"""Analyzer tests: representative snippets, magics, malformed and huge input."""

from __future__ import annotations

import pytest

from nexus.analyzer import MAX_OPS, MAX_SOURCE_CHARS, Expr, analyze_cell, strip_magics
from nexus.failsafe import Deadline

PD = "import pandas as pd\n"
NP = "import numpy as np\n"

CASES = [
    ("method_no_import", "df.drop_duplicates()", ["drop_duplicates"]),
    ("read_csv_alias", PD + 'df = pd.read_csv("x.csv")', ["pandas.read_csv"]),
    ("from_import", 'from pandas import read_csv\nread_csv("x.csv")', ["pandas.read_csv"]),
    ("from_import_as", 'from pandas import read_csv as rc\nrc("x")', ["pandas.read_csv"]),
    ("pd_merge", PD + 'pd.merge(a, b, on="k", how="left")', ["pandas.merge"]),
    ("df_merge", 'df.merge(o, on="k", how="inner")', ["merge"]),
    ("pd_concat", PD + "pd.concat([a, b])", ["pandas.concat"]),
    ("np_zeros", NP + "np.zeros((10, 10))", ["numpy.zeros"]),
    ("np_linalg", NP + "np.linalg.inv(m)", ["numpy.linalg.inv"]),
    ("from_numpy_submodule", "from numpy import linalg\nlinalg.inv(m)", ["numpy.linalg.inv"]),
    ("import_submodule_as", "import numpy.linalg as la\nla.inv(m)", ["numpy.linalg.inv"]),
    ("matmul_operator", "c = a @ b", ["operator.matmul"]),
    ("chain_order", 'df.groupby("a").apply(f)', ["groupby", "apply"]),
    (
        "chain_from_function",
        PD + 'pd.read_csv("f").drop_duplicates()',
        ["pandas.read_csv", "drop_duplicates"],
    ),
    ("var_alias", "df2 = df\ndf2.drop_duplicates()", ["drop_duplicates"]),
    ("plain_python", "x = 1 + 2", []),
    ("print_only", 'print("hello")', []),
    ("empty", "", []),
    ("whitespace", "  \n\n\t\n", []),
    ("comment_only", "# df.drop_duplicates()", []),
    ("syntax_error", "df.drop_duplicates(", []),
    ("bad_indent", "if x:\ny = 1", []),
    ("line_magic", "%matplotlib inline\ndf.drop_duplicates()", ["drop_duplicates"]),
    ("shell_line", '!pip install foo\ndf.sort_values("a")', ["sort_values"]),
    ("shell_in_block", 'if x:\n    !ls\n    df.sort_values("a")', ["sort_values"]),
    ("cell_magic_time", '%%time\ndf.merge(b, on="k")', ["merge"]),
    ("cell_magic_unknown", "%%bash\ndf.merge(b)", []),
    ("line_magic_time", "%time df.drop_duplicates()", ["drop_duplicates"]),
    ("timeit_options", '%timeit -n 1 -r 1 df.sort_values("a")', ["sort_values"]),
    ("magic_assignment", "files = !ls\ndf.drop_duplicates()", ["drop_duplicates"]),
    ("help_line", "df.drop_duplicates?\ndf.sort_values('a')", ["sort_values"]),
    ("unknown_pandas_call", PD + 'pd.DataFrame({"a": [1]})', []),
    ("unresolved_module", "np.zeros(3)", []),
    ("shadowed_module", "np = 5\nnp.zeros(3)", []),
    ("null_byte", "df.drop_duplicates()\x00", []),
    ("deep_nesting", "(" * 10_000 + ")" * 10_000, []),
    ("continuation_not_magic", "x = (a\n     % b)\ndf.sort_values('a')", ["sort_values"]),
    ("continuation_not_bang", "ok = (a\n      != b)\ndf.sort_values('a')", ["sort_values"]),
]


@pytest.mark.parametrize(("source", "expected"), [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_detected_names(source, expected):
    assert [op.name for op in analyze_cell(source)] == expected


def test_case_count():
    assert len(CASES) >= 25


def test_kwargs_literals_and_expressions():
    (op,) = analyze_cell('df.drop_duplicates(subset=["a", "b"], keep="last")')
    assert op.kwargs == {"subset": ["a", "b"], "keep": "last"}
    (op,) = analyze_cell("df.merge(o, on=col, how='left')")
    assert op.kwargs["on"] == "col" and isinstance(op.kwargs["on"], Expr)
    assert op.kwargs["how"] == "left" and not isinstance(op.kwargs["how"], Expr)


def test_positional_args_and_receiver():
    (op,) = analyze_cell('df.drop_duplicates(["a"])')
    assert op.args == (["a"],)
    assert op.receiver == "df"
    assert op.variables == ("df",)


def test_variable_alias_resolved_to_root():
    (op,) = analyze_cell("df2 = df\ndf2.drop_duplicates()")
    assert op.variables == ("df",) and op.receiver == "df"


def test_alias_follows_and_drops_on_rebinding():
    (op,) = analyze_cell("df2 = df\ndf2 = other\ndf2.drop_duplicates()")
    assert op.variables == ("other",)
    (op,) = analyze_cell("df2 = df\ndf2 = make()\ndf2.drop_duplicates()")
    assert op.variables == ("df2",)


def test_module_alias_names_are_not_variables():
    (op,) = analyze_cell(PD + 'pd.merge(a, b, on="k")')
    assert op.variables == ("a", "b") and op.receiver is None


def test_lambda_params_are_not_variables():
    (op,) = analyze_cell("df.apply(lambda r: r + k, axis=1)")
    assert op.variables == ("df", "k")


def test_nested_op_variables():
    ops = analyze_cell("df.merge(o.drop_duplicates(), on='k')")
    assert [op.name for op in ops] == ["drop_duplicates", "merge"]
    assert ops[1].variables == ("df", "o")


def test_lineno():
    ops = analyze_cell("x = 1\n\ndf.sort_values('a')")
    assert ops[0].lineno == 3


def test_namespace_resolves_modules_from_earlier_cells():
    import numpy
    import pandas

    ns = {"pd": pandas, "np": numpy}
    assert [o.name for o in analyze_cell('pd.read_csv("x")', ns)] == ["pandas.read_csv"]
    assert [o.name for o in analyze_cell("np.zeros(3)", ns)] == ["numpy.zeros"]


def test_namespace_resolves_known_function():
    from pandas import read_csv

    assert [o.name for o in analyze_cell('rc("x")', {"rc": read_csv})] == ["pandas.read_csv"]


def test_namespace_dataframe_is_not_a_symbol():
    import pandas

    ns = {"df": pandas.DataFrame({"a": [1]})}
    (op,) = analyze_cell("df.drop_duplicates()", ns)
    assert op.variables == ("df",)


def test_huge_cell_over_cap_is_ignored():
    assert analyze_cell("df.drop_duplicates()\n" * (MAX_SOURCE_CHARS // 10)) == []


def test_many_ops_are_capped():
    source = "df.drop_duplicates()\n" * 5000
    assert len(source) < MAX_SOURCE_CHARS
    assert len(analyze_cell(source)) == MAX_OPS


def test_non_string_source():
    assert analyze_cell(None) == []  # type: ignore[arg-type]


def test_expired_deadline_raises():
    with pytest.raises(TimeoutError):
        analyze_cell("df.drop_duplicates()", deadline=Deadline(0.0))


def test_strip_magics_output():
    assert strip_magics("%%capture out\nx = 1").strip() == "x = 1"
    assert strip_magics("%%sql\nselect 1") == ""
    assert strip_magics("  \n") == ""
    assert strip_magics("if x:\n    %matplotlib inline") == "if x:\n    pass"
