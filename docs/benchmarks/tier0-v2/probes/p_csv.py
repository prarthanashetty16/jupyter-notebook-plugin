import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *

def mkfile(cfg, tag):
    path = CACHE / f"csv_{tag}.csv"
    df = make_frame(cfg)
    if not path.exists(): df.to_csv(path, index=False)
    return str(path), df

def peak(path, code):
    full = code.format(p=repr(path))
    m = measure_call(P.run, setup=P.setup, setup_args=({}, full), summarize=P.summarize, repeats=2)
    return m

if __name__ == "__main__":
    N = 1_000_000
    base = dict(n_rows=N, seed=51, with_key=False, n_category=0, n_datetime=0)
    cfgs = {
      "numeric 7 cols": DatasetConfig(**{**base, "n_int":4,"n_float":3,"n_object":0,"cardinality":0.5}),
      "numeric 2 cols": DatasetConfig(**{**base, "n_int":1,"n_float":1,"n_object":0,"cardinality":0.5}),
      "strings 4 cols card .05": DatasetConfig(**{**base, "n_int":0,"n_float":0,"n_object":4,"cardinality":0.05}),
      "strings 4 cols all distinct": DatasetConfig(**{**base, "n_int":0,"n_float":0,"n_object":4,"cardinality":1.0}),
      "mixed 2i 2f 2s": DatasetConfig(**{**base, "n_int":2,"n_float":2,"n_object":2,"cardinality":0.05}),
    }
    for name, cfg in cfgs.items():
        path, df = mkfile(cfg, name.replace(" ", "_").replace(".", ""))
        fbytes = Path(path).stat().st_size
        # in-memory result: pointers/values (shallow) and the string objects it holds
        out = pd.read_csv(path)
        shallow = float(out.memory_usage(index=False, deep=False).sum())
        deep = float(out.memory_usage(index=False, deep=True).sum())
        ncols = out.shape[1]; dt = dict(out.dtypes.astype(str)); del out
        rows = []
        for lab, code in (("default", "pd.read_csv({p})"), ("low_memory=False", "pd.read_csv({p}, low_memory=False)"),
                          ("chunks 100k (no concat)", "[c.shape for c in pd.read_csv({p}, chunksize=100000)]")):
            m = peak(path, code)
            rows.append(f"{lab}={m.delta_bytes/N:.0f}" if m.delta_bytes else f"{lab}=cens")
        print(f"{name:28s} file={fbytes/N:5.1f} B/row result: shallow={shallow/N:5.1f} deep={deep/N:5.1f} | peak B/row: " + "  ".join(rows), flush=True)
        print("     dtypes:", sorted(set(dt.values())))
