import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
if __name__ == "__main__":
    N = 2_000_000
    base = dict(n_rows=N, seed=11, cardinality=0.05, with_key=False, n_category=0, n_datetime=0)
    f_txt = DatasetConfig(**{**base, "n_int":0,"n_float":0,"n_object":2})
    f_int3 = DatasetConfig(**{**base, "n_int":3,"n_float":0,"n_object":0})
    f_mix = DatasetConfig(**{**base, "n_int":1,"n_float":0,"n_object":2})
    for nm,cfg,code in (("2 text keys (16 B/row frame)",f_txt,'df.sort_values(["s0","s1"])'),
                        ("3 int keys (24 B/row frame)",f_int3,'df.sort_values(["i0","i1","i2"])'),
                        ("3 int keys desc",f_int3,'df.sort_values(["i0","i1","i2"], ascending=False)'),
                        ("int+2 text keys",f_mix,'df.sort_values(["s0","i0","s1"])'),
                        ("1 text key, text-only frame",f_txt,'df.sort_values("s0")'),
                        ("1 int key desc",f_int3,'df.sort_values("i0", ascending=False)')):
        sh=shallow_row_bytes(cfg); r=probe({"df":cfg},code)
        print(f"{nm:32s} shallow={sh:4.0f} take={sh+16:3.0f}  measured={r['B_per_row']}")
