"""(b) Held-out validation of the factorize model: probe points NOT used in its derivation.

Measures ``df["c"].astype("category")`` with the project instrument and compares it with
``factorize_peak_bytes`` evaluated at the true distinct count and at the scatter that
``stats.hash_scatter`` reports for the same column (i.e. including the Tier 1 statistic).
"""

import pathlib
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from pb2_generators import meas  # noqa: E402

from nexus import stats  # noqa: E402
from nexus.models import _util as u  # noqa: E402

MIB = 2**20


def text_vocab(kind, U, rng):
    if kind == "seq":
        return np.array([f"id_{i:010d}" for i in range(U)], dtype=object)
    chars = np.array(list(string.ascii_lowercase))
    a = rng.integers(0, 26, size=(U, 14))
    return np.array(["".join(r) for r in chars[a]], dtype=object)


POINTS = [  # (kind, key layout, n, U)
    ("text", "random", 1_500_000, 3_000),
    ("text", "random", 3_000_000, 200_000),
    ("text", "random", 3_000_000, 600_000),
    ("text", "seq", 2_000_000, 100_000),
    ("text", "random", 800_000, 50_000),
    ("numeric", "dense", 1_000_000, 30_000),
    ("numeric", "dense", 3_000_000, 400_000),
    ("numeric", "random", 1_000_000, 30_000),
    ("numeric", "random", 3_000_000, 400_000),
    ("numeric", "random", 1_500_000, 1_200_000),
    ("numeric", "random", 600_000, 5_000),
]

if __name__ == "__main__":
    rng = np.random.default_rng(99)
    for kind, layout, n, U in POINTS:
        codes = rng.permutation(np.concatenate([np.arange(U), rng.integers(0, U, n - U)]))
        if kind == "text":
            col = pd.Series(text_vocab(layout, U, rng)[codes], dtype=object)
        else:
            vocab = np.arange(U) if layout == "dense" else rng.integers(0, 2**62, U)
            col = pd.Series(vocab[codes].astype(np.int64))
        df = pd.DataFrame({"c": col})
        measured = meas(df, f"v_{kind}_{layout}_{n}_{U}", 'df["c"].astype("category")')
        sc = stats.hash_scatter(df["c"], text=kind == "text")
        model = u.factorize_peak_bytes(kind, n, U, sc.value) / MIB
        model_random = u.factorize_peak_bytes(kind, n, U, 1.0) / MIB
        print(
            f"{kind:7s} {layout:6s} n={n:>9,} U={U:>9,}: measured {measured:7.1f}  model(scatter={sc.value:4.2f}) {model:7.1f}"
            f"  ratio {measured / model:4.2f}   | model(random keys) {model_random:7.1f}  ratio {measured / model_random:4.2f}",
            flush=True,
        )
