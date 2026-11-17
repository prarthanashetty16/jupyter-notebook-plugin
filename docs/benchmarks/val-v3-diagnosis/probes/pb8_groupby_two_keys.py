"""(b) groupby on two keys (int i0 + text s0): measured peak vs a structural formula.

Candidate: sum of the per-key code bases (kept alive) + the largest single-key table (freed before the
next key) + a hash table over the combined group ids (G distinct) + id arrays; compared with probes.
Prints measured B/row, G, and the candidate terms so the decomposition can be read off.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P  # noqa: E402
from probe_lib import MIB, frame_dir, measure_call  # noqa: E402

from benchmarks.datasets import make_frame  # noqa: E402
from benchmarks.suite import BASE  # noqa: E402

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
    for card in (60, 800, 6000, 40000):
        cfg = BASE.with_(n_rows=n, cardinality=card, seed=313)
        dirs = {"df": frame_dir(cfg)}
        out = {}
        for tag, code in (
            ("i0 only", 'df.groupby("i0")["f0"].sum()'),
            ("s0 only", 'df.groupby("s0")["f0"].sum()'),
            ("i0+s0", 'df.groupby(["i0", "s0"])["f0"].sum()'),
        ):
            m = measure_call(
                P.run, setup=P.setup, setup_args=(dirs, code), summarize=P.summarize, repeats=2
            )
            out[tag] = None if m.delta_bytes is None else m.delta_bytes / MIB
        df = make_frame(cfg)
        g = df.groupby(["i0", "s0"]).ngroups
        print(
            f"n={n:,} card={card:>6}: "
            + "  ".join(f"{k}={v:6.1f}" for k, v in out.items())
            + f" MiB   groups(i0,s0)={g:,}  ({out['i0+s0'] * MIB / n:5.1f} B/row; i0+s0 minus (i0 only + s0 only) = "
            f"{out['i0+s0'] - out['i0 only'] - out['s0 only']:6.1f} MiB)",
            flush=True,
        )
