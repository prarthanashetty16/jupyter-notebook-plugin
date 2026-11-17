"""(d) drop_duplicates on the null-heavy frame: which allocations scale with nullable columns?

Same generator configuration as the failing val-v3 case (null_rate 0.35 on float/text/category/
datetime columns), measured with the project instrument at several sizes. Variants isolate the cost
per column kind: ``subset`` of one column kind at a time, and the same frame without nulls.
Prints measured B/row and the current model's value for the same features (Tier 1 inputs taken from
the true frame, so any gap is the formula, not the statistics).
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P  # noqa: E402
from probe_lib import MIB, frame_dir, measure_call  # noqa: E402

from benchmarks.datasets import make_frame  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402

CASES = {
    "full, nulls": ("df.drop_duplicates()", {}),
    "full, no nulls": ("df.drop_duplicates()", {"null_rate": 0.0}),
    "subset f0,f1": ('df.drop_duplicates(subset=["f0", "f1"])', {}),
    "subset s0,s1": ('df.drop_duplicates(subset=["s0", "s1"])', {}),
    "subset c0": ('df.drop_duplicates(subset=["c0"])', {}),
    "subset d0": ('df.drop_duplicates(subset=["d0"])', {}),
    "subset i0,i1 (no nulls possible)": ('df.drop_duplicates(subset=["i0", "i1"])', {}),
    "subset f0,s0,c0,d0": ('df.drop_duplicates(subset=["f0", "s0", "c0", "d0"])', {}),
}

if __name__ == "__main__":
    sizes = [int(x) for x in sys.argv[1:]] or [500_000, 1_000_000, 2_000_000]
    base_kw = dict(dup_rate=0.15, cardinality=0.04, null_rate=0.35, str_len=18, seed=301)
    for n in sizes:
        for name, (code, over) in CASES.items():
            cfg = BASE.with_(n_rows=n, **{**base_kw, **over})
            dirs = {"df": frame_dir(cfg)}
            m = measure_call(
                P.run, setup=P.setup, setup_args=(dirs, code), summarize=P.summarize, repeats=2
            )
            mib = None if m.delta_bytes is None else m.delta_bytes / MIB
            per_row = None if mib is None else mib * MIB / n
            df = make_frame(cfg)
            sub = None
            if "subset" in code:
                sub = eval(code[code.index("[") : code.rindex("]") + 1])
            cols = sub or list(df.columns)
            n_null = sum(int(df[c].isna().any()) for c in cols)
            print(
                f"n={n:>9,} {name:34s} peak={mib if mib is None else round(mib, 1)} MiB "
                f"({None if per_row is None else round(per_row, 1)} B/row)  survivors="
                f"{len(df.drop_duplicates(subset=sub)):>9,}  key cols={len(cols)}  null cols={n_null}",
                flush=True,
            )
