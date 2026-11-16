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

THROUGHPUTS = (
    "copy_bps", "num_hash_s", "text_hash_s", "num_argsort_s", "text_argsort_s", "np_sort_s",
    "csv_parse_bps", "blas_flops", "cast_s", "to_str_s", "agg_s",
)  # fmt: skip


def test_default_profile_is_uncalibrated():
    assert machine().calibrated is False
    assert machine().copy_bps == MachineProfile().copy_bps


def test_quick_calibration_is_finite_positive_and_plausible():
    profile = calibrate.measure_profile(quick=True)
    assert profile.calibrated and profile.meta["quick"] is True
    for name in THROUGHPUTS:
        value = getattr(profile, name)
        assert math.isfinite(value) and value > 0, name
    assert 1e8 < profile.copy_bps < 1e12
    assert 1e8 < profile.blas_flops < 1e14
    assert profile.text_hash_s > profile.num_hash_s


def test_profile_cache_roundtrip_and_ensure(tmp_path, monkeypatch):
    path = tmp_path / "p.json"
    monkeypatch.setenv(machine_mod.ENV_VAR, str(path))
    assert load_profile() is None
    first = calibrate.ensure_profile(quick=True)
    assert path.exists() and load_profile().copy_bps == first.copy_bps
    assert calibrate.ensure_profile(quick=True).copy_bps == first.copy_bps  # cached, not re-run
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
    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "m.json"))
    df = pd.DataFrame({"k": range(5000), "v": np.arange(5000.0)})

    def time_estimate(copy_bps):
        save_profile(MachineProfile(copy_bps=copy_bps, calibrated=True))
        report = Pipeline(tier=0).run("df.copy()\ndf.sort_values('v')", {"df": df, "pd": pd})
        return next(e for e in report.estimates if e.op.name == "sort_values").estimate

    slow, fast = time_estimate(1e6), time_estimate(1e12)
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
