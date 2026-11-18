"""Functions that run inside spawned child processes (importable at module level)."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class State:
    env: dict[str, Any]
    source: str


def load_env(payload: dict[str, Any]) -> State:
    """Load the cached inputs from disk into a kernel-like namespace (never measured as the op)."""
    import numpy as np
    import pandas as pd

    env: dict[str, Any] = {"pd": pd, "np": np}
    for name, path in payload["frames"].items():
        env[name] = pd.read_pickle(path)
    return State(env=env, source=payload["source"])


def _exec(source: str, env: dict[str, Any]) -> Any:
    tree = ast.parse(source)
    exec(compile(tree, "<cell>", "exec"), env)  # noqa: S102  (benchmark-generated cells only)
    return env.get("r")


def _drain(value: Any) -> Any:
    """A chunked reader is consumed chunk by chunk and each chunk discarded (the intended use)."""
    if hasattr(value, "__next__") and hasattr(value, "close"):
        n = 0
        for chunk in value:
            n += len(chunk)
        return n
    return value


def run_cell(state: State) -> Any:
    return _drain(_exec(state.source, state.env))


def summarize(result: Any) -> dict[str, Any]:
    return {"result_type": type(result).__name__}


def suggest_child(state: State) -> dict[str, Any]:
    """Run the NEXUS suggestion engine on the cell against the live namespace (read-only)."""
    from nexus.analyzer import analyze_cell
    from nexus.state import StateInspector, candidate_paths
    from nexus.suggestions import suggest

    ops = analyze_cell(state.source, state.env)
    names = [v for op in ops for v in op.variables]
    paths = [p for op in ops for p in candidate_paths(op)]
    inspection = StateInspector().inspect(names, state.env, paths=paths)
    out = []
    for s in suggest(state.source, state.env, inspection, ops, keep_hidden=True, budget_s=20.0):
        b, a = s.before, s.after
        out.append(
            {
                "rule": s.rule, "title": s.title, "kind": s.kind, "semantics": s.semantics,
                "semantics_detail": s.semantics_detail, "modified_source": s.modified_source,
                "shown": s.shown, "hidden_reason": s.hidden_reason, "op": s.op_name,
                "saving_bytes": s.saving_bytes, "saving_frac": s.saving_frac,
                "estimate_source": s.estimate_source,
                "before": None if b is None else [b.ram_low, b.ram_expected, b.ram_high],
                "after": None if a is None else [a.ram_low, a.ram_expected, a.ram_high],
            }
        )  # fmt: skip
    return {"ops": [o.name for o in ops], "suggestions": out}


def as_info(result: Any) -> dict[str, Any]:
    return result if isinstance(result, dict) else {}


def _compare(a: Any, b: Any) -> dict[str, Any]:
    import numpy as np
    import pandas as pd

    out: dict[str, Any] = {
        "comparable": True,
        "identical": False,
        "dtype_changes": [],
        "max_abs_err": None,
    }
    if isinstance(a, pd.Series) and isinstance(b, pd.Series):
        a, b = a.to_frame("x"), b.to_frame("x")
    if isinstance(a, pd.DataFrame) and isinstance(b, pd.DataFrame):
        try:
            pd.testing.assert_frame_equal(a, b)
            out["identical"] = True
        except AssertionError:
            pass
        out["dtype_changes"] = [
            f"{c}: {a[c].dtype} -> {b[c].dtype}"
            for c in a.columns
            if c in b.columns and a[c].dtype != b[c].dtype
        ]
        out["index_dtype_changed"] = str(a.index.dtype) != str(b.index.dtype)
        out["same_shape"] = a.shape == b.shape
        if a.shape == b.shape:
            err = 0.0
            for c in a.columns:
                if c in b.columns and pd.api.types.is_numeric_dtype(a[c].dtype):
                    x = a[c].to_numpy(dtype="float64")
                    y = pd.to_numeric(b[c], errors="coerce").to_numpy(dtype="float64")
                    with np.errstate(all="ignore"):
                        d = np.nanmax(np.abs(x - y)) if len(x) else 0.0
                    err = max(err, float(d) if np.isfinite(d) else 0.0)
            out["max_abs_err"] = err
        return out
    try:
        fa, fb = float(a), float(b)
        out["identical"] = fa == fb
        out["max_abs_err"] = abs(fa - fb)
        out["max_rel_err"] = abs(fa - fb) / max(abs(fa), 1e-300)
        return out
    except (TypeError, ValueError):
        out["comparable"] = False
        return out


def verify(state: State) -> dict[str, Any]:
    """Run the original and the modified cell on copies of the namespace and compare the results."""
    srcs = state.source.split("\0")
    va = _drain(_exec(srcs[0], dict(state.env)))
    vb = _drain(_exec(srcs[1], dict(state.env)))
    return _compare(va, vb)
