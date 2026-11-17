import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
if __name__ == "__main__":
    N = 2_000_000
    base = dict(n_rows=N, seed=7, cardinality=0.05)
    frames = {
        "default": DatasetConfig(**base),
        "unshared_str": DatasetConfig(**base, share_strings=False),
        "narrow_1int": DatasetConfig(**{**base, "n_int":1,"n_float":0,"n_object":0,"n_category":0,"n_datetime":0,"with_key":False}),
        "narrow_2cols": DatasetConfig(**{**base, "n_int":1,"n_float":1,"n_object":0,"n_category":0,"n_datetime":0,"with_key":False}),
        "wide_20f": DatasetConfig(**{**base, "n_int":4,"n_float":16,"n_object":0,"n_category":0,"n_datetime":0}),
    }
    for fname, cfg in frames.items():
        sh = shallow_row_bytes(cfg)
        for key, code in (("i0", 'df.sort_values("i0")'), ("f0", 'df.sort_values("f0")'), ("s0", 'df.sort_values("s0")'), ("i0,f0", 'df.sort_values(["i0","f0"])')):
            cols = make_frame(cfg).columns
            if key.split(",")[0] not in cols or (key=="i0,f0" and "f0" not in cols): continue
            r = probe({"df": cfg}, code)
            take = sh + 16; sortp = 42
            print(f"{fname:14s} shallow={sh:5.1f} B/row  key={key:6s} measured={r['B_per_row']}  pred take={take:.0f} sort={sortp} max={max(take,sortp):.0f}  status={r['status']} bound={r['bound_MiB']}")
