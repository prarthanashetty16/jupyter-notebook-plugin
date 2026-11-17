# Probes behind the Phase 4b.2 diagnosis (`docs/benchmarks/val-v3-diagnosis.md`)

Isolated allocation probes: one pandas call on a purpose-built synthetic frame, measured with the
project instrument (`nexus.measure.measure_call`: spawned child, inputs loaded from disk, OS peak
counters), sometimes with `tracemalloc`. They test MECHANISMS and are not benchmark points. Run from
the repo root, e.g. `python docs/benchmarks/val-v3-diagnosis/probes/pb9_validate_factorize.py`;
`probe_lib.py` caches generated frames in `probe_cache/` (git-ignored). Kept as run (not linted).
Do not run them while a benchmark is running.

| script | question |
|---|---|
| pa1_offset, pa2_tiny_first_call | (a) is there a fixed / first-call offset? (no) |
| pb1_category_sweep | (b) astype -> category, OS peak vs tracemalloc, over n and distinct count |
| pb2_generators, pb3_steps, pb4_content | (b) same n and U, different key content: 48 vs 86 MiB; which step; which property |
| pb5_int_keys | (b) int64 keys: dense 0..U-1 vs random ids |
| pb6_hash_replica, pb7_int_hash_replica | (b) khash X31 string / int64 hash replicas vs measured resident table growth |
| pb8_groupby_two_keys | (b) two-key groupby: bases + id arrays + combined-id table |
| pb9_validate_factorize | (b) held-out validation of `factorize_peak_bytes` (+ `stats.hash_scatter`) |
| pb10_numeric_base | (b) numeric base / copy phase of astype -> category vs `pd.factorize` |
| pc1_merge_rows, pc2_merge_nonunique, pc3_merge_design, pc3_fit | (c) merge: output rows vs formula, non-unique right keys, 27-probe design and fit |
| pd1_dd_null_columns, pd2_dd_formula_terms | (d) drop_duplicates: cost per nullable column kind; formula terms at the true statistics |
| pe1_seed_variance | (e) estimator variance over 10 sampling seeds vs systematic error |

`pc3_merge_design.csv` is the raw output of `pc3_merge_design.py`.
