import tracemalloc, numpy as np, pandas as pd, sys
N=1_000_000
rng=np.random.default_rng(3)
for digits in (1,7,12):
    v=rng.integers(10**(digits-1) if digits>1 else 0, 10**digits, N)
    s=pd.Series(v)
    tracemalloc.start(25)
    r=s.astype(str)
    cur,peak=tracemalloc.get_traced_memory()
    snap=tracemalloc.take_snapshot()
    tracemalloc.stop()
    print(f"{digits} digits: final={cur/N:.1f} B/row traced-peak={peak/N:.1f} B/row dtype={r.dtype}")
# step by step on the 7 digit case
v=rng.integers(10**6,10**7,N)
tracemalloc.start()
o=np.asarray(v,dtype=object); c,p=tracemalloc.get_traced_memory(); print("np.asarray(int64,dtype=object):",c/N,p/N)
tracemalloc.stop()
tracemalloc.start()
from pandas._libs import lib
res=lib.ensure_string_array(v, convert_na_value=False); c,p=tracemalloc.get_traced_memory(); print("lib.ensure_string_array:",c/N,p/N)
tracemalloc.stop()
tracemalloc.start()
r=pd.array(v.astype(str) if False else res, dtype=pd.StringDtype(na_value=np.nan)); c,p=tracemalloc.get_traced_memory(); print("StringDtype from object array:",c/N,p/N, type(r))
tracemalloc.stop()
