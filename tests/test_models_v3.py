"""Phase 7b models: set_index (second attempt, zero-copy), apply(np.<ufunc>), merge sort=True, read_csv serial
Tier 0; explode and value_counts stay uncovered (their derivations failed the probes)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nexus.pipeline import Pipeline


def _est(src: str, ns: dict, tier: int = 1):
    return {e.model: e for e in Pipeline(tier=tier).run(src, {"pd": pd, "np": np, **ns}).estimates}


def test_set_index_is_zero_copy_and_refuses_unprobed_forms():
    df = pd.DataFrame({"k": np.arange(1000), "f": np.ones(1000), "s": ["x"] * 1000})
    e = _est("r = df.set_index('k')", {"df": df})["set_index"].estimate
    assert (e.ram_low, e.ram_expected) == (0, 0) and e.ram_high == 8 * 1000
    for src in ("r = df.set_index('s')", "r = df.set_index(['k', 'f'])", "r = df.set_index('k', append=True)",
                "r = df.set_index('k', verify_integrity=True)", "df.set_index('k', inplace=True)"):  # fmt: skip
        assert "set_index" not in _est(src, {"df": df}), src


def test_apply_ufunc_result_dtype_and_refusals():
    df = pd.DataFrame({"f32": np.ones(1000, dtype="float32"), "i": np.arange(1000)})
    assert (
        _est("a = df['f32'].apply(np.log)", {"df": df})["apply_ufunc"].estimate.ram_expected == 4000
    )
    assert (
        _est("a = df['i'].apply(np.sqrt)", {"df": df})["apply_ufunc"].estimate.ram_expected == 8000
    )
    for src in (
        "a = df['i'].apply(lambda x: x)",
        "a = df.apply(np.sqrt)",
        "a = df['i'].apply(np.add)",
    ):
        assert "apply_ufunc" not in _est(src, {"df": df}), src


def test_explode_and_value_counts_are_uncovered():
    s = pd.Series([[1, 2]] * 1000, dtype=object)
    assert not _est("e = s.explode()", {"s": s})
    assert not _est("v = s.value_counts()", {"s": pd.Series(np.arange(1000))})


def test_merge_sort_true_is_never_left_elided():
    rng = np.random.default_rng(0)
    left = pd.DataFrame({"k": rng.integers(0, 100, 50_000), "v": rng.random(50_000)})
    right = pd.DataFrame({"k": np.arange(100), "w": np.ones(100)})
    ns = {"left": left, "right": right}
    plain = _est("m = left.merge(right, on='k')", ns)["merge"].features
    srt = _est("m = left.merge(right, on='k', sort=True)", ns)["merge"].features
    assert plain["left_elided"] and not srt["left_elided"]


def test_read_csv_tier0_serial_low_bound(tmp_path, monkeypatch):
    from nexus.models import read_csv as rc

    p = tmp_path / "x.csv"
    pd.DataFrame({"a": np.random.default_rng(0).random(20_000)}).to_csv(p, index=False)
    size = p.stat().st_size
    e = _est(f"a = pd.read_csv({str(p)!r})", {}, tier=0)["read_csv"].estimate
    assert e.ram_low == int(8.0 * size / rc.FIELD_WIDTH_RANGE[1])  # < 5 MiB: the serial reader
