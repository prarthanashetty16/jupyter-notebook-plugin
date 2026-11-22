"""Phase 6d: the machine-profile / power check of held-out runs (benchmarks.heldout_env)."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

import benchmarks.heldout_env as he
from nexus import machine as machine_mod
from nexus.machine import reference_profile, save_profile


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


def _profile(**meta):
    ref = reference_profile()
    return replace(ref, meta={**ref.meta, **meta})


def test_reference_machine_accepts_only_the_reference_profile(real_check, monkeypatch):
    _reference_identity(monkeypatch, real_check, same=True)
    save_profile(reference_profile())
    rec = real_check.require_profile()
    assert rec["profile_id"] == reference_profile().profile_id and rec["profile_mode"].startswith(
        "reference"
    )
    corrupted = machine_mod.scaled(
        reference_profile(), 10.0
    )  # e.g. a quick battery profile over it
    save_profile(replace(corrupted, meta={**corrupted.meta, "quick": True}))
    with pytest.raises(real_check.HeldoutEnvironmentError, match="not the reference profile"):
        real_check.require_profile()


def test_new_machine_needs_a_fresh_full_mains_profile(real_check, monkeypatch):
    _reference_identity(monkeypatch, real_check, same=False)
    now = time.time()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 3600))
    save_profile(_profile(timestamp=stamp, quick=False, power="unknown"))
    rec = real_check.require_profile(now=now)
    assert rec["profile_mode"].startswith("new machine") and rec["profile_id"]
    old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 24 * 3600))
    save_profile(_profile(timestamp=old, quick=False))
    with pytest.raises(real_check.HeldoutEnvironmentError, match="in this session"):
        real_check.require_profile(now=now)
    save_profile(_profile(timestamp=stamp, quick=True))
    with pytest.raises(real_check.HeldoutEnvironmentError, match="quick"):
        real_check.require_profile(now=now)
    save_profile(_profile(timestamp=stamp, quick=False, power="battery"))
    with pytest.raises(real_check.HeldoutEnvironmentError, match="battery"):
        real_check.require_profile(now=now)


def test_battery_now_and_missing_profile_are_refused(real_check, monkeypatch):
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "battery")
    with pytest.raises(real_check.HeldoutEnvironmentError, match="battery"):
        real_check.require_profile()
    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    with pytest.raises(real_check.HeldoutEnvironmentError, match="no calibrated"):
        real_check.require_profile()  # the conftest's isolated profile path is empty


def test_heldout_entry_points_call_the_check(monkeypatch, tmp_path):
    from benchmarks.multicell import run as mc
    from benchmarks.realworld import run_notebook as rn
    from benchmarks.realworld import synthetic

    def refuse(now=None):
        raise he.HeldoutEnvironmentError("refused (test)")

    monkeypatch.setattr(he, "require_profile", refuse)
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    with pytest.raises(he.HeldoutEnvironmentError):
        mc.run(heldout=True, reason="test", results=tmp_path / "mc")
    nb = synthetic.write(tmp_path / "nb", rows=1000)["syn_fail"]
    with pytest.raises(he.HeldoutEnvironmentError):
        rn.run(nb, tmp_path / "rn", rn.Limits())
    assert not (tmp_path / "mc" / "heldout" / "results.jsonl").exists()
