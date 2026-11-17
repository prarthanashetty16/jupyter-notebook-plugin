"""Phase 4a: structural Tier 0 fixes (sort_values, merge, read_csv, astype, concat, drop_duplicates).

The expected numbers are the derivations in the model docstrings, checked against isolated
allocation probes when they were written; these tests pin the formulas and the properties that
matter (pointer copies ignore string payload, merge takes M as an input, read_csv never
under-predicts a real file beyond its stated range).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.measure import measure_call
from nexus.models.astype import (
    AstypeModel,
    str_object_bytes,
    to_str_peak_per_row,
)
from nexus.models.concat import ConcatModel
from nexus.models.drop_duplicates import DropDuplicatesModel
from nexus.models.merge import MergeModel, output_rows_range
from nexus.models.read_csv import ReadCsvModel, parse_peak_bytes
from nexus.models.sort_values import SortValuesModel
from nexus.pipeline import Pipeline
from nexus.state import StateInspector

MIB = 2**20
N = 1_000_000


# -- descriptors -------------------------------------------------------------------------------
def test_frame_descriptor_separates_moved_bytes_from_deep_bytes():
    df = pd.DataFrame({"i": np.arange(1000), "s": [f"value-{i}" for i in range(1000)]})
    inspection = StateInspector().inspect(["df"], {"df": df})
    desc = inspection.variables["df"]
    assert desc.shallow_bytes == 1000 * 8 + 1000 * 8  # int64 values + str pointers
    assert desc.moved_bytes == desc.shallow_bytes
    assert desc.nbytes > desc.moved_bytes  # deep size counts the string payload


# -- sort_values -------------------------------------------------------------------------------
def sort_features(moved, k=1, kt=0, deep=None):
    return {
        "n_rows": N,
        "n_keys": k,
        "n_text_keys": kt,
        "input_bytes": deep or moved,
        "moved_bytes": moved,
    }


def test_sort_values_peak_is_indexer_plus_copy_plus_index_not_deep_bytes():
    e = SortValuesModel().estimate(sort_features(68 * N, deep=180 * N), 0)
    assert e.ram_expected == (68 + 8 + 8) * N  # probe: 84.2 B/row measured
    assert e.ram_low == pytest.approx(0.98 * e.ram_expected)  # probe tolerance (-2%)


def test_sort_values_narrow_frame_is_dominated_by_the_nargsort_temporaries():
    e = SortValuesModel().estimate(sort_features(8 * N), 0)
    assert e.ram_expected == 42 * N  # probe: 41.2 B/row measured
    assert e.ram_high >= e.ram_expected + 24 * N  # nothing returned between the phases


def test_sort_values_text_keys_cost_more_than_numeric_keys_when_several():
    numeric = SortValuesModel().estimate(sort_features(16 * N, k=2, kt=0), 0).ram_expected
    text = SortValuesModel().estimate(sort_features(16 * N, k=2, kt=2), 0).ram_expected
    assert text > numeric


# -- merge -------------------------------------------------------------------------------------
def merge_features(nl, nr, how="inner", row_l=56.0, row_r=40.0):
    return {
        "n_left": nl,
        "n_right": nr,
        "bytes_left": row_l * nl * 3,
        "bytes_right": row_r * nr * 3,
        "moved_left": row_l * nl,
        "moved_right": row_r * nr,
        "key_text": False,
        "how": how,
        "out_rows": output_rows_range(nl, nr, how),
        "out_rows_source": "tier0_prior",
    }


def test_output_rows_range_has_semantic_floors():
    assert output_rows_range(100, 50, "inner")[0] < 100
    assert output_rows_range(100, 50, "left")[0] == 100
    assert output_rows_range(100, 50, "right")[0] == 50
    lo, mid, hi = output_rows_range(100, 50, "outer")
    assert lo >= 100 and lo <= mid <= hi and hi >= 150


def test_merge_ram_is_a_function_of_the_explicit_output_row_count():
    f = merge_features(N, N)
    small = MergeModel.ram_at(f, 0.1 * N)
    big = MergeModel.ram_at(f, 4 * N)
    assert big > 5 * small
    e = MergeModel().estimate({**f, "out_rows": (N, N, N), "out_rows_source": "tier1"}, 0)
    assert e.ram_expected == MergeModel.ram_at(f, N)
    assert e.ram_low < e.ram_expected  # low assumes the left copy is elided


def test_merge_charges_moved_bytes_not_string_payload():
    f = merge_features(N, N)
    deeper = {**f, "bytes_left": f["bytes_left"] * 10, "bytes_right": f["bytes_right"] * 10}
    assert MergeModel().estimate(f, 0).ram_expected == MergeModel().estimate(deeper, 0).ram_expected


def test_merge_hash_table_is_presized_regardless_of_distinct_keys():
    # 1.5M-row sides, tiny M: phase 1 (table 2**21 buckets) still dominates
    f = merge_features(1_500_000, 1_500_000)
    assert MergeModel.ram_at(f, 1000) > 30 * MIB


# -- concat ------------------------------------------------------------------------------------
def test_concat_copies_pointers_not_string_payload_and_adds_the_index():
    base = {"total_bytes": 90 * 2 * N, "moved_bytes": 68 * 2 * N, "total_rows": 2 * N}
    e = ConcatModel().estimate(base, 0)
    assert e.ram_low == 68 * 2 * N
    assert e.ram_expected == 68 * 2 * N + 12 * 2 * N  # probe: moved + 12 B/row
    deeper = {**base, "total_bytes": 10 * base["total_bytes"]}
    assert ConcatModel().estimate(deeper, 0).ram_expected == e.ram_expected
    ignored = ConcatModel().estimate({**base, "ignore_index": True}, 0)
    assert ignored.ram_expected == 68 * 2 * N  # RangeIndex: no index array


# -- drop_duplicates ---------------------------------------------------------------------------
def dd_features(k, moved, n=N, **extra):
    return {
        "n_rows": n,
        "n_keys": k,
        "n_text_keys": 0,
        "input_bytes": moved,
        "moved_bytes": moved,
        **extra,
    }


def test_drop_duplicates_range_spans_all_duplicates_to_all_unique():
    e = DropDuplicatesModel().estimate(dd_features(9, 68 * 4 * N, n=4 * N), 0)
    assert e.ram_low < e.ram_expected < e.ram_high


def test_drop_duplicates_with_known_distinct_fraction_collapses_to_the_error_band():
    f = dd_features(3, 24 * 2 * N, n=2 * N, distinct_fraction=1.0, key_distinct_fraction=0.632)
    e = DropDuplicatesModel().estimate(f, 0)
    assert e.ram_low == pytest.approx(0.8 * e.ram_expected)  # the formula's probe error band
    assert e.ram_high == pytest.approx(1.2 * e.ram_expected)
    assert e.ram_expected / (2 * N) == pytest.approx(67, abs=1)  # probe (n=2M): 67.1 B/row


def test_drop_duplicates_many_keys_need_the_id_compression_step():
    few = DropDuplicatesModel.ram_at(dd_features(3, 24 * N), 0.001, 0.5)
    many = DropDuplicatesModel.ram_at(dd_features(9, 24 * N), 0.5, 0.5)
    assert many > few * 1.5


def test_drop_duplicates_ignores_string_sharing():
    shared = dd_features(9, 68 * N)
    unshared = {**shared, "input_bytes": 300 * N}  # only the deep size differs
    a = DropDuplicatesModel().estimate(shared, 0).ram_expected
    assert a == DropDuplicatesModel().estimate(unshared, 0).ram_expected


# -- astype ------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("digits", "expected"), [(1, 64), (7, 96), (9, 112), (17, 112)]
)  # probe-measured: 64.3, 96.4, 112.5, 112.5 B/row
def test_int_to_str_peak_matches_the_probes(digits, expected):
    got = to_str_peak_per_row("int", digits)
    if digits == 1:  # cached ints: no int objects
        got = 2 * 8 + str_object_bytes(1)
    assert got == expected


def test_float_and_datetime_to_str_have_no_object_temporary():
    assert to_str_peak_per_row("float", 17) == 72  # probe 72.4
    assert to_str_peak_per_row("float", 6) == 56  # probe 56.3
    assert to_str_peak_per_row("datetime", 19) == 72  # probe 72.4


def test_astype_to_str_range_reflects_unknown_length():
    f = {"n_rows": N, "source_dtype": "int64", "target": "str"}
    e = AstypeModel().estimate(f, 0)
    assert e.ram_low < e.ram_expected < e.ram_high
    exact = AstypeModel().estimate({**f, "str_len": 7}, 0)
    assert exact.ram_expected == 96 * N  # Tier 1 length collapses the range


def test_astype_to_category_spans_few_to_all_distinct_instead_of_a_point():
    f = {"n_rows": N, "source_dtype": "object", "target": "category"}
    e = AstypeModel().estimate(f, 0)
    assert e.ram_low == 24 * N and e.ram_high == 83 * N  # probe extremes, constant in n
    assert e.ram_low < e.ram_expected < e.ram_high
    num = AstypeModel().estimate({**f, "source_dtype": "int64"}, 0)
    assert num.ram_low == 16 * N and num.ram_high == 59 * N


def test_astype_numeric_casts_unchanged():
    e = AstypeModel().estimate({"n_rows": N, "source_dtype": "int64", "target": "int32"}, 0)
    assert e.ram_expected == 4 * N


# -- read_csv: the dangerous (under-prediction) direction --------------------------------------
def _write_csv(path, rows: int, kind: str) -> None:
    rng = np.random.default_rng(3)
    if kind == "strings":  # all-distinct 12-character text: the worst realistic case
        cols = {
            f"s{j}": pd.Series([f"v{rng.integers(10**10):011d}" for _ in range(rows)])
            for j in range(4)
        }
    elif kind == "short_ints":
        cols = {f"c{j}": rng.integers(0, 10, rows) for j in range(8)}
    else:
        cols = {f"f{j}": rng.random(rows) for j in range(4)}
    pd.DataFrame(cols).to_csv(path, index=False)


@pytest.mark.parametrize("kind", ["strings", "short_ints", "floats"])
def test_read_csv_never_under_predicts_beyond_its_high_end(tmp_path, kind):
    """Regression: the first-draft range (0.5-5x file) sat below real strings/short-int files."""
    path = tmp_path / f"{kind}.csv"
    _write_csv(path, 200_000, kind)
    file_bytes = path.stat().st_size
    est = ReadCsvModel().estimate({"file_bytes": file_bytes}, 0)
    result = measure_call(_ReadCall(str(path)), repeats=2)
    assert result.status == "ok"
    actual = result.delta_bytes if result.delta_bytes is not None else result.bound_bytes
    assert actual <= est.ram_high, f"{kind}: {actual / file_bytes:.1f}x file beyond range"
    assert est.ram_expected >= 0.4 * actual  # and not absurdly high at the expected value


class _ReadCall:
    """Picklable callable for ``measure_call`` (module-level class, spawn-safe)."""

    def __init__(self, path: str) -> None:
        self.path = path

    def __call__(self, _state: object) -> int:
        return len(pd.read_csv(self.path))


def test_read_csv_tier1_inputs_give_the_documented_point_estimate():
    peak = parse_peak_bytes(
        53e6, 1e6, 4, text_cols=4, str_chars=12, unique_fraction=1.0
    )  # all-distinct 4 x 12 char text, probe 384 B/row
    assert peak / 1e6 == pytest.approx(384, rel=0.1)
    e = ReadCsvModel().estimate({"file_bytes": 53e6, "n_rows": 1e6, "n_cols": 4}, 0)
    assert e.ram_low < e.ram_expected < e.ram_high


def test_read_csv_pipeline_estimate_is_above_the_first_draft_range(tmp_path):
    path = tmp_path / "x.csv"
    _write_csv(path, 1000, "floats")
    report = Pipeline(tier=0).run(f"pd.read_csv({str(path)!r})", {"pd": pd})
    assert report.estimates
    size = path.stat().st_size
    assert report.estimates[0].estimate.ram_high > 5 * size  # old high end was 5x


def test_drop_duplicates_null_key_columns_add_one_int64_array_each():
    """Probe: nulls in 6 key columns added 47.9 B/row = 8 x 6 (maybe_lift in get_group_index)."""
    f = dd_features(9, 68 * 2 * N, n=2 * N, distinct_fraction=0.7, key_distinct_fraction=0.28)
    none = DropDuplicatesModel().estimate({**f, "n_nullable_keys": 6, "null_key_columns": 0}, 0)
    six = DropDuplicatesModel().estimate({**f, "n_nullable_keys": 6, "null_key_columns": 6}, 0)
    assert six.ram_expected - none.ram_expected == pytest.approx(8 * 6 * 2 * N, rel=0.01)


def test_drop_duplicates_tier0_range_widens_with_nullable_dtypes():
    base = dd_features(9, 68 * N, n=N)
    with_nullable = DropDuplicatesModel().estimate({**base, "n_nullable_keys": 6}, 0)
    without = DropDuplicatesModel().estimate({**base, "n_nullable_keys": 0}, 0)
    assert with_nullable.ram_high > without.ram_high
    assert with_nullable.ram_low == without.ram_low


def test_can_hold_null_by_dtype():
    from nexus.models._util import can_hold_null

    assert not can_hold_null("int64") and not can_hold_null("uint8") and not can_hold_null("bool")
    assert all(can_hold_null(d) for d in ("float64", "object", "str", "category", "Int64"))
    assert can_hold_null("datetime64[s]")
