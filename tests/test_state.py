"""State inspector and resource probe tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nexus.analyzer import analyze_cell
from nexus.state import (
    ArrayDescriptor,
    FrameDescriptor,
    ResourceProbe,
    SeriesDescriptor,
    StateInspector,
    candidate_paths,
    describe_file,
    read_cgroup_memory,
)


def inspect(obj, **kwargs):
    return StateInspector(**kwargs).inspect(["x"], {"x": obj})


def test_numeric_frame_exact():
    df = pd.DataFrame({"a": np.arange(1000), "b": np.random.default_rng(0).random(1000)})
    desc = inspect(df).variables["x"]
    assert isinstance(desc, FrameDescriptor)
    assert desc.shape == (1000, 2)
    assert desc.dtypes == {"a": "int64", "b": "float64"}
    assert desc.dtype_counts == {"int64": 1, "float64": 1}
    assert desc.index_kind == "RangeIndex"
    assert desc.nbytes == int(df.memory_usage(deep=True).sum())
    assert not desc.sampled and desc.text_columns == 0


def test_text_frame_small_matches_deep_exactly():
    df = pd.DataFrame({"s": [f"value-{i}" for i in range(500)], "n": range(500)})
    desc = inspect(df).variables["x"]
    assert desc.nbytes == int(df.memory_usage(deep=True).sum())
    assert desc.text_columns == 1 and not desc.sampled


def test_text_frame_large_is_sampled_and_close():
    n = 20_000
    df = pd.DataFrame({"s": [f"value-{i:08d}" for i in range(n)], "n": np.arange(n)})
    desc = inspect(df, sample_rows=1000).variables["x"]
    true = int(df.memory_usage(deep=True).sum())
    assert desc.sampled
    assert abs(desc.nbytes - true) / true < 0.05


def test_string_index_counted():
    df = pd.DataFrame({"n": range(100)}, index=[f"row-{i}" for i in range(100)])
    desc = inspect(df).variables["x"]
    assert desc.index_nbytes > 100 * 8
    assert desc.nbytes == int(df.memory_usage(deep=True).sum())


def test_multiindex_and_empty_frames():
    mi = pd.DataFrame({"v": [1, 2]}, index=pd.MultiIndex.from_tuples([("a", 1), ("b", 2)]))
    assert inspect(mi).variables["x"].shape == (2, 1)
    assert inspect(pd.DataFrame()).variables["x"].shape == (0, 0)


def test_series_numeric_and_text():
    s = pd.Series(np.arange(100.0))
    desc = inspect(s).variables["x"]
    assert isinstance(desc, SeriesDescriptor)
    assert desc.shape == (100,) and desc.dtype == "float64"
    assert desc.nbytes == int(s.memory_usage(deep=True))
    t = pd.Series([f"v{i}" for i in range(300)])
    assert inspect(t).variables["x"].nbytes == int(t.memory_usage(deep=True))


def test_ndarray_and_memmap(tmp_path):
    arr = np.zeros((10, 20), dtype=np.float32)
    desc = inspect(arr).variables["x"]
    assert isinstance(desc, ArrayDescriptor)
    assert (desc.shape, desc.dtype, desc.nbytes, desc.memmap) == ((10, 20), "float32", 800, False)
    mm = np.memmap(tmp_path / "m.bin", dtype="float64", mode="w+", shape=(4,))
    assert inspect(mm).variables["x"].memmap is True
    del mm


def test_unknown_objects_and_missing_names_ignored():
    result = StateInspector().inspect(["a", "b", "nope"], {"a": [1, 2], "b": "text"})
    assert result.variables == {} and result.skipped == ()


def test_zero_budget_skips_everything():
    ns = {"a": np.zeros(3), "b": np.zeros(3)}
    result = StateInspector(time_budget_s=0.0).inspect(["a", "b"], ns, paths=["p"])
    assert result.variables == {}
    assert result.skipped == ("a", "b", "p")


def test_description_failure_is_skipped_not_raised():
    class Bad(pd.DataFrame):
        @property
        def shape(self):
            raise RuntimeError("boom")

    result = StateInspector().inspect(["x"], {"x": Bad({"a": [1]})})
    assert result.skipped == ("x",)


def test_describe_file(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("a,b\n1,2\n")
    assert describe_file(str(f)).nbytes == f.stat().st_size
    assert describe_file(str(tmp_path)) is None
    assert describe_file(str(tmp_path / "missing.csv")) is None
    assert describe_file("bad\x00path") is None
    assert describe_file("a,b\n1,2\n") is None


def test_candidate_paths_and_file_inspection(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("x\n1\n")
    (op,) = analyze_cell(f"import pandas as pd\npd.read_csv({str(f)!r}, sep=',')")
    assert candidate_paths(op) == [str(f)]
    result = StateInspector().inspect([], {}, paths=candidate_paths(op))
    assert result.files[str(f)].nbytes == f.stat().st_size
    (variable_op,) = analyze_cell("import pandas as pd\npd.read_csv(path)")
    assert candidate_paths(variable_op) == []
    (other,) = analyze_cell('df.merge(o, on="x.csv")')
    assert candidate_paths(other) == []


# -- resources -----------------------------------------------------------------------------
def test_probe_live_snapshot():
    snap = ResourceProbe().snapshot()
    assert 0 < snap.available_ram <= snap.total_ram
    assert snap.effective_available <= snap.available_ram
    assert snap.effective_total <= snap.total_ram


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_cgroup_v2(tmp_path):
    _write(tmp_path / "memory.max", "1073741824\n")
    _write(tmp_path / "memory.current", "536870912\n")
    _write(tmp_path / "memory.stat", "anon 1\ninactive_file 104857600\n")
    cg = read_cgroup_memory(tmp_path, tmp_path / "no-proc-file")
    assert (cg.version, cg.limit, cg.usage) == (2, 1073741824, 536870912 - 104857600)


def test_cgroup_v2_unlimited_and_nested(tmp_path):
    _write(tmp_path / "memory.max", "max\n")
    _write(tmp_path / "memory.current", "5\n")
    assert read_cgroup_memory(tmp_path, tmp_path / "none") is None
    proc = tmp_path / "proc_cgroup"
    _write(proc, "0::/job/a\n")
    _write(tmp_path / "job" / "a" / "memory.max", "2048\n")
    _write(tmp_path / "job" / "a" / "memory.current", "1024\n")
    cg = read_cgroup_memory(tmp_path, proc)
    assert (cg.limit, cg.usage) == (2048, 1024)


def test_cgroup_v1(tmp_path):
    _write(tmp_path / "memory" / "memory.limit_in_bytes", "2147483648\n")
    _write(tmp_path / "memory" / "memory.usage_in_bytes", "1000\n")
    _write(tmp_path / "memory" / "memory.stat", "total_inactive_file 400\n")
    cg = read_cgroup_memory(tmp_path, tmp_path / "none")
    assert (cg.version, cg.limit, cg.usage) == (1, 2147483648, 600)


def test_cgroup_v1_unlimited_sentinel(tmp_path):
    _write(tmp_path / "memory" / "memory.limit_in_bytes", "9223372036854771712\n")
    _write(tmp_path / "memory" / "memory.usage_in_bytes", "1000\n")
    assert read_cgroup_memory(tmp_path, tmp_path / "none") is None


def test_probe_uses_cgroup_limit(tmp_path):
    _write(tmp_path / "memory.max", "1024\n")
    _write(tmp_path / "memory.current", "24\n")
    probe = ResourceProbe(cgroup_root=tmp_path, proc_cgroup=tmp_path / "none", read_cgroups=True)
    snap = probe.snapshot()
    assert snap.cgroup is not None
    assert snap.effective_total == 1024 and snap.effective_available == 1000


def test_probe_ignores_cgroups_when_disabled(tmp_path):
    _write(tmp_path / "memory.max", "1024\n")
    _write(tmp_path / "memory.current", "24\n")
    probe = ResourceProbe(cgroup_root=tmp_path, read_cgroups=False)
    assert probe.snapshot().cgroup is None


@pytest.mark.parametrize("bad", ["", "garbage", "-"])
def test_cgroup_garbage_is_ignored(tmp_path, bad):
    _write(tmp_path / "memory.max", bad)
    _write(tmp_path / "memory.current", bad)
    assert read_cgroup_memory(tmp_path, tmp_path / "none") is None


# -- memory blocks (informational feature) ---------------------------------------------------------
def test_block_info_single_multi_and_consolidated():
    from nexus.state import frame_block_info

    arrays = {f"f{i}": np.arange(100.0) for i in range(3)}
    multi = pd.DataFrame(arrays, copy=False)
    n_blocks, consolidated = frame_block_info(multi)
    assert n_blocks == 3 and consolidated is False
    merged = multi.copy()
    assert frame_block_info(merged) == (1, True)
    mixed = pd.DataFrame({"i": np.arange(10), "f": np.arange(10.0)})
    assert frame_block_info(mixed) == (2, True)


def test_descriptor_carries_blocks_and_inspection_does_not_mutate():
    from nexus.state import frame_block_info

    df = pd.DataFrame({f"f{i}": np.arange(50.0) for i in range(4)}, copy=False)
    before = frame_block_info(df)
    desc = inspect(df).variables["x"]
    assert (desc.n_blocks, desc.consolidated) == before == (4, False)
    assert frame_block_info(df) == before  # no consolidation as a side effect


def test_block_info_degrades_gracefully(monkeypatch):
    import types

    from nexus import state
    from nexus.state import frame_block_info

    assert frame_block_info(object()) == (None, None)
    assert frame_block_info(types.SimpleNamespace(_mgr=types.SimpleNamespace())) == (None, None)

    class Boom:
        @property
        def _mgr(self):
            raise RuntimeError("pandas internals changed")

    assert frame_block_info(Boom()) == (None, None)
    monkeypatch.setattr(state, "frame_block_info", lambda df: (None, None))
    df = pd.DataFrame({"a": [1, 2, 3]})
    desc = inspect(df).variables["x"]
    assert desc.n_blocks is None and desc.consolidated is None and desc.shape == (3, 1)
