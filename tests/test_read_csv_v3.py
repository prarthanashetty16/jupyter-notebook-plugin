"""Phase 7b read_csv: reader-path terms, the unknown-path range, the worker count and the argument rules."""

from __future__ import annotations

import pandas as pd
import pytest

from nexus.models import read_csv as rc
from nexus.pipeline import Pipeline

MIB = 2**20


def _features(path: str, **over):
    f = {"file_bytes": 300 * MIB, "n_rows": 2e6, "rows_range": (2e6, 2e6, 2e6), "n_cols": 8,
         "total_cols": 8, "text_cols": 0, "str_chars": 0.0, "unique_fraction": 0.0,
         "unique_range": (0.0, 0.0, 0.0), "bytes_per_field": 18.5, "value_bytes_per_row": 64.0,
         "reader_path": path, "workers": 6}  # fmt: skip
    f.update(over)
    return f


def test_parallel_numeric_is_file_plus_two_value_copies():
    lo, exp, hi = rc.ReadCsvModel.tier1_ram(_features("parallel"))
    v = 2e6 * 64
    assert exp == pytest.approx(300 * MIB + 2 * v)
    assert lo < exp < hi


def test_series_wrap_and_serial_terms():
    v = 2e6 * 64
    _, wrap, _ = rc.ReadCsvModel.tier1_ram(_features("parallel_wrap"))
    assert wrap == pytest.approx(300 * MIB + v + rc.worker_buffer_bytes(6, 18.5))
    lo, _, hi = rc.ReadCsvModel.tier1_ram(_features("serial"))
    assert lo == pytest.approx(v)  # the result itself
    assert hi >= v + rc.serial_chunk_bytes(8, 18.5, 2e6)


def test_unknown_path_spans_both_readers():
    lo_u, exp_u, hi_u = rc.ReadCsvModel.tier1_ram(_features("unknown"))
    lo_s, _, _ = rc.ReadCsvModel.tier1_ram(_features("serial"))
    _, exp_p, hi_p = rc.ReadCsvModel.tier1_ram(_features("parallel"))
    assert (lo_u, exp_u, hi_u) == (min(lo_s, lo_u), exp_p, hi_p)


def test_text_files_keep_the_v2_formula_on_the_parallel_path():
    f = _features(
        "parallel", text_cols=2, str_chars=8.0, unique_fraction=0.1, unique_range=(0.1, 0.1, 0.1)
    )
    _, exp, _ = rc.ReadCsvModel.tier1_ram(f)
    assert exp == pytest.approx(rc.parse_peak_bytes(300 * MIB, 2e6, 8, text_cols=2, str_chars=8.0,
                                                    unique_fraction=0.1))  # fmt: skip


def test_reader_path_rules(monkeypatch):
    monkeypatch.setattr(rc, "parallel_workers", lambda: 6)
    big = 50 * MIB
    assert rc.reader_path("x.csv", big, {}) == ("parallel", 6)
    assert rc.reader_path("x.csv", big, {"dtype": {"a": "float32"}})[0] == "parallel_wrap"
    assert rc.reader_path("x.csv", big, {"dtype": "float32"})[0] == "parallel"
    assert rc.reader_path("x.csv", big, {"usecols": ["a"]})[0] == "serial"
    assert rc.reader_path("x.csv", big, {"nrows": 5})[0] == "serial"
    assert rc.reader_path("x.csv", 4 * MIB, {})[0] == "serial"
    assert rc.reader_path("x.csv.gz", big, {})[0] == "serial"
    monkeypatch.setattr(rc, "parallel_workers", lambda: 1)
    assert rc.reader_path("x.csv", big, {})[0] == "serial"
    monkeypatch.setattr(rc, "parallel_workers", lambda: None)
    assert rc.reader_path("x.csv", big, {})[0] == "unknown"


def test_worker_count_is_pandas_own(monkeypatch):
    from pandas.io.parsers import readers

    with pd.option_context("mode.max_threads", 3):
        assert rc.parallel_workers() == readers._default_n_workers() == 3


def test_subset_reads_have_a_zero_tier0_low(tmp_path):
    p = tmp_path / "x.csv"
    pd.DataFrame({"a": range(10_000), "b": range(10_000)}).to_csv(p, index=False)
    rep = Pipeline(tier=0).run(f"pd.read_csv({str(p)!r}, nrows=10)", {"pd": pd})
    assert rep.estimates[0].estimate.ram_low == 0
    rep = Pipeline(tier=0).run(f"pd.read_csv({str(p)!r})", {"pd": pd})
    assert rep.estimates[0].estimate.ram_low > 0
