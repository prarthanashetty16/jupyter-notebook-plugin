# Isolated allocation probes (Phase 4a)

The scripts behind every "verified with isolated probes" claim in the Tier 0 model docstrings
(`src/nexus/models/`). They measure one pandas call on a purpose-built synthetic frame (NOT a
benchmark point) with the project's own instrument, `nexus.measure.measure_call` (spawned child,
inputs loaded from disk, OS peak counters), and compare it with the formula. Run from the repo root,
e.g. `python docs/benchmarks/tier0-v2/probes/p_sort.py`; `probe_lib.py` caches generated frames in
`probe_cache/` next to it (git-ignored). They are kept as run (not linted).

| script | mechanism tested |
|---|---|
| p_sort, p_sort2, p_sort3 | sort_values: copy of shallow bytes + indexer + index; nargsort temporaries; lexsort with text keys |
| p_dd, p_dd2 | drop_duplicates: factorize / id fusion / compress step / null lift; n = 1M vs 2M |
| p_cc, p_cc2 | concat: shallow copy + 12 B/row index; shared vs unshared strings |
| p_mg, p_mg2 | merge: indexer phase vs full merge, left-copy elision, presized hash table |
| p_as, p_as_tm, p_cat, p_cat2, p_cat_tm | astype to str (object-int temporary, pymalloc classes) and to category (by distinct count) |
| p_csv, p_csv2, p_csv3 | read_csv: default vs low_memory=False vs chunked; width / column sweeps |
| p_cache | in-process timing of argsort / duplicated / gather at 125k..8M rows (cache effect, no memory pressure) |

Instrument limits: a probe whose peak stays below the setup peak is censored and printed as `None`
(single-column `drop_duplicates(subset=...)` probes); nothing was inferred from those.
