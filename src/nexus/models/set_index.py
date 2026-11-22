"""Model for ``df.set_index(col)`` (Phase 7b, SECOND-ATTEMPT derivation).

The first derivation ("``Index(values)`` copies the key array": 8 B/row) was contradicted in Phase 7a
(0.003). The second, written down with a fresh probe grid and the bar before the probe ran
(``docs/benchmarks/phase7b/probes/p7b_second_attempts.py``, commit e7578a8), passed every variant
(12M rows: int key with 3 other dtype groups, float key, ``drop=False``: 0.2-0.4 MiB measured against a
derived 0): in pandas 3.1.1 ``set_index`` makes a shallow copy (blocks shared), builds the Index on the
column's own array without copying, and ``del frame[col]`` splits the block as views. **Peak = 0**
(metadata only), and the result shares the input's memory (output 0).

``high`` is one copy of the key column (n x itemsize). That bound is not measured: it is a margin in
case a pandas build copies the key after all. Only the probed form is modelled: one numeric column as the
key, ``drop`` a literal bool. ``append``, ``inplace``, ``verify_integrity`` (which hashes the key), several
keys and text keys (not probed) are refused.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from nexus.analyzer import DetectedOp
from nexus.models import _time as tt
from nexus.models import _util as u
from nexus.models.base import Estimate, NoEstimateError, OperationModel
from nexus.registry import register_model
from nexus.state import Inspection


@register_model
class SetIndexModel(OperationModel):
    """Peak RAM of ``df.set_index(col)`` (module docstring)."""

    name = "set_index"

    def matches(self, op: DetectedOp) -> bool:
        return op.name == "set_index"

    def features(self, op: DetectedOp, state: Inspection) -> dict[str, Any]:
        df = u.frame(state, op.receiver)
        key = op.args[0] if op.args else op.kwargs.get("keys")
        if len(op.args) > 1 or set(op.kwargs) - {"keys", "drop"}:
            raise NoEstimateError("only set_index(col[, drop=...]) is modelled")
        if not isinstance(key, str) or key not in df.dtypes:
            raise NoEstimateError("the key is not one literal column of the frame")
        if not isinstance(op.kwargs.get("drop", True), bool):
            raise NoEstimateError("drop= is not a literal bool")
        try:
            dt = np.dtype(df.dtypes[key])
        except TypeError as exc:
            raise NoEstimateError("text / extension keys were not probed") from exc
        if dt.kind not in "iufb":
            raise NoEstimateError("only numeric keys were probed")
        return {"n_rows": df.shape[0], "key_itemsize": int(dt.itemsize)}

    def estimate(self, features: dict[str, Any], tier: int) -> Estimate:
        u.require_tier(tier)
        copy = float(features["n_rows"]) * features["key_itemsize"]
        return u.build(
            (0.0, 0.0, copy),
            u.time_band_for_tier(tt.copy_s(64.0), tier),
            0.7,
            tier,
            ["no copy: the Index wraps the key column's array (pandas 3, copy-on-write)"],
        )
