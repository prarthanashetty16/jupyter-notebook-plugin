"""env_info works where psutil has no cpu_freq (CI, macOS): the frequency is recorded as unknown."""

from __future__ import annotations

import psutil


def test_env_info_without_cpu_freq(monkeypatch):
    from benchmarks import runner

    monkeypatch.delattr(psutil, "cpu_freq", raising=False)
    env = runner.env_info()
    assert env["cpu_max_mhz"] == ""
