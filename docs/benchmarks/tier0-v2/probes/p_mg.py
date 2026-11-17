import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from nexus.models.merge import MergeModel

def mk(n, keys, seed, n_int, n_float, text_key=False, n_obj=1):
    rng = np.random.default_rng(seed)
    if text_key:
        vocab = np.array([f"k{v:010d}" for v in range(int(keys.max()) + 1)], dtype=object)
        k = pd.Series(vocab[keys], dtype=object)
    else:
        k = keys
    d = {"key": k}
    for j in range(n_int): d[f"i{j}"] = rng.integers(0, 10**6, n)
    for j in range(n_float): d[f"f{j}"] = rng.random(n)
    vocab = np.array([f"str{v:08d}" for v in range(1000)], dtype=object)
    for j in range(n_obj): d[f"s{j}"] = pd.Series(vocab[rng.integers(0, 1000, n)], dtype=object)
    return pd.DataFrame(d)

def save(df, tag):
    path = CACHE / ("mg_" + tag)
    if not (path / "meta.json").exists(): store.save(df, path)
    return str(path)

def case(name, L, R, how, tag):
    dl, dr = save(L, tag + "L"), save(R, tag + "R")
    code = f'pd.merge(left, right, on="key", how="{how}")'
    m = measure_call(P.run, setup=P.setup, setup_args=({"left": dl, "right": dr}, code), summarize=P.summarize, repeats=2)
    M = m.info["out_rows"]
    f = dict(n_left=len(L), n_right=len(R), bytes_left=1, bytes_right=1,
             moved_left=float(L.memory_usage(index=False, deep=False).sum()),
             moved_right=float(R.memory_usage(index=False, deep=False).sum()))
    pred = MergeModel.ram_at(f, M, left_elided=(how == "left" and len(R) <= len(L) and R["key"].is_unique) or False)
    got = m.delta_bytes
    print(f"{name:34s} nl={len(L):>8} nr={len(R):>8} M={M:>8} measured={'cens' if got is None else round(got/MIB,1)} MiB  formula={pred/MIB:7.1f} MiB  ratio={(got or 0)/pred:.2f}", flush=True)

if __name__ == "__main__":
    N = 1_500_000
    rng = np.random.default_rng(5)
    perm = rng.permutation(N)
    L = mk(N, perm, 1, 3, 2); R = mk(N, rng.permutation(N), 2, 2, 1)
    case("1:1 inner equal", L, R, "inner", "a")
    case("1:1 left", L, R, "left", "a")
    Rs = mk(N//4, rng.permutation(N)[:N//4], 3, 2, 1)
    case("pk-fk: right small unique", L, Rs, "inner", "b")
    case("pk-fk left", L, Rs, "left", "b")
    Rd = mk(N, rng.integers(0, N//3, N), 4, 2, 1)           # right keys repeat ~3x (non-unique)
    Ld = mk(N//3, rng.permutation(N//3), 5, 3, 2)
    case("fanout3 non-unique right", Ld, Rd, "inner", "c")
    Rlow = mk(N, rng.permutation(N*10)[:N] , 6, 2, 1)
    case("10% overlap", L, Rlow, "inner", "d")
    Lt = mk(N, perm, 7, 3, 2, text_key=True); Rt = mk(N, rng.permutation(N), 8, 2, 1, text_key=True)
    case("text key 1:1", Lt, Rt, "inner", "e")
