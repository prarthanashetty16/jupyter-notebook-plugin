"""Operations v4 deliberately does not model, with the reason the UNKNOWN message gives (pre-registration item (4)).

An operation listed here still gets no estimate: naming the reason tells the user that NEXUS knows the operation and
why it declines, instead of failing silently. Every entry records the evidence behind the deferral.
"""

from __future__ import annotations

import ast
from typing import Any

DEFERRED: dict[str, str] = {
    # third and last attempt failed (docs/benchmarks/phase8/probes/p8_value_counts_diag.out): the hash table's
    # resident pages depend on the key values themselves (1M keys: 1.69x the source-derived pages)
    "value_counts": "memory depends on the exact key values, through the hash table's pages",
    "apply": "apply with a Python function: per-element allocations are not derivable",
    "map": "mapper workspace not derived: dict and NumPy ufunc peaks exceeded the v4 derivation",
    "to_csv": "deferred in v4: writer buffers not derived",
    "join": "deferred in v4: not derived",
    "pandas.get_dummies": "deferred in v4: not derived",
    "corr": "deferred in v4: not derived",
    # v4 Should item: first derivation 0.58-0.68 (p8_duplicated.out); the one allowed second derivation (amendment 3)
    # under-predicted a dense id-like key by 1.29 (p8_duplicated_b2.out): not adopted
    "duplicated": "not modelled in v4: the hash table's memory depends on the key values (dense ids measured 1.29x)",
}
# pandas 3.1.1 ``head`` / ``tail`` are ``iloc[...].copy()``: the receiver already copies (probe p8_copy_receivers)
COPY_OF_COPYING_RECEIVER = (
    "copy of head() / tail(), which already copy in pandas 3.1.1: not modelled in v4"
)


def reason(op: Any) -> str | None:
    """The deferral reason for a detected operation, or None if it is not deferred."""
    name = getattr(op, "name", None)
    if name == "copy":
        recv = getattr(getattr(getattr(op, "node", None), "func", None), "value", None)
        if (
            isinstance(recv, ast.Call)
            and isinstance(recv.func, ast.Attribute)
            and recv.func.attr in ("head", "tail")
        ):
            return COPY_OF_COPYING_RECEIVER
        return None
    return DEFERRED.get(name or "")
