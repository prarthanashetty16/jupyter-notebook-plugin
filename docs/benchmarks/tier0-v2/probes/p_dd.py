import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
from nexus.models.drop_duplicates import DropDuplicatesModel
if __name__ == "__main__":
    N = 2_000_000
    z = dict(n_rows=N, seed=21, with_key=False, n_category=0, n_datetime=0)
    cases = [
     ("3 int, all distinct", DatasetConfig(**z, n_int=3,n_float=0,n_object=0,cardinality=1.0), 'df.drop_duplicates()', None),
     ("3 int, card 0.001, dup .5", DatasetConfig(**z, n_int=3,n_float=0,n_object=0,cardinality=0.001,dup_rate=0.5), 'df.drop_duplicates()', None),
     ("3 text, card .05", DatasetConfig(**z, n_int=0,n_float=0,n_object=3,cardinality=0.05), 'df.drop_duplicates()', None),
     ("2 float 2 int, uniform", DatasetConfig(**z, n_int=2,n_float=2,n_object=0,cardinality=0.1,dup_rate=0.3), 'df.drop_duplicates()', None),
     ("default mixed dup .5", DatasetConfig(n_rows=N, seed=22, dup_rate=0.5), 'df.drop_duplicates()', None),
     ("default mixed unshared strings", DatasetConfig(n_rows=N, seed=22, dup_rate=0.5, share_strings=False), 'df.drop_duplicates()', None),
     ("subset single low-card int", DatasetConfig(n_rows=N, seed=23, cardinality=0.001), 'df.drop_duplicates(subset=["i0"])', ["i0"]),
     ("subset single text card .05", DatasetConfig(n_rows=N, seed=23, cardinality=0.05), 'df.drop_duplicates(subset=["s0"])', ["s0"]),
     ("subset 2 cols", DatasetConfig(n_rows=N, seed=23, cardinality=0.05), 'df.drop_duplicates(subset=["i0","s0"])', ["i0","s0"]),
    ]
    for name,cfg,code,subset in cases:
        df = make_frame(cfg)
        cols = subset or list(df.columns)
        k = len(cols)
        keyfrac = sum(df[c].nunique(dropna=False) for c in cols)/k/N
        rowfrac = len(df.drop_duplicates(subset=subset))/N
        moved = float(df.memory_usage(index=False, deep=False).sum())
        feats = dict(n_rows=N, n_keys=k, input_bytes=moved, moved_bytes=moved)
        pred = DropDuplicatesModel.ram_at(feats, keyfrac, rowfrac)/N
        r = probe({"df": cfg}, code)
        print(f"{name:32s} k={k} key_frac={keyfrac:.3f} row_frac={rowfrac:.3f} measured={r['B_per_row']}  formula={pred:6.1f}  ratio={(r['B_per_row'] or 0)/pred:.2f} bound={r['bound_MiB']}MiB")
