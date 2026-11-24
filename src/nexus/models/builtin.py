"""Loader for the built-in operation models (importing them registers them)."""

from __future__ import annotations

import importlib

_MODULES = (
    "drop_duplicates",
    "merge",
    "groupby",
    "sort_values",
    "read_csv",
    "astype",
    "concat",
    "matmul",
    "np_sort",
    "copy_fillna",
    "explode_apply",
    "set_index",
    "dropna",
    "reset_index",
)


def load_builtin_models() -> None:
    """Import every built-in model module (idempotent; registration happens at import)."""
    for name in _MODULES:
        importlib.import_module(f"nexus.models.{name}")
