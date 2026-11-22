# Phase 7a: diagnosis and pre-registration for freeze v3 (information only)

No file in the `models-frozen-v2` manifest changed (guard: 0 problems; `git diff models-frozen-v2` on the manifest files is
empty). Mode B: val-v5 is sealed and unread; test-v2 is sealed. Every probe ran on mains power (recorded per row; a run that
found the laptop on battery refused to start and was re-run once it was plugged in). All inputs are synthetic or dev.
pandas 3.1.1, numpy 2.5.5, Windows 11, 16 logical CPUs. Probes and raw outputs: `probes/` (run from the repository root with
`PYTHONPATH=.`). Pre-registration: `../phase7-preregistration.md`. Held-out designs: `heldout_design.md`.

## Pre-flight

| item | state |
|---|---|
| CI | **not run**: no git remote is configured, so there is no Actions run. Open; needs a push. |
| freeze guard | 0 problems against `models-frozen-v2` (43 files) |
| tags | `models-frozen-v1`, `models-frozen-v2` |
| your files in the repository | no notebook, dataset or output tracked. Derived metadata of the Phase 8a notebooks (file names, cell indexes, operation lists, line counts, result tables) is tracked. Kept by your decision. |

## (1a) read_csv: what the peak scales with (`p1a_read_csv.py`, `p1a_analysis.py`)

The first hypothesis was that the low_memory reader concatenates chunks and then consolidates (`peak = R + V2 + T`). The
first run **contradicted** it (numeric peaks ~4.4x the frame). The source then explained it: pandas 3.1.1 reads a local,
uncompressed file >= 5 MiB through a **threaded parallel reader** (`io/parsers/readers._read_csv_parallel`).
`_can_parallelize_csv` decides which reader runs, and the worker count is `min(cpu_count, 6, CPUs available to the process)`:

| path (when) | derived peak | probe ratio measured / derived |
|---|---|---|
| parallel, direct block assembly (no `usecols` / `nrows` / `parse_dates` / dict or text `dtype`; >= 5 MiB; > 1 worker) | **F + 2V**: the mmapped file's pages + per-chunk column arrays + the final blocks they are copied into | **1.003-1.018 on 13 numeric variants** (rows 1M-4M, 4-16 columns, int / float, float32, `sep='\t'`, `header=None`, 10% NA, `na_values`, a 4F+2I+2text mix) |
| parallel, "series wrap" (`dtype` dict) | F + V + W (the mmap is closed before the per-column concatenation; W = 6 workers x one chunk's parser buffers) | 1.008 (1 variant) |
| serial (`usecols`, `nrows`, `parse_dates`, small files, 1 CPU) | V + S + T (T = one low_memory tokenizer chunk of all file columns) | **0.71-0.92** (T over-estimated; the measured excess over V is 15-22 MiB) and **1.36** for `parse_dates` (the conversion is not modelled) |
| text columns on the parallel path | 8 B pointer + new `str` objects (frozen per-chunk uniqueness) | **1.05-1.26: not derived** |

F = file bytes, V = rows x the kept columns' itemsizes, S = text term. **The frozen Tier 1 formula with the true shape measures
0.78-0.80 on numeric files**, which is the 1.22-1.25x over-prediction found in the Phase 6c held-out cells. On the serial path it
measures 0.05-0.12, because it ignores `usecols` / `nrows`.
*Derivable:* parallel numeric (both branches), with path selection from the call's arguments, the file size and the available
CPUs. *Not derivable yet:* the serial-path chunk term (a range [V + S, V + S + T] covers every variant), text columns on the
parallel path, `parse_dates`.
*Consequence beyond RAM:* the read_csv cost depends on the CPUs available to the process (1 CPU means the serial path). Time
models and the Linux VM must record it.

## (1b) The 10-17% over-prediction without loads (`p1b_nonload_bias.py`; 4M / 10M rows)

Per statement, tracemalloc and the OS peak of the cell's prefixes agree within 1%:

| template | measured vs predicted | cause |
|---|---|---|
| chain | merge peak 128.4 vs 128.4; merge **result left behind 30.5 vs 91.8 predicted** (`_output` merge term) | pandas 3 does not copy the left columns when every left row matches once in left order: only the right columns are new. The cell model keeps 61 MiB too much alive during the sort. |
| rebinding | sort 274.7 vs 274.7, concat 518.8 vs 518.8; cell 764 vs 855 | the same merge output term, plus `m = df.sort_values(...)` **releases** the old `m`, which the cell model keeps (by design, conservatively) |
| copy_fillna | `copy` 213.6 vs Tier 0 expected 366.2 (= its own `low`) | copying `str` columns copies their pointer arrays, not the string objects. Partly hidden by the uncovered `fillna(0)` (137 MiB). |
| astype_groupby | 193.6 vs 194 at 10M rows (**1.00**) | none at >= 200 MiB. The 1.11 at 1-2M rows is a small-size effect near the 32 MiB floor. |

*Derivable* (all three are source questions with a probe already pointing at the answer): the merge left-elision condition
for the output term, release on rebinding of a name bound in this cell to a result made in this cell without an alias, and
the copy term for text columns.

## (1c) Operations on a frame created earlier in the cell (`p1c_cell_frames.py`; 2M-row `wide`)

| operation on `a = read_csv(...)` | measured MiB | shapes / dtypes propagated (Tier 0 on the true frame) | column statistics carried (Tier 1 on the true frame) |
|---|---|---|---|
| `concat([a, a2])` | 412 | **1.00** (shapes are enough) | 1.00 |
| `a.fillna(0)` | 252 | expected 1.00, range 0..252 (which blocks hold NaN is unknown) | 1.00 (zero width; the measured peak is 0.07% ABOVE that zero-width high) |
| `a.merge(right)`, unique right keys | 66 | expected 3.68x | 1.22x |
| `a.merge(right)`, every right key twice | 459 | expected 0.53x | 1.06x |
| `a.groupby('k')['v'].sum()` | 34 | expected 2.65x | 1.15x |

The read_csv Tier 1 sample (8.4k rows) finds the NaN column correctly, and estimates the key's distinct count at 53k
(truth 50k), with a 95% range of 7.7k-1.9M.
**Answer:** propagating shapes / dtypes is enough for concat, copy and sort (value-preserving or size-only operations)
and bounds fillna. Merge, groupby, drop_duplicates and astype(category) need COLUMN statistics. For a frame made by a
value-preserving operation (copy, sort, fillna on other columns), the input's statistics carry over exactly. For a frame
made by read_csv, only the sample's statistics exist, and their ranges are wide.

## (1d) Coverage candidates (`p1d_coverage.py`; adoption bar fixed in the script: every variant within +-15%)

| operation | measured MiB | derived MiB | ratio | verdict |
|---|---|---|---|---|
| `s.apply(np.sqrt)` (ufunc), 25M | 190.8 | 190.7 | **1.000** | **derivable: in scope** |
| `Series.explode`, 3M lists, mean 6 | 338.0 | 297.6 | **1.136** | **derivable: in scope** (needs a list-length sample: Tier 1) |
| `DataFrame.explode` (+1 column) | 1123 | 847 | 1.326 | contradicted: uncovered |
| `df.set_index('k' / 'f0')`, 16M | 0.4 | 122 | 0.003 | **contradicted**: pandas 3 does not copy the key into the index. A zero-copy second derivation may be tried in 7b (reported as a second attempt). |
| `df.set_index(str key)` | censored (below the setup peak) | 61 | - | no evidence |
| `value_counts`, u = 8M of 20M | 636 | 455 | 1.398 | contradicted: uncovered |
| `value_counts`, u = 1000 of 40M | 15.9 | 7.4 | 2.14 | contradicted: uncovered |
| `s.apply(lambda v: v * 2)`, 6M | 602 | 275 | 2.19 | contradicted: uncovered |
| `df.apply(f, axis=1)`, 1.5M | 243 | 195 | 1.25 | contradicted: uncovered |
| `str` `fillna('z')`, 25M | 286 | 215 | 1.33 | contradicted: uncovered |
| `str` `fillna(0)` (coerces to object) | 525 | 405 | 1.30 | contradicted: uncovered |

## (1e) Determinism and the statistics budget (`p1e_determinism.py`; 3M and 10M rows; 5 fresh-process repeats per cell)

* **Wherever statistics ran, the estimate was identical across repeats** (spread 0), frozen and prototype alike. The sampler's
  seeds are constants, and at these sizes the sample hits its 200k cap.
* **The non-determinism is the budget gate:**
  * merge at 10M rows takes 0.32-0.51 s of analysis and falls back to Tier 0 in EVERY condition, 16 cores included
    (deterministic, but a coverage loss);
  * on 2 contended cores, merge at 3M flips between Tier 1 and Tier 0 across repeats (frozen 2 / 5 Tier 1; prototype 4 / 5);
  * the fixed-sample prototype flipped once for drop_duplicates on 2 uncontended cores, because its gate is stricter than
    the frozen adaptive sample size.
* Analysis time on 2 contended cores roughly doubles (0.13 -> 0.30 s). No other operation fell back.
* One child crashed natively (0xC0000005) in the last group (2 contended cores, 10M, astype). The group was re-run alone and
  gave 5 / 5 identical estimates (`p1e_determinism_rerun.out`). The crash is not explained.

*Derivable proposal:* a fixed sample size and a seed from the cell hash (cheap, already deterministic in practice). The gate
is decided by a DETERMINISTIC cost prediction (the per-row statistics cost from the machine profile, not live timing), with
the hard deadline kept as the safety net and every fallback shown ("statistics skipped: ..."). The 250 ms ceiling is not
raised.

## (1f) Risk v2 candidates (stored dev data; rule committed first in `f8e4eba`; `p1f_risk_v2.py`)

| candidate | R1 recall | misses added vs C0 | R2 pooled | merge | read_csv | R3 |
|---|---|---|---|---|---|---|
| C0 as is | 100% (1119 / 1119) | - | 25.0% | **58.8%** | **78.0%** | 98.6% |
| C1 read_csv Tier 1 high | 100% | 0 | 22.6% | **58.8%** | 44.1% | 98.6% |
| C2 merge Tier 1 high | 100% | 0 | 20.1% | 11.8% | **78.0%** | 98.6% |
| **C3 both (selected, rule step 2)** | 100% | 0 | **17.7%** | **11.8%** | **44.1%** | 98.6% |

One merge point was excluded from the own-high swap, because its Tier 1 expected differs between the stored states. This is a
dev selection. It becomes a claim only through val-v5.

## Proposed v3 change list (to be done in Phase 7b; each one derived, probed, regression-checked)

| # | change | expected effect | risk |
|---|---|---|---|
| 1 | read_csv: path selection; parallel numeric `F + 2V` / series-wrap `F + V + W`; serial as a range; Tier 1 for usecols / dtype / nrows / na_values | load bias 1.22-1.25x -> ~1.0; Tier 1 for the argument cells (Phase 6c `load_dtype_nrows` 3.6x, `loads3_tsv` 2.0x) | depends on the CPUs available (a different machine = a different path); text columns unchanged; a new pandas version can change the reader |
| 2 | `_output` merge term with left elision | chain / rebinding bias -> ~1.0 | wrong elision condition leads to under-prediction of retained memory: needs probes with unmatched keys / sort=True / how='left' |
| 3 | cell model: release on rebinding (no alias, result made in this cell) | rebinding bias -> ~1.0 | aliases the AST cannot see (`l.append(m)`, closures): conservative fallback needed |
| 4 | copy of `str` columns: pointer arrays only | copy Tier 0 expected 1.7x -> 1.0 | none known |
| 5 | deterministic Tier 1 (fixed sample, hashed seed, deterministic gate, visible fallback) | same cell -> same estimate on a machine | the gate's cost model can be wrong on a slow machine; the deadline stays |
| 6 | risk C3 + named-operation UNKNOWN | R2 dev 25% -> 18%, merge / read_csv under 50% | read_csv own high changes with change 1: re-checked before the freeze |
| 7 | coverage: `Series.explode`, ufunc `apply`; shapes / dtypes carried between statements; column statistics carried through value-preserving operations and from the read_csv sample | more cells fully estimated; load-then-merge / concat-of-reads / copy-then-astype get estimates | statistics from an 8k-row read sample are wide (merge / groupby ranges widen) |

Out of v3, documented as uncovered: set_index (unless the second derivation passes), value_counts, DataFrame.explode, apply
with Python functions (element-wise and row-wise), fillna on pandas-3 text columns, parse_dates, and text columns on the
parallel reader path (frozen term kept).

## Needs a decision (owner)

1. **CI**: push to a remote (both tags) so that one Actions run exists before v3.
2. **Machine dependence of read_csv**: v3 makes the read_csv estimate depend on the CPUs available. Accept this, or model
   only the single-CPU serial path conservatively?
3. **set_index second derivation in 7b**: allow it (reported as a second attempt), or leave set_index uncovered.
4. The **Phase 8b notebook collection** (`heldout_design.md` (d)): you collect, I download nothing.
