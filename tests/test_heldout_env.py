"""Phase 6d: the machine-profile / power check of held-out runs (benchmarks.heldout_env).

The first invocation of a run pins the profile in the run's meta.json; later invocations (resume,
pilot -> full) require the same profile and ignore its age.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace

import pytest

import benchmarks.heldout_env as he
from nexus import machine as machine_mod
from nexus.machine import reference_profile, save_profile

HOUR = 3600.0


@pytest.fixture
def real_check(monkeypatch):
    """The real require_profile (the conftest stubs it) on a mains machine."""
    import importlib

    import nexus.power

    fresh = importlib.reload(he)
    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    yield fresh
    importlib.reload(he)


def _reference_identity(monkeypatch, mod, same: bool) -> None:
    ident = he._identity(reference_profile().meta)
    monkeypatch.setattr(
        mod, "_this_machine", lambda: ident if same else ("Linux-6.8", "x86_64", 64)
    )


def _stamp(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


def _profile(**meta):
    ref = reference_profile()
    return replace(ref, meta={**ref.meta, **meta})


def _fresh_vm_profile(t: float, **meta):
    """A full mains-or-unknown calibration on a new machine, measured at ``t`` (not the reference id)."""
    p = machine_mod.scaled(reference_profile(), 1.3)
    return replace(
        p, meta={**p.meta, "timestamp": _stamp(t), "quick": False, "power": "unknown", **meta}
    )


def test_reference_machine_accepts_only_the_reference_profile(real_check, monkeypatch, tmp_path):
    _reference_identity(monkeypatch, real_check, same=True)
    save_profile(reference_profile())
    rec = real_check.require_profile(tmp_path / "a")
    assert rec["profile_id"] == reference_profile().profile_id
    assert rec["profile_mode"] == "first invocation: reference machine: reference profile"
    corrupted = machine_mod.scaled(
        reference_profile(), 10.0
    )  # e.g. a quick battery profile over it
    save_profile(replace(corrupted, meta={**corrupted.meta, "quick": True}))
    with pytest.raises(real_check.HeldoutEnvironmentError, match="not the reference profile"):
        real_check.require_profile(tmp_path / "b")


def test_first_invocation_pins_a_fresh_full_mains_profile(real_check, monkeypatch, tmp_path):
    _reference_identity(monkeypatch, real_check, same=False)
    now = time.time()
    prof = _fresh_vm_profile(now - HOUR)
    save_profile(prof)
    run = tmp_path / "run"
    rec = real_check.require_profile(run, now=now)
    assert rec["profile_mode"].startswith("first invocation: new machine")
    pin = json.loads((run / "meta.json").read_text(encoding="utf-8"))[he.PIN_KEY]
    assert pin["profile_id"] == prof.profile_id == rec["profile_id"] and pin["profile_file_sha256"]
    for bad, match in (
        (_fresh_vm_profile(now - 24 * HOUR), "FIRST invocation"),
        (_fresh_vm_profile(now - HOUR, quick=True), "quick"),
        (_fresh_vm_profile(now - HOUR, power="battery"), "battery"),
    ):
        save_profile(bad)
        with pytest.raises(real_check.HeldoutEnvironmentError, match=match):
            real_check.require_profile(tmp_path / f"new-{match}", now=now)
        assert not (
            tmp_path / f"new-{match}" / "meta.json"
        ).exists()  # a refused first call pins nothing


def test_resume_after_30_hours_needs_the_same_profile_and_ignores_its_age(
    real_check, monkeypatch, tmp_path
):
    _reference_identity(monkeypatch, real_check, same=False)
    now = time.time()
    save_profile(_fresh_vm_profile(now - HOUR))
    run = tmp_path / "run"
    first = real_check.require_profile(run, now=now)
    later = real_check.require_profile(run, now=now + 30 * HOUR)  # 31 h after the calibration
    assert later["profile_mode"].startswith("resumed: pinned profile")
    assert later["profile_id"] == first["profile_id"]
    with pytest.raises(real_check.HeldoutEnvironmentError, match="FIRST invocation"):
        real_check.require_profile(tmp_path / "other", now=now + 30 * HOUR)  # a NEW run is first


def test_a_changed_profile_mid_run_aborts(real_check, monkeypatch, tmp_path):
    _reference_identity(monkeypatch, real_check, same=False)
    now = time.time()
    prof = _fresh_vm_profile(now - HOUR)
    save_profile(prof)
    run = tmp_path / "run"
    real_check.require_profile(run, now=now)
    save_profile(_fresh_vm_profile(now, power="mains"))  # re-calibrated mid-run: a new, fresh id
    with pytest.raises(real_check.HeldoutEnvironmentError, match="SAME profile"):
        real_check.require_profile(run, now=now + HOUR)
    save_profile(replace(prof, meta={**prof.meta, "note": "edited"}))  # same id, file changed
    assert machine_mod.load_profile().profile_id == prof.profile_id
    with pytest.raises(real_check.HeldoutEnvironmentError, match=r"file \(same id\)"):
        real_check.require_profile(run, now=now + HOUR)
    save_profile(prof)  # the original file back: the run may resume
    assert real_check.require_profile(run, now=now + HOUR)["profile_mode"].startswith("resumed")


def test_battery_aborts_first_and_resumed_invocations(real_check, monkeypatch, tmp_path):
    import nexus.power

    _reference_identity(monkeypatch, real_check, same=False)
    run = tmp_path / "run"
    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    with pytest.raises(real_check.HeldoutEnvironmentError, match="no calibrated"):
        real_check.require_profile(run)  # the conftest's isolated profile path is empty
    now = time.time()
    save_profile(_fresh_vm_profile(now - HOUR))
    real_check.require_profile(run, now=now)
    monkeypatch.setattr(nexus.power, "power_state", lambda: "battery")
    with pytest.raises(real_check.HeldoutEnvironmentError, match="battery"):
        real_check.require_profile(run, now=now)  # resumed on battery
    with pytest.raises(real_check.HeldoutEnvironmentError, match="battery"):
        real_check.require_profile(tmp_path / "new", now=now)  # first call on battery


def test_pilot_then_full_run_keeps_the_pin_through_the_runner(real_check, monkeypatch, tmp_path):
    """The runner rewrites meta.json on every invocation; the pin must survive a --pilot run, and the
    full run 30 h later must pass on the same profile. Synthetic points (a made-up case marked as a
    protected group), so no real held-out configuration is touched."""
    from benchmarks.datasets import DatasetConfig
    from benchmarks.runner import RunConfig, run_suite
    from benchmarks.split import VAL
    from benchmarks.suite import FrameInput, GridPoint

    _reference_identity(monkeypatch, real_check, same=False)
    t0 = time.time()
    monkeypatch.setattr(real_check, "_now", lambda: t0)
    save_profile(_fresh_vm_profile(t0 - HOUR))
    base = DatasetConfig(n_rows=2000)
    pts = [
        GridPoint(
            id=f"test-only/pin_{i}|n=2000",
            case=f"test-only/pin_{i}",
            op="drop_duplicates",
            source="df.drop_duplicates()",
            size=2000,
            inputs=(FrameInput(base.with_(n_rows=2000, seed=900 + i)),),
            repeats=1,
            footprint_factor=3.0,
            split=VAL,
        )  # fmt: skip
        for i in range(2)
    ]
    out = tmp_path / "results" / "pin"
    run_suite(RunConfig(suite="small", out_dir=out, calibrate=False, pilot=1), pts)
    pin = json.loads((out / "meta.json").read_text(encoding="utf-8"))[he.PIN_KEY]
    monkeypatch.setattr(real_check, "_now", lambda: t0 + 30 * HOUR)
    run_suite(RunConfig(suite="small", out_dir=out, calibrate=False), pts)  # the full run
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta[he.PIN_KEY] == pin
    assert meta["heldout_environment"]["profile_mode"].startswith("resumed")
    save_profile(_fresh_vm_profile(t0 + 30 * HOUR))  # re-calibrated before a further resume
    with pytest.raises(real_check.HeldoutEnvironmentError, match="SAME profile"):
        run_suite(RunConfig(suite="small", out_dir=out, calibrate=False), pts)


def test_heldout_entry_points_call_the_check(monkeypatch, tmp_path):
    from benchmarks.multicell import run as mc
    from benchmarks.realworld import run_notebook as rn
    from benchmarks.realworld import synthetic

    seen = []

    def refuse(run_dir=None, now=None):
        seen.append(run_dir)
        raise he.HeldoutEnvironmentError("refused (test)")

    monkeypatch.setattr(he, "require_profile", refuse)
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    with pytest.raises(he.HeldoutEnvironmentError):
        mc.run(heldout=True, reason="test", results=tmp_path / "mc")
    nb = synthetic.write(tmp_path / "nb", rows=1000)["syn_fail"]
    with pytest.raises(he.HeldoutEnvironmentError):
        rn.run(nb, tmp_path / "rn", rn.Limits())
    assert seen == [tmp_path / "mc" / "heldout", tmp_path / "rn"]  # each run's own results folder
    assert not (tmp_path / "mc" / "heldout" / "results.jsonl").exists()
