"""Keep tests independent of any machine profile / calibration cached in the user's directories,
and of the git state: held-out code paths call ``benchmarks.frozen.require_frozen``, which tests
replace with a stub (``test_timecal`` checks the real guard logic and that the paths call it)."""

from __future__ import annotations

import pytest

from nexus import timecal
from nexus.machine import ENV_VAR, machine


@pytest.fixture(autouse=True)
def _isolated_machine_profile(tmp_path_factory, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path_factory.mktemp("profile") / "machine.json"))
    monkeypatch.delenv(timecal.ENV_VAR, raising=False)  # the packaged artifact
    machine.cache_clear()
    timecal.artifact.cache_clear()
    yield
    machine.cache_clear()
    timecal.artifact.cache_clear()


@pytest.fixture(autouse=True)
def _frozen_stub(monkeypatch):
    import benchmarks.frozen as frozen

    stub = {"frozen_tag": "test-stub", "frozen_commit": "test", "head": "test"}
    monkeypatch.setattr(frozen, "require_frozen", lambda tag=frozen.FROZEN_TAG: stub)
