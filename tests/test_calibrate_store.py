"""Machine profile / calibration and the on-disk dataset store."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from benchmarks import store
from benchmarks.datasets import DatasetConfig, make_frame
from benchmarks.suite import ArrayInput, CsvInput, FrameInput, JoinInput
from nexus import calibrate
from nexus import machine as machine_mod
from nexus.machine import MachineProfile, load_profile, machine, save_profile
from nexus.pipeline import Pipeline

CURVE_NAMES = (
    "copy_bps", "read_bps", "num_factorize_s", "text_factorize_s", "object_take_s",
    "num_argsort_s", "text_argsort_s", "np_sort_s", "blas64_flops", "blas32_flops",
)  # fmt: skip
SCALARS = (
    "csv_num_field_s", "csv_text_field_s", "int_to_str_s", "float_to_str_s", "datetime_to_str_s",
    "cast_s", "agg_s", "first_touch_bps",
)  # fmt: skip


def test_default_profile_is_uncalibrated():
    assert machine().calibrated is False
    assert machine().meta.get("generic") is True  # the documented generic profile


def test_quick_calibration_is_finite_positive_and_plausible():
    profile = calibrate.measure_profile(quick=True)
    assert profile.calibrated and profile.meta["quick"] is True and profile.is_current_format
    for name in CURVE_NAMES:
        pts = profile.curves[name]
        assert len(pts) >= 2, name
        assert all(math.isfinite(y) and y > 0 for _, y in pts), name
    for name in SCALARS:
        value = getattr(profile, name)
        assert math.isfinite(value) and value > 0, name
    assert 1e8 < profile.at("copy_bps", 1e6) < 1e12
    assert 1e8 < profile.at("blas64_flops", 1e7) < 1e14
    assert profile.at("text_factorize_s", 1e4) > profile.at("num_factorize_s", 1e4)
    assert profile.csv_text_field_s > profile.csv_num_field_s
    assert profile.meta["calibration_version"] == calibrate.CALIBRATION_VERSION
    assert profile.page_fault_s_per_byte >= 0.0


def test_profile_cache_roundtrip_and_ensure(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    monkeypatch.setenv(machine_mod.ENV_VAR, str(path))
    assert load_profile() is None
    first = calibrate.ensure_profile(quick=True)
    assert path.exists() and load_profile().profile_id == first.profile_id
    assert calibrate.ensure_profile(quick=True).profile_id == first.profile_id  # cached, not re-run
    assert machine().calibrated is True
    forced = calibrate.ensure_profile(quick=True, force=True)
    assert forced.meta["timestamp"] >= first.meta["timestamp"]


def test_corrupt_profile_falls_back_to_defaults(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    monkeypatch.setenv(machine_mod.ENV_VAR, str(path))
    machine.cache_clear()
    assert load_profile() is None and machine().calibrated is False


def test_models_read_the_profile(tmp_path, monkeypatch):
    from nexus.machine import reference_profile, scaled

    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "m.json"))
    df = pd.DataFrame({"k": range(5000), "v": np.arange(5000.0)})

    def time_estimate(factor):
        save_profile(scaled(reference_profile(), factor))
        report = Pipeline(tier=0).run("df.copy()\ndf.sort_values('v')", {"df": df, "pd": pd})
        return next(e for e in report.estimates if e.op.name == "sort_values").estimate

    slow, fast = time_estimate(10.0), time_estimate(0.1)
    assert slow.time_expected > fast.time_expected
    assert slow.ram_expected == fast.ram_expected  # RAM models are untouched by the profile


def test_cli_show_and_quick(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "cli.json"))
    calibrate.main(["--show"])
    assert "no calibrated profile" in capsys.readouterr().out
    calibrate.main(["--quick"])
    assert "copy_bps" in capsys.readouterr().out
    calibrate.main(["--show"])
    assert "calibrated=True" in capsys.readouterr().out


# -- store ---------------------------------------------------------------------------------------
def test_store_frame_roundtrip_all_dtypes(tmp_path):
    df = make_frame(DatasetConfig(n_rows=3000, null_rate=0.1, dup_rate=0.3, cardinality=0.05))
    store.save(df, tmp_path / "f")
    loaded = store.load(tmp_path / "f")
    pd.testing.assert_frame_equal(df, loaded)
    assert loaded["s0"].dtype == object
    assert len({id(x) for x in loaded["s0"]}) < 400  # shared string objects survive pickling


def test_store_array_roundtrip_and_errors(tmp_path):
    arr = np.random.default_rng(0).random((20, 30))
    store.save(arr, tmp_path / "a")
    np.testing.assert_array_equal(store.load(tmp_path / "a"), arr)
    with pytest.raises(TypeError):
        store.save([1, 2, 3], tmp_path / "bad")


def test_input_specs_generate_once_and_load(tmp_path):
    cache = str(tmp_path)
    cfg = DatasetConfig(n_rows=500)
    for spec, names in (
        (FrameInput(cfg), {"df"}),
        (JoinInput(cfg, 200), {"df", "right"}),
        (ArrayInput((50,), "v"), {"v"}),
    ):
        spec.ensure(cache)
        marker = spec.directory(cache) / "DONE"
        stamp = marker.stat().st_mtime_ns
        spec.ensure(cache)  # cached: nothing regenerated
        assert marker.stat().st_mtime_ns == stamp
        assert set(spec.load(cache)) == names
    csv = CsvInput(cfg)
    csv.ensure(cache)
    assert pd.read_csv(csv.load(cache)["path"]).shape[0] == 500


def test_env_info_is_recorded():
    from benchmarks.runner import ENV_FIELDS, env_info

    info = env_info()
    assert set(ENV_FIELDS) <= set(info)
    assert info["instrument"] == "os-peak-v2" and info["pandas_str_default"]
    json.dumps(info, default=str)


def test_stale_calibration_version_is_remeasured(tmp_path, monkeypatch):
    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "old.json"))
    first = calibrate.ensure_profile(quick=True)
    stale = MachineProfile(**{**vars(first), "meta": {**first.meta, "calibration_version": 1}})
    save_profile(stale)
    again = calibrate.ensure_profile(quick=True)
    assert again.meta["calibration_version"] == calibrate.CALIBRATION_VERSION
    assert again.meta["timestamp"] >= stale.meta["timestamp"]
