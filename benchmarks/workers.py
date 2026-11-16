"""Functions that run inside spawned child processes (must stay importable at module level)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class State:
    ns: dict[str, Any]
    code: Any
    source: str
    info: dict[str, Any] = field(default_factory=dict)


def _nbytes(obj: Any) -> int:
    import numpy as np
    import pandas as pd

    if isinstance(obj, pd.DataFrame):
        return int(obj.memory_usage(deep=True).sum())
    if isinstance(obj, np.ndarray):
        return int(obj.nbytes)
    return 0


def prepare_inputs(specs: list[Any], cache_dir: str) -> None:
    """Generate and cache every input (runs in a spawned prep process, never measured)."""
    for spec in specs:
        spec.ensure(cache_dir)


def build_state(payload: dict[str, Any]) -> State:
    """Load cached inputs from disk into a kernel-like namespace (``pd``/``np`` imported)."""
    import numpy as np
    import pandas as pd

    from nexus.measure import read_memory

    ns: dict[str, Any] = {"pd": pd, "np": np}
    rss_before = read_memory().rss
    for spec in payload["inputs"]:
        ns.update(spec.load(payload["cache_dir"]))
    code = compile(payload["source"], "<bench>", "eval")
    info = {
        "input_bytes": sum(_nbytes(v) for v in ns.values()),
        "input_resident_bytes": max(0, read_memory().rss - rss_before),
    }
    return State(ns=ns, code=code, source=payload["source"], info=info)


@dataclass
class Outcome:
    """Operation result plus setup facts, so ``summarize_result`` can report both."""

    value: Any
    setup_info: dict[str, Any]


def run_op(state: State) -> Outcome:
    return Outcome(eval(state.code, state.ns), state.info)


def summarize_result(outcome: Outcome) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    result, info = outcome.value, dict(outcome.setup_info)
    if isinstance(result, pd.DataFrame):
        info.update(out_rows=int(result.shape[0]), out_bytes=_nbytes(result))
    elif isinstance(result, pd.Series):
        info.update(out_rows=int(len(result)), out_bytes=int(result.memory_usage(deep=True)))
    elif isinstance(result, np.ndarray):
        info.update(out_rows=int(result.shape[0]), out_bytes=int(result.nbytes))
    return info


def predict(state: State, tier: int) -> dict[str, Any]:
    """Run NEXUS on the cell source against the live namespace; report estimates and overhead."""
    from nexus.pipeline import Pipeline

    pipeline = Pipeline(tier=tier)
    cold = pipeline.run(state.source, state.ns)
    warm = pipeline.run(state.source, state.ns)
    return {
        "overhead_cold_s": cold.elapsed_s,
        "overhead_warm_s": warm.elapsed_s,
        "ops": [op.name for op in cold.ops],
        "skipped": list(cold.inspection.skipped),
        "inspected_bytes": sum(d.nbytes for d in cold.inspection.variables.values())
        + sum(f.nbytes for f in cold.inspection.files.values()),
        "estimates": [
            {
                "op": item.op.name,
                "model": item.model,
                "ram_low": item.estimate.ram_low,
                "ram_expected": item.estimate.ram_expected,
                "ram_high": item.estimate.ram_high,
                "time_low": item.estimate.time_low,
                "time_expected": item.estimate.time_expected,
                "time_high": item.estimate.time_high,
                "confidence": item.estimate.confidence,
                "drivers": item.estimate.drivers,
                "features": item.features,
            }
            for item in cold.estimates
        ],
    }


def as_info(result: Any) -> dict[str, Any]:
    return result if isinstance(result, dict) else {}
