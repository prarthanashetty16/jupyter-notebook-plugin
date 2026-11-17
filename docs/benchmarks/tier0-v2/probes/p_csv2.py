import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from p_csv import peak

def write(name, df):
    path = CACHE / f"csv2_{name}.csv"
    if not path.exists(): df.to_csv(path, index=False)
    return str(path)

if __name__ == "__main__":
    N = 1_000_000
    rng = np.random.default_rng(8)
    rows = []
    cases = {
      "8 short ints (1 digit)": pd.DataFrame({f"c{j}": rng.integers(0, 10, N) for j in range(8)}),
      "2 short ints": pd.DataFrame({f"c{j}": rng.integers(0, 10, N) for j in range(2)}),
      "4 long floats (18 ch)": pd.DataFrame({f"c{j}": rng.random(N) for j in range(4)}),
      "1 long float": pd.DataFrame({"c0": rng.random(N)}),
      "1 int 9 digits": pd.DataFrame({"c0": rng.integers(10**8, 10**9, N)}),
      "20 short ints": pd.DataFrame({f"c{j}": rng.integers(0, 10, N) for j in range(20)}),
    }
    for name, df in cases.items():
        path = write(name.replace(" ", "_").replace("(","").replace(")",""), df)
        F = Path(path).stat().st_size / N
        out = df.shape[1] * 8.0
        m = peak(path, "pd.read_csv({p})"); ml = peak(path, "pd.read_csv({p}, low_memory=False)")
        print(f"{name:26s} fields={df.shape[1]:2d} file={F:5.1f} out={out:5.0f} | default={m.delta_bytes/N:6.1f}  low_memory=False={ml.delta_bytes/N:6.1f}   peak-out={m.delta_bytes/N-out:6.1f}  (peak-out)/F={(m.delta_bytes/N-out)/F:.2f}", flush=True)
