"""Plain-text rendering of a CellReport (verbose mode)."""

from __future__ import annotations

from typing import Any

from nexus.analyzer import Expr
from nexus.pipeline import CellReport
from nexus.state import ArrayDescriptor, Descriptor, FrameDescriptor, SeriesDescriptor
from nexus.timebuckets import describe as describe_time


def human_bytes(n: float) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def human_seconds(s: float) -> str:
    return f"{s * 1000:.0f} ms" if s < 1 else f"{s:.1f} s"


def _fmt_value(value: Any) -> str:
    return str(value) if isinstance(value, Expr) else repr(value)


def _describe(desc: Descriptor) -> str:
    approx = " (sampled)" if desc.sampled else ""
    size = f"{human_bytes(desc.nbytes)}{approx}"
    if isinstance(desc, FrameDescriptor):
        blocks = "" if desc.n_blocks is None else f" blocks={desc.n_blocks}"
        return f"DataFrame shape={desc.shape} {size} index={desc.index_kind}{blocks} dtypes={desc.dtype_counts}"
    if isinstance(desc, SeriesDescriptor):
        return f"Series shape={desc.shape} dtype={desc.dtype} {size} index={desc.index_kind}"
    if isinstance(desc, ArrayDescriptor):
        mm = " memmap" if desc.memmap else ""
        return f"ndarray shape={desc.shape} dtype={desc.dtype} {size}{mm}"
    return f"{desc.kind} {size}"


FALLBACK_PREFIX = "reduced-accuracy estimate: statistics unavailable"
_FALLBACK_REASONS = {
    "time budget": "time budget",
    "hard deadline": "hard deadline; Tier 0 estimate retained",
    "frame created in this cell": "frame created in this cell: shapes propagated, no statistics",
    "no statistics": "unsupported arguments",
}


def _has_statistics(model: str) -> bool:
    """True when the model defines Tier 1 statistics (a Tier-0-only model never falls back)."""
    from nexus.models.base import OperationModel
    from nexus.registry import default_registry

    m = default_registry.get(model)
    return m is not None and type(m).tier1_features is not OperationModel.tier1_features


def fallback_reason(item: Any) -> str | None:
    """Why an estimate is Tier 0 although statistics were asked for; None when it is not a fallback.

    A model without statistics (Tier 0 only) is not a fallback. Display only: no estimate or risk
    class depends on it (Phase 6c, item 4).
    """
    t1 = (getattr(item, "features", None) or {}).get("tier1")
    est = getattr(item, "estimate", None)
    if est is None:
        return None
    if est.note and "Tier 1 rejected" in est.note:
        return "statistics rejected by the sanity guard"
    if isinstance(t1, dict) and t1.get("used") is False and est.tier == 0:
        if not _has_statistics(getattr(item, "model", "")):
            return None
        reason = str(t1.get("reason", ""))
        return _FALLBACK_REASONS.get(reason, reason or "statistics failed")
    return None


def fallback_notes(report: CellReport) -> list[str]:
    """One prominent line per estimate that fell back to Tier 0."""
    out = []
    for item in report.estimates:
        why = fallback_reason(item)
        if why:
            out.append(f"{FALLBACK_PREFIX} ({why}) for {item.op.name}")
    return out


def format_report(report: CellReport) -> str:
    """Multi-line text: detected ops, variable/file descriptors, estimates, resources."""
    if not report.ops:
        return "[nexus] no known operations in this cell"
    lines = [
        f"[nexus] {len(report.ops)} operation(s) detected (analysis {human_seconds(report.elapsed_s)})"
    ]
    for op in report.ops:
        args = [_fmt_value(a) for a in op.args] + [
            f"{k}={_fmt_value(v)}" for k, v in op.kwargs.items()
        ]
        lines.append(f"  line {op.lineno}: {op.name}({', '.join(args)}) vars={list(op.variables)}")
    for name, desc in report.inspection.variables.items():
        lines.append(f"  {name}: {_describe(desc)}")
    for path, fdesc in report.inspection.files.items():
        lines.append(f"  file {path}: {human_bytes(fdesc.nbytes)} on disk")
    if report.inspection.skipped:
        lines.append(f"  not inspected (budget/errors): {list(report.inspection.skipped)}")
    for item in report.estimates:
        e = item.estimate
        lines.append(
            f"  estimate {item.op.name} [{item.model}, tier {e.tier}]: "
            f"RAM {human_bytes(e.ram_low)}-{human_bytes(e.ram_high)} "
            f"(expected {human_bytes(e.ram_expected)}), "
            f"time {describe_time(e.time_low, e.time_expected, e.time_high)}, "
            f"confidence {e.confidence:.2f}; drivers: {'; '.join(e.drivers) or 'n/a'}"
            + (f" [{', '.join(e.flags)}]" if e.flags else "")
        )
        why = fallback_reason(item)
        if why:
            lines.append(f"    ** {FALLBACK_PREFIX} ({why}) **")
    if report.resources is not None:
        r = report.resources
        limit = f", container limit {human_bytes(r.cgroup.limit)}" if r.cgroup else ""
        lines.append(
            f"  RAM available {human_bytes(r.effective_available)} of "
            f"{human_bytes(r.effective_total)}{limit}"
        )
    return "\n".join(lines)
