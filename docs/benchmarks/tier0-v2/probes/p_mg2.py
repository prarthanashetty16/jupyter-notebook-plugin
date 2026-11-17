import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from p_mg import mk, save

def run(name, L, R, how, tag):
    dl, dr = save(L, tag + "L"), save(R, tag + "R")
    out = {}
    for lab, code in (("indexers only", f'__import__("pandas.core.reshape.merge", fromlist=["x"]).get_join_indexers([left["key"]._values],[right["key"]._values], how="{how}")'),
                      ("full merge", f'pd.merge(left, right, on="key", how="{how}")')):
        m = measure_call(P.run, setup=P.setup, setup_args=({"left": dl, "right": dr}, code), summarize=P.summarize, repeats=2)
        out[lab] = m.delta_bytes
    M = pd.merge(L, R, on="key", how=how).shape[0]
    nl, nr = len(L), len(R)
    f = lambda v: "cens" if v is None else f"{v/MIB:6.1f}"
    print(f"{name:28s} nl={nl:>8} nr={nr:>8} M={M:>8}  indexers={f(out['indexers only'])} MiB  full={f(out['full merge'])} MiB   (8nl={8*nl/MIB:.1f} 8nr={8*nr/MIB:.1f} 8M={8*M/MIB:.1f} MiB)", flush=True)

if __name__ == "__main__":
    N = 1_500_000
    rng = np.random.default_rng(5)
    perm = rng.permutation(N)
    L = mk(N, perm, 1, 3, 2); R = mk(N, rng.permutation(N), 2, 2, 1)
    run("1:1 inner", L, R, "inner", "a")
    Rs = mk(N//4, rng.permutation(N)[:N//4], 3, 2, 1)
    run("right small unique inner", L, Rs, "inner", "b")
    run("right small unique left", L, Rs, "left", "b")
    Rd = mk(N, rng.integers(0, N//3, N), 4, 2, 1); Ld = mk(N//3, rng.permutation(N//3), 5, 3, 2)
    run("fanout3 non-unique right", Ld, Rd, "inner", "c")
    run("fanout3 left join", Ld, Rd, "left", "c")
