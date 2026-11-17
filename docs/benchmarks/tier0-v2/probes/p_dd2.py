import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
from nexus.models.drop_duplicates import DropDuplicatesModel
if __name__ == "__main__":
    for N in (1_000_000, 2_000_000):
        for nr in (0.0, 0.1):
            cfg = DatasetConfig(n_rows=N, seed=61, dup_rate=0.3, null_rate=nr, cardinality=0.05)
            df = make_frame(cfg)
            k = df.shape[1]
            keyfrac = float(np.mean([df[c].nunique(dropna=False) for c in df.columns]))/N
            rowfrac = len(df.drop_duplicates())/N
            nulls = sum(int(df[c].isna().any()) for c in df.columns)
            moved = float(df.memory_usage(index=False, deep=False).sum())
            f = dict(n_rows=N, n_keys=k, input_bytes=moved, moved_bytes=moved)
            base = DropDuplicatesModel.ram_at(f, keyfrac, rowfrac)/N
            r = probe({"df": cfg}, "df.drop_duplicates()")
            print(f"n={N:>8} null_rate={nr}: key cols with nulls={nulls}  measured={r['B_per_row']:6}  formula(no lift)={base:6.1f}  measured-formula={r['B_per_row']-base:5.1f} B/row  (8*nulls={8*nulls})", flush=True)
