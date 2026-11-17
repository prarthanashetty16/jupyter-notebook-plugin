import tracemalloc, numpy as np, pandas as pd
N=1_000_000
rng=np.random.default_rng(4)
def tm(label, f):
    tracemalloc.start(); r=f(); c,p=tracemalloc.get_traced_memory(); tracemalloc.stop(); print(f"   {label:34s} final={c/N:6.1f} peak={p/N:6.1f} B/row"); return r
for U in (100, 1_000_000):
    vocab=np.array([f"value_{i:09d}" for i in range(U)],dtype=object)
    codes=rng.permutation(np.concatenate([np.arange(U), rng.integers(0,U,N-U)])) if U<N else rng.permutation(N)
    s=pd.Series(vocab[codes],dtype=object); v=s.to_numpy()
    print(f"text U={U}")
    tm("factorize(sort=False)", lambda: pd.factorize(v, sort=False))
    tm("factorize(sort=True)", lambda: pd.factorize(v, sort=True))
    tm("Series.astype('category')", lambda: s.astype("category"))
    sn=pd.Series(codes.astype('int64')); print(f"int U={U}")
    tm("Series.astype('category')", lambda: sn.astype("category"))
