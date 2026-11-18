"""Suggestion data types and the rule interface (Phase 5, Part B of the pre-registration).

A rule never edits the user's cell and never runs code: it proposes a modified source text, a
semantics label and a *virtual change* of the state; the engine re-estimates the cell on that
virtual state with the frozen models. A rule that cannot prove safety returns None (refuses).
"""

from __future__ import annotations

import ast
import difflib
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from nexus.analyzer import DetectedOp
from nexus.failsafe import Deadline
from nexus.models.base import Estimate
from nexus.state import FileDescriptor, FrameDescriptor, Inspection

PRESERVING = "preserving"
CHANGES_PRECISION = "changes_precision"
CHANGES_DTYPE = "changes_dtype"
CHANGES_RESULTS = "changes_results"
SEMANTICS = (PRESERVING, CHANGES_PRECISION, CHANGES_DTYPE, CHANGES_RESULTS)  # least change first


@dataclass(frozen=True, kw_only=True)
class VirtualChange:
    """What a suggestion does to the state the estimator sees (nothing is executed or mutated).

    ``frames`` / ``files`` replace descriptors; ``temp_bytes`` is memory the modified cell holds
    in addition to the operation's own peak (e.g. the narrowed copy of an operand); ``transient``
    is added to ``high`` only. ``descriptor_saving`` is used by rules whose saving is the exact
    size of an avoided allocation and for which no frozen operation model exists (copy, delete).
    """

    frames: dict[str, FrameDescriptor] = field(default_factory=dict)
    files: dict[str, FileDescriptor] = field(default_factory=dict)
    temp_bytes: int = 0
    transient: int = 0
    descriptor_saving: int | None = None


@dataclass(frozen=True, kw_only=True)
class Suggestion:
    rule: str
    title: str
    explanation: str
    original_source: str
    modified_source: str
    semantics: str
    semantics_detail: str
    virtual: VirtualChange = field(default_factory=VirtualChange, repr=False)
    kind: str = "peak"  # "peak": lowers the cell's peak; "headroom": frees memory for later cells
    op_name: str = ""
    before: Estimate | None = None
    after: Estimate | None = None
    saving_bytes: int = 0
    saving_frac: float = 0.0
    estimate_source: str = "model"  # "model" (frozen estimator on virtual state) | "descriptor"
    notes: tuple[str, ...] = ()

    def diff(self) -> str:
        a = self.original_source.splitlines()
        b = self.modified_source.splitlines()
        return "\n".join(difflib.unified_diff(a, b, "cell", "cell (suggested)", lineterm="", n=0))


@dataclass(kw_only=True)
class Context:
    """Read-only inputs of a rule."""

    source: str
    tree: ast.Module
    op: DetectedOp
    inspection: Inspection
    namespace: Mapping[str, Any]
    deadline: Deadline
    all_ops: list[DetectedOp] = field(default_factory=list)


class SuggestionRule(ABC):
    name: ClassVar[str]
    ops: ClassVar[tuple[str, ...]] = ()

    def applies(self, op: DetectedOp, state: Inspection) -> bool:
        """Cheap syntactic / state check; the default only checks the operation name."""
        return op.name in self.ops

    @abstractmethod
    def propose(self, ctx: Context) -> Suggestion | None:
        """A suggestion, or None when safety cannot be proved."""
