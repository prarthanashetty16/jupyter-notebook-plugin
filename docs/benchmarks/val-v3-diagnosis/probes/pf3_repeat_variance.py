"""(4b.3) Run-to-run spread of get_join_indexers on one frame pair (is the 36-70 MiB swing noise?)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import CACHE, MIB, measure_call
CODE = '__import__("pandas.core.reshape.merge", fromlist=["x"]).get_join_indexers([df["k"]._values],[right["k"]._values], how="inner")'
if __name__ == "__main__":
    for tag in ("pf1000000_0.25_2.0_0.1", "pf1000000_0.25_6.0_0.1", "pf1000000_0.25_10.0_0.1"):
        dl, dr = str(CACHE / ("mn_" + tag + "L")), str(CACHE / ("mn_" + tag + "R"))
        m = measure_call(P.run, setup=P.setup, setup_args=({"df": dl, "right": dr}, CODE), summarize=P.summarize, repeats=6)
        print(tag, [round(r.delta_bytes / MIB, 1) if r.delta_bytes is not None else None for r in m.runs], flush=True)
