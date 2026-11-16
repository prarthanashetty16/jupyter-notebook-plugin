"""Integration tests: real InteractiveShell with the extension loaded."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pandas as pd
import pytest
from IPython.core.interactiveshell import InteractiveShell
from traitlets.config import Config

from nexus.extension import get_session
from nexus.models.base import OperationModel
from nexus.models.noop import NoopModel
from nexus.pipeline import Pipeline
from nexus.registry import ModelRegistry


@pytest.fixture
def shell():
    cfg = Config()
    cfg.HistoryManager.enabled = False
    InteractiveShell.clear_instance()
    ip = InteractiveShell.instance(config=cfg)
    ip.run_line_magic("load_ext", "nexus")
    yield ip
    ip.run_line_magic("unload_ext", "nexus")
    InteractiveShell.clear_instance()


def use_registry(shell, *models):
    registry = ModelRegistry()
    for model in models:
        registry.add(model)
    session = get_session(shell)
    session.pipeline = Pipeline(registry=registry)
    return session


class Raising(OperationModel):
    name = "raising"

    def matches(self, op):
        return True

    def features(self, op, state):
        raise RuntimeError("model exploded")

    def estimate(self, features, tier):
        raise AssertionError("unreachable")


def test_load_registers_hooks_and_magic(shell):
    session = get_session(shell)
    assert session is not None
    assert session.pre_run_cell in shell.events.callbacks["pre_run_cell"]
    assert session.post_run_cell in shell.events.callbacks["post_run_cell"]
    assert "nexus" in shell.magics_manager.magics["line"]


def test_unload_removes_everything(shell):
    session = get_session(shell)
    shell.run_line_magic("unload_ext", "nexus")
    assert session.pre_run_cell not in shell.events.callbacks["pre_run_cell"]
    assert session.post_run_cell not in shell.events.callbacks["post_run_cell"]
    assert "nexus" not in shell.magics_manager.magics["line"]
    assert get_session(shell) is None
    shell.run_line_magic("load_ext", "nexus")


def test_magics(shell, capsys):
    shell.run_cell("%nexus status")
    assert "NEXUS: on" in capsys.readouterr().out
    shell.run_cell("%nexus off")
    assert "NEXUS: off" in capsys.readouterr().out
    assert get_session(shell).enabled is False
    shell.run_cell("%nexus on")
    shell.run_cell("%nexus verbose on")
    assert get_session(shell).verbose is True
    assert "verbose on" in capsys.readouterr().out
    shell.run_cell("%nexus verbose off")
    assert get_session(shell).verbose is False
    shell.run_cell("%nexus bogus")
    assert "usage" in capsys.readouterr().out


def test_verbose_prints_ops_and_descriptors(shell, capsys):
    use_registry(shell, NoopModel())
    shell.run_cell("%nexus verbose on")
    capsys.readouterr()
    shell.user_ns["df"] = pd.DataFrame({"a": [1, 1, 2], "b": ["x", "x", "y"]})
    result = shell.run_cell('df.drop_duplicates(subset=["a"])')
    out = capsys.readouterr().out
    assert result.success
    assert "drop_duplicates" in out and "subset=['a']" in out
    assert "df: DataFrame shape=(3, 2)" in out
    assert "estimate drop_duplicates [noop, tier 0]" in out


def test_verbose_off_prints_nothing_and_cell_output_intact(shell, capsys):
    shell.user_ns["df"] = pd.DataFrame({"a": [1, 1]})
    result = shell.run_cell("len(df.drop_duplicates())")
    assert result.result == 1
    assert "[nexus]" not in capsys.readouterr().out


def test_disabled_does_no_analysis(shell):
    session = use_registry(shell, NoopModel())
    shell.run_cell("%nexus off")
    session.last_report = None
    shell.user_ns["df"] = pd.DataFrame({"a": [1]})
    shell.run_cell("df.drop_duplicates()")
    assert session.last_report is None


def test_raising_model_never_affects_the_cell(shell, capsys):
    session = use_registry(shell, Raising(), NoopModel())
    shell.run_cell("%nexus verbose on")
    capsys.readouterr()
    shell.user_ns["df"] = pd.DataFrame({"a": [1, 1, 2]})
    result = shell.run_cell("len(df.drop_duplicates())")
    out = capsys.readouterr().out
    assert result.success and result.result == 2
    assert [e.model for e in session.last_report.estimates] == ["noop"]
    assert "exploded" not in out


def test_user_exception_is_untouched(shell, capsys):
    result = shell.run_cell("1 / 0")
    assert isinstance(result.error_in_exec, ZeroDivisionError)
    assert get_session(shell)._active == 0


def test_broken_pipeline_is_silent(shell, capsys):
    session = get_session(shell)

    class Broken:
        registry = ModelRegistry()

        def run(self, *a, **k):
            raise RuntimeError("pipeline exploded")

    session.pipeline = Broken()
    shell.run_cell("%nexus verbose on")
    capsys.readouterr()
    result = shell.run_cell("x = 1 + 1\nx")
    captured = capsys.readouterr()
    assert result.success and result.result == 2
    assert "exploded" not in captured.out + captured.err


def test_slow_analysis_times_out_silently(shell, capsys):
    class Slow(NoopModel):
        name = "slow"

        def features(self, op, state):
            time.sleep(1.0)
            return super().features(op, state)

    session = use_registry(shell, Slow())
    session.budget_s = 0.05
    shell.run_cell("%nexus verbose on")
    capsys.readouterr()
    shell.user_ns["df"] = pd.DataFrame({"a": [1]})
    t0 = time.perf_counter()
    result = shell.run_cell("df.drop_duplicates()")
    elapsed = time.perf_counter() - t0
    assert result.success
    assert elapsed < 0.8
    assert session.last_report is None
    assert "[nexus]" not in capsys.readouterr().out
    assert session._active == 0 and session._in_hook is False


def test_reentrancy_inside_analysis_is_ignored(shell):
    session = get_session(shell)
    calls = []

    class Reentrant(NoopModel):
        name = "reentrant"

        def features(self, op, state):
            session.pre_run_cell(SimpleNamespace(raw_cell="df.drop_duplicates()"))
            session.post_run_cell(None)
            return super().features(op, state)

    class Counting(Pipeline):
        def run(self, *args, **kwargs):
            calls.append(1)
            return super().run(*args, **kwargs)

    registry = ModelRegistry()
    registry.add(Reentrant())
    session.pipeline = Counting(registry=registry)
    shell.user_ns["df"] = pd.DataFrame({"a": [1]})
    shell.run_cell("df.drop_duplicates()")
    assert len(calls) == 1
    assert session._active == 0 and session._in_hook is False
    assert [e.model for e in session.last_report.estimates] == ["reentrant"]


def test_nested_cell_execution_is_not_analyzed(shell):
    session = get_session(shell)
    calls = []

    class Counting(Pipeline):
        def run(self, source, *args, **kwargs):
            calls.append(source)
            return super().run(source, *args, **kwargs)

    session.pipeline = Counting(registry=ModelRegistry())
    shell.user_ns["shell"] = shell
    result = shell.run_cell("shell.run_cell('x = 1')\ny = 2")
    assert result.success
    assert len(calls) == 1 and "shell.run_cell" in calls[0]
    assert session._active == 0
    shell.run_cell("z = 3")
    assert len(calls) == 2


def test_hooks_tolerate_missing_info(shell):
    session = get_session(shell)
    session.pre_run_cell()
    session.pre_run_cell(None)
    session.pre_run_cell(SimpleNamespace(raw_cell=None))
    assert session._active == 3
    for _ in range(4):
        session.post_run_cell()
    assert session._active == 0


def test_real_ipython_process_load_ext():
    """`%load_ext nexus` in a real IPython process, one cell per line via stdin."""
    script = textwrap.dedent(
        """\
        %load_ext nexus
        %nexus verbose on
        import pandas as pd
        df = pd.DataFrame({"a": [1, 1, 2]})
        df.drop_duplicates()
        %nexus status
        exit()
        """
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "IPython",
            "--simple-prompt",
            "--no-banner",
            "--colors=NoColor",
            "--HistoryManager.enabled=False",
            "--TerminalInteractiveShell.confirm_exit=False",
        ],
        input=script,
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    assert "NEXUS: on" in out, out
    assert "drop_duplicates" in out and "DataFrame shape=(3, 1)" in out, out
    assert "Traceback" not in out, out
