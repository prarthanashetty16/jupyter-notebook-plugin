"""v4 item (1d) MEASUREMENT FIXES (not new attempts): the same statements and derivations as ``p8_copy_receivers.py``.

* The 10%-selected ``df.loc[mask].copy()`` and the ``str``-comparison mask were censored there: their peaks (13.6 and
  12 B/row) stayed below the setup peak, which unpickling the two ``str`` columns raised by about 8 B/row each. Both
  scale with n, so a larger frame alone cannot fix it; the fix changes the frame's composition. The loc variant runs on
  an all-numeric frame (16 float64 columns); the str variant on a frame with ONE str column among numeric ones.
* ``tail``: checked like ``head`` (pandas 3.1.1 ``tail`` is expected to be ``iloc[-n:].copy()`` too). Two derivations
  are printed: the view derivation (M r / n, as for head) and the copying-receiver one (2 M r / n).
* ``df.sort_values('f0').copy()`` on the first probe's 8M-row frame (seed 31) was measured at 1038.1 MiB; this run
  prints the EXISTING models' estimates for that statement (prediction only, the same frame rebuilt) for comparison.

    python docs/benchmarks/phase8/probes/p8_copy_receivers_fix.py > docs/benchmarks/phase8/probes/p8_copy_receivers_fix.out
"""

from __future__ import annotations

import gc
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
BAR = 0.15
SORT_MEASURED_MIB = 1038.1  # p8_copy_receivers.out


def numeric_frame(n: int, cols: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({f"f{i}": rng.random(n) for i in range(cols)})


def str_frame(n: int, seed: int) -> pd.DataFrame:
    df = numeric_frame(n, 6, seed)
    rng = np.random.default_rng(seed + 1)
    vocab = np.array([f"x{i:05d}" for i in range(30_000)], dtype=object)
    s = vocab[rng.integers(0, len(vocab), n)].copy()
    s[rng.random(n) < 0.05] = None
    df["s0"] = pd.array(s, dtype="str")
    return df


def setup(path: str, src: str) -> dict[str, Any]:
    ns = {"pd": pd, "np": np, "df": pd.read_pickle(path), "__src__": src}
    gc.collect()
    return ns


def run(ns: dict[str, Any]) -> int:
    exec(compile(ns["__src__"], "cell", "exec"), ns)  # noqa: S102  (fixed probe statements only)
    return 0


def mask_peak(n: int, k: int, m: float, compare: float) -> float:
    f = k / n
    return max(compare * n, n + 16.0 * k + m * f, 8.0 * k + 2 * m * f)


def measure(path: str, src: str, derived: dict[str, float]) -> None:
    mm = measure_call(run, setup=setup, setup_args=(path, src), repeats=3)
    got = mm.delta_bytes
    row: dict[str, Any] = {"statement": src, "censored": got is None, "bound_mib": mm.bound_bytes / MIB,
                           "measured_mib": None if got is None else got / MIB}  # fmt: skip
    for name, w in derived.items():
        r = None if got is None else got / w
        row[f"derived_{name}_mib"] = w / MIB
        row[f"ratio_{name}"] = r
        row[f"within_bar_{name}"] = None if r is None else abs(r - 1) <= BAR
    print(json.dumps(row))


def first_frame() -> pd.DataFrame:
    """The first probe's 8M-row frame (seed 31), rebuilt by its own ``frame()``."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "p8_copy_receivers", Path(__file__).with_name("p8_copy_receivers.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.frame()


def main() -> None:
    print(json.dumps({"pandas": pd.__version__, "numpy": np.__version__, "bar": BAR}))
    with tempfile.TemporaryDirectory() as tmp:
        n = 8_000_000
        df = numeric_frame(n, 16, 41)
        m = 8.0 * n * 16
        k = int((df["f0"] > 0.9).sum())
        path = str(Path(tmp) / "num.pkl")
        df.to_pickle(path)
        r = 4_000_000
        del df
        gc.collect()
        measure(path, "y = df.loc[df['f0'] > 0.9].copy()", {"mask": mask_peak(n, k, m, 1.0)})
        measure(
            path,
            "y = df.tail(4_000_000).copy()",
            {"view": m * r / n, "copying_receiver": 2 * m * r / n},
        )

        n = 12_000_000
        df = str_frame(n, 43)
        m = 8.0 * n * df.shape[1]
        k = int((df["s0"] == "x00001").sum())
        path = str(Path(tmp) / "str.pkl")
        df.to_pickle(path)
        del df
        gc.collect()
        measure(path, "y = df[df['s0'] == 'x00001'].copy()", {"mask": mask_peak(n, k, m, 12.0)})

    from nexus.cellpeak import cell_estimate
    from nexus.pipeline import Pipeline

    src = "y = df.sort_values('f0').copy()"
    rep = Pipeline(tier=1).run(src, {"df": first_frame(), "pd": pd})
    cell, _m, _f = cell_estimate(src, rep.estimates)
    print(json.dumps({
        "statement": src, "measured_mib": SORT_MEASURED_MIB, "source": "p8_copy_receivers.out",
        "estimates": [{"model": e.model, "tier": e.estimate.tier, "low_mib": e.estimate.ram_low / MIB,
                       "expected_mib": e.estimate.ram_expected / MIB, "high_mib": e.estimate.ram_high / MIB}
                      for e in rep.estimates],
        "uncovered": [o.name for o in rep.ops if id(o) not in {id(e.op) for e in rep.estimates}],
        "cell_high_mib": None if cell is None else cell.ram_high / MIB,
        "cell_expected_mib": None if cell is None else cell.ram_expected / MIB,
    }))  # fmt: skip


if __name__ == "__main__":
    main()
