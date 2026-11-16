# NEXUS Project Phases

## Phase Checklist

- [x] **Phase 1: Foundation** — Repo setup, CI/CD, dummy test
- [ ] **Phase 2: Tier 0 estimators** — AST analyzer, operation registry, closed-form models
- [x] **Phase 3: Benchmark** ✓ **checkpoint** — Evaluation harness, ground-truth measurement
- [ ] **Phase 4: Tier 1 and 2** — Statistics collection, dry-run sampler, extrapolation
- [ ] **Phase 5: Risk and suggestions** — Risk classification, rule-based suggestion engine
- [ ] **Phase 6: Calibration** — Systematic error analysis, uncertainty bounds
- [ ] **Phase 7: UX and robustness** — IPython extension, error handling, edge cases
- [ ] **Phase 8: Real-world evaluation** ✓ **checkpoint** — Test on real notebooks, refine models
- [ ] **Phase 9: Docs and release** — API docs, examples, PyPI release
- [ ] **Phase 10: JupyterLab UI** *(optional)* — Interactive preview panel
- [ ] **Phase 11: Extensions** *(optional)* — GPU, LLM suggestions, other languages

## Decisions and findings

### Phase 1 decisions
- **Platform abstraction**: Using `multiprocessing.spawn` and `psutil` for cross-platform memory measurement
- **Build system**: `pyproject.toml` with setuptools; `src/nexus` layout for clean packaging
- **Linting**: ruff for speed and ease; targets Python 3.10+
- **CI/CD**: GitHub Actions workflows for Windows, Ubuntu; macOS added when needed
- **Minimal dependencies**: Core depends only on psutil, pandas, numpy, ipython

### Phase 1 implementation decisions and findings
- **Hook safety**: analysis runs in a daemon thread with a hard join timeout (budget 250 ms + 50 ms grace) and also polls a cooperative `Deadline`. A timed-out analysis is abandoned and NEXUS stays silent. Known cost: an abandoned thread can briefly keep running (it stops at the next deadline check).
- **Re-entrancy**: `_in_hook` blocks anything fired while analysing; `_active` counts cells between pre/post so a cell run from inside a cell (`get_ipython().run_cell`) is ignored. `post_run_cell` after `%load_ext nexus` arrives with no matching pre and is ignored.
- **Detection is syntactic**: `x.copy()` is reported even if `x` is a list; models must confirm types from the inspected state. Method ops are named by bare method (`drop_duplicates`), module functions canonically (`pandas.read_csv`). Ops come back in execution order.
- **Magics**: `%time`/`%timeit`/`%%time`/`%%capture` keep their body for analysis; other magics, `!` and `?` lines become `pass`; unknown cell magics (`%%bash`) drop the cell.
- **No dataflow yet**: only `df2 = df` aliasing. A variable created earlier in the same cell (`a = np.zeros(..); a @ a`) has no descriptor because it is not in the namespace yet; Tier 0 models must treat such inputs as unknown, not guess.
- **State cost**: pandas/numpy are found via `sys.modules` (never imported by NEXUS). Text-column deep memory uses a deterministic strided sample (default 10k rows) scaled to full length; `sampled=True` marks it. Strided sampling can be biased on periodic data. Variables not described within budget are listed in `Inspection.skipped`, never partially described.
- **Cgroups**: v1 and v2 limits are read only on Linux; usage is the working set (usage minus inactive file cache). Tested with fake cgroup trees only, **not yet verified in a real container or Colab**.
- **Test caveat**: `pre_run_cell` does not fire for `silent=True` runs, so `ipython script.ipy` does not trigger NEXUS; the process-level test pipes cells through stdin instead.
- Dev environment has pandas 3 (default `str` dtype); the text-column path handles it. Not yet run against pandas 1.5/2.x.
- Fixed Phase 0 slips: empty `benchmarks/` and `examples/` were untracked (added `.gitkeep`); `.gitignore` wrongly excluded `*.json/*.csv/*.ipynb`; package discovery now includes subpackages.

### Open questions for Phase 2
- Which pandas/numpy operations to prioritize for Tier 0 models?
- Sampling strategy for `memory_usage(deep=True)` on large objects?
- How to safely sandbox dry-runs in Tier 2 without breaking user kernels?


## Phase 3: benchmark harness and baseline results (small suite)

Phase 2 is **not** ticked: Phase 3 needed something to measure, so a first-draft Tier 0 model set
(`drop_duplicates, merge, groupby, sort_values, read_csv, astype, concat, matmul, np_sort`) was
written from first principles *before any benchmark data existed* and frozen. Their constants are
guesses (`models/_util.py`); nothing was tuned after seeing results.

### What was built
- `nexus.measure.measure_call`: spawned process per repeat; parent polls child RSS every ~2 ms;
  RAM = incremental peak (max RSS minus RSS after setup); time measured inside the child.
- `benchmarks/`: `datasets.py` (seeded generators), `suite.py` (28 cases x sizes), `workers.py`,
  `runner.py` (resumable, sequential, memory-capped, CSV), `evaluate.py` (metrics, report, figures).
- Run: `python -m benchmarks small` (about 3 minutes, 87 points) or `full` (1e4..1e7 rows);
  `make bench-small` / `make bench-full`. Snapshot of this run: `docs/benchmarks/small-baseline/`.

### Run
Windows 11, 16 logical CPUs, pandas 3.1.1, numpy 2.5.5, sizes 1e4 / 1e5 / 5e5 rows (matmul dims
200/500/1000), 3 repeats, 87/87 points completed, memory cap 1.4 GB. Tier 0 only.

### Measured accuracy (Tier 0, all operations pooled)
| | valid points | median rel. error | p90 rel. error | bias (pred/actual) | coverage of [low, high] | mean range width |
|---|---|---|---|---|---|---|
| RAM | 53 | 92% | 558% | 1.9x (over) | 70% | 243% |
| Time | 35 | 69% | 472% | 1.65x (over) | 80% | 378% |

Only 53 of 87 points have a RAM actual >= 1 MiB and only 35 a time >= 10 ms; the rest are below the
validity floor (RSS polling and timer noise) and are excluded. Analysis overhead: median 2.6 ms,
p90 5.0 ms, max 6.3 ms (budget 250 ms), at these sizes. Estimates were produced for every point.

| op | RAM median err | RAM bias | RAM coverage | time median err | time coverage |
|---|---|---|---|---|---|
| astype | 32% | 0.69 | 71% | 87% | 100% |
| drop_duplicates | 59% | 1.59 | 100% | 28% | 100% |
| groupby | 308% | 4.08 | 100% | 57% | 67% |
| merge | 533% | 6.33 | 45% | 59% | 86% |
| numpy.sort | 2% (n=1) | 1.02 | n=1 | n/a | n/a |
| operator.matmul | 261% | 3.61 | 100% | 501% | 0% |
| pandas.concat | 50% | 1.32 | 50% | 35% | 100% |
| pandas.read_csv | 60% | 0.63 | 100% | 140% | 67% |
| sort_values | 140% | 2.40 | **0%** | 95% | 60% |

### Findings
**Predictable at Tier 0 (RAM, within roughly 2x):** `astype` numeric-to-numeric (bias 0.96-0.98),
`drop_duplicates` on numeric data (0.98), `concat` of numeric frames (0.82), `read_csv` on numeric
files (0.98). `drop_duplicates` peak RAM was driven by data size and dtype, not duplicate fraction:
at 500k rows `mixed_dup0` peaked at 61 MB and `mixed_dup50` at 71 MB while output size halved
(90 MB to 49 MB). That supports the stated cost-driver claim for peak RAM; it was seen on one dataset
family and one machine only.

**Not predictable at Tier 0:**
- `merge`: over-predicted 6x (bias 6.3, 55% of actuals below the predicted low). The model assumes
  output rows = max(n_left, n_right); the real output here was at most the right side (n/2), and
  string columns were far cheaper than assumed. Overlap and fan-out variants differ by 2x in
  output but Tier 0 cannot see them.
- `groupby`: over-predicted 4x; the analyzer reports only the `groupby` call, not the aggregation
  after it, so aggregated columns and group count are unknown.
- `sort_values`: consistently over-predicted 2.4x with 0% coverage; the hypothesis "result is a full
  copy, peak ~ input bytes" is **falsified** here: peak was well below the frame's deep size.
- Anything with text columns: `drop_duplicates/strings` 2.65x, `concat/mixed` 1.9x. Likely cause:
  `memory_usage(deep=True)` counts every shared Python string once per reference, but generated and
  `read_csv`-style low-cardinality strings share objects, so deep bytes overstate resident memory.
  This is an input-descriptor problem (state inspector), not only a model problem. Hypothesis, not
  yet isolated.
- Time constants are poor where they depend on the machine or the codec: `read_csv` numeric 12.9x
  over (parse rate guess far too low), `matmul` 6x over, `sort_values` by string 5.7x over.

**Ranges:** RAM ranges are too wide for `merge`, `groupby`, `matmul`, `read_csv` (width 300-620%)
while `sort_values` (68%), `concat` (70%) and `astype` category cases are too narrow and miss
(coverage 0-50%). The 70% pooled RAM coverage is flattered by systematic over-prediction plus wide
ranges; the misses are almost all *below_low* (actual smaller than predicted low). Under-prediction
beyond the range (`above_high`) was only 2% of RAM points. Time bands (fixed 0.25x..4x) are 375%
wide everywhere and cover 80%.

**OOM warnings:** with this suite the largest footprints are under 256 MB, so only the 64 MB (25
positives) and 128 MB (11 positives) limits have positives. At 64 MB the `expected` rule scored 100%
precision/100% recall and the `high` rule 69%/100%; at 128 MB `high` was 50%/91% and `expected`
53%/73%. At 256 MB and above there are no positives, only false alarms from `high` (8 at 256 MB, 5 at
512 MB). **OOM precision/recall at realistic limits is not measurable until the full suite runs.**

### Measurement validity problems (must be resolved before trusting ground truth)
1. **RSS under-measures when the allocator reuses freed memory.** `np.sort` of a random 100k array
   (800 KB) peaked at 0 B, and a *sorted* 500k array (4 MB) at 0.1 MB while the *random* 500k array
   showed 3.9 MB for the identical allocation. `drop_duplicates(subset=["s0"])` peaks (0.26-0.5 MB)
   are implausibly small too. Setup garbage freed before the baseline can be reused by the operation.
2. 34 of 87 points have RAM actuals under 1 MiB and 52 of 87 time actuals under 10 ms, so the small
   suite validates mostly the 5e5-row points. Sizes of 1e6+ are needed for reliable numbers.
3. `input_bytes` is deep memory (see string-sharing issue above); it is not resident bytes.

### Recommendations for Tiers 1 and 2
1. First fix the ground truth: add a cross-check (e.g. build inputs by loading from disk so setup
   leaves no reusable garbage, or `tracemalloc` for numpy allocations) and run the full suite.
2. Tier 1 should compute the quantities that dominated the errors: join key overlap and fan-out,
   distinct-group count, duplicate fraction (from a bounded sample), string cardinality and whether
   strings are shared objects (sample `id()` uniqueness), so descriptors report resident bytes rather
   than deep bytes. Expose the aggregation after `groupby` from the analyzer.
3. Tier 2 (sampled dry run) should target `merge`, `groupby` and `read_csv`, where Tier 0 ranges are
   widest, and all time estimates that depend on throughput (`read_csv`, `matmul`, string sorts).
4. Replace fixed throughput constants with a one-time per-machine micro-benchmark (Phase 6).

### Tuning ideas (logged, NOT applied)
- merge: output rows from a sampled key intersection; lower the string-column row-byte weight.
- sort_values: peak well below input bytes; revisit the "full copy" term once resident bytes are used.
- groupby: model group count from sampled distinct count; stop assuming 30% value copy.
- read_csv: parse rate and expansion factor depend on dtype mix; sniff the header/first rows (Tier 1).
- matmul: BLAS flop rate and buffer constant; measure rate at first use.
- time bands: derive from measured spread instead of a fixed 0.25x..4x.
- model confidence values are unvalidated priors; calibrate against coverage in Phase 6.

### Decisions
- Predicted/actual RAM is *incremental peak* (inputs excluded); chosen because it is what an OOM
  check compares against free RAM.
- Validity floors (1 MiB RAM, 10 ms time) are measurement-reliability filters, reported with counts.
- The harness kills children above a memory cap (default 40% of available RAM, max 8 GiB) and skips
  points whose estimated footprint exceeds it; both outcomes are recorded, never dropped silently.
- Results are CSV (no pyarrow dependency); matplotlib is the `bench` extra.
