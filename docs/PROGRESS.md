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

> **Superseded/provisional:** every number in this section was measured with the flawed v1 instrument. See "Phase 3b" below.

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


## Phase 3b: measurement instrument fix and re-baseline (v2)

### Measurement flaw (finding)
The Phase 3 instrument polled the child's RSS every ~2 ms and took the maximum. That **under-measures
whenever the allocator reuses memory freed during setup** and misses short spikes. Evidence from v1:
a 100k `np.sort` (800 KB array) peaked at 0 B; a *sorted* 500k array at 0.1 MB versus 3.9 MB for the
*random* array doing the identical copy; `drop_duplicates(subset=["s0"])` peaks implausibly small.
Every v1 accuracy number was therefore measured against a faulty ground truth and is **provisional /
superseded** (the v1 report is kept as `docs/benchmarks/small-baseline-v1/`). The v1 verdicts quoted in
the Phase 3 section above should be read through the v1-to-v2 table below.

### New instrument (`nexus.measure`, `benchmarks/store.py`)
- RAM = OS-tracked peak counter read *inside the measured process* (Windows `peak_wset`, Linux `VmHWM`,
  macOS `ru_maxrss`) behind one function, `read_memory`. Polling is kept only as a cross-check.
- Inputs are generated once, cached to disk as `.npy` (one per column) and **loaded** in the child
  (`DataFrame(dict, copy=False)` leaves no transient), then `gc`, then baseline = RSS and setup peak =
  OS peak. Operation peak = OS peak after minus baseline.
- The Windows/macOS peak counter cannot be reset (verified: a 100 MB allocation after a freed 200 MB
  is invisible). If the operation never exceeds the setup peak the run is **censored** (upper bound
  recorded, delta `None`), never 0. Linux resets the counter after setup via `/proc/self/clear_refs`
  (**untested here; only Windows was available**).
- Floors (configurable): RAM 32 MiB above baseline, time 100 ms; spread = (max-min)/median over 3
  repeats, excluded above 30%. Every report shows valid / censored (below setup peak, below floor) /
  excluded counts separately. Every result row records python, pandas, numpy, pyarrow ("none" here),
  pandas default string dtype (`str`; generated text columns are `object`), OS, CPU, RAM, git commit.
- Suite sizes raised to 300k / 1M / 3M rows (matmul 1000-3000); `full` is 100k-10M but was **not run**.

### Instrument validation (`tests/test_measure_validation.py`, 13 tests, passing on Windows)
Known allocations measure within +/-10%: `np.ones` 100 MiB, `bytes` 100 MiB, repeated allocate/free
(peak not sum), `np.sort` of random and sorted 100 MiB arrays (the v1 regression: now both within 10%
of 100 MiB and of each other), DataFrame copy. A `df.copy()` of a frame stored as 4 float blocks
measured 2x the data (200 MiB) against my first expectation of 1x; `tracemalloc` (independent oracle)
confirms pandas consolidates blocks on copy, so the instrument was right and the expectation wrong. The
test now uses `tracemalloc` as the oracle for both single-block (1x) and multi-block (2x) frames. Frame
block layout therefore changes copy-like peaks by 2x, which Tier 1 may need to model. Setup garbage:
measured on Linux, censored with an upper bound on Windows (tested, never 0). Cross-check on the v2 run:
polled RSS never exceeded the OS peak (0 of 246 runs), median poll/OS ratio 0.98.

### v2 run
Windows 11, pandas 3.1.1, numpy 2.5.5, no pyarrow, 16 logical CPUs, 3 repeats, 1.5 GB memory cap;
7.7 minutes. 82 points measured, 5 skipped (merge at 3M rows, estimated above the cap). Spread
exclusions: 0 (repeats were highly consistent). Setup-peak censoring: 0 (disk loading works). Machine
profile calibrated with `nexus-calibrate-machine` (e.g. CSV parse 483 MB/s vs the old guess of 80 MB/s).

| | | valid | censored | excluded | median err | p90 err | bias | coverage | width |
|---|---|---|---|---|---|---|---|---|
| RAM | v1 | 53 | n/a | 34 (below old floor) | 92% | 558% | 1.92 | 70% | 243% |
| RAM | v2 | 46 | 36 | 0 | 64% | 268% | 1.35 | 78% | 197% |
| Time | v1 | 35 | n/a | 52 (below old floor) | 69% | 472% | 1.65 | 80% | 378% |
| Time | v2 | 37 | 45 | 0 | 64% | 85% | 0.38 | 81% | 378% |

v1 and v2 differ in sizes (v2 is 3-6x larger) as well as instrument, so per-point comparison is not
possible; pooled and per-operation comparisons are in `docs/benchmarks/small-baseline-v2/comparison.md`.
RAM models and priors were **not changed**, so RAM movement is instrument plus sizes. Time models read the
calibrated profile, so time movement mixes instrument and calibration. Re-scoring the *same v2
measurements* with the old default constants separates them:

| time model (same v2 actuals) | valid | median err | p90 err | bias | coverage |
|---|---|---|---|---|---|
| default (guessed) constants | 37 | 66% | 335% | 1.25 | 81% |
| calibrated constants | 37 | 64% | 85% | 0.38 | 81% |

Calibration cut the worst-case time error (p90 335% to 85%) but introduced a systematic 2.6x
**under**-prediction: microbenchmark throughputs measure warm, in-cache, small workloads, and the time
models omit page-fault, allocation and per-column overheads. Not tuned; logged as a finding.

### Which earlier verdicts changed
Unchanged by the better instrument (so not artifacts): `merge` over-predicted ~5x (bias 5.2), `groupby`
over-predicted ~2x (2.1, down from 4.1), `sort_values` over-predicted ~2.3x with **0% RAM coverage**
(the "peak ~ input bytes" hypothesis stays falsified), text-heavy `drop_duplicates` over-predicted 2.7x,
`concat` of mixed frames 2x. `drop_duplicates` peak RAM is independent of duplicate fraction: at 3M rows
`mixed_dup0` and `mixed_dup50` both peaked at 335 MB (identical to within 0.1%), while output size halves;
this cost-driver claim is now solidly supported on this dataset family.
Changed: `matmul` RAM bias 3.6 to 0.96 (the v1 figure came from tiny 200-1000 matrices where the assumed
BLAS buffer dominated); `read_csv` RAM went from 0.63 to **0.37** (under-prediction, up to 2.8x on string
files: 1327 MB actual vs 466 MB predicted at 3M rows, though inside the wide [low, high]); `astype` to
category on high-cardinality strings is under-predicted 2.3-4x. Under-predicting verdicts matter more than
over-predicting ones for OOM warning. `np.sort` is now measured correctly (1M sorted: 7.7 MB vs 8 MB
expected; 3M: 23.0 MB vs predicted 22.9 MB) but every point is below the 32 MiB floor, so it is censored
and reported as such: it needs >= 5M rows. Time: `matmul` bias 6.0 to 0.81 and `read_csv` 2.4 to 0.37
(calibration effect, see above); other operations moved from over- to under-prediction for the same reason.

### OOM warnings with v2 (pooled across ops/sizes, tier 0)
Positives exist for 64-1024 MB limits (66, 49, 34, 19, 3). Rule `expected`: precision/recall 96/98% (64 MB),
89/96% (128), 86/91% (256), 95/95% (512), 17/33% (1024, 3 positives). Rule `high`: recall 97-100% but
precision 68-75% at 128-512 MB and 16% at 1024 MB. Caveats: pooled over operations and sizes (large
inputs dominate, so this is easier than per-operation use), uses *deep* input bytes on both sides, and has
very few positives above 512 MB. Treat as indicative only.

### Remaining caveats
Windows only (Linux reset path and macOS `ru_maxrss` path untested; CI will exercise Linux). Synthetic data.
`full` suite (up to 10M rows) not run. Resident vs deep input bytes: the harness now records
`input_resident_bytes` for this check, not yet analysed. Analysis overhead unchanged (median 4.2 ms,
max 14.9 ms of the 250 ms budget).

### Additional decisions
- Throughput constants moved to `nexus.machine.MachineProfile` (cached JSON, `nexus-calibrate-machine`;
  uncalibrated defaults equal the old guesses and are used when no profile exists). Other priors (expansion
  factors, group-count prior, bands) are unchanged. Calibration runs only on its own microbenchmarks.
- Runner now also generates missing predictions when an actual already exists (bug found during the
  ablation; regression test added), and has `--no-calibrate` for the default-constants ablation.


## Phase 3c: full baseline preparation, dev/test split, cross-platform check

No estimator model or prior was changed in this phase. Only the calibration *primitives* (item 4) changed.

### Dev/test split (frozen, `benchmarks/split.json`)
- **Unit = case** (operation + source + dataset configuration). All sizes of a case stay together, so the
  split is by configuration, not by row or size. 47 cases: **29 dev**, **18 test**.
- **Rule:** dev = every case already present in a committed report under `docs/benchmarks` (all of these
  were examined in Phases 3 and 3b); test = every other case, never measured or evaluated before the freeze.
- The test cases are *new configurations* the dev cases never use: null rates, zipfian ("real_like") value
  distributions, datetime keys, longer strings, `outer`/`right` joins, two-key groupby, three-frame concat,
  rectangular matmul, reverse-sorted and float32 arrays, int32 casts, datetime-to-str. Each of the 9
  operations has at least one dev and one test configuration. Expect test results to be worse than dev:
  that is the point (the models were designed while looking at the dev cases).
- `split.json` stores SHA-256 digests of both lists; `load_split` refuses a modified file. Tests assert the
  test cases appear in no committed report, every suite case is classified exactly once, and a case is never
  split across dev and test.
- **Guard.** Dev tooling (`load_joined`, reports, `compare`, calibration, anything built on them) reads only
  `actuals.csv`/`predictions.csv`. The runner writes test-split results to `<results>/sealed/` and
  `load_joined` refuses dev files containing a test case. The normal report shows only the *count* of test
  points measured. The test split is read only by
  `python -m benchmarks evaluate <dir> --final --reason "..."`, which requires a reason, logs every use in
  the **Test-split access log** at the end of this file, and writes `final_report.md` with dev and test
  results in separate sections. A test scans the source tree and fails if other modules reference the sealed
  area, and checks `nexus.calibrate` never imports benchmark code. Limitation: this is procedural; the sealed
  CSVs are plain files and anyone can open them.

### Suite extension and the full run
- `full` suite: rows 1M / 3M / 10M / 30M (matmul dims 2000-8000; `np.sort` arrays 5M-100M elements; `read_csv`
  capped at 3M rows). At the default floors most points now exceed 32 MiB. Points above the memory cap are
  recorded as `skipped_cap`, never dropped. 180 points in total (111 dev, 69 test); `--max-size 10000000`
  leaves 136.
- Runner: dev split first, resumable (re-run the same command; finished actuals are kept, missing predictions
  are filled), Ctrl+C safe, `run.log` plus an atomically written `progress.json`; `python -m benchmarks status
  <dir>` (second terminal) prints state, ETA, counts by outcome and the last log lines; `python -m benchmarks plan`
  is a dry run showing how many points fit under a cap.
- **Not run by me.** On this machine 4.0 GiB of 15.6 GiB RAM was free, so a 4 GiB cap would be unsafe. Exact
  commands are in the final answer of this phase and in CLAUDE.md.

### Memory blocks feature
`FrameDescriptor.n_blocks` and `.consolidated` (`nexus.state.frame_block_info`): reads `df._mgr.blocks`
defensively, never mutates the frame (it does not call `_consolidate`), and returns `(None, None)` if pandas
internals change or the object is unusual. `consolidated` means "no two blocks share a dtype". Shown in
verbose output; recorded as `input_blocks` in benchmark rows; **no model uses it**. Motivation: Phase 3b showed
a 4-block frame's `copy()` peaks at 2x its size.

### Calibration primitives v2 (information only)
Changes: working sets 64-256 MB (far beyond cache), outputs allocated fresh in every repetition (cold
first touch included), CSV file ~100 MB, plus separately measured `warm_copy_bps`, `first_touch_bps` and
`page_fault_s_per_byte` (~0.2 ns/byte here; informational, unused by models). Cached profiles from the
older version are re-measured automatically (`calibration_version`). Calibration took 29 s. It was run
**once**; nothing was fitted to benchmark points, and no iteration followed.
Effect on the *existing* v2 dev measurements (same actuals; predictions only re-run):

| time model | valid | median err | p90 err | bias | coverage |
|---|---|---|---|---|---|
| default guesses | 37 | 66% | 335% | 1.25 | 81% |
| calibration v1 (small, warm primitives) | 37 | 64% | 85% | 0.38 | 81% |
| calibration v2 (large, cold primitives) | 37 | 47% | 116% | 0.93 | 97% |

Per-operation time bias (default / v1 / v2): drop_duplicates 0.64 / 0.35 / 1.00, sort_values 1.66 / 0.45 /
1.41, merge 1.41 / 0.41 / 1.48, astype 1.09 / 0.60 / 0.90, matmul 5.99 / 0.81 / 0.93, concat 0.76 / 0.16 /
0.70, groupby 0.42 / 0.32 / 0.71, read_csv 2.23 / 0.37 / 0.37. RAM numbers are unchanged (RAM models do not use
the profile). Caveats: these are the same dev points used to understand the problem in Phase 3b, so the
improvement is not an independent test (the test split exists for that); coverage rose partly because wider
time bands (x0.25..x4 around a better-centred value) cover more; `read_csv` remains 2.7x under-predicted
(a ~100 MB mixed CSV parse microbenchmark does not capture string/category construction); the p90 got
slightly worse (85% to 116%).

### CI
`.github/workflows/ci.yml`: lint on ubuntu; tests on ubuntu, windows and macOS, each on Python 3.10 and 3.12
(`fail-fast: false`), with the instrument validation suite as its own step on every platform. The old
workflow only triggered on `main`/`develop` while this repo's branch is `master`; it now triggers on every
push and pull request. **CI has not run:** the repo has no remote. Local Windows is the only platform
verified; Linux and macOS behaviour (the `/proc/self/clear_refs` reset path, macOS `ru_maxrss`, macOS memory
compression affecting RSS) is untested.

### What remains unvalidated
- Linux and macOS (instrument validation, reset path, calibration), and Python 3.10 (only 3.12 run here).
- The full suite, including every >3M-row point and the 1-4 GB points; the 5M+ element `np.sort` cases.
- The test split has not been measured or evaluated at all; all accuracy figures so far are dev-split.
- Real (non-synthetic) data; string-sharing vs resident bytes (`input_resident_bytes` is recorded, not analysed).
- The OOM precision/recall figures (pooled, deep input bytes, few positives above 512 MB).

## Test-split access log

Every use of the sealed test split is recorded here by `evaluate --final` (timestamp, git commit, results
directory, number of test points, reason, command). Entries are appended below; none so far.
