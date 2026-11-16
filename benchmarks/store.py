"""On-disk dataset cache (one ``.npy`` per column) so measured processes *load* their inputs.

Loading column by column into ``DataFrame(dict, copy=False)`` leaves almost no transient peak,
which keeps the setup peak close to the baseline (see ``nexus.measure``). Object columns are
pickled by ``np.save``, which preserves shared string objects.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def save(obj: Any, path: Path) -> None:
    """Save a DataFrame or ndarray under directory ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, np.ndarray):
        np.save(path / "array.npy", obj, allow_pickle=False)
        (path / "meta.json").write_text(json.dumps({"kind": "ndarray"}))
        return
    if not isinstance(obj, pd.DataFrame):
        raise TypeError(f"cannot store {type(obj).__name__}")
    columns = []
    for i, name in enumerate(obj.columns):
        col = obj.iloc[:, i]
        if isinstance(col.dtype, pd.CategoricalDtype):
            np.save(path / f"{i}.npy", col.cat.codes.to_numpy(), allow_pickle=False)
            with (path / f"{i}.cats").open("wb") as fh:
                pickle.dump(col.cat.categories, fh)
            columns.append({"name": name, "kind": "category"})
        elif col.dtype == object:
            np.save(path / f"{i}.npy", col.to_numpy(), allow_pickle=True)
            columns.append({"name": name, "kind": "object"})
        else:
            np.save(path / f"{i}.npy", col.to_numpy(), allow_pickle=False)
            columns.append({"name": name, "kind": "plain"})
    (path / "meta.json").write_text(json.dumps({"kind": "frame", "columns": columns}))


def load(path: Path) -> Any:
    """Load what ``save`` wrote."""
    meta = json.loads((path / "meta.json").read_text())
    if meta["kind"] == "ndarray":
        return np.load(path / "array.npy", allow_pickle=False)
    data: dict[str, Any] = {}
    for i, col in enumerate(meta["columns"]):
        arr = np.load(path / f"{i}.npy", allow_pickle=col["kind"] == "object")
        if col["kind"] == "category":
            with (path / f"{i}.cats").open("rb") as fh:
                categories = pickle.load(fh)
            data[col["name"]] = pd.Categorical.from_codes(arr, categories=categories)
        elif col["kind"] == "object":
            data[col["name"]] = pd.Series(arr, dtype=object)
        else:
            data[col["name"]] = arr
    return pd.DataFrame(data, copy=False)
