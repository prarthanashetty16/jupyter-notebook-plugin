# Diagnosis of the val-v3 failures (Phase 4b.2)

val-v3 was read by the developer and a reviewer, so it is **development data now** (split version 4).
Nothing in this document is evidence of generalisation; the held-out check is val-v4 (not run).
Every claim below cites a probe in `docs/benchmarks/val-v3-diagnosis/probes/` (project instrument:
spawned child, inputs loaded from disk, OS peak counters; `tracemalloc` where noted). The probes are
synthetic frames built for the mechanism, not benchmark points. Fixes were derived from the pandas
mechanism and these probes; no constant was fitted to a val-v3 point (the three constants that were
fitted are named in "What was fitted" and come from probe grids).

## Summary

| failure on val-v3 | cause class | evidence |
|---|---|---|
| astype `str_to_category_card12000`, groupby `str_card0p04_two_values`, `two_keys_card800` (n = 1M, also 3M) and the two dev points from 4b (`str_to_category_zipf`, `two_keys_mean_realistic`) | **a formula term is missing** (resident pages of a presized hash table), hidden by a probe-design confound in Phase 4a; the statistics were right | (a), (b), (e) |
| merge `inner_overlap25_fanout6` (Tier 1 moved *below* Tier 0) | **a formula term is missing** (the sort-based join factorizes both sides in one table); the output-row statistic was right | (c) |
| drop_duplicates `null_heavy_full` at 10M ("killed at the cap", scored above-high) | **a measurement/scoring artifact**: the harness cap is on *total* RSS, and my own evaluator scored the cap as the operation's delta; plus a planner that let the point run | (d) |
| the "fixed offset at n = 1M" | **rejected**: there is no first-call or fixed overhead; it is (a)'s table term, which saturates once n reaches the presize cap | (a) |

## (a) Is there a fixed offset at n = 1M? No

*Probes `pa1_offset.py`, `pa2_tiny_first_call.py`.*

First-call overhead, measured in a fresh child with tiny inputs (the instrument reports a delta only
when the call exceeds the peak reached while loading the inputs, so a fixed first-call cost of tens
of MiB would show up even at 5k rows):

| operation | n = 5k | 20k | 50k | 200k |
|---|---|---|---|---|
| astype -> category (12000 distinct strings) | 0.5 MiB | 1.3 | 2.9 | 11.1 |
| groupby (str key) | 0.6 | 1.5 | 2.4 | 10.8 |
| groupby (int + str keys) | 1.0 | 2.4 | 4.7 | 17.8 |
| drop_duplicates (null-heavy frame) | 1.4 | 3.7 | 9.0 | 36.4 |

The deltas scale with n from the smallest size; the intercept is below 0.5 MiB. Nothing resembling
the 35-40 MiB seen at n = 1M exists in a first call. The other eight columns of the val-v3 frame do not
matter either: the same operation on the full frame and on the single `s0` column measured 63.0 and
63.2 MiB at n = 1M.

What *does* look like a fixed offset is the same astype/category call over n at 12000 distinct random
strings (`pb1_category_sweep.py`, B/row): 67.0 (300k), 64.6 (600k), 66.2 (1M), 52.1 (1.5M), 45.1 (2M),
38.1 (3M), 34.6 (4M). Per row it falls as n grows, i.e. a roughly constant number of MiB above a
linear part: that is a **table whose size stops growing at ~1M rows**. With few distinct values (12) the
same call costs 24 B/row at every n.

**Conclusion (a):** no first-call overhead; the "offset" is the saturating table term of (b).
It is not modelled as an additive range `[0, c]` because there is nothing to put in it.

## (b) astype -> category at high cardinality: why Tier 1 was worse than Tier 0

*Probes `pb1`..`pb10`, `pe1_seed_variance.py`.*

**The statistics were right.** For the failing points Tier 1's distinct-count estimate equals the
truth (12000 of 12000 for astype card12000; 40000 for `str_card0p04`; 20000 for `int_card20000`;
sd over 10 sampling seeds 0.0-0.1%; `pe1`). The error is in the RAM formula that consumed them.

**Isolating the allocation.** `tracemalloc` (pandas' khash allocator is traced) and the OS peak, same
call, text column, 2M rows (`pb1`):

| distinct | OS peak | tracemalloc peak |
|---|---|---|
| 12 | 46.3 MiB | 80.1 MiB |
| 12000 | 85.9 MiB | 80.1 MiB |

`tracemalloc` is identical (80.1 MiB) because the same hash table is *allocated* in both cases; the OS
peak differs by 39.6 MiB because the table's pages only become resident when a key hashes into them.
Twelve keys touch 12 pages; twelve thousand random keys touch ~95% of a 2^21-bucket table. The table
is allocated for `min(n, 2**20 + 7)` entries whatever the distinct count (`SIZE_HINT_LIMIT` in pandas),
so for n >= ~1M it is always 2^21 buckets = 48 MiB of arrays for text keys.

**Why the Phase 4a curve missed it (a probe-design confound).** Same n, same distinct count (12000),
two string sets (`pb2`, `pb3`, `pb4`): `value_000000123`-style and `000000000123`-style sequential
strings peak at **47.8-48.0 MiB**; random lowercase strings and hex digests at **86.0-86.2 MiB**
(factorize alone, 2M rows). Phase 4a's `p_cat.py` used sequential strings (and ints 0..U-1); the
benchmark generator makes random strings. khash hashes strings with X31 (`h = 31h + byte`), under
which sequential keys land in neighbouring buckets and touch a few pages. Replicating the hash
(`pb6_hash_replica.py`) predicts the touched table MiB for the four string sets as 1.7, 1.7, 39.8 and
39.7 against 1.8, 2.0, 40.2 and 40.0 measured. For int64 keys (`pb5`, `pb7`) the same replica gives
16.0 / 22.5 / 30.2 MiB touched for dense 5000 / random 5000 / random 12000 keys against 15.3 / 21.8 /
29.7 measured.

**The model** (`nexus.models._util.factorize_peak_bytes`; derivation in its comment block):
`max(factorize phase, copy phase)`, factorize phase = `base * n` + resident table pages + `unique
bytes * distinct`; table buckets `2^ceil(log2(max(min(n, 2^20 + 7), distinct) / 0.77))`; touched share
`1 - exp(-distinct / pages)` for random keys (a table that had to grow is fully resident); text arrays
16 + 8 B/bucket, numeric 8 + 8; the numeric copy phase is 16.3 B/row independent of U (`pb10`:
astype of an int column costs 16.3 B/row at U = 20..1000 but equals `pd.factorize` once the table
dominates). Validation, none of it a benchmark point:

* the 12 sweep probes it was derived from: ratio measured/model 0.97-1.01;
* **11 held-out probes** (`pb9_validate_factorize.py`: other n, other U, random and sequential text,
  dense and random ints; scatter taken from the Tier 1 statistic): random text 0.99-1.00 (4 points),
  random ints 0.94-0.98 (4), dense ints 0.85 and 1.01, sequential text 0.83. It over-predicts clustered
  keys by up to 20% and never under-predicts by more than 1%.

`stats.hash_scatter` (Tier 1) replays khash's string/int64 hash over <= 8000 sampled distinct values
and returns the share of table pages they touch relative to random keys (1.0 random, 0.05 sequential
strings, 0.7 dense ints; 9-11 ms). Tier 0 (no data) spans "few distinct" .. "all distinct, random
keys". The old `FACTORIZE_KNOTS` curve (n = 2M, sequential keys) is gone; the Phase 4a note that the
curve varies ~15% with n was an under-statement: the n-dependence is the presize cap (a 3x change in
B/row between 300k and 4M at fixed distinct count).

**Why Tier 1 was worse than Tier 0.** Tier 0's wide range (24 .. 83 B/row, expected 44.6) happened to
contain the true 66 B/row; Tier 1 narrowed around the (wrong, sequential-key) curve at 25 B/row.
Narrowing a range around a biased centre is exactly what the range policy (Step 3) now guards against.

## (c) merge `inner_overlap25_fanout6`: the statistic was right, the formula was not

*Probes `pc1`, `pc2`, `pc3` (36-point grid), `pc3_fit.py`.*

| n | true output rows | Tier 1 estimate [low, mid, high] | RAM actual | Tier 1 RAM (old formula) | old formula at the TRUE M |
|---|---|---|---|---|---|
| 1M | 87,504 | 86,420 / 90,234 / 94,048 | 71.8 MiB | 41.2 / 51.6 / 59.4 | 51.6 |
| 3M | 262,500 | 248,067 / 257,502 / 266,937 | 180.6 MiB | 71.6 / 89.6 / 103.3 | 89.7 |

The interval contains the truth (3% error); the sampler is a deterministic key-hash sample, so it has no
seed variance (its output-row error across all val-v3 merge points was within 1-3%). Fed the *true*
output rows the old formula still gives 51.6 / 89.7 MiB: **the formula, not the statistic, is
2x low at 3M.** Tier 1 moved below Tier 0 because Tier 0's output-rows prior (1M..4M rows) over-charged by
accident (111 MiB) and Tier 1's correct, small M exposed the missing term.

Cause (pandas 3.1 `_factorize_keys`): when the right keys are not unique the join is sort-based and
one factorizer sees both sides, so its hash table holds the UNION of the left and right keys (the 4a
formula sized it by the right keys' distinct count), both code arrays stay alive, and the group-sort adds
the sorters and per-group counts. Fitting the structural terms to 27 probes (unique left keys, fan-out
2 / 6, overlap 0.2 / 0.9, 0.5M-2M rows; `pc3_fit.py`): `table(union) + 16 B*(nl+nr) + 8 B*union + 16 B*M`
gives measured/formula **1.02 (range 0.83-1.17)**; at 3M (`pc2`) it gives 155 MiB against 181 measured.
The unique-right path is unchanged (probe ratio 0.93-0.99). Tier 1 now supplies `left_distinct`
(`join_profile`) and the overlap for the union estimate. Re-evaluated at the true M the old points
become 62.4 / 72.0 (1M, actual 71.8) and 154.6 / 178.4 (3M, actual 180.6). An unexplained +-17% remains
between fan-out 2 and 6 at equal right size; it is carried by the range, not modelled.

## (d) drop_duplicates `null_heavy_full` at 10M: an artifact of my scoring and of the planner

*Probes `pd1_dd_null_columns.py`, `pd2_dd_formula_terms.py`.*

Allocations that scale with nullable columns, measured on the failing configuration (null rate 0.35 on
float/text/category/datetime columns; B/row; `pd1`):

| frame | n = 0.5M | 1M | 2M |
|---|---|---|---|
| full, 6 null-containing key columns | 193.9 | 201.5 | 193.2 |
| same frame, no nulls | 145.8 | 153.4 | 145.0 |
| difference (nulls) | **48.1** | **48.1** | **48.2** |
| `subset=[f0,f1]` (2 float, null-containing) | 62.6 | 66.5 | 63.8 |
| `subset=[s0,s1]` | 49.9 | 49.8 | 48.4 |
| `subset=[c0]` / `[d0]` | 3.9 / 46.0 | 3.7 / 47.3 | 4.2 / 47.5 |
| `subset=[i0,i1]` (cannot hold nulls) | 71.6 | 72.9 | 72.6 |

The null term is exactly **8 B/row per null-containing key column** (6 x 8 = 48), the `maybe_lift` copy
that the 4a formula already charges for *all nullable key columns*; non-key columns cost nothing. So
the 4a term covers every nullable column, key and non-key. The formula evaluated at the **true**
statistics: 84.9 vs 92.4 measured (0.5M), 169.8 vs 192.1 (1M), 372.2 vs 368.6 (2M): the known 4a
residual (the model is 8-13% low at 0.5-1M for 9-column frames, "cause not identified"); that
residual is within the 4a band and, still unexplained, is carried by the range policy rather than
patched.

**The 10M point.** The harness kills a child whose *total* RSS passes the cap (2.5 GiB; killed at
2.74 GB). My previous evaluator scored such a point as an actual **equal to the cap**, i.e. 2.68 GB of
*incremental* peak, which is wrong by the resident inputs (~1 GB at 10M rows: baseline 155 MB at 1M and
307 MB at 3M for this case, line-extrapolated). The correct bound is
`rss_at_kill - baseline` = **1.90 GB**; against Tier 1's range for that point (1.12 / 1.77 / 2.22 GB)
it is *inside* the range, not above `high`. The "above-high, dangerous" reading of this point in the
val-v3 report came from my scoring rule and is retracted (corrected in `evaluate.py`, with a test).
Per-row, measured 202.6 (1M) and 196 B/row (3M) imply ~1.96 GB at 10M, consistent with the bound.

The real defect is the **planner**: it admitted the point because `input bytes x 3` (2.28 GB) was under the
cap, while baseline (~0.85 GB) + Tier 1 `high` (2.22 GB) = 3.1 GB was not. Fixed in Step 4.

## (e) Estimator variance vs systematic error

*Probe `pe1_seed_variance.py`: 10 sampling seeds on the failing configurations (n = 1M).*

| statistic | true | mean / true | sd / true | min..max / true | interval contains truth |
|---|---|---|---|---|---|
| distinct, astype card12000 | 12,000 | 1.000 | 0.000 | 1.000..1.000 | 10/10 |
| distinct, groupby str_card0p04 | 40,000 | 1.000 | 0.001 | 0.999..1.001 | 10/10 |
| distinct, groupby int_card20000 | 20,000 | 1.000 | 0.000 | 1.000..1.000 | 10/10 |
| distinct rows, groupby two_keys_card800 | 505,945 | 1.263 | 0.007 | 1.245..1.277 | 10/10 |
| distinct rows, drop_duplicates null_heavy | 850,000 | 1.169 | 0.000 | 1.169..1.169 | 10/10 |

Estimator variance is negligible (sd <= 0.7%). The only statistical error is a *systematic* Chao1
over-estimate of distinct rows (x1.26, x1.17 for multi-key and whole-row hashes: the over-estimate is
the safe direction and its interval still contains the truth). None of the failures comes from sampling noise.

## What was fitted, and what was not

Derived from the pandas mechanism and validated on probes that were not used to derive them:
the table geometry (presize cap, 77% load, bytes per bucket), the page-residency law, the two hash
replicas. Constants taken from probes: `FACTORIZE_BASE` text 24.1 / numeric 8.65 B/row,
`FACTORIZE_FLOOR` numeric 16.3 B/row, `UNIQUE_BYTES` 8 / 16, text table strides 16 + 8 (all read off the
sweep probes at few and at all-distinct values). Fitted to probe grids (not to benchmark points):
`CLUSTER_FILL` = 0.1 (three dense-int probes), `COMBO_COEXIST` = 0.5 (four two-key probes), the merge
sort-path coefficients (27-probe grid, structural, checked with fixed integer coefficients).
Known residuals: dense/sequential keys are over-predicted by up to 20%; two-key groupby at low group
counts by ~20%; merge sort path +-17%; drop_duplicates 8-13% low on wide frames (4a, unexplained).

## After the fixes (development data; the same measured actuals, predictions re-run)

Points that failed on val-v3, plus the two dev points 4b could not explain, Tier 1 RAM before and after
(MiB; `docs/benchmarks/tier1-v2/before_after.md` has the full per-operation tables):

| point | actual | before: low / expected / high | after: low / expected / high | in range |
|---|---|---|---|---|
| astype `str_to_category_card12000` 1M | 62.9 | 20 / 25 / 36 | 53 / 63 / 80 | no -> yes |
| astype `str_to_category_card12000` 3M | 108.7 | 57 / 71 / 102 | 95 / 109 / 132 | no -> yes |
| groupby `str_card0p04_two_values` 1M | 71.4 | 24 / 30 / 42 | 60 / 72 / 81 | no -> yes |
| groupby `str_card0p04_two_values` 3M | 118.0 | 69 / 90 / 182 | 104 / 118 / 138 | yes -> yes |
| groupby `two_keys_card800` 1M | 81.1 | 31 / 46 / 73 | 47 / 89 / 157 | no -> yes |
| groupby `two_keys_card800` 3M | 163.0 | 93 / 139 / 219 | 132 / 184 / 325 | yes -> yes |
| merge `inner_overlap25_fanout6` 1M | 71.8 | 41 / 52 / 59 | 50 / 62 / 72 | no -> yes |
| merge `inner_overlap25_fanout6` 3M | 180.6 | 72 / 90 / 103 | 123 / 155 / 178 | no -> **no** (1.2% above high) |
| astype `str_to_category_zipf` 1M (dev, 4b) | 60.2 | 19 / 25 / 38 | 48 / 60 / 80 | no -> yes |
| groupby `two_keys_mean_realistic` 1M (dev, 4b) | 78.7 | 32 / 48 / 78 | 69 / 105 / 149 | no -> yes |
| drop_duplicates `null_heavy_full` 10M | >= 1,811 (lower bound, not "2,560") | 1064 / 1687 / 2116 | unchanged (no drop_duplicates change) | yes -> yes |
| drop_duplicates `null_subset_f0_s0` 1M | 50.5 | 51 / 63 / 76 | unchanged | no (1% below low) |

Still wrong after the fixes: merge `inner_overlap25_fanout6` at 3M (expected 0.86x, 1.2% above `high`),
and the 8-13% under-prediction of wide-frame drop_duplicates (4a residual, unexplained). The two-key
groupby range is wide (47 .. 157 MiB around a 81 MiB actual) because the combined-id table's scatter is
unknown. These points informed the fixes: they show that the failures are *gone on the points that
exposed them*, which is not evidence that no other failure exists.
