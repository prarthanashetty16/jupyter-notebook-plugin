"""Cheap, bounded-time descriptors of live kernel state and machine resources.

Pandas/numpy are looked up in ``sys.modules`` rather than imported: if the user holds a
DataFrame, pandas is already loaded. Anything expensive (deep memory of text columns) is
measured on a deterministic strided sample and scaled. A hard time budget applies; variables
not described in time are reported in ``Inspection.skipped``, never partially described.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil

from nexus.analyzer import DetectedOp, Expr
from nexus.failsafe import Deadline

log = logging.getLogger("nexus")

_MISSING = object()
CGROUP_ROOT = Path("/sys/fs/cgroup")
PROC_CGROUP = Path("/proc/self/cgroup")


# -- descriptors -------------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class Descriptor:
    """Base descriptor. ``nbytes`` is in-memory size (file size on disk for files).

    ``sampled`` is True when ``nbytes`` was extrapolated from a row sample.
    """

    name: str
    kind: str
    nbytes: int
    sampled: bool = False


@dataclass(frozen=True, kw_only=True)
class FrameDescriptor(Descriptor):
    kind: str = "DataFrame"
    shape: tuple[int, int]
    dtypes: dict[str, str]
    dtype_counts: dict[str, int]
    index_kind: str
    index_nbytes: int
    text_columns: int
    n_blocks: int | None = None  # pandas memory blocks; None if not introspectable
    consolidated: bool | None = None  # True if no two blocks share a dtype
    # What a row-moving operation (take, concat, boolean mask) copies: numeric values and, for
    # text, the 8-byte pointers only. Excludes the string objects (shared, never copied) and the
    # index. None for descriptors built without it; ``moved_bytes`` then falls back to ``nbytes``.
    shallow_bytes: int | None = None
    # v4 item (1b): a frame made in the cell by a deep ``copy()`` of a kernel frame holds that frame's values, so
    # Tier 1 statistics may read the kernel object of this name (None: no such object, statistics are skipped)
    stats_alias: str | None = None

    @property
    def moved_bytes(self) -> int:
        """Bytes copied when rows are taken, concatenated or filtered (see ``shallow_bytes``)."""
        return self.shallow_bytes if self.shallow_bytes is not None else self.nbytes


@dataclass(frozen=True, kw_only=True)
class SeriesDescriptor(Descriptor):
    kind: str = "Series"
    shape: tuple[int]
    dtype: str
    index_kind: str
    index_nbytes: int


@dataclass(frozen=True, kw_only=True)
class ArrayDescriptor(Descriptor):
    kind: str = "ndarray"
    shape: tuple[int, ...]
    dtype: str
    memmap: bool = False


@dataclass(frozen=True, kw_only=True)
class FileDescriptor(Descriptor):
    kind: str = "file"


@dataclass(frozen=True, kw_only=True)
class Inspection:
    """Result of one inspection pass; also the ``state`` handed to operation models."""

    variables: dict[str, Descriptor] = field(default_factory=dict)
    files: dict[str, FileDescriptor] = field(default_factory=dict)
    skipped: tuple[str, ...] = ()
    elapsed_s: float = 0.0

    def get(self, name: str) -> Descriptor | None:
        return self.variables.get(name)


# -- files -------------------------------------------------------------------------------
_PATH_KWARGS = frozenset({"filepath_or_buffer", "path", "path_or_buf", "io", "file", "fname"})
_NUMPY_READERS = frozenset({"numpy.load", "numpy.loadtxt", "numpy.genfromtxt"})


def candidate_paths(op: DetectedOp) -> list[str]:
    """String-literal file paths a reader op refers to (first positional arg or path kwargs)."""
    if not (op.name.startswith("pandas.read_") or op.name in _NUMPY_READERS):
        return []
    values: list[Any] = list(op.args[:1])
    values += [v for k, v in op.kwargs.items() if k in _PATH_KWARGS]
    return [v for v in values if isinstance(v, str) and not isinstance(v, Expr)]


def describe_file(path: str) -> FileDescriptor | None:
    """Size on disk of a regular file, or None if it does not exist / is not a file."""
    if not path or len(path) > 4096 or "\n" in path or "\x00" in path:
        return None
    try:
        st = os.stat(os.path.expanduser(path))
    except (OSError, ValueError):
        return None
    if not stat.S_ISREG(st.st_mode):
        return None
    return FileDescriptor(name=path, nbytes=st.st_size)


# -- in-memory objects -------------------------------------------------------------------
def _is_text_like(pd: Any, dtype: Any) -> bool:
    return bool(pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype))


def _stride(obj: Any, step: int) -> Any:
    return obj.iloc[::step] if hasattr(obj, "iloc") else obj[::step]


def frame_block_info(df: Any) -> tuple[int | None, bool | None]:
    """(number of memory blocks, consolidated?) of a DataFrame, or (None, None).

    Reads pandas internals (``_mgr.blocks``) defensively and never mutates the frame: any failure
    (private API change, unusual subclass) yields ``(None, None)``. ``consolidated`` is "no two
    consolidatable blocks share a dtype", which is when pandas would not merge blocks (a deep
    ``copy()`` of a non-consolidated frame stacks each dtype group again). Phase 7b: like pandas'
    ``BlockManager._consolidate_check``, blocks that cannot be consolidated (extension blocks, e.g.
    pandas-3 ``str`` columns) are ignored; counting them marked frames with two text columns as not
    consolidated, and the copy model then charged a consolidation that never happens
    (docs/benchmarks/phase7a/probes/p1b_nonload_bias.out: 213.6 MiB measured vs 366 expected).
    """
    try:
        blocks = df._mgr.blocks
        dtypes = [str(b.dtype) for b in blocks if getattr(b, "_can_consolidate", True)]
        return len(blocks), len(set(dtypes)) == len(dtypes)
    except Exception:
        return None, None


class StateInspector:
    """Describe variables from a namespace within a hard time budget."""

    def __init__(self, *, time_budget_s: float = 0.1, sample_rows: int = 10_000) -> None:
        self._budget_s = time_budget_s
        self._sample_rows = sample_rows
        self._max_listed_columns = 1000

    def inspect(
        self,
        names: Iterable[str],
        namespace: Mapping[str, Any],
        *,
        paths: Iterable[str] = (),
        deadline: Deadline | None = None,
    ) -> Inspection:
        """Describe ``names`` (DataFrame/Series/ndarray only) and ``paths`` (files on disk).

        Unknown names and other object types are ignored. Names that could not be described
        within the budget, or whose description failed, are listed in ``skipped``.
        """
        t0 = time.perf_counter()
        own = Deadline(self._budget_s)

        def check() -> None:
            own.check()
            if deadline is not None:
                deadline.check()

        variables: dict[str, Descriptor] = {}
        files: dict[str, FileDescriptor] = {}
        skipped: list[str] = []
        for name in dict.fromkeys(names):
            try:
                check()
                obj = namespace.get(name, _MISSING)
                desc = None if obj is _MISSING else self._describe(name, obj, check)
            except TimeoutError:
                skipped.append(name)
                continue
            except Exception:
                log.debug("nexus: could not describe %r", name, exc_info=True)
                skipped.append(name)
                continue
            if desc is not None:
                variables[name] = desc
        for path in dict.fromkeys(paths):
            try:
                check()
            except TimeoutError:
                skipped.append(path)
                continue
            file_desc = describe_file(path)
            if file_desc is not None:
                files[path] = file_desc
        return Inspection(
            variables=variables,
            files=files,
            skipped=tuple(skipped),
            elapsed_s=time.perf_counter() - t0,
        )

    def _describe(self, name: str, obj: Any, check: Callable[[], None]) -> Descriptor | None:
        pd = sys.modules.get("pandas")
        if pd is not None:
            if isinstance(obj, pd.DataFrame):
                return self._frame(name, obj, pd, check)
            if isinstance(obj, pd.Series):
                return self._series(name, obj, pd)
        np = sys.modules.get("numpy")
        if np is not None and isinstance(obj, np.ndarray):
            return ArrayDescriptor(
                name=name,
                nbytes=int(obj.nbytes),
                shape=tuple(int(x) for x in obj.shape),
                dtype=str(obj.dtype),
                memmap=isinstance(obj, np.memmap),
            )
        return None

    def _text_nbytes(self, obj: Any, measure: Callable[[Any, bool], Any]) -> tuple[int, bool]:
        """Deep size of a text-like column/index; strided sample + scaling when large."""
        n = len(obj)
        if n <= self._sample_rows:
            return int(measure(obj, True)), False
        sample = _stride(obj, n // self._sample_rows)
        return int(measure(sample, True) / len(sample) * n), True

    def _index_nbytes(self, index: Any, pd: Any) -> tuple[int, bool]:
        if isinstance(index, pd.MultiIndex) or not _is_text_like(pd, index.dtype):
            return int(index.memory_usage(deep=False)), False
        return self._text_nbytes(index, lambda o, deep: o.memory_usage(deep=deep))

    @staticmethod
    def _series_measure(obj: Any, deep: bool) -> Any:
        return obj.memory_usage(index=False, deep=deep)

    def _frame(self, name: str, df: Any, pd: Any, check: Callable[[], None]) -> FrameDescriptor:
        shallow = df.memory_usage(index=False, deep=False)
        total = int(shallow.sum())
        dtypes = list(df.dtypes)
        sampled = False
        text_columns = 0
        for i, dtype in enumerate(dtypes):
            if _is_text_like(pd, dtype):
                text_columns += 1
                check()
                deep, was_sampled = self._text_nbytes(df.iloc[:, i], self._series_measure)
                total += deep - int(shallow.iloc[i])
                sampled = sampled or was_sampled
        check()
        index_nbytes, index_sampled = self._index_nbytes(df.index, pd)
        cap = self._max_listed_columns
        n_blocks, consolidated = frame_block_info(df)
        return FrameDescriptor(
            name=name,
            nbytes=total + index_nbytes,
            sampled=sampled or index_sampled,
            shape=(int(df.shape[0]), int(df.shape[1])),
            dtypes={str(c): str(d) for c, d in zip(df.columns[:cap], dtypes[:cap], strict=False)},
            dtype_counts=dict(Counter(str(d) for d in dtypes)),
            index_kind=type(df.index).__name__,
            index_nbytes=index_nbytes,
            text_columns=text_columns,
            n_blocks=n_blocks,
            consolidated=consolidated,
            shallow_bytes=int(shallow.sum()),
        )

    def _series(self, name: str, s: Any, pd: Any) -> SeriesDescriptor:
        if _is_text_like(pd, s.dtype):
            values, sampled = self._text_nbytes(s, self._series_measure)
        else:
            values, sampled = int(s.memory_usage(index=False, deep=False)), False
        index_nbytes, index_sampled = self._index_nbytes(s.index, pd)
        return SeriesDescriptor(
            name=name,
            nbytes=values + index_nbytes,
            sampled=sampled or index_sampled,
            shape=(int(len(s)),),
            dtype=str(s.dtype),
            index_kind=type(s.index).__name__,
            index_nbytes=index_nbytes,
        )


# -- machine resources -------------------------------------------------------------------
@dataclass(frozen=True, kw_only=True)
class CgroupMemory:
    """Container memory limit. ``usage`` is the working set (usage minus inactive file cache)."""

    version: int
    limit: int
    usage: int


@dataclass(frozen=True, kw_only=True)
class ResourceSnapshot:
    """``available_ram`` is psutil's *available* (what can be allocated without swapping)."""

    total_ram: int
    available_ram: int
    cgroup: CgroupMemory | None = None
    swap_free: int | None = None  # None: unknown; never added to headroom (see nexus.risk)
    rss: int | None = None  # this kernel's resident set (already excluded from ``available_ram``)

    @property
    def effective_total(self) -> int:
        return min(self.total_ram, self.cgroup.limit) if self.cgroup else self.total_ram

    @property
    def effective_available(self) -> int:
        if self.cgroup is None:
            return self.available_ram
        return min(self.available_ram, max(0, self.cgroup.limit - self.cgroup.usage))


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError):
        return None


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    try:
        return int(text.strip()) if text is not None else None
    except ValueError:
        return None


def _read_limit(path: Path) -> int | None:
    """Limit file value; None for missing, ``max`` or the v1 'unlimited' sentinel."""
    value = _read_int(path)
    return value if value is not None and value < (1 << 60) else None


def _stat_value(path: Path, key: str) -> int:
    for line in (_read_text(path) or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == key:
            try:
                return int(parts[1])
            except ValueError:
                return 0
    return 0


def _relative_cgroup_paths(proc_cgroup: Path) -> tuple[str | None, str | None]:
    """(cgroup v2 path, cgroup v1 memory-controller path) of this process."""
    v2 = v1 = None
    for line in (_read_text(proc_cgroup) or "").splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        hierarchy, controllers, path = parts
        if hierarchy == "0" and controllers == "":
            v2 = path
        elif "memory" in controllers.split(","):
            v1 = path
    return v2, v1


def _candidate_dirs(base: Path, rel: str | None) -> list[Path]:
    dirs = [base]
    if rel and rel.strip("/"):
        dirs.insert(0, base / rel.strip("/"))
    return dirs


def read_cgroup_memory(
    root: Path = CGROUP_ROOT, proc_cgroup: Path = PROC_CGROUP
) -> CgroupMemory | None:
    """Tightest cgroup v2 or v1 memory limit that applies to this process, if any."""
    rel_v2, rel_v1 = _relative_cgroup_paths(proc_cgroup)
    best: CgroupMemory | None = None
    candidates = [
        (2, d, "memory.max", "memory.current", "memory.stat", "inactive_file")
        for d in _candidate_dirs(root, rel_v2)
    ] + [
        (
            1,
            d,
            "memory.limit_in_bytes",
            "memory.usage_in_bytes",
            "memory.stat",
            "total_inactive_file",
        )
        for d in _candidate_dirs(root / "memory", rel_v1)
    ]
    for version, d, limit_file, usage_file, stat_file, inactive_key in candidates:
        limit = _read_limit(d / limit_file)
        usage = _read_int(d / usage_file)
        if limit is None or usage is None:
            continue
        working_set = max(0, usage - _stat_value(d / stat_file, inactive_key))
        found = CgroupMemory(version=version, limit=limit, usage=working_set)
        if best is None or found.limit < best.limit:
            best = found
    return best


class ResourceProbe:
    """Free/total RAM and container memory limit; cgroups are only read on Linux."""

    def __init__(
        self,
        *,
        cgroup_root: Path = CGROUP_ROOT,
        proc_cgroup: Path = PROC_CGROUP,
        read_cgroups: bool | None = None,
    ) -> None:
        self._root = cgroup_root
        self._proc = proc_cgroup
        self._read = sys.platform.startswith("linux") if read_cgroups is None else read_cgroups

    def snapshot(self) -> ResourceSnapshot:
        vm = psutil.virtual_memory()
        cgroup = read_cgroup_memory(self._root, self._proc) if self._read else None
        swap_free = rss = None
        try:
            swap_free = int(psutil.swap_memory().free)
            rss = int(psutil.Process().memory_info().rss)
        except Exception:  # optional extras: never let them hide the RAM figures
            pass
        return ResourceSnapshot(
            total_ram=int(vm.total),
            available_ram=int(vm.available),
            cgroup=cgroup,
            swap_free=swap_free,
            rss=rss,
        )
