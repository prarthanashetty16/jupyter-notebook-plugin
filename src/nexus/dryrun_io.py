"""Cheap, read-only hand-over of sample data to the sandbox child, and the recipe executor.

Approach (why not memory-mapped files or shared memory): the parent writes each sample once as raw
``.npy`` files (numeric columns: one memcpy per column; strings: one pickle; categories: codes +
categories) into a private temp directory and the child reads them back into ordinary memory, the
way the benchmark instrument loads its inputs. A memory-mapped array would be counted as resident
the moment the operation touches it, which would put the INPUT into the measured peak; shared
memory cannot hold Python string objects and needs a resource tracker that behaves differently on
Windows and POSIX. Files are portable, their cost is small next to the samples (a few MiB) and the
parent never shares an address space with the child.

The child executes a ``Recipe`` (data, not source text): see ``execute``.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def save_frame(df: pd.DataFrame, path: Path) -> None:
    """Write ``df`` (columns only; the index is not kept) under directory ``path``."""
    path.mkdir(parents=True, exist_ok=True)
    cols = []
    for i, name in enumerate(df.columns):
        col = df.iloc[:, i]
        dtype = str(col.dtype)
        if isinstance(col.dtype, pd.CategoricalDtype):
            np.save(path / f"{i}.npy", col.cat.codes.to_numpy(), allow_pickle=False)
            with (path / f"{i}.cats").open("wb") as fh:
                pickle.dump(col.cat.categories, fh)
            cols.append({"name": name, "kind": "category", "dtype": dtype})
        elif col.dtype == object or dtype == "str":
            np.save(path / f"{i}.npy", col.to_numpy(dtype=object), allow_pickle=True)
            cols.append({"name": name, "kind": "object", "dtype": dtype})
        else:
            np.save(path / f"{i}.npy", col.to_numpy(), allow_pickle=False)
            cols.append({"name": name, "kind": "plain", "dtype": dtype})
    (path / "meta.json").write_text(json.dumps({"kind": "frame", "columns": cols}))


def load_frame(path: Path) -> pd.DataFrame:
    meta = json.loads((path / "meta.json").read_text())
    data: dict[str, Any] = {}
    for i, col in enumerate(meta["columns"]):
        arr = np.load(path / f"{i}.npy", allow_pickle=col["kind"] == "object")
        if col["kind"] == "category":
            with (path / f"{i}.cats").open("rb") as fh:
                categories = pickle.load(fh)
            data[col["name"]] = pd.Categorical.from_codes(arr, categories=categories)
        elif col["kind"] == "object":
            s = pd.Series(arr, dtype=object)
            data[col["name"]] = s.astype(col["dtype"]) if col["dtype"] != "object" else s
        else:
            data[col["name"]] = arr
    return pd.DataFrame(data, copy=False)


def save_array(arr: np.ndarray, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    np.save(path / "array.npy", arr, allow_pickle=False)
    (path / "meta.json").write_text(json.dumps({"kind": "array"}))


def load_object(path: Path) -> Any:
    kind = json.loads((path / "meta.json").read_text())["kind"]
    return np.load(path / "array.npy", allow_pickle=False) if kind == "array" else load_frame(path)


def execute(recipe: dict[str, Any], objs: dict[str, Any], csv_path: str | None = None) -> Any:  # noqa: C901
    """Run one supported operation on sample objects. Only ever called inside the sandbox child."""
    kind, ops, kw, extra = (
        recipe["kind"],
        recipe["operands"],
        dict(recipe["kwargs"]),
        recipe["extra"],
    )
    if kind == "merge":
        return objs[ops[0]].merge(objs[ops[1]], **kw)
    if kind == "groupby_agg":
        gb = objs[ops[0]].groupby(extra["by"], **kw["groupby"])
        if extra["cols"]:
            gb = gb[extra["cols"] if len(extra["cols"]) > 1 else extra["cols"][0]]
        return getattr(gb, extra["agg"])(**kw["agg"])
    if kind == "astype":
        return objs[ops[0]][extra["column"]].astype(extra["target"])
    if kind == "concat":
        return pd.concat([objs[n] for n in ops], **kw)
    if kind == "sort_values":
        return objs[ops[0]].sort_values(**kw)
    if kind == "drop_duplicates":
        return objs[ops[0]].drop_duplicates(**kw)
    if kind == "np_sort":
        return np.sort(objs[ops[0]], **kw)
    if kind == "matmul":
        return objs[ops[0]] @ objs[ops[1]]
    if kind == "read_csv":
        return pd.read_csv(csv_path, **kw)
    raise ValueError(f"unknown recipe kind {kind!r}")


def result_rows(result: Any) -> int | None:
    try:
        return int(len(result))
    except TypeError:
        return None
