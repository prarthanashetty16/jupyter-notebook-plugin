import time, numpy as np, pandas as pd, psutil
print("avail GiB at start: %.1f" % (psutil.virtual_memory().available/2**30))
rng = np.random.default_rng(1)
def best(f, reps=5):
    ts=[]
    for _ in range(reps):
        t=time.perf_counter(); f(); ts.append(time.perf_counter()-t)
    return min(ts)
print(f"{'n':>10} {'data MiB':>9} | {'argsort ns/elem':>16} {'n log2 n norm':>14} | {'duplicated ns/elem':>19} | {'take(gather) ns/elem':>21}")
rows=[]
for n in (125_000, 250_000, 500_000, 1_000_000, 2_000_000, 4_000_000, 8_000_000):
    k = rng.integers(0, n, n)                # random int64 keys, ~63% distinct
    s = pd.Series(k)
    idx = rng.permutation(n)
    a = best(lambda: np.argsort(k, kind="quicksort"))
    d = best(lambda: s.duplicated())
    g = best(lambda: k[idx])
    rows.append((n,a,d,g))
    print(f"{n:>10} {n*8/2**20:9.0f} | {a/n*1e9:16.1f} {a/(n*np.log2(n))*1e9:14.2f} | {d/n*1e9:19.1f} | {g/n*1e9:21.1f}", flush=True)
import math
def slope(i): 
    x=np.log([r[0] for r in rows]); y=np.log([r[i] for r in rows]); return np.polyfit(x,y,1)[0]
print("log-log slope of time vs n over 125k..8M: argsort %.2f  duplicated %.2f  gather %.2f" % (slope(1),slope(2),slope(3)))
sub=[r for r in rows if 1_000_000<=r[0]<=8_000_000]
x=np.log([r[0] for r in sub])
print("slope over 1M..8M: argsort %.2f duplicated %.2f gather %.2f" % tuple(np.polyfit(x,np.log([r[i] for r in sub]),1)[0] for i in (1,2,3)))
