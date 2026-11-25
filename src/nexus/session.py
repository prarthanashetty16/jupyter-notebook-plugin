"""Per-shell session: hook bodies with strict fail-safe behaviour and a re-entrancy guard."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from nexus.failsafe import Deadline, run_with_timeout
from nexus.pipeline import CellReport, Pipeline
from nexus.render import fallback_notes, format_report
from nexus.risk import RiskReport, assess
from nexus.suggestions.format import describe_all

log = logging.getLogger("nexus")

DEFAULT_BUDGET_S = 0.25
DEFAULT_TIER = 1  # Phase 6c: statistics on by default; Tier 2 dry runs are opt-in (%nexus tier 2)
_GRACE_S = 0.05


class NexusSession:
    """State and hook handlers for one IPython shell.

    Every hook body swallows all exceptions (logged at debug level). ``_in_hook`` stops NEXUS
    from analysing anything triggered while it is already analysing; ``_active`` counts cells
    between pre_run_cell and post_run_cell so a cell run from inside a cell
    (``get_ipython().run_cell``) is ignored instead of clobbering the outer one.
    """

    def __init__(
        self,
        shell: Any,
        *,
        pipeline: Pipeline | None = None,
        budget_s: float = DEFAULT_BUDGET_S,
        printer: Callable[[str], None] | None = None,
    ) -> None:
        self._shell = shell
        self.pipeline = pipeline or Pipeline(tier=DEFAULT_TIER)
        self.budget_s = budget_s
        self._printer = printer or print
        self.enabled = True
        self.verbose = False
        self.last_report: CellReport | None = None
        self.last_risk: RiskReport | None = None
        self.last_source: str | None = None
        self.deadline_firings = 0
        self.suggestions: list[Any] = []
        self.enabled_rules: set[str] = (
            set()
        )  # suggestion rules that are off by default and opted in
        self._in_hook = False
        self._active = 0

    def pre_run_cell(self, *args: Any) -> None:
        try:
            self._pre(args[0] if args else None)
        except Exception:
            log.debug("nexus: pre_run_cell failed", exc_info=True)

    def post_run_cell(self, *args: Any) -> None:
        try:
            if self._in_hook:
                return
            if self._active > 0:
                self._active -= 1
        except Exception:
            log.debug("nexus: post_run_cell failed", exc_info=True)

    def _pre(self, info: Any) -> None:
        if self._in_hook:
            return
        self._active += 1
        try:
            if self._active > 1 or not self.enabled:
                return
            source = getattr(info, "raw_cell", None)
            if not isinstance(source, str) or not source.strip():
                return
            self._in_hook = True
            try:
                self.last_report = None
                self.last_risk = None
                self.last_source = source
                self.suggestions = []
                deadline = Deadline(self.budget_s)
                namespace = self._shell.user_ns
                pipeline = self.pipeline
                try:
                    report = run_with_timeout(
                        lambda: pipeline.run(source, namespace, deadline), self.budget_s + _GRACE_S
                    )
                except TimeoutError:
                    self.deadline_firings += 1
                    log.debug("nexus: hard analysis deadline fired; cell left unestimated")
                    return
                self.last_report = report
                self.last_risk = assess(report)
                risk = self.last_risk
                if self.verbose:
                    self._printer(format_report(report))
                    if risk is not None:
                        self._printer(risk.format())
                elif risk is not None and risk.risk.is_alert:
                    notes = "".join("\n  " + n for n in fallback_notes(report))
                    self._printer(
                        risk.format() + notes + "\n  (%nexus suggestions for ways to lower it)"
                    )
            finally:
                self._in_hook = False
        except BaseException as exc:
            if not isinstance(exc, Exception):
                self._active = max(0, self._active - 1)
            raise

    def set_tier(self, tier: int) -> str:
        """Tier 0 (closed form), 1 (statistics, the default) or 2 (the controller may dry-run)."""
        self.pipeline = Pipeline(tier=tier)
        extra = " (Tier 2 dry runs enabled: the controller may escalate)" if tier == 2 else ""
        return f"[nexus] tier {tier}{extra}"

    def status(self) -> str:
        parts = [
            f"NEXUS: {'on' if self.enabled else 'off'}",
            f"tier {getattr(self.pipeline, '_tier', '?')}",
            f"verbose {'on' if self.verbose else 'off'}",
            f"models registered: {len(self.pipeline.registry)}",
            f"time budget: {self.budget_s * 1000:.0f} ms",
            f"hard-deadline firings: {self.deadline_firings}",
        ]
        if self.last_report is not None:
            parts.append(f"last analysis: {self.last_report.elapsed_s * 1000:.1f} ms")
        return ", ".join(parts)

    def explain(self) -> str:
        """Full report of the last analysed cell (operations, estimates, risk)."""
        if self.last_report is None:
            return "[nexus] no analysed cell yet"
        parts = [format_report(self.last_report)]
        if self.last_risk is not None:
            parts.append(self.last_risk.format())
        return "\n".join(parts)

    def set_rule(self, name: str, enable: bool) -> str:
        """Opt a suggestion rule that is off by default in or out; unknown names are refused."""
        from nexus.suggestions.rules import RULES

        known = {r.name: r for r in RULES}
        if name not in known:
            return f"[nexus] unknown rule {name!r}; known: {', '.join(sorted(known))}"
        (self.enabled_rules.add if enable else self.enabled_rules.discard)(name)
        default = known[name].enabled_by_default
        return f"[nexus] rule {name}: {'on' if default or name in self.enabled_rules else 'off'}"

    def show_suggestions(self, namespace: Any) -> str:
        """Compute and list ranked suggestions for the last cell (nothing is executed)."""
        from nexus.suggestions import suggest

        report, source = self.last_report, self.last_source
        if report is None or not report.ops or source is None:
            return "[nexus] no analysed cell with a known operation"
        self.suggestions = suggest(
            source, namespace, report.inspection, report.ops, enable=self.enabled_rules
        )
        if not self.suggestions:
            return "[nexus] no suggestion that is provably safe and saves enough memory"
        lines = describe_all(self.suggestions)
        lines.append("Use %nexus apply <n> to print the modified source (it is not run).")
        return "\n".join(lines)

    def apply(self, n: int) -> str:
        """The modified source of suggestion ``n``; never executed or written anywhere."""
        if not 1 <= n <= len(self.suggestions):
            return "[nexus] no such suggestion; run %nexus suggestions first"
        sg = self.suggestions[n - 1]
        return (
            f"# suggested cell (NOT executed) - {sg.title} [{sg.semantics}]\n{sg.modified_source}"
        )
