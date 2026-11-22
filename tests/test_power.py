"""Power state and the calibration CLI's power policy (Phase 6b), with faked power sources."""

from __future__ import annotations

from collections import namedtuple

import psutil
import pytest

from nexus import calibrate, calibrate_cli, power
from nexus.machine import load_profile

Battery = namedtuple("Battery", "percent secsleft power_plugged")


def _fake(monkeypatch, source):
    if isinstance(source, Exception):

        def raise_(*_a, **_k):
            raise source

        monkeypatch.setattr(psutil, "sensors_battery", raise_)
    else:
        monkeypatch.setattr(psutil, "sensors_battery", lambda: source)


@pytest.mark.parametrize(
    ("source", "state"),
    [
        (Battery(90, -2, True), "mains"),
        (Battery(40, 3600, False), "battery"),
        (None, "unknown"),  # cloud VM / server: no battery sensor
        (RuntimeError("sensor error"), "unknown"),
        (Battery(50, -1, None), "unknown"),
    ],
)
def test_power_state(monkeypatch, source, state):
    _fake(monkeypatch, source)
    assert power.power_state() == state


def _stub_measure(monkeypatch):
    real = calibrate.measure_profile
    monkeypatch.setattr(calibrate, "measure_profile", lambda quick=False: real(quick=True))


@pytest.mark.parametrize(
    ("source", "recorded", "warned"),
    [
        (Battery(90, -2, True), "mains", False),
        (None, "unknown", True),
        (OSError("no sensor access"), "unknown", True),
    ],
)
def test_cli_measures_and_records_power(monkeypatch, capsys, source, recorded, warned):
    _fake(monkeypatch, source)
    _stub_measure(monkeypatch)
    assert calibrate_cli.main(["--force"]) == 0
    err = capsys.readouterr().err
    assert ("power state unknown" in err) is warned
    profile = load_profile()
    assert profile is not None and profile.meta["power"] == recorded
    assert profile.meta["power_end"] == recorded


def test_cli_refuses_only_on_detected_battery(monkeypatch, capsys):
    _fake(monkeypatch, Battery(40, 3600, False))
    real_ensure = calibrate.ensure_profile
    called = []
    monkeypatch.setattr(calibrate, "ensure_profile", lambda **kw: called.append(kw))
    assert calibrate_cli.main(["--force"]) == 2
    assert "on battery power" in capsys.readouterr().err and not called
    # restore only what this test replaced: monkeypatch.undo() would also undo the conftest's
    # isolation of the profile path and write to the user's real cache (a Phase 6b bug)
    monkeypatch.setattr(calibrate, "ensure_profile", real_ensure)
    _stub_measure(monkeypatch)
    assert calibrate_cli.main(["--force", "--allow-battery"]) == 0
    assert load_profile().meta["power"] == "battery"


def test_power_meta_does_not_change_the_profile_id(monkeypatch):
    _fake(monkeypatch, None)
    _stub_measure(monkeypatch)
    calibrate_cli.main(["--force"])
    profile = load_profile()
    from dataclasses import replace

    assert replace(profile, meta={}).profile_id == profile.profile_id
