import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
if __name__ == "__main__":
    N = 1_500_000
    d = DatasetConfig(n_rows=N, seed=31, cardinality=0.05)
    d2 = DatasetConfig(n_rows=N, seed=32, cardinality=0.05)  # different vocabularies
    dnum = DatasetConfig(n_rows=N, seed=33, n_object=0, n_category=0)
    dun = DatasetConfig(n_rows=N, seed=31, cardinality=0.05, share_strings=False)
    dun2 = DatasetConfig(n_rows=N, seed=32, cardinality=0.05, share_strings=False)
    dobj = DatasetConfig(n_rows=N, seed=34, n_category=0, cardinality=0.05)
    dobj2 = DatasetConfig(n_rows=N, seed=35, n_category=0, cardinality=0.05)
    dstr = DatasetConfig(n_rows=N, seed=34, n_category=0, cardinality=0.05, str_dtype="str")
    cases = [("2 frames, categoricals differ", {"a":d,"b":d2}, "pd.concat([a,b])"),
             ("2 frames same seed (same cats)", {"a":d,"b":d}, "pd.concat([a,b])"),
             ("2 frames ignore_index", {"a":d,"b":d2}, "pd.concat([a,b], ignore_index=True)"),
             ("numeric only", {"a":dnum,"b":dnum}, "pd.concat([a,b])"),
             ("object, no category, shared", {"a":dobj,"b":dobj2}, "pd.concat([a,b])"),
             ("object, unshared", {"a":dun,"b":dun2}, "pd.concat([a,b])"),
             ("3 frames object", {"a":dobj,"b":dobj2,"c":dobj}, "pd.concat([a,b,c])"),
             ]
    for name, frames, code in cases:
        dfs = {k: make_frame(c) for k,c in frames.items()}
        moved = sum(float(x.memory_usage(index=False, deep=False).sum()) for x in dfs.values())
        tot = sum(len(x) for x in dfs.values())
        r = probe(frames, code, units=tot)
        ign = "ignore_index" in code
        pred = (moved + (0 if ign else 8*tot))/tot
        print(f"{name:32s} moved={moved/tot:5.1f} B/row pred(moved+idx)={pred:5.1f}  measured={r['B_per_row']}  ratio={(r['B_per_row'] or 0)/pred:.2f}")
