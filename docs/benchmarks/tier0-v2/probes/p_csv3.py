import sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
from p_csv import peak
from p_csv2 import write

if __name__ == "__main__":
    N = 1_000_000
    rng = np.random.default_rng(9)
    pts = []
    print("family A: 1 column, vary width")
    for d in (1, 4, 9, 15):
        df = pd.DataFrame({"c0": rng.integers(10**(d-1) if d>1 else 0, 10**d, N)})
        path = write(f"A{d}", df); F = Path(path).stat().st_size / N
        m = peak(path, "pd.read_csv({p})"); pts.append((F, 1, m.delta_bytes/N))
        print(f"  digits={d:2d} file/row={F:5.1f}  peak={m.delta_bytes/N:6.1f} B/row", flush=True)
    print("family B: 4-digit ints, vary number of columns")
    for k in (1, 4, 16, 32):
        df = pd.DataFrame({f"c{j}": rng.integers(1000, 10000, N) for j in range(k)})
        path = write(f"B{k}", df); F = Path(path).stat().st_size / N
        m = peak(path, "pd.read_csv({p})"); pts.append((F, k, m.delta_bytes/N))
        print(f"  cols={k:2d} file/row={F:5.1f}  peak={m.delta_bytes/N:6.1f} B/row  per field={m.delta_bytes/N/k:5.1f}", flush=True)
    A = np.array([[f, k] for f, k, _ in pts]); y = np.array([p for *_, p in pts])
    coef, res, *_ = np.linalg.lstsq(A, y, rcond=None)
    print("least squares  peak = a*F + b*fields :  a=%.2f b=%.1f" % tuple(coef), " max rel err %.0f%%" % (100*np.max(np.abs(A@coef-y)/y)))
