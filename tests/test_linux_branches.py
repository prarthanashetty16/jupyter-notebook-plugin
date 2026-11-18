"""The Linux / POSIX branches of the platform layer, exercised on any OS with fakes.

The developer machine is Windows, so these branches (VmRSS / VmHWM from /proc, the peak reset through
/proc/self/clear_refs, ru_maxrss, page faults through ``resource``, cgroup files, /proc/cpuinfo) only
run for real on the Linux VM. Here they run against synthetic /proc content and a fake ``resource``
module so that a parsing or portability bug shows up before the VM does.
"""

from __future__ import annotations

import io
import subprocess
import sys
import types
from pathlib import Path

import pytest

from nexus import measure

STATUS = (
    "Name:\tpython\nVmPeak:\t  999999 kB\nVmHWM:\t  234567 kB\nVmRSS:\t  123456 kB\nThreads:\t1\n"
)


def _fake_open(files: dict[str, str], written: list[tuple[str, str]] | None = None):
    def fake(path, mode="r", *a, **k):
        path = str(path)
        if "w" in mode:
            if files.get(path) == "DENIED":
                raise PermissionError(path)
            buf = io.StringIO()
            buf.close = lambda p=path, b=buf: (
                written.append((p, b.getvalue())) if written is not None else None
            )  # type: ignore[method-assign]
            return buf
        if path not in files:
            raise FileNotFoundError(path)
        return io.StringIO(files[path])

    return fake


@pytest.fixture
def linux(monkeypatch):
    monkeypatch.setattr(measure.sys, "platform", "linux")
    return monkeypatch


def test_read_memory_parses_vmrss_and_vmhwm_in_kib(linux):
    linux.setattr(measure, "open", _fake_open({"/proc/self/status": STATUS}), raising=False)
    r = measure.read_memory()
    assert (r.rss, r.peak) == (123456 * 1024, 234567 * 1024)


def test_read_memory_of_another_pid_reads_that_pids_status(linux):
    linux.setattr(measure, "open", _fake_open({"/proc/4242/status": STATUS}), raising=False)
    assert measure.read_memory(4242).peak == 234567 * 1024


def test_read_memory_falls_back_to_psutil_and_ru_maxrss_when_proc_is_unreadable(linux):
    fake_resource = types.SimpleNamespace(
        RUSAGE_SELF=0, getrusage=lambda who: types.SimpleNamespace(ru_maxrss=5000)
    )
    linux.setitem(sys.modules, "resource", fake_resource)
    linux.setattr(
        measure, "open", _fake_open({}), raising=False
    )  # /proc missing (a restricted sandbox)
    r = measure.read_memory()
    assert r.rss > 0 and r.peak == 5000 * 1024  # Linux ru_maxrss is in KiB


def test_read_memory_macos_style_ru_maxrss_is_in_bytes(monkeypatch):
    monkeypatch.setattr(measure.sys, "platform", "darwin")
    fake_resource = types.SimpleNamespace(
        RUSAGE_SELF=0, getrusage=lambda who: types.SimpleNamespace(ru_maxrss=7_000_000)
    )
    monkeypatch.setitem(sys.modules, "resource", fake_resource)
    assert measure.read_memory().peak == 7_000_000


def test_reset_peak_writes_5_to_clear_refs_and_reports_success(linux):
    written: list[tuple[str, str]] = []
    linux.setattr(measure, "open", _fake_open({}, written), raising=False)
    assert measure.reset_peak() is True
    assert written == [("/proc/self/clear_refs", "5")]  # "5" resets the peak RSS (VmHWM)


def test_reset_peak_is_false_where_clear_refs_is_not_writable(linux):
    linux.setattr(measure, "open", _fake_open({"/proc/self/clear_refs": "DENIED"}), raising=False)
    assert measure.reset_peak() is False  # containers / gVisor: runs are then censored, not wrong


def test_reset_peak_is_false_off_linux(monkeypatch):
    monkeypatch.setattr(measure.sys, "platform", "win32")
    assert measure.reset_peak() is False


def test_read_faults_uses_minor_plus_major_on_unix(monkeypatch):
    monkeypatch.setattr(measure.sys, "platform", "linux")
    ru = types.SimpleNamespace(ru_minflt=100, ru_majflt=7)
    monkeypatch.setitem(
        sys.modules, "resource", types.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda who: ru)
    )
    assert measure.read_faults() == (107, 7)


def test_the_runner_reads_distribution_and_cpu_model_from_linux_files(monkeypatch):
    from benchmarks import runner

    real = Path.read_text

    def fake_read_text(self, *a, **k):
        name = str(self).replace("\\", "/")
        if name == "/etc/os-release":
            return 'NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 22.04.4 LTS"\n'
        if name == "/proc/cpuinfo":
            return "processor\t: 0\nmodel name\t: AMD EPYC 7B13\n"
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    assert runner._os_release() == "Ubuntu 22.04.4 LTS" and runner._cpu_model() == "AMD EPYC 7B13"
    monkeypatch.setattr(
        Path, "read_text", lambda self, *a, **k: (_ for _ in ()).throw(OSError("no such file"))
    )
    assert runner._os_release() and runner._cpu_model() is not None  # falls back on Windows / macOS


def test_the_sandbox_starts_without_create_no_window(monkeypatch, tmp_path):
    """subprocess.CREATE_NO_WINDOW does not exist on POSIX: the dry run must not depend on it."""
    from nexus import dryrun

    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)
    seen = {}
    real_popen = subprocess.Popen

    def popen(cmd, **kw):
        seen.update(kw)
        return real_popen(
            [sys.executable, "-c", "pass"], **{k: v for k, v in kw.items() if k != "creationflags"}
        )

    monkeypatch.setattr(subprocess, "Popen", popen)
    out = dryrun.run_child({"result": str(tmp_path / "r.json")}, tmp_path / "s.json", 30, 2**31)
    assert (
        out["status"] == "died" and seen["creationflags"] == 0
    )  # no result file: reported, not raised


def test_no_module_uses_fork_or_the_unix_only_resource_at_import_time():
    """Project rule: spawn only; ``resource`` only inside the Unix branches."""
    root = Path(__file__).resolve().parents[1]
    for path in (root / "src" / "nexus").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert 'get_context("fork")' not in text and "os.fork" not in text, path
        for line in text.splitlines():
            if line.startswith("import resource") or line.startswith("from resource"):
                pytest.fail(f"module-level resource import in {path}")
