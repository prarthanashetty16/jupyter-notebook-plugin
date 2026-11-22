"""Probe (RAM >= 200 MiB, OS peak, fresh process, inputs from disk): DataFrame.copy() and fillna().

HYPOTHESES (pandas 3.1 source + small in-process checks of what is shared). Run 1 (kept as
``p_copy_fillna_run1.out``) contradicted two of them; run 2 uses the source-derived corrections:
  - copy of a fragmented frame: + the numpy dtype groups that ``_consolidate_inplace`` stacks again;
  - fillna: 4 bool masks per element (mask, ~mask, ~cond, ~icond in Block.where), not 1;
  - fillna on a pandas-3 ``str`` (extension) column: not derived, refused by the model.
The original hypotheses:
* ``copy()`` (deep) copies every block: increment = the frame's moved bytes (numeric values and object
  POINTERS; the string objects are shared, not copied); a fragmented frame is consolidated by the copy
  (6 blocks -> 1) without a second full copy. ``copy(deep=False)`` shares: ~0.
* ``fillna(scalar)``: per BLOCK (one block per dtype in a consolidated frame), a block is copied only if it
  holds a missing value; blocks without one (and int / bool blocks, which cannot hold one) are shared under
  copy-on-write. During the copy an ``isna`` mask (1 byte per element) of the block is alive.
  Increment = sum over blocks with a missing value of (block bytes) + the largest such mask.
* ``fillna({col: v})``: only the named columns are copied (column bytes + its mask).

    python docs/benchmarks/phase6c/probes/p_copy_fillna.py
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from nexus.measure import measure_call

MIB = 2**20
N = 4_000_000


def frame(nan_in: str | None, fragmented: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    cols = {f"f{i}": rng.random(N) for i in range(4)}
    cols.update({f"i{i}": rng.integers(0, 10**6, N) for i in range(2)})
    vocab = np.array([f"w{x:011d}" for x in range(50_000)], dtype=object)
    cols.update({f"s{i}": vocab[rng.integers(0, len(vocab), N)] for i in range(2)})
    df = pd.DataFrame(cols)
    if nan_in == "float":
        df.loc[df.index[::1000], "f0"] = np.nan
    elif nan_in == "object":
        df.loc[df.index[::1000], "s0"] = None
    if fragmented:
        out = pd.DataFrame({"f0": df["f0"]})
        for c in df.columns[1:]:
            out[c] = df[c]  # one block per inserted column
        df = out
    return df


def setup(path: str) -> pd.DataFrame:
    df = pd.read_pickle(path)
    gc.collect()
    return df


def op_copy(df: pd.DataFrame) -> int:
    return len(df.copy())


def op_copy_shallow(df: pd.DataFrame) -> int:
    return len(df.copy(deep=False))


def op_fillna(df: pd.DataFrame) -> int:
    return len(df.fillna(0))


def op_fillna_dict(df: pd.DataFrame) -> int:
    return len(df.fillna({"f0": 0.0}))


def blocks(df: pd.DataFrame) -> list[tuple[str, int, int, bool]]:
    """(dtype, bytes, elements, has_na) per block."""
    out = []
    for blk in df._mgr.blocks:
        vals = blk.values
        arr = np.asarray(vals)
        out.append((str(blk.dtype), int(arr.nbytes), int(arr.size), bool(pd.isna(arr).any())))
    return out


def derived(df: pd.DataFrame, case: str) -> float:
    b = blocks(df)
    moved = sum(x[1] for x in b)
    if case == "copy":  # run 2: + the dtype groups a consolidating copy stacks again (BlockManager.copy)
        numpy = [x for x in b if not x[0].startswith(("str", "string", "category"))]
        count: dict[str, int] = {}
        for x in numpy:
            count[x[0]] = count.get(x[0], 0) + 1
        return moved + sum(x[1] for x in numpy if count[x[0]] > 1)
    if case == "copy_shallow":
        return 0.0
    if case == "fillna":  # run 2: Block.fillna -> Block.where keeps 4 bool masks alive (source)
        hit = [x for x in b if x[3]]
        if any(x[0].startswith(("str", "string")) for x in hit):
            return float("nan")  # extension (str) block: not derived, the model refuses
        return sum(x[1] for x in hit) + 4 * max((x[2] for x in hit), default=0)
    if case == "fillna_dict":
        return 8 * N + 4 * N  # column f0 + its 4 masks
    raise ValueError(case)


def main() -> None:
    print(f"pandas {pd.__version__}")
    print("case                     frame        blocks  measured MiB  derived MiB  ratio")
    cases = [("copy", None, False, op_copy), ("copy", None, True, op_copy),
             ("copy_shallow", None, False, op_copy_shallow), ("fillna", None, False, op_fillna),
             ("fillna", "float", False, op_fillna), ("fillna", "object", False, op_fillna),
             ("fillna_dict", "float", False, op_fillna_dict)]  # fmt: skip
    with tempfile.TemporaryDirectory() as tmp:
        for case, nan_in, frag, fn in cases:
            df = frame(nan_in, frag)
            want = derived(df, case)
            nb = df._mgr.nblocks
            path = str(Path(tmp) / "f.pkl")
            df.to_pickle(path)
            del df
            gc.collect()
            m = measure_call(fn, setup=setup, setup_args=(path,), repeats=3)
            got = m.delta_bytes
            label = f"{'frag' if frag else 'consol'} nan={nan_in}"
            if got is None:
                print(f"{case:24} {label:14} {nb:5}  censored (bound {m.bound_bytes / MIB:.0f})  {want / MIB:9.0f}")
            else:
                ratio = got / want if want else float("nan")
                print(f"{case:24} {label:14} {nb:5}  {got / MIB:11.0f}  {want / MIB:11.0f}  {ratio:5.2f}")


if __name__ == "__main__":
    main()
