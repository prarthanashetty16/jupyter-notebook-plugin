"""The dev-only --allow-battery option: refused without the flag, for held-out and for calibration; recorded
as 'battery (user-accepted)' with raw readings when used."""

from __future__ import annotations

import pytest

from benchmarks import powerguard


@pytest.fixture
def on_battery(monkeypatch):
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "battery")
    monkeypatch.setattr(
        powerguard, "psutil_reading", lambda: "sbattery(percent=90, power_plugged=False)"
    )
    monkeypatch.setattr(
        powerguard, "wmi_reading", lambda: {"PowerOnline": False, "Discharging": True}
    )
    monkeypatch.delenv(powerguard.ENV_FLAG, raising=False)


def test_refused_without_the_flag_and_outside_dev(on_battery):
    with pytest.raises(SystemExit):
        powerguard.power_record(False, "dev")
    for context in ("heldout", "calibrate"):
        with pytest.raises(SystemExit, match="refused"):
            powerguard.power_record(True, context)


def test_accepted_dev_run_records_the_raw_readings(on_battery, monkeypatch):
    rec = powerguard.power_record(True, "dev")
    assert rec["power"] == powerguard.ACCEPTED == "battery (user-accepted)"
    assert (
        "power_plugged=False" in rec["battery_psutil"] and rec["battery_wmi"]["Discharging"] is True
    )
    assert powerguard.recorded("battery") == powerguard.ACCEPTED  # rows of this step
    assert powerguard.recorded("mains") == "mains"
    monkeypatch.delenv(powerguard.ENV_FLAG)
    assert powerguard.recorded("battery") == "battery"  # outside an accepted step: unchanged


def test_mains_needs_no_flag(monkeypatch):
    import nexus.power

    monkeypatch.setattr(nexus.power, "power_state", lambda: "mains")
    assert powerguard.power_record(False, "heldout") == {"power": "mains"}


def test_heldout_notebook_run_refuses_the_flag(on_battery, tmp_path):
    from benchmarks.realworld import run_notebook

    nb = tmp_path / "x.ipynb"
    nb.write_text('{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}')
    with pytest.raises(SystemExit):
        run_notebook.run(nb, tmp_path / "out", allow_battery=True, dev=False)


def test_stop_level(monkeypatch, on_battery):
    monkeypatch.setattr(powerguard, "battery_percent", lambda: 29.0)
    assert powerguard.below_stop_level()
    monkeypatch.setattr(powerguard, "battery_percent", lambda: 31.0)
    assert not powerguard.below_stop_level()


def test_report_note_says_timings_are_unusable():
    assert "NOT usable for calibration" in powerguard.BATTERY_NOTE
