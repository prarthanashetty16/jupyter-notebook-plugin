"""Keep tests independent of any machine profile cached in the user's profile directory."""

from __future__ import annotations

import pytest

from nexus.machine import ENV_VAR, machine


@pytest.fixture(autouse=True)
def _isolated_machine_profile(tmp_path_factory, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path_factory.mktemp("profile") / "machine.json"))
    machine.cache_clear()
    yield
    machine.cache_clear()
