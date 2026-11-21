"""Phase 6: machine profile v3 curves, conformal fitting, the calibration artifact and the freeze guard."""

from __future__ import annotations

import json
import math
import warnings

import numpy as np
import pandas as pd
import pytest

from nexus import calfit, timecal
from nexus import machine as machine_mod
from nexus.machine import MachineProfile, generic_profile, machine, reference_profile, save_profile
from nexus.models.base import Estimate


def _est(tier: int = 1, t: float = 1.0) -> Estimate:
    return Estimate(ram_low=1, ram_expected=2, ram_high=3, time_low=t / 4, time_expected=t,
                    time_high=4 * t, confidence=0.7, tier=tier)  # fmt: skip


@pytest.fixture
def artifact_file(tmp_path, monkeypatch):
    art = {
        "format": 1, "name": "test", "validated_pandas": [".".join(pd.__version__.split(".")[:2])],
        "tier01": {"1": {"groupby": {"residual": 0.5, "range": "per-operation", "q_lo": -0.5, "q_hi": 0.7},
                         "matmul": {"residual": 2.0, "range": "generic"}},
                   "0": {}},
        "tier01_generic": {"1": {"q_lo": -1.0, "q_hi": 1.0}, "0": {"q_lo": -1.2, "q_hi": 1.2}},
        "tier2": {"merge": {"q": 0.5, "range": "per-operation"}}, "tier2_generic": {"q": 1.5},
    }  # fmt: skip
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(art))
    monkeypatch.setenv(timecal.ENV_VAR, str(path))
    timecal.artifact.cache_clear()
    yield path
    timecal.artifact.cache_clear()


@pytest.fixture
def calibrated_machine(tmp_path, monkeypatch):
    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "m.json"))
    save_profile(reference_profile())
    yield
    machine.cache_clear()


# -- machine profile v3 --------------------------------------------------------------------------
def test_curve_interpolates_log_log_and_extrapolates_bounded():
    p = MachineProfile(curves={"num_factorize_s": [[100, 1e-8], [10_000, 1e-7]],
                               "copy_bps": [[1e3, 1e10], [1e6, 1e9]]})  # fmt: skip
    assert p.at("num_factorize_s", 1_000) == pytest.approx(math.sqrt(1e-8 * 1e-7))
    assert p.at("num_factorize_s", 10) == pytest.approx(1e-8)  # below: cache-resident, flat
    assert p.at("num_factorize_s", 1e6) == pytest.approx(1e-6, rel=1e-6)  # slope 0.5 kept
    assert p.at("copy_bps", 1e9) <= 1e9  # a throughput never rises beyond the measured range
    with pytest.raises(KeyError):
        p.at("nope", 1)


def test_reference_profile_is_complete_and_generic_is_slower_and_flagged():
    ref = reference_profile()
    assert ref.is_current_format and ref.calibrated
    gen = generic_profile()
    assert not gen.calibrated and gen.meta["generic"] is True
    assert gen.at("num_factorize_s", 1e5) == pytest.approx(2 * ref.at("num_factorize_s", 1e5))
    assert gen.at("copy_bps", 1e8) == pytest.approx(ref.at("copy_bps", 1e8) / 2)
    assert gen.csv_text_field_s == pytest.approx(2 * ref.csv_text_field_s)
    assert ref.profile_id == reference_profile().profile_id and len(ref.profile_id) == 12


def test_uncalibrated_machine_uses_the_generic_profile():
    assert machine().calibrated is False  # conftest points the cache at an empty file
    assert machine().meta.get("generic") is True


def test_old_format_profile_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setenv(machine_mod.ENV_VAR, str(tmp_path / "old.json"))
    save_profile(MachineProfile(calibrated=True, meta={"format": 2}))
    assert machine().calibrated is False
    machine.cache_clear()


# -- conformal fitting ----------------------------------------------------------------------------
def test_conformal_bounds_finite_sample_rank_and_contain_zero():
    r = np.arange(1, 20) / 10.0  # 19 positive residuals
    lo, hi = calfit.conformal_bounds(r, 0.10)
    assert hi == pytest.approx(1.9)  # ceil(20 * 0.95) = 19th of 19
    assert lo == 0.0  # the range always contains the estimate
    lo, hi = calfit.conformal_bounds(-r, 0.10)
    assert lo == pytest.approx(-1.9) and hi == 0.0


def test_tier2_score_is_one_on_the_range_edges():
    assert calfit.tier2_score(4.0, 0.5, 2.0, 4.0) == pytest.approx(1.0)
    assert calfit.tier2_score(1.0, 1.0, 2.0, 4.0) == pytest.approx(1.0)
    assert calfit.tier2_score(2.0, 1.0, 2.0, 4.0) == pytest.approx(0.0)


def _frame(n_cfg: int, bias: float = 2.0) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for c in range(n_cfg):
        for s in range(3):
            e = 1.0 + s
            rows.append({"model": "m", "op": "m", "tier": 1, "case": f"c{c}", "expected": e,
                         "actual": e * bias * float(np.exp(rng.normal(0, 0.2)))})  # fmt: skip
    return pd.DataFrame(rows)


def test_loco_uses_other_configurations_and_generic_below_eight():
    d = _frame(10)
    out = calfit.loco_tier01(d)
    assert set(out["range_kind"]) == {"per-operation"}
    assert out["m_loco"].between(1.6, 2.5).all()
    cov = ((out["low_cal"] <= out["actual"]) & (out["actual"] <= out["high_cal"])).mean()
    assert cov > 0.8
    few = calfit.loco_tier01(_frame(5))
    assert set(few["range_kind"]) == {"generic"}


def test_fit_tier01_records_residual_and_range_kind():
    entries, generic = calfit.fit_tier01(pd.concat([_frame(10), _frame(4).assign(model="x")]))
    assert entries["1"]["m"]["range"] == "per-operation" and "q_hi" in entries["1"]["m"]
    assert entries["1"]["x"]["range"] == "generic" and "q_hi" not in entries["1"]["x"]
    assert entries["1"]["m"]["residual"] == pytest.approx(2.0, rel=0.2)
    assert generic["1"]["q_lo"] <= 0 <= generic["1"]["q_hi"]


# -- runtime application ----------------------------------------------------------------------------
def test_per_operation_calibration(artifact_file, calibrated_machine):
    out = timecal.calibrate("groupby", _est(t=2.0))
    assert out.time_expected == pytest.approx(1.0)  # residual 0.5
    assert out.time_low == pytest.approx(math.exp(-0.5))
    assert out.time_high == pytest.approx(math.exp(0.7))
    assert out.flags == ()
    assert (out.ram_low, out.ram_expected, out.ram_high) == (1, 2, 3)  # RAM untouched


def test_generic_range_is_flagged(artifact_file, calibrated_machine):
    out = timecal.calibrate("matmul", _est(t=1.0))
    assert out.time_expected == pytest.approx(2.0)
    assert out.time_high == pytest.approx(2.0 * math.e)
    assert timecal.FLAG_GENERIC in out.flags
    unknown = timecal.calibrate("never_fitted", _est(t=1.0))
    assert timecal.FLAG_GENERIC in unknown.flags and unknown.time_expected == 1.0


def test_absent_or_outdated_artifact_widens_and_flags(tmp_path, monkeypatch, calibrated_machine):
    for content in (None, json.dumps({"format": 99})):
        path = tmp_path / "missing.json"
        if content is not None:
            path.write_text(content)
        monkeypatch.setenv(timecal.ENV_VAR, str(path))
        timecal.artifact.cache_clear()
        out = timecal.calibrate("groupby", _est(t=1.0))
        assert timecal.FLAG_NO_ARTIFACT in out.flags
        assert out.time_low == pytest.approx(0.25 / 3) and out.time_high == pytest.approx(12.0)
    timecal.artifact.cache_clear()


def test_uncalibrated_machine_widens_and_flags(artifact_file):
    out = timecal.calibrate("groupby", _est(t=2.0))
    assert machine_mod.UNCALIBRATED_FLAG in out.flags
    assert out.time_high == pytest.approx(math.exp(0.7) * 3)


def test_unvalidated_pandas_warns_once_widens_and_flags(
    artifact_file, calibrated_machine, monkeypatch
):
    art = json.loads(artifact_file.read_text())
    art["validated_pandas"] = ["0.1"]
    artifact_file.write_text(json.dumps(art))
    timecal.artifact.cache_clear()
    timecal._warn_pandas_once.cache_clear()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = timecal.calibrate("groupby", _est(t=2.0))
        timecal.calibrate("groupby", _est(t=2.0))
    assert sum("unvalidated" in str(w.message) or "outside" in str(w.message) for w in caught) == 1
    assert timecal.FLAG_PANDAS in out.flags
    assert out.time_high == pytest.approx(math.exp(0.7) * 2)


def test_tier2_calibration_raises_the_own_range_to_q(artifact_file, calibrated_machine):
    (lo, e, hi), flags = timecal.calibrate_tier2("merge", 0.25, 1.0, 4.0)
    assert (lo, e, hi) == (pytest.approx(0.5), 1.0, pytest.approx(2.0)) and flags == []
    (lo, e, hi), flags = timecal.calibrate_tier2("groupby", 0.25, 1.0, 4.0)
    assert hi == pytest.approx(4.0**1.5) and timecal.FLAG_GENERIC in flags


def test_packaged_artifact_is_valid_and_lists_its_fitted_parameters():
    timecal.artifact.cache_clear()
    art = timecal.artifact()
    assert art is not None and art["format"] == timecal.SUPPORTED_FORMAT
    assert art["fitted_parameters"] and all("fitted_on" in p for p in art["fitted_parameters"])
    assert art["data"]["split"].startswith("dev")
    assert art["machine_profile_id"]


def test_pipeline_estimates_carry_calibrated_time_and_flags():
    from nexus.pipeline import Pipeline

    df = pd.DataFrame({"k": np.arange(20_000) % 7, "v": np.arange(20_000.0)})
    rep = Pipeline(tier=1).run('df.groupby("k")["v"].sum()', {"df": df, "pd": pd})
    est = rep.estimates[0].estimate
    assert machine_mod.UNCALIBRATED_FLAG in est.flags  # tests run without a calibrated profile
    assert est.time_low <= est.time_expected <= est.time_high


# -- freeze guard ---------------------------------------------------------------------------------
def test_frozen_guard_refuses_an_unknown_tag_or_a_modified_tree():
    from benchmarks.frozen import NotFrozenError, check_state, frozen_state

    state = frozen_state("no-such-tag-xyz")
    assert state["problems"]
    with pytest.raises(NotFrozenError):
        check_state(state)
    with pytest.raises(NotFrozenError, match="differs"):
        check_state({"tag": "t", "tag_commit": "x", "head": "y", "problems": ["differs from t: a"]})
    ok = check_state({"tag": "t", "tag_commit": "abc", "head": "abc", "problems": []})
    assert ok["frozen_commit"] == "abc"


def test_heldout_evaluation_and_runs_call_the_freeze_guard(monkeypatch, tmp_path):
    import benchmarks.frozen as frozen
    from benchmarks import evaluate

    def refuse(tag=frozen.FROZEN_TAG):
        raise frozen.NotFrozenError("not frozen")

    monkeypatch.setattr(frozen, "require_frozen", refuse)
    with pytest.raises(frozen.NotFrozenError):
        evaluate.write_validation_report(tmp_path, "test")
    with pytest.raises(frozen.NotFrozenError):
        evaluate.write_final_report(tmp_path, "test")


def _tag_present() -> bool:
    import subprocess

    from benchmarks import frozen

    done = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{frozen.FROZEN_TAG}"],
                          cwd=frozen.ROOT, capture_output=True)  # fmt: skip
    return done.returncode == 0


@pytest.mark.skipif(not _tag_present(), reason="the freeze tag is not in this checkout")
def test_manifest_guard_scope_and_refusals(monkeypatch, tmp_path):
    from benchmarks import frozen

    files = frozen.frozen_files()
    assert (
        "src/nexus/models/merge.py" in files
        and "src/nexus/calibration/calibration-v1.json" in files
    )
    assert "src/nexus/measure.py" in files and "tests/test_measure_validation.py" in files
    others = [f for f in files if f != "tests/test_measure_validation.py"]
    assert not any(
        f.startswith(("docs/", "tests/", "benchmarks/")) or f == ".gitignore" for f in others
    )
    real = frozen.tag_hashes()
    assert frozen.frozen_state()["problems"] == [], (
        "the working tree must match the tag on frozen files"
    )
    changed = dict(real)
    changed["src/nexus/ranges.py"] = "0" * 64
    monkeypatch.setattr(frozen, "tag_hashes", lambda tag=frozen.FROZEN_TAG: changed)
    probs = frozen.frozen_state()["problems"]
    assert any("differs" in p and "ranges.py" in p for p in probs)
    fewer = {k: v for k, v in real.items() if k != "src/nexus/risk.py"}
    monkeypatch.setattr(frozen, "tag_hashes", lambda tag=frozen.FROZEN_TAG: fewer)
    assert any("new file under a frozen pattern" in p for p in frozen.frozen_state()["problems"])
    extra = {**real, "src/nexus/models/gone.py": "1" * 64}
    monkeypatch.setattr(frozen, "tag_hashes", lambda tag=frozen.FROZEN_TAG: extra)
    assert any("missing" in p for p in frozen.frozen_state()["problems"])
