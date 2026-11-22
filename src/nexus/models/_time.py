"""Derived wall-time terms of the operation models (Phase 6; RAM is not computed here).

Every term is an algorithm step times a primitive measured on THIS machine (``nexus.machine``,
format 3), evaluated at the working set the step actually touches. The mechanisms were checked by
isolated probes before they were put here (``docs/benchmarks/phase6/probes/``):

* hash-based steps (factorize in groupby, astype("category"), drop_duplicates, merge) cost per row
  ``factorize_s(G)``, rising with the distinct count G: 4.7 -> 74 ns/row (int64) and 27 -> 407 ns/row
  (str) from G = 100 to 3M (``p_hash_workingset``); the frozen models charged one constant;
* groupby (``sort=True``) and astype("category") also SORT the G uniques: ``G log2 G`` comparisons;
* moving Python objects (object columns in concat / sort / merge output, categoricals with
  DIFFERENT categories, which ``concat`` materialises as ``str``) costs an incref on each object:
  5 ns at 1k distinct objects, 58-65 ns at 1-3M (``p_concat_category``, ``p_hash_workingset``);
* read_csv costs per FIELD by parsed type: ~9-14 ns numeric, ~150-190 ns text or date (dates are
  read as text by default) (``p_csv_astype_matmul``); the frozen model used one byte rate;
* astype(str) costs depend on the source: float -> str ~4x int -> str;
* matmul: float32 runs at ~2.6-3x the float64 flop rate.

Unknown distinct counts (Tier 0) use the geometric middle of the times at the two extremes (one
distinct value .. all distinct), the same convention as the RAM models. What these terms cannot
explain is left to the per-operation residual of the calibration artifact (``nexus.timecal``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from nexus.machine import machine

READ_CSV_FIELD_WIDTH = math.sqrt(2.0 * 24.0)  # B/field, geometric middle of read_csv's 2..24 range


def nlogn(n: float) -> float:
    return max(n, 0.0) * math.log2(max(n, 2.0))


def copy_s(nbytes: float) -> float:
    """Cold copy of ``nbytes`` into fresh memory (throughput at that working set)."""
    return max(nbytes, 0.0) / machine().at("copy_bps", max(nbytes, 1.0))


def factorize_s(kind: str, n: float, distinct: float) -> float:
    """Hash ``n`` values of ``kind`` ("numeric" / "text") into a table of ``distinct`` keys."""
    curve = "text_factorize_s" if kind == "text" else "num_factorize_s"
    return max(n, 0.0) * machine().at(curve, max(distinct, 1.0))


def sort_uniques_s(kind: str, distinct: float) -> float:
    """Sort ``distinct`` unique keys (groupby sort=True, category construction)."""
    curve = "text_argsort_s" if kind == "text" else "num_argsort_s"
    return nlogn(distinct) * machine().at(curve, max(distinct, 2.0))


def take_objects_s(n: float, distinct: float) -> float:
    """Move ``n`` Python-object pointers drawn from ``distinct`` objects (incref each)."""
    return max(n, 0.0) * machine().at("object_take_s", max(distinct, 1.0))


def argsort_s(kind: str, n: float) -> float:
    curve = "text_argsort_s" if kind == "text" else "num_argsort_s"
    return nlogn(n) * machine().at(curve, max(n, 2.0))


def unknown(fn: Callable[[float], float], n: float) -> float:
    """Geometric middle of ``fn`` at one distinct value and at ``n`` distinct values."""
    lo, hi = fn(1.0), fn(max(n, 1.0))
    return math.sqrt(max(lo, 1e-12) * max(hi, 1e-12))


def _mid(values: Sequence[float] | None) -> float | None:
    if values is None:
        return None
    return float(values[1]) if isinstance(values, (list, tuple)) else float(values)


# -- per operation -----------------------------------------------------------------------------
def groupby(f: dict[str, Any]) -> float:
    n = float(f["n_rows"])
    kinds = f.get("key_kinds") or ["text"] * int(f["n_keys"])
    cols = len(f["aggregated_columns"]) if f.get("aggregated_columns") else f["n_value_cols"]
    key_fracs = f.get("key_fractions")
    groups = f.get("groups_fraction")
    m = machine()

    def at(fracs: list[float], gfrac: float) -> float:
        t = 0.0
        for kind, frac in zip(kinds, fracs, strict=False):
            if kind == "category":
                t += copy_s(8 * n)  # the codes are reused; no hashing
            else:
                t += factorize_s(kind, n, frac * n)
        g = max(gfrac * n, 1.0)
        if len(kinds) > 1:
            t += factorize_s("numeric", n, g)  # combined group ids
        t += sum(sort_uniques_s("text" if k == "text" else "numeric", g) for k in kinds)
        return t + n * cols * m.agg_s

    if groups is None:
        return math.sqrt(at([1 / n] * len(kinds), 1 / n) * at([1.0] * len(kinds), 1.0))
    fracs = [_mid(x) or 1.0 for x in key_fracs] if key_fracs else [_mid(groups)] * len(kinds)
    return at(fracs, _mid(groups) or 1.0)  # type: ignore[arg-type]


def astype(f: dict[str, Any], source_kind: str) -> float:
    n = float(f["n_rows"])
    source, target = f["source_dtype"], f["target"]
    text = source in ("object", "str", "string") or source.startswith("string")
    m = machine()
    if target == "category":
        kind = "text" if text else "numeric"

        def at(distinct: float) -> float:
            return factorize_s(kind, n, distinct) + sort_uniques_s(kind, distinct) + copy_s(4 * n)

        frac = f.get("distinct_fraction")
        return unknown(at, n) if frac is None else at(frac * n)
    if target in ("str", "object"):
        if text:
            return unknown(lambda d: take_objects_s(n, d), n)
        per = {
            "float": m.float_to_str_s,
            "datetime": m.datetime_to_str_s,
        }.get(source_kind, m.int_to_str_s)
        return n * per
    itemsize = float(f.get("target_itemsize") or 8)
    return n * m.cast_s + copy_s(n * itemsize)


def read_csv(f: dict[str, Any]) -> float:
    m = machine()
    rows, cols, text = f.get("n_rows"), f.get("n_cols"), f.get("text_cols")
    if rows is None or cols is None or text is None:  # Tier 0: field count and types unknown
        fields = float(f["file_bytes"]) / READ_CSV_FIELD_WIDTH
        return fields * math.sqrt(m.csv_num_field_s * m.csv_text_field_s)
    rows = float(rows)
    return rows * ((cols - text) * m.csv_num_field_s + text * m.csv_text_field_s)


def concat(f: dict[str, Any]) -> float:
    rows = float(f.get("total_rows") or 0)
    moved = float(f.get("moved_bytes") or f["total_bytes"])
    base = copy_s(moved)
    obj_cols = float(f.get("object_cols") or 0)
    cat_cols = float(f.get("category_cols") or 0)

    def objects(distinct: float | None) -> float:
        if obj_cols == 0:
            return 0.0
        if distinct is None:
            return obj_cols * unknown(lambda d: take_objects_s(rows, d), rows)
        return obj_cols * take_objects_s(rows, distinct)

    def categories(mismatched: float, distinct: float | None) -> float:
        if mismatched == 0:
            return 0.0
        if distinct is None:
            return mismatched * unknown(lambda d: take_objects_s(rows, d), rows)
        return mismatched * take_objects_s(rows, distinct)

    t_obj = objects(f.get("object_distinct"))
    if "category_mismatch" in f:  # Tier 1: compared the categories of the inputs
        return base + t_obj + categories(f["category_mismatch"], f.get("category_distinct"))
    same = base + t_obj
    if cat_cols == 0:
        return same
    differ = same + categories(cat_cols, None)  # Tier 0: unknown whether the categories agree
    return math.sqrt(max(same, 1e-12) * differ)


def merge(f: dict[str, Any]) -> float:
    nl, nr = float(f["n_left"]), float(f["n_right"])
    kind = "text" if f.get("key_text") else "numeric"
    out = f.get("out_rows")
    mid = _mid(out) if out is not None else max(nl, nr)
    row_l = float(f.get("moved_left") or f["bytes_left"]) / max(nl, 1.0)
    row_r = float(f.get("moved_right") or f["bytes_right"]) / max(nr, 1.0)
    left_copy = 0.0 if f.get("left_elided") else row_l
    assemble = copy_s(mid * (left_copy + row_r))  # type: ignore[operator]
    rd, ld = _mid(f.get("right_distinct")), _mid(f.get("left_distinct"))
    if rd is None or ld is None:
        return unknown(lambda d: factorize_s(kind, nl + nr, d), nl + nr) + assemble
    return factorize_s(kind, nl + nr, max(rd, ld)) + assemble


def drop_duplicates(f: dict[str, Any], out_bytes: float) -> float:
    n = float(f["n_rows"])
    k, kt = int(f["n_keys"]), int(f["n_text_keys"])

    def at(key_frac: float, rows_frac: float) -> float:
        t = kt * factorize_s("text", n, key_frac * n) + (k - kt) * factorize_s(
            "numeric", n, key_frac * n
        )
        if k > 1:
            t += factorize_s("numeric", n, rows_frac * n)  # combined row ids
        return t

    kr, fr = f.get("key_fraction_range"), f.get("distinct_rows_range")
    if kr is None or fr is None:
        frac = f.get("distinct_fraction")
        if frac is not None:
            t = at(frac, frac)
        else:
            t = math.sqrt(at(1 / n, 1 / n) * at(1.0, 1.0))
    else:
        t = at(_mid(kr) or 1.0, _mid(fr) or 1.0)
    return t + copy_s(out_bytes)


def sort_values(f: dict[str, Any]) -> float:
    n = float(f["n_rows"])
    k, kt = int(f["n_keys"]), int(f["n_text_keys"])
    moved = float(f.get("moved_bytes") or f["input_bytes"])
    sort = kt * argsort_s("text", n) + (k - kt) * argsort_s("numeric", n)
    text_cols = float(f.get("n_text_cols") or 0)
    take = text_cols * unknown(lambda d: take_objects_s(n, d), n)
    return sort + copy_s(moved) + take


def np_sort(f: dict[str, Any]) -> float:
    n = float(f["size"])
    return nlogn(n) * machine().at("np_sort_s", max(n, 2.0))


def matmul(f: dict[str, Any]) -> float:
    m_, k, p = (float(f[x]) for x in ("m", "k", "p"))
    work = m_ * k * p
    curve = "blas32_flops" if int(f.get("itemsize", 8)) == 4 else "blas64_flops"
    return 2.0 * work / machine().at(curve, work)


def copy(f: dict[str, Any]) -> float:
    """DataFrame.copy(): a cold copy of the moved bytes + an incref per object pointer (Phase 6c)."""
    if not f.get("deep", True):
        return 0.0
    n = float(f["n_rows"])
    objects = float(f.get("text_cols") or 0) * unknown(lambda d: take_objects_s(n, d), n)
    return copy_s(float(f["moved_bytes"])) + objects


def fillna(f: dict[str, Any], copied_bytes: float) -> float:
    """fillna(value): an isna scan of every nullable column + the copy of the blocks filled (Phase 6c)."""
    scanned = float(sum(f["column_bytes"].values()))
    read = scanned / machine().at("read_bps", max(scanned, 1.0)) if scanned else 0.0
    return read + copy_s(copied_bytes)
