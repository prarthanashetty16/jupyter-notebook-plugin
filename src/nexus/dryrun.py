"""Tier 2: sandboxed dry runs on samples, then a scaling fit to the full size.

Pipeline of one dry run (``run_dryrun``):

1. ``dryrun_safety.analyze_safety``: only side-effect-free, fully understood single-operation cells
   qualify (unknown means unsafe). The result is a ``Recipe`` (data), never source text.
2. ``dryrun_sample.build_samples``: nested samples (key-hash for merge / groupby / drop_duplicates,
   row samples elsewhere), written once as ``.npy`` files into a private temp directory.
3. One SANDBOX CHILD per sample size (``python -m nexus._dryrun_child``): a fresh interpreter started
   with ``subprocess`` (not ``multiprocessing``), so it also works from inside another daemon
   process (the benchmark's prediction worker), does not re-import the kernel's ``__main__`` (the
   ``spawn`` constraint on Windows, where a Jupyter kernel's ``__main__`` is not importable), and
   shares no address space with the user's objects. The parent enforces a hard wall-clock timeout
   and a resident-memory cap by killing the child; whatever happens to the child (crash, hang,
   out-of-memory kill) is converted to "no estimate".
4. ``dryrun_fit.fit_scaling`` per quantity (RAM, time): three laws, forward cross-validation,
   extrapolation with model-selection uncertainty; "no estimate" if unreliable.

Measurement floors: a RAM delta under ``RAM_FLOOR_BYTES`` or a time under ``TIME_FLOOR_S`` is
dominated by allocator, page-granularity and timer noise and is not used. If fewer than three sample
sizes remain above the floor the quantity gets no Tier 2 estimate.

Known pitfalls and what is done about them (see PROGRESS.md for the evidence):
* cold-start / first-touch / allocator effects at small sizes: each size runs cold in its own
  process (like the benchmark's measured call) and sizes below the floors are dropped;
* sample-independent fixed costs: the intercept ``a`` of every law;
* hash tables are presized for ``min(n, 2**20 + 7)`` entries: a sample below that cap cannot show
  the saturation of the table, so a fit across the cap is FLAGGED (``crosses_presize_cap``) and
  its RAM is not trusted for hash-based operations;
* key layout (random vs sequential keys changes how many table pages become resident): samples
  by key hash thin dense keys into scattered ones; measured in tests, reported, not corrected.
"""

from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import psutil

from nexus.dryrun_fit import FitResult, fit_scaling
from nexus.dryrun_safety import Recipe, analyze_safety
from nexus.dryrun_sample import NoSampleError, SamplePlan, build_samples
from nexus.failsafe import Deadline
from nexus.models.base import Estimate

log = logging.getLogger("nexus")

MIB = 2**20
RAM_FLOOR_BYTES = 1 * MIB
TIME_FLOOR_S = 0.002
CHILD_TIMEOUT_S = 30.0
CHILD_MEM_CAP = 1 << 30
DEFAULT_BUDGET_S = 40.0
HASH_KINDS = frozenset({"merge", "groupby_agg", "drop_duplicates"})
PRESIZE_CAP = 2**20 + 7
WIDE_RANGE = 1.0  # escalate when (high - low) / expected is at least this
RISK_FRACTION = 0.5  # ... or when the estimate's high exceeds this share of the available RAM
MIN_RUN_S = 5.0  # a dry run costs ~2 s whatever the cell does: below this expected run time a wide
# range is not worth it (on the development data the dry run was cheaper than the real run for only
# 18% of the points); the RAM-risk condition is exempt (an out-of-memory kill costs more than 2 s)
OP_NAMES = {
    "merge": {"merge", "pandas.merge"},
    "groupby_agg": {"groupby"},
    "astype": {"astype"},
    "concat": {"pandas.concat"},
    "sort_values": {"sort_values"},
    "drop_duplicates": {"drop_duplicates"},
    "np_sort": {"numpy.sort"},
    "matmul": {"operator.matmul", "numpy.matmul", "numpy.dot", "dot"},
    "read_csv": {"pandas.read_csv"},
}


@dataclass(frozen=True)
class DryRunResult:
    reason: str = ""  # why there is no estimate at all ("" when something was fitted)
    kind: str = ""
    sampling: str = ""
    levels: tuple[dict[str, Any], ...] = ()
    ram: FitResult | None = None
    time: FitResult | None = None
    overhead_s: float = 0.0
    target: float = math.nan
    notes: tuple[str, ...] = ()
    safety: tuple[str, ...] = field(default=())

    def diagnostics(self) -> dict[str, Any]:
        return {
            "reason": self.reason, "kind": self.kind, "sampling": self.sampling, "levels": list(self.levels),
            "ram": self.ram.diagnostics() if self.ram else None,
            "time": self.time.diagnostics() if self.time else None,
            "overhead_s": self.overhead_s, "target": self.target, "notes": list(self.notes),
        }  # fmt: skip


def _child_env() -> dict[str, str]:
    import nexus

    env = dict(os.environ)
    root = str(Path(nexus.__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join([root, *filter(None, [env.get("PYTHONPATH")])])
    return env


def run_child(
    spec: dict[str, Any], spec_path: Path, timeout_s: float, mem_cap: int
) -> dict[str, Any]:
    """Run one sandbox child; always returns a dict with ``status`` (ok / error / timeout / memory_limit / died)."""
    spec_path.write_text(json.dumps(spec))
    result_path = Path(spec["result"])
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        [sys.executable, "-m", "nexus._dryrun_child", str(spec_path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=_child_env(), creationflags=flags,
    )  # fmt: skip
    status = "ok"
    t0 = time.monotonic()
    try:
        ps = psutil.Process(proc.pid)
        while proc.poll() is None:
            if time.monotonic() - t0 > timeout_s:
                status = "timeout"
                break
            try:
                if ps.memory_info().rss > mem_cap:
                    status = "memory_limit"
                    break
            except psutil.Error:
                break
            time.sleep(0.004)
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:  # pragma: no cover - a kill that did not take
            log.debug("nexus: dry-run child did not exit after kill")
    if status != "ok":
        return {"status": status}
    try:
        return json.loads(result_path.read_text())
    except (OSError, ValueError):
        return {"status": "died", "returncode": proc.returncode}


def run_dryrun(  # noqa: C901
    source: str,
    namespace: Mapping[str, Any],
    *,
    budget_s: float = DEFAULT_BUDGET_S,
    child_timeout_s: float = CHILD_TIMEOUT_S,
    child_mem_cap: int = CHILD_MEM_CAP,
    tmp_root: str | None = None,
) -> DryRunResult:
    """Dry-run ``source`` on samples and fit RAM and time to the full size. Never raises."""
    t0 = time.perf_counter()
    deadline = Deadline(budget_s)
    try:
        verdict = analyze_safety(source, namespace)
        if not verdict.safe or verdict.recipe is None:
            return DryRunResult(
                reason="not safe to dry-run: " + "; ".join(verdict.reasons), safety=verdict.reasons
            )
        recipe = verdict.recipe
        with tempfile.TemporaryDirectory(prefix="nexus-dryrun-", dir=tmp_root) as tmp:
            root = Path(tmp)
            plan = build_samples(recipe, namespace, root, deadline)
            return _measure_and_fit(
                recipe, plan, root, deadline, child_timeout_s, child_mem_cap, t0
            )
    except NoSampleError as why:
        return DryRunResult(reason=f"no sample: {why}", overhead_s=time.perf_counter() - t0)
    except TimeoutError:
        return DryRunResult(reason="time budget exhausted", overhead_s=time.perf_counter() - t0)
    except Exception as exc:
        log.debug("nexus: dry run failed", exc_info=True)
        return DryRunResult(
            reason=f"dry run failed ({type(exc).__name__})", overhead_s=time.perf_counter() - t0
        )


def _measure_and_fit(recipe: Recipe, plan: SamplePlan, root: Path, deadline: Deadline, timeout_s: float,
                     mem_cap: int, t0: float) -> DryRunResult:  # fmt: skip
    rjson = recipe.to_json()
    if recipe.kind == "matmul":
        rjson["operands"] = ["L", "R"]
    rows: list[dict[str, Any]] = []
    for k, level in enumerate(plan.levels):
        deadline.check()
        spec = {
            "dir": str(root / f"level{k}"), "objects": level.objects, "recipe": rjson,
            "csv": level.csv, "result": str(root / f"result{k}.json"),
        }  # fmt: skip
        out = run_child(
            spec, root / f"spec{k}.json", min(timeout_s, max(1.0, deadline.remaining())), mem_cap
        )
        row = {"n_eff": level.n_eff, "rows": level.rows, **{k2: out.get(k2) for k2 in
               ("status", "time_s", "delta_bytes", "censored", "bound_bytes", "out_rows", "error")}}  # fmt: skip
        rows.append(row)
        if out.get("status") != "ok":
            return DryRunResult(reason=f"sample run failed ({out.get('status')}: {out.get('error', '')[:120]})",
                                kind=recipe.kind, sampling=plan.sampling, levels=tuple(rows),
                                overhead_s=time.perf_counter() - t0, target=plan.target)  # fmt: skip
    ram_pts = [
        (r["n_eff"], r["delta_bytes"])
        for r in rows
        if r["delta_bytes"] is not None and r["delta_bytes"] >= RAM_FLOOR_BYTES
    ]
    time_pts = [
        (r["n_eff"], r["time_s"])
        for r in rows
        if r["time_s"] is not None and r["time_s"] >= TIME_FLOOR_S
    ]
    ram = _fit(ram_pts, plan.target, "RAM", RAM_FLOOR_BYTES, rows, "delta_bytes")
    tim = _fit(time_pts, plan.target, "time", TIME_FLOOR_S, rows, "time_s")
    notes = list(plan.notes)
    if (
        recipe.kind in HASH_KINDS
        and plan.target > PRESIZE_CAP
        and plan.levels[-1].n_eff < PRESIZE_CAP
    ):
        notes.append("crosses_presize_cap")
    return DryRunResult(
        "" if (ram.ok or tim.ok) else "no reliable fit for RAM or time", recipe.kind, plan.sampling, tuple(rows),
        ram, tim, time.perf_counter() - t0, plan.target, tuple(notes),
    )  # fmt: skip


def _fit(
    points: list[tuple[float, float]],
    target: float,
    what: str,
    floor: float,
    rows: list[dict[str, Any]],
    key: str,
) -> FitResult:
    if len(points) < 3:
        biggest = max((r[key] for r in rows if r.get(key) is not None), default=0.0)
        return FitResult(False, f"{what}: {len(points)} sample sizes above the {floor:g} floor "
                         f"(largest measured {biggest:g}): the largest sample is too small", target=target)  # fmt: skip
    return fit_scaling([p[0] for p in points], [p[1] for p in points], target)


def matching_op(recipe_kind: str, op_name: str) -> bool:
    return op_name in OP_NAMES.get(recipe_kind, set())


def should_escalate(estimate: Estimate, available_bytes: float | None = None) -> bool:
    """Escalate to Tier 2 only when it can matter: an upper bound near the free RAM, or a wide range
    on a cell that runs long enough (``MIN_RUN_S``) for a ~2 s dry run to pay."""
    if available_bytes is not None and estimate.ram_high > RISK_FRACTION * available_bytes:
        return True
    width = (estimate.ram_high - estimate.ram_low) / max(estimate.ram_expected, 1)
    return width >= WIDE_RANGE and estimate.time_expected >= MIN_RUN_S


def tier2_estimate(result: DryRunResult, base: Estimate) -> Estimate | None:
    """Combine a dry run with the Tier 1 / Tier 0 estimate ``base``: fitted quantities replace its
    own, the other one is kept (and said so in ``note``). None if nothing was fitted."""
    ram, tim = result.ram, result.time
    if not ((ram and ram.ok) or (tim and tim.ok)):
        return None
    r = (
        (ram.low, ram.expected, ram.high)
        if ram and ram.ok
        else (base.ram_low, base.ram_expected, base.ram_high)
    )
    t = (
        (tim.low, tim.expected, tim.high)
        if tim and tim.ok
        else (base.time_low, base.time_expected, base.time_high)
    )
    cvs = [f.laws[f.best]["cv"] for f in (ram, tim) if f and f.ok]
    note = (
        f"Tier 2 dry run ({result.kind}; {result.sampling}): RAM from the "
        f"{'fit' if ram and ram.ok else 'tier ' + str(base.tier) + ' (no reliable fit)'}, time from the "
        f"{'fit' if tim and tim.ok else 'tier ' + str(base.tier) + ' (no reliable fit)'}"
    )
    return replace(
        base,
        ram_low=int(r[0]), ram_expected=int(r[1]), ram_high=int(r[2]),
        time_low=t[0], time_expected=t[1], time_high=t[2],
        confidence=max(0.3, 1.0 - 2.0 * max(cvs)), tier=2, note=note,
        drivers=[*base.drivers, f"dry run on samples, scaling fit ({', '.join(f.best for f in (ram, tim) if f and f.ok)})"],
        diagnostics=result.diagnostics(),
    )  # fmt: skip
