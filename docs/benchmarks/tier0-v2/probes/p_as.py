import sys, sys; import pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import probe_lib as P
from probe_lib import *
import sys as _s

def save(df, tag):
    path = CACHE / ("as_" + tag)
    if not (path / "meta.json").exists(): store.save(df, path)
    return str(path)

def meas(df, tag, code):
    d = save(df, tag)
    m = measure_call(P.run, setup=P.setup, setup_args=({"df": d}, code), summarize=P.summarize, repeats=2)
    return m

if __name__ == "__main__":
    N = 2_000_000
    rng = np.random.default_rng(3)
    print("pandas str default:", pd.Series(["a"]).dtype, "| sys.getsizeof('1234567')=", sys.getsizeof("1234567"))
    for digits in (1, 3, 5, 7, 9, 12, 17):
        lo = 10 ** (digits - 1) if digits > 1 else 0
        v = rng.integers(lo, min(10**digits, 2**62), N)
        m = meas(pd.DataFrame({"c": v}), f"int{digits}", 'df["c"].astype(str)')
        print(f"int64 {digits:2d} digits: peak={m.delta_bytes/N if m.delta_bytes else None:6.1f} B/row  (str obj size={sys.getsizeof('1'*digits)})", flush=True)
    for nm, v in (("float rand (17 chars)", rng.random(N)), ("float round2", np.round(rng.random(N)*1000, 2))):
        m = meas(pd.DataFrame({"c": v}), nm.split()[0]+nm[-3:], 'df["c"].astype(str)')
        print(f"{nm:22s}: peak={m.delta_bytes/N if m.delta_bytes else None:6.1f} B/row", flush=True)
    ts = pd.Series(np.datetime64("2020-01-01") + rng.integers(0, 10**8, N).astype("timedelta64[s]"))
    m = meas(pd.DataFrame({"c": ts}), "dt", 'df["c"].astype(str)')
    print(f"datetime64 -> str      : peak={m.delta_bytes/N if m.delta_bytes else None:6.1f} B/row (str len {len(str(ts[0]))})", flush=True)
