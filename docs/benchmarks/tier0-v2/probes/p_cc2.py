import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
if __name__ == "__main__":
    N = 2_000_000
    z = dict(n_rows=N, with_key=False, n_category=0, n_datetime=0, n_object=0)
    for nm, kw in (("1 int", dict(n_int=1,n_float=0)), ("4 int", dict(n_int=4,n_float=0)), ("8 int", dict(n_int=8,n_float=0)), ("2 int 2 float", dict(n_int=2,n_float=2))):
        cfg = DatasetConfig(**z, **kw, seed=41); cfg2 = DatasetConfig(**z, **kw, seed=42)
        w = 8*(kw["n_int"]+kw["n_float"])
        for code in ("pd.concat([a,b])", "pd.concat([a,b], ignore_index=True)"):
            r = probe({"a":cfg,"b":cfg2}, code, units=2*N)
            print(f"{nm:14s} moved={w} B/row  {code:40s} measured={r['B_per_row']}  extra={r['B_per_row']-w if r['B_per_row'] else None}")
