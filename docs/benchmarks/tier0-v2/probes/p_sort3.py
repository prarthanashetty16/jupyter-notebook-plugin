import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe_lib import *
if __name__ == "__main__":
    N = 2_000_000
    base = dict(n_rows=N, seed=13, cardinality=0.05, with_key=False, n_category=0, n_datetime=0, n_float=0)
    for kt, ki in ((1,1),(2,0),(3,0),(4,0),(1,2)):
        cfg = DatasetConfig(**{**base, "n_int":max(ki,1) if ki else 0, "n_object":kt}) if True else None
        keys = [f"s{j}" for j in range(kt)] + [f"i{j}" for j in range(ki)]
        sh=shallow_row_bytes(cfg); r=probe({"df":cfg}, f"df.sort_values({keys!r})")
        print(f"text keys={kt} int keys={ki} frame shallow={sh:3.0f} take={sh+16:3.0f} measured={r['B_per_row']}")
    # high-cardinality text keys (hash table sized by distinct values)
    cfg = DatasetConfig(**{**base, "n_int":0, "n_object":2, "cardinality":1.0})
    sh=shallow_row_bytes(cfg); r=probe({"df":cfg}, 'df.sort_values(["s0","s1"])')
    print(f"2 text keys, all distinct: take={sh+16:3.0f} measured={r['B_per_row']}")
