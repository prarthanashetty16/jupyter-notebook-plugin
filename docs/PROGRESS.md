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

> **Superseded in part by Phase 3d:** the 18 "test" cases described here are now the *exposed-v1* group (their values were printed to the console and run.log); the sealed split is `test-v2`.

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
  the **Test-split access log** section of this file, and writes `final_report.md` with dev and test
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
directory, number of test points, reason, command). Entries are appended below. The first records an exposure of the version-1 test split (not a final evaluation); there has been no `evaluate --final` access to `test-v2`.
- 2026-11-17 | EXPOSURE (not an `evaluate --final` access) | split version 1, test group (18 cases, 52 points, full suite, `--max-size 10000000`) | what: measured peak RAM and time, censoring/classification detail and Tier 0 predicted RAM and time for those points were printed to the console and written to `benchmarks/results/full/run.log` | how: `run_suite` logged one detailed line per point for every split; only the CSV files had been separated into `sealed/`, the log path was missed | reported by the project owner | consequence: group renamed `exposed-v1` (development and diagnosis only, never final claims), replaced by the new sealed `test-v2` (17 cases); runner now logs id/status/elapsed only for sealed groups | NOT scrubbed yet: the run.log was not present in this workspace; run `python -m benchmarks.maintenance scrub-logs benchmarks/results/full`
- 2026-11-17 20:32:09 | git `99f9f01` | val-v3 | results `benchmarks/results/val-v3` | 105 val-v3 points | reason: 4b held-out check of Tier 1 | `python -m benchmarks evaluate benchmarks/results/val-v3 --val --reason 4b held-out check of Tier 1`  **[aborted, no report produced: `evaluate --val` failed with FileNotFoundError before reading any value; fixed in the following commit]**
- 2026-11-17 21:55:59 | git `297c09f` | val-v3 | results `benchmarks/results/val-v3` | 105 val-v3 points | reason: 4b held-out check of Tier 1 | `python -m benchmarks evaluate benchmarks/results/val-v3 --val --reason 4b held-out check of Tier 1`
- 2026-11-17 | RECLASSIFICATION (not an `evaluate` access) | val-v3 -> dev | the val-v3 report (`benchmarks/results/val-v3/validation_report.md`, one `evaluate --val` access, logged above) was read by the developer and a reviewer, so val-v3 is no longer held out. Split version 4 merges its 36 cases into dev (list kept as `provenance["val-v3"]`) and freezes the new held-out `val-v4` (40 cases, never run). Its results were copied into `benchmarks/results/dev-v4-before/` with `python -m benchmarks.maintenance migrate-val3`. test-v2 stays sealed and unrun.
- 2026-11-17 23:50:48 | git `b5997d1` | val-v4 | results `benchmarks/results/val-v4` | 119 val-v4 points | reason: 4b.2 held-out check of the repaired Tier 1 | `python -m benchmarks evaluate benchmarks/results/val-v4 --val --reason 4b.2 held-out check of the repaired Tier 1`
- 2026-11-18 10:38:26 | git `b5997d1` | val-v4 | results `benchmarks/results/val-v4` | 119 val-v4 points | reason: 4b.2 held-out check of the repaired Tier 1 | `python -m benchmarks evaluate benchmarks/results/val-v4 --val --reason 4b.2 held-out check of the repaired Tier 1`
- 2026-11-18 | RECLASSIFICATION (not an `evaluate` access) | val-v4 -> dev | val-v4 failed its pre-registered criterion (Tier 1 above_high 5.4% per point vs 3%) and its report was read by the developer and a reviewer. Split version 5 merges its 40 cases into dev (list kept as `provenance["val-v4"]`) and has NO held-out validation group. Results copied to `benchmarks/results/dev-v5/` with `maintenance migrate-val4`. test-v2 stays sealed and unrun.
- 2026-11-18 | CREATION (not an access) | val-v5 | split version 6 freezes `val-v5` (47 configurations, seeds >= 501, no generator value shared with dev, the former val-v3 / val-v4 or test-v2; sizes up to 30M rows, np.sort to 400M, matmul to 16000) as the held-out validation group for a Linux machine with >= 32 GB RAM. NOT run and no value read. Created in Phase 4d after the controller rules and success criteria were pre-registered (docs/benchmarks/phase4d-preregistration.md).

## Phase 3d: test-split integrity repair and baseline diagnosis

No estimator model or constant was changed in this phase.

### Exposure of the version-1 test split (what happened and what was done)
- **What was exposed.** During the first full run (Phase 3c commands), the runner printed, to the console and
  to `benchmarks/results/full/run.log`, one detailed line per point for *every* split: measured peak RAM and
  time, the censoring/classification detail, and the Tier 0 predicted RAM and time. That included the 52 points
  of the 18 version-1 test cases. Reported by the project owner after the run.
- **How.** Phase 3c separated only the result *files* (`sealed/`); the console/log path was not covered by the
  guard and nobody checked it. The guard tests covered CSVs, reports and imports, not log output.
- **Consequence.** The version-1 test group is renamed **`exposed-v1`**: it may be used for development and
  diagnosis but **never for final claims**. A fresh sealed group, **`test-v2`**, replaces it (below). The
  exposure is recorded in the access log at the end of this file.
- **Runner fix.** For any sealed group the runner now logs only `[i/N] <point id>: <status> [<elapsed>s]`
  (no predictions, actuals, censoring or classification detail), and on a harness error only the exception
  *type* (no message, no traceback). Regression tests assert the exact line format and that non-sealed groups
  still log values. `status`, `progress.json` and the normal report already showed only ids/counts.
- **Scrub tooling.** `python -m benchmarks.maintenance scrub-logs <dir>` rewrites every log line naming an
  exposed-v1 or test-v2 point down to timestamp, index, id, status and elapsed time (idempotent, tested);
  `migrate-exposed <dir>` moves the exposed-v1 rows from `sealed/` into the development files with
  `split=exposed-v1` (tested).
- **NOT done: the existing `run.log` could not be scrubbed and the full-run results could not be analysed.**
  `benchmarks/results/full/` (and its `run.log`) does not exist in this workspace: the full run's output is not
  on this machine's copy of the repo, and no other copy was found. Both scrubbing and `docs/benchmarks/full-v3/`
  need that directory. Run these where the results are (or copy the directory to `benchmarks/results/full`):
  `python -m benchmarks.maintenance migrate-exposed benchmarks/results/full`, then
  `python -m benchmarks.maintenance scrub-logs benchmarks/results/full` (also scrub any saved terminal output
  or pasted copies yourself; the tool only knows `*.log` files), then
  `python -m benchmarks.diagnose benchmarks/results/full --out docs/benchmarks/full-v3`.

### Split version 2 (`benchmarks/split.json`, frozen 2026-11-17, digests per group, history kept)
| group | cases | status |
|---|---|---|
| `dev` | 29 | examined in Phases 3/3b |
| `exposed-v1` | 18 | the old sealed split; values were printed; development/diagnosis only |
| `test-v2` | 17 | **sealed**, never run or evaluated |

- `test-v2` cases are named `v2/...`, cover all 9 operations (2 configurations each, 1 for matmul), and differ
  from every dev and exposed-v1 configuration: tests assert (a) no input configuration is equal (compared
  independent of row count), (b) no random seed is shared (v2 seeds are 101-123 and 1103/1104), (c) at least 10
  cases use generator options no dev or exposed case uses, and (d) none appears in a committed report.
- New generator options (defaults reproduce every earlier dataset **bit for bit**, regression-tested with
  portable content hashes): `zipf_exponent` (heavier skew, 1.8), `null_pattern="clustered"` (nulls in runs of
  ~64 rows), `str_len_dist="variable"` (lognormal string lengths 3..4x), `ordering="block_sorted"` (sorted within
  4096-row blocks), zipfian right-key fan-out in joins, `nearly_sorted` and `few_unique` (int64) arrays. Join
  shapes: right smaller (0.25x, skewed fan-out, left join) and right larger (1.5x, 30% overlap). Also new:
  composite string keys with variable lengths, five-frame and unequal-frame concat with `ignore_index`, a
  tall-skinny matmul, categorical-heavy and datetime-heavy CSVs, `int -> category` and `float -> int64` casts.
- Guard unchanged in spirit: only `evaluate --final` reads `test-v2`; development loaders return `dev` and
  `exposed-v1` rows only and refuse a `test-v2` case; reports label exposed-v1 as "development and diagnosis
  only". **`test-v2` is opt-in**: the default `--splits` is `dev,exposed-v1`, so no ordinary run measures it.
- Do not run `test-v2` until the models/constants are frozen for the claim.
  To run it later (about 44 of 49 points fit under a 2.5 GiB cap with `--max-size 10000000`):
  ```
  nexus-calibrate-machine                       # fix the machine profile BEFORE; do not recalibrate afterwards
  python -m benchmarks plan --suite full --splits test-v2 --mem-limit-gb 2.5 --max-size 10000000
  python -m benchmarks full --splits test-v2 --mem-limit-gb 2.5 --max-size 10000000 --no-report
  python -m benchmarks status benchmarks/results/full          # counts only for test-v2
  python -m benchmarks evaluate benchmarks/results/full --final --reason "<why now>"   # logged; use once
  ```
  Each `--final` run appends to the access log. Re-running with changed models after seeing the result burns
  the split; create `test-v3` instead.

### read_csv engine check
- **The benchmark and the NEXUS model both assume the default C engine.** `pd.read_csv(path)` resolves to
  `CParserWrapper` here (pandas 3.1.1); pyarrow is not installed, so no pyarrow scenario exists and none was
  needed. The engine is now recorded in every result row (`read_csv_engine`, `read_csv_text_dtype`), and a test
  fails loudly if pandas' default engine ever changes or a suite source passes `engine=`.
- The model has no engine awareness: `pd.read_csv(f, engine="pyarrow")` would be estimated with C-engine
  numbers (and the analyzer ignores the kwarg). A pyarrow scenario should be added when pyarrow is available,
  together with a model decision; not changed here.
- With pandas 3, text columns come back as `str` (python-backed string dtype), although the benchmark's
  generated frames use `object`; read_csv outputs are therefore not the same dtype as the other operations'
  inputs (relevant to the read_csv RAM under-prediction; unverified).
- **Parse throughput (plausibility check, small-suite files, this machine, 16 logical CPUs):**

| scenario | 300k rows | 1M rows | 3M rows | wall / CPU time, 1M rows |
|---|---|---|---|---|
| numeric (7 cols) | 1082 MB/s | 1391 MB/s | 1380 MB/s | 0.17 s / 0.33 s (CPU/wall 2.0); 259 MB file: 0.23 s / 1.06 s (4.5) |
| mixed (int/float/text/category/date) | 199 MB/s | 181 MB/s | 178 MB/s | 0.70 s / 0.88 s (1.3) |
| strings (4 text columns) | 174 MB/s | 144 MB/s | 131 MB/s | 0.76 s / 0.77 s (1.0) |

  The 1.1-1.4 GB/s numeric figure looked too fast for a single-threaded parser; re-timing a 259 MB numeric file
  standalone gave 0.23 s wall but 1.06 s CPU, so the C engine in this pandas build **uses several threads** for
  numeric content, while string-heavy files run single-threaded (CPU/wall 1.0). Parse throughput therefore
  depends on dtype mix and on core count, which no single `csv_parse_bps` (calibrated at ~485 MB/s on a mixed
  100 MB file) can capture: a data-dependent time error, not a calibration error.

### Diagnosis, preliminary (small suite only; superseded by "Full-data diagnosis" below)
`benchmarks/diagnose.py` (new; tests use synthetic data with known structure) builds the per-point
predicted/actual tables, log-log slopes of time and RAM versus n, and a rule-based structural vs data-dependent
classification (rule and thresholds in its docstring and in `findings.md`).
**`docs/benchmarks/full-v3/findings.md` was not produced** (full-run results unavailable, see above). To
validate the tool on real data I ran it on what exists: the 87 dev points of the small suite (3 sizes
300k/1M/3M, scored with the current calibration): `docs/benchmarks/small-diagnosis/findings.md`. It contains no
exposed-v1 points, so everything below is **preliminary**: 3-5 scenarios per operation, one data parameter varied
at a time, and a median of 1-3 valid points per scenario.

Two kinds of "data-dependent" need separating, and the automatic rule cannot: an error that depends on a feature
Tier 0 *already has* (dtype mix, shapes, file size) is a **formula** problem fixable without new statistics; one
that depends on a quantity Tier 0 cannot see (cardinality, duplicate fraction, key overlap/fan-out, which columns
are aggregated, text content) needs **Tier 1 statistics or a Tier 2 dry run**.
Folds below are median predicted/actual per scenario on the log scale (+ over, - under):

| operation | main error | verdict | evidence (dev, small suite) |
|---|---|---|---|
| merge | RAM over x2.8..x5.8 | **structural** (formula) with an output-size component | four variants (1:1, 10% overlap, fan-out 3, left join) are +4.5..+5.8 regardless of overlap or join type; many-to-many, the one with the largest output, is the least wrong (+2.8). Per-scenario spread is only x1.3, but all five variants use right = n/2, so overlap/fan-out are under-sampled. The default output-rows prior (max of the two sizes) is the suspect |
| sort_values | RAM over x2.3 | **structural** | +2.26 (int key), +2.46 (int+float), +2.25 (string key): identical regardless of key dtype or data; the "peak ~ input bytes + indexer" formula is wrong. Time slope 1.23-1.30 vs 1.04-1.07 modelled: superlinear scaling, also structural |
| drop_duplicates | RAM over x1.6; time scaling | **structural** (dtype weights + exponent) | RAM +1.6/+1.4 (mixed), +2.7 (strings), -1.2 (numeric): depends on dtype mix, which Tier 0 sees. Time slope 1.18-1.28 in every scenario vs 1.0 modelled (hash tables outgrow cache); duplicate fraction changes neither (consistent with the Phase 3b finding) |
| groupby | RAM +1.3..+4.1; time +6.9 / -1.7 | **data-dependent** (cardinality, aggregated columns) | folds change sign with key cardinality: low-cardinality string key +2.5 RAM / +6.9 time, high-cardinality -1.0..+1.7 RAM / -1.7 time, numeric-all-columns +4.1. The rule labels RAM "structural" (spread x1.6 is below its x2 threshold with only 3 scenarios); the raw scenario folds say otherwise. Needs group count (Tier 1) and the aggregation target |
| read_csv | RAM under -1.6..-2.9; time sign flips | RAM **structural**, time **data-dependent** | RAM under-predicted in all three scenarios (numeric -1.6, mixed -2.7, strings -2.85). Time: numeric +2.8 (faster than modelled: multithreaded parse), mixed -2.7, strings -3.4; the sign follows dtype mix, so a header/first-rows sniff (Tier 1) is the fix. Likely contributing: pandas 3 returns `str` dtype, not `object` |
| astype | RAM under -1.6..-3.0; time +1.4..-2.9 | **data-dependent** (cardinality) | category conversion of a high-cardinality string column is -3.0 (down to -4) vs -1.55 for low cardinality (prior assumes 10% distinct); time flips sign (+3.4 low-card, -2.9 high-card) |
| concat | RAM +2.0 mixed, -1.2 numeric | **structural** (text weighting) | the text-dtype frames are over-predicted ~2x, numeric slightly under; dtype is visible at Tier 0 (shared strings make deep bytes overstate RSS). Time slope 1.21 vs 1.0 |
| matmul | no dominant error at d=1000-3000 | none yet | -1.04 RAM, -1.08 time; time slope 2.34 vs 3.0 modelled (BLAS efficiency rises with d), one scenario only |
| np.sort | not assessable | n/a | all small-suite points fall under the 32 MiB floor; needs the 5M+ element points |

Overall: **structural** errors dominate RAM (merge, sort_values, drop_duplicates, concat, read_csv) and the
superlinear time scaling (drop_duplicates, sort_values, concat, high-cardinality groupby); these are Tier 0
formula problems that more statistics will not fix by themselves. **Data-dependent** errors are groupby,
astype and read_csv time (cardinality, dtype content): those are the Tier 1 / Tier 2 targets. This must be
re-done on the full dev + exposed-v1 data (more scenarios and sizes up to 30M, which will test the slopes).

### Full-data diagnosis (dev + exposed-v1; `docs/benchmarks/full-v3/findings.md`)
- [x] `migrate-exposed` (52 actuals / 48 predictions moved, `sealed/` now empty), `scrub-logs` (48 lines
  redacted), `diagnose` run. **Verification:** a scan of every file under `benchmarks/results/full` finds no
  test-v2 case name (test-v2 was never run); exposed-v1 ids occur only in `actuals.csv`/`predictions.csv`
  (both carry a `split` column) and in `run.log`, where lines are reduced to id, status and elapsed time.
  `report.md`, `points_joined.csv`, `metrics_*.csv` and the figures are dev-only (84 points).
- Data: 84 dev + 52 exposed-v1 points, 124 measured, 12 skipped by the 2.5 GiB cap (all at the largest sizes
  of the heaviest scenarios). Sizes reach 10M rows only for astype, drop_duplicates, groupby (cheap scenarios),
  sort_values, concat, np.sort; **merge, read_csv, high-cardinality groupby/astype stop at 3M**, so their
  slopes rest on two points. The predictions come from the current models (`src/` is unchanged since the run's
  commit cc45596).
- **Fixed during this step:** `migrate-exposed` appended current-schema rows (41 columns) under the old header
  of `actuals.csv`/`predictions.csv` (39/35 columns, written before `read_csv_engine`/`read_csv_text_dtype`
  existed), which made both files unreadable. `maintenance.upgrade_header` now rewrites a file under the
  current header, decoding each row by its own width, and `migrate-exposed` calls it. Row counts verified
  (136 actuals, 124 predictions).
- The `diagnose` auto-rule is only a first pass. It compares bias with scenario spread and therefore calls
  groupby time "structural" (bias x3.7 > spread x2.8) although the per-scenario fold flips sign with key
  cardinality. The classification below is from the per-scenario folds (median over sizes) and takes the rule's
  output as one input.

Median fold per scenario (+ over, - under) and the log-log slope of actual time (predicted slope is ~1 for every
operation except matmul, where it is 3; full per-scenario slope table in `findings.md` section 2):

| operation | RAM | time | time slope (actual) | classification (full data) | change vs small suite |
|---|---|---|---|---|---|
| merge | +1.7..+7.7 (1:1 +5.4, overlap10 +7.7, left +6.7, fan-out3 +4.6, fan-out4 str +7.2, many-many +2.8, outer +1.7) | +1.1..+3.2, outer -2.5 | 1.23-1.50 | RAM: **structural over-prediction (~x5) plus data-dependent** (output size: predicted value is constant across scenarios while actual varies 84-310 MB at 3M rows); time: structural exponent | RAM "structural only" becomes "structural + data-dependent": the small suite had every variant at right = n/2 and hid the spread (x4.5 across scenarios, not x1.3). Time slope is 1.3-1.5, not 1 |
| sort_values | +2.27..+2.46, all dtypes | -1.4..-1.8 numeric/datetime, +1.4..+1.8 string | 1.35-1.40 | **structural** (constant RAM factor x2.3, spread x1.04; superlinear time) | unchanged. Time sign differs by dtype, which Tier 0 sees (formula, not statistics) |
| drop_duplicates | mixed +1.6, strings +3.1, numeric -1.04, nulls -1.00, subset +1.6 | -1.1..-2.1, strings +1.0, **subset on one low-card string column +14.6** | 1.24-1.45 (1.05 for subset) | RAM **structural** (dtype weights). Time: **structural exponent** (slope 1.4, numeric 10M is -4.4) plus **data-dependent** for `subset=` on low-cardinality keys (cost follows distinct count, not rows) | time slope higher than 1.18-1.28 seen at 3M; the subset scenario is new evidence of a data-dependent component |
| groupby | +1.3..+7.4 (cat key zipf +7.4, int +4.1, str low-card +2.6, two keys +1.5, str high-card +1.3) | +6.3 low-card, +9.3 zipf, **-2.0 high-card** | 0.83-1.07, high-card 1.52 | **data-dependent** (group count, aggregated columns, key distribution) | unchanged verdict, stronger evidence: time sign flips with cardinality, and 3 of 5 scenarios over-predict RAM by >= x2.5 |
| read_csv | -1.4..-2.8, all negative | numeric +2.9 (wide), strings -3.2, mixed -2.7, nulls -1.9 | 0.87-1.09 | RAM **structural** (constant under-prediction); time **data-dependent on dtype mix** (sign follows content, throughput 150-1460 MB/s) | unchanged. wide_numeric and nulls scenarios confirm; time is linear in n (slope ~1.0) |
| astype | plain numeric casts -1.00 (exact), to-str -1.2..-1.6, to-category -1.5 (low-card), -2.1 (zipf), -3.0 (high-card) | to-str +1.4/-1.4, category +3.2 low-card/+2.9 zipf/-2.5 high-card | 0.98-1.02 (1.48 high-card, 2 points) | RAM: numeric casts correct; to-str **structural** (text object overhead); to-category **data-dependent** (cardinality). Time: category **data-dependent** (sign flips) | refined: the single "data-dependent" label split by target dtype |
| concat | text frames +2.0..+2.1, numeric -1.2 | -1.4..+1.9 | numeric 0.99, text/multi-frame 1.16-1.42 | RAM **structural** (text weighting, size-independent); time mild superlinear exponent for text frames | unchanged; the dev/exposed bias gap (1.28 vs 2.10) is a scenario-mix effect, not a size effect |
| matmul | -1.02..-1.06 | -1.1..+1.07 | 2.68-2.77 (model 3.0) | no dominant error (2 scenarios) | unchanged; slope < 3 is BLAS efficiency rising with d, absorbed by calibration in the measured range |
| np.sort | -1.00 | +1.2 | 1.09-1.19 | no dominant error | assessable now (5M/10M points): RAM exact, time slope slightly above the modelled 1.06 |

Scaling: actual time is superlinear (slope 1.3-1.4) for sort_values, drop_duplicates, merge and concat, against a
modelled ~1.0-1.06; linear for astype, groupby (except high-cardinality, 1.5) and read_csv. Because the size trend
of the fold is -0.3 to -0.4 per decade for sort_values and drop_duplicates, **errors are smallest at small n and
grow in the direction of under-prediction exactly where OOM and long-runtime risk matters**. RAM slopes are ~1.0 for most scenarios. Slopes of 0.17-0.66 sit on 2-3 points near the 32 MiB floor
(baseline dominates; not sub-linear memory). Two three-point scenarios well above the floor are also below 0.9
(drop_duplicates/strings 0.85, groupby/two_keys 0.82); they are unexplained here and not interpreted.

Caveats: 2-3 sizes per scenario (merge/read_csv: two), one machine, one pandas/numpy build; exposed-v1 points
are shown labelled and are for diagnosis only, never a final claim.

### Next steps
1. Phase 4 candidates, in order of leverage on the evidence above: (a) Tier 0 formula fixes that need no
   statistics: merge RAM level, sort_values RAM factor, concat/drop_duplicates text weighting, time exponents
   (~1.3-1.4) for sort/dedup/merge/concat; (b) Tier 1 statistics where the error follows data content: group
   count / distinct count (groupby, astype to category, drop_duplicates with subset), key overlap and fan-out
   (merge), dtype mix of a file header sample (read_csv time).
2. Keep test-v2 sealed until models are frozen; any model change after seeing these diagnoses is fine, but the
   final claim needs the sealed split.
3. Tooling follow-up (not done here): `python -m benchmarks status` labelled the exposed-v1 rows still in
   `sealed/` as "test-v2 (count only)" and, after migration, counts them under "dev". The run itself never
   measured test-v2, but the label is misleading and should be fixed in `benchmarks/__main__.py`.


## Phase 4a: structural Tier 0 fixes

Scope: fix the **structural** RAM errors found in Phase 3d, from how pandas/numpy implement each
operation. Rules: derive from the implementation (source read, isolated allocation probes), do not
fit constants to benchmark points; develop against `dev`, validate on the held-out `exposed-v1`
(never a final claim); keep ranges honest; `test-v2` stayed sealed and was not run. **Time models
were not changed** (step 6, see below).

- [x] 0. Memory-pressure check. `nexus.measure` now records available RAM (start, minimum), page faults
  (all/major) and swap rise per run; `python -m benchmarks.pressure` screens a results directory.
  Report: `docs/benchmarks/tier0-v2/pressure.md`.
- [x] 1. sort_values RAM. [x] 2. merge RAM as a function of output rows. [x] 3. read_csv RAM (+ regression
  test). [x] 4. astype to-str / to-category. [x] 5. concat / drop_duplicates string sharing.
- [x] 6. Time models: left unchanged, with evidence (below).
- [x] 7. `python -m benchmarks status` shows dev, exposed-v1 and test-v2 separately (grouped by `split.json`,
  not by a stored column).
- [x] 8. Before/after on identical measurements: `docs/benchmarks/tier0-v2/before_after.md` (+ CSVs and
  `points_ram.csv`). Probe scripts: `docs/benchmarks/tier0-v2/probes/`. Lint/tests pass on Windows.

### Method note: before/after is scored on the SAME measurements
Actuals are independent of the models, so instead of re-measuring (27 min, and ambient time noise of
+-40% between sessions would blur the comparison) the old `actuals.csv` was kept and only the Tier 0
predictions were re-run (`benchmarks/results/tier0-v2`, 4.5 min, all 136 dev + exposed-v1 points;
`tier0_compare` asserts the time predictions are identical before/after). To re-measure everything
with the new instrumentation (about 27 min; close other programs, >= 6 GiB free so the pressure screen is
clean):
```
python -m benchmarks full --out benchmarks/results/full-v4 --mem-limit-gb 2.5 --max-size 10000000
python -m benchmarks status benchmarks/results/full-v4
python -m benchmarks.pressure benchmarks/results/full-v4
python -m benchmarks.maintenance scrub-logs benchmarks/results/full-v4
python -m benchmarks evaluate benchmarks/results/full-v4
```

### Step 0: memory pressure (details in `pressure.md`)
No swap/pagefile rise at any of 142 re-measured points; available RAM never below 876 MiB. 12 of the 33
points at 10M rows or > 1 GiB were flagged (all in drop_duplicates / sort_values / concat, measured while
2-4 GiB were free); the RAM values do not change with it (-1%..+4%). Time did: the flagged session was
uniformly 1.28x slower than the original run (flagged and unflagged points alike), 10M points about +15%
beyond that, and unflagged sessions still differ by up to 40% for the same point. **The super-linear
slopes survive the exclusion of suspect points** (sort_values 1.30-1.58, drop_duplicates 1.16-1.37 on
unflagged points; in-process primitives with no pressure possible: argsort 1.34, duplicated 1.35,
gather 1.61) and are a cache-hierarchy effect of the working set, not paging and not a complexity class.
Windows has no per-process hard-fault counter, so paging was only observable through available RAM,
pagefile use and the soft-fault ratio.

### What each model now says (derivations are in the model docstrings)
| operation | mechanism (pandas 3.1) | Tier 0 range | verified with isolated probes |
|---|---|---|---|
| sort_values | peak = max(nargsort temporaries: 5 x int64 + 2 masks; take: **shallow** copy of all columns + int64 indexer + int64 index). Object columns copy 8-byte pointers: the string payload (deep bytes) is never copied, which is why the peak was ~84 B/row for every key type | low = -2%, expected = max of the phases, high = both phases + text-key tables | 8..168 B/row frames: take phase within 0.5%; single-key phase 41.2 vs 42; text multi-key adds ~5 B/row per key (measured) |
| merge | output rows M is an explicit input (`features["out_rows"]`, `out_rows_source`). Phase 1 = presized hash table (`min(max(nl, nr), 2^20+7)` entries, whatever the distinct count) + codes + indexers; phase 2 = both indexers + M x (moved bytes of both sides); pandas skips a side's copy when its indexer is a range | M: semantic floors (a left join keeps all left rows ...) + the unchanged 0.1x/1x/4x prior; low assumes the left copy is elided; Tier 1 replaces M | 0.82-1.05 vs formula when the elision matches; the presized table explained a 23 MiB gap |
| read_csv | not the frame size: peak ~ 1.6 x file + 13.5 B/field + 6 B/row (+ a new 16-byte-class `str` per text cell; de-duplication only per chunk). A chunked (no concat) read peaks at 13-73 B/row vs 71-384 for the default | file bytes only: bytes/field w in 2..24 (2.4x..11.4x the file), +-20% probe band | width sweep 1.56 B per file byte, column sweep 21.3 B/field; all-distinct 4 x 12-char text 384 vs 401 from the formula; +-20% overall |
| astype -> str | new `str` objects: 8 + pymalloc class16(41 + len); integers add an object-int temporary (8 + 32 B/row); float/datetime do not | length 1..20 (int) etc., expected = geometric middle; `str_len` (Tier 1) collapses it | 7 int widths, 2 float, datetime: 64.3/90.8/96.4/96.4/112.5/112.5/112.5 vs 64/96/96/96/112/112/112 |
| astype -> category | factorize + code remap; per-row cost independent of n | low = few distinct (24 text / 16 numeric B/row), high = all distinct (83 / 59), expected = geometric middle | 3 sizes (1M/2M/4M) x 3 cardinalities; **mid cardinalities are not linear in U/n** (documented) |
| concat | `np.concatenate` of shallow bytes + int64 index (+12 B/row measured incl. a transient; 0 with `ignore_index`) | low = moved, expected = + index, high = 2 x moved + index (dtype unification) | numeric exact (`moved + 12`); mixed frames 4-13% above |
| drop_duplicates | factorize per key (8 B/row codes kept, presized table), id fusion (+ compress step when the distinct-count product can exceed 2^63), `duplicated` table, mask/take; **each key column holding a null adds one int64 array** (`maybe_lift`) | distinct fraction 0..1, null columns 0..all nullable dtypes (Tier 0 sees dtype), +-20% formula band | 3-key numeric/text 67.1/66.9 vs 67.0; 4+ keys needed the compress step; nulls added 47.9 / 47.8 B/row = 8 x 6 columns at n = 1M / 2M |

Descriptor change: `FrameDescriptor.shallow_bytes` / `moved_bytes` (what a take/concat/filter copies);
deep `nbytes` is no longer used by those models. Tier 1 hooks are explicit features set to `None` at
Tier 0: `out_rows`, `distinct_fraction`, `key_distinct_fraction`, `null_key_columns`, `str_len`,
`n_rows/n_cols/text_cols/str_chars/unique_fraction` (read_csv). The "shared string objects" question
resolved differently than assumed: for take/concat/mask the string objects are shared *by construction*
(pointers are copied), so no sharing feature is needed there (probes: shared vs unshared strings gave
identical peaks); the data-dependent quantity is the distinct count that sizes hash tables, which is the
Tier 1 feature above. Where objects ARE created (read_csv, astype to str) the model uses the new-object
size.

### Before / after, RAM, same measurements (valid points only; bias = median expected/actual)
| operation | dev bias | dev median err | dev coverage | exposed-v1 bias | exposed median err | exposed coverage |
|---|---|---|---|---|---|---|
| sort_values | 2.28 -> 1.01 | 128% -> 1% | 0% -> 100% | 2.27 -> 1.01 | 127% -> 1% | 0% -> 100% |
| merge | 5.22 -> 2.03 | 422% -> 103% | 70% -> 90% | 4.45 -> 1.04 | 345% -> 41% | 50% -> 100% |
| concat | 1.40 -> 0.96 | 58% -> 4% | 50% -> 100% | 2.10 -> 0.93 | 110% -> 7% | 0% -> 100% |
| read_csv | 0.38 -> 1.10 | 62% -> 10% | 100% -> 100% | 0.64 -> 1.87 | 36% -> 87% | 100% -> 100% |
| astype | 0.62 -> 1.00 | 38% -> 12% | 89% -> 100% | 0.83 -> 1.10 | 17% -> 10% | 86% -> 100% |
| drop_duplicates | 1.57 -> 1.14 | 57% -> 14% | 100% -> 100% | 1.54 -> 0.70 | 54% -> 30% | 100% -> 100% |
| groupby, np.sort, matmul | unchanged (not in scope) | | | | | |
| ALL (dev / exposed-v1) | 1.57 -> 1.04 | 64% -> 8% | 76% -> 98% | 1.05 -> 1.00 | 52% -> 10% | 67% -> 100% |

Share of valid actuals above `high` (the dangerous direction): 2% -> 0% on both splits. Mean range
width: dev 1.86 -> 1.71, exposed 1.73 -> 1.53 (ranges did not widen overall; per-operation widths in
`before_after.md`).

### Which structural errors went away on BOTH dev and exposed-v1
- **Gone on both:** sort_values RAM (x2.3 over -> within 1%), concat RAM (x1.4 / x2.1 over -> -4% / -7%),
  the read_csv under-prediction (x0.38 / x0.64 -> now over; two of the three new regression files,
  all-distinct strings at 7.5x and one-digit ints at 5.8x the file size, exceed the first-draft `high` of 5x), astype to-str.
- **Constant fixed, remainder is data-dependent (Tier 1):** merge (x5.2 / x4.5 -> x2.0 / x1.0; the rest is
  the unknown M and the left-copy elision, e.g. dev `left_1to1` still x3.3 and exposed `outer_overlap50`
  x0.62 under), astype to-category (the range now brackets all points; expected still x0.6-1.6 by
  cardinality), drop_duplicates dev (x1.57 -> 1.14).
- **Did not go away / worse on one split:** drop_duplicates on exposed-v1 (bias 1.54 -> **0.70**, median
  error 30%): `expected` under-predicts the null-heavy `realistic_nulls` and the high-survivor
  `subset_i0_s0_lowcard` scenarios; all points are inside the range (coverage 100%, none above `high`).
  read_csv on exposed-v1 is over-predicted x1.87 (x2.2 for `wide_numeric`, x1.9 for dev `numeric`): the
  unknown field width puts `expected` at 4.4x the file while float-heavy files are 2.0-2.3x; Tier 1 (a
  header sample) is the fix. groupby (x2.6 dev / x1.5) is untouched and data-dependent.

### Honest notes
- **The null-lift term in drop_duplicates was triggered by an exposed-v1 failure**: the null-heavy
  `realistic_nulls` points were under-predicted after the first revision. The mechanism was then read from
  `get_group_index` and verified with an isolated probe on synthetic frames (47.9 B/row = 8 x 6), not fitted
  to those points; but exposed-v1 is no longer a clean hold-out for that scenario, and its validation rests
  on the probe. `test-v2` has no such exposure.
- Coefficients that are measured, not derived from pandas source: read_csv (1.6 / 13.5 / 6), the multi-key
  text sort (45 + 5 per key), the category extremes (24/83, 16/59), concat's 12 B/row index and the
  +-20% / -2% error bands. All come from isolated probes (scripts in
  `docs/benchmarks/tier0-v2/probes/`), none from benchmark points, each stated in its docstring with the
  probe values. The mechanism behind read_csv's second copy (chunk concatenation) is inferred, and a
  drop_duplicates under-prediction at n = 1M (+18% at 9 keys, +5% at 2M) is unexplained and covered by the
  band.
- Ranges: none was narrowed below its probe error band. sort_values' range is narrow (derivation exact);
  merge, read_csv, astype and drop_duplicates stay wide because Tier 0 genuinely does not know M, the field
  width, the cardinality or the distinct count.
- Out of scope and unchanged: all time models, groupby, matmul, np.sort. `test-v2` was not touched.
- Fixed on the way: `python -m benchmarks status` (grouped by `split.json`); `ResultStore` upgrades an
  older header automatically (the Phase 3d corruption cannot recur).

### Step 6 (time models): why they were left alone
The evidence for a different complexity class does not survive. Slopes stay at 1.2-1.6 with suspect points
removed, but the same slopes appear for in-process primitives where pressure is impossible, because the
per-element cost rises as the working set outgrows the caches (argsort 21 -> 92 ns/element from 125k to 8M
rows). sort_values is already modelled as n log n (which explains ~1.05 of the 1.3-1.5 observed); hash
operations are O(n) by algorithm. A working-set-dependent cost needs machine-specific breakpoints
(calibration, Phase 6); an exponent fitted to three sizes would be the forbidden tuning.

### Next steps
1. Tier 1 statistics, now with explicit feature slots: distinct counts per key column and per row
   (drop_duplicates, groupby, astype category), output-row estimate from key overlap/fan-out and copy
   elision (merge), header/row sample for read_csv (rows, columns, text columns, string length), null counts
   per key column, integer string length for astype.
2. Phase 6 calibration: a working-set-dependent time cost (cache breakpoints) and re-validation of the
   error bands on a clean machine; re-run the full benchmark (command above) so the pressure screen covers
   the original 136 points.
3. groupby RAM (x2.6 dev) was not part of this phase; derive it the same way (hash table by distinct keys,
   result frame, aggregation temporaries).
4. When the models are frozen: run `test-v2` once (procedure in the Phase 3d notes).


## Phase 4b: Tier 1 data statistics

**Status: implemented and evaluated on dev. The held-out check (`val-v3`) was then run and read; see Phase 4b.2 below: it found failures, and val-v3 is dev data from split version 4 on.**
Everything below that says "dev" was available while the models were built and tuned; the held-out
check on val-v3 is still to be run by the project owner (command at the end). `test-v2` stayed sealed.

- [x] 0. Split hygiene: `split.json` is now version 3. exposed-v1 is **dev** (its list is kept as
  `provenance`); a new held-out `val-v3` (36 cases, seeds >= 301, no non-default generator value, join
  ratio or array dtype/pattern shared with dev or test-v2; tests pin it) is frozen with a digest. The runner
  writes val-v3 to `<results>/validation/` and logs only id/status/elapsed; `status` shows it as "count only";
  `evaluate --val --reason "..."` is the only reader and logs every use in the Test-split access log below.
  Tests: non-overlap of configurations, seeds and parameter values, protected-case refusal in development
  loaders, tokens bound to their group, redaction of runner logs (also on harness errors).
- [x] `nexus/stats.py` (Tier 1 statistics) and `Tier1Context` / `tier1_features` in the model API; the pipeline
  calls them at `tier >= 1`, falls back to Tier 0 on any failure, a too-small sample or an exhausted
  budget, and records `tier1: {used, reason | sample, confidence, method, stats_s}` in the logged features.
- [x] Tier 1 for astype (category cardinality; string-object sizes), groupby (group counts, aggregated
  columns), merge (output rows, overlap, copy elision), drop_duplicates (survivors, key distinct counts, null
  key columns), read_csv (rows, columns, field width, string uniqueness).
- [ ] **Not done:** DataFrame block layout (the `consolidated` flag exists but no probe showed an effect on a
  copy-like peak; the 4a probes found `moved bytes + indexer` exact), and the shared-string *feature*: see below.
- [x] Evaluation: `benchmarks/tier1_compare.py`; dev report in `docs/benchmarks/tier1-dev/`; `evaluate --val`
  includes the same comparison for val-v3.

### The statistics (what each one is, what bounds it, what it costs)
| statistic | method | interval | cost |
|---|---|---|---|
| distinct count (groupby groups, category cardinality, per-key tables) | stratified row sample (<= 200k, time-fitted by a timed pilot) -> Chao1 point estimate | lower = distinct seen; upper = seen + unseen rows allowed by the Good-Turing missing-mass bound (McAllester-Schapire, 95%); complete = exact | 7-15 ms (ints, 200k rows) |
| distinct rows / survivors (drop_duplicates, multi-key groupby) | same on row hashes (`hash_pandas_object`; categorical columns hashed by code) | same | 40 ms at ~25k rows x 9 columns |
| null key columns | float/datetime columns scanned completely (a single null makes pandas lift the column); other columns sampled, `possible` when the sample shows none | Wilson for fractions | 2-3 ms per 10M floats |
| merge output rows, overlap, key uniqueness | **coordinated key-hash sampling** of both sides (same hash predicate: sampled keys have all rows on both sides) + exact counts of up to 64 heavy keys found in a 100k-row sample (skew-aware) | Horvitz-Thompson variance + rule-of-3 for unseen heavy light keys; semantic floors (left join >= n_left) | 80-180 ms at 2M-15M scanned rows; text keys only up to 400k rows |
| read_csv shape | head 1 MiB + 3 seeked 256 KiB chunks (<= 1.75 MiB read): rows from line lengths, columns, text columns, string length, per-**parser-chunk** string uniqueness | line-length min/max over chunks; Chao1 at chunk scale | 10-40 ms |
| text columns | mean string length (CI), share of repeated values that reuse one object (object ids, read-only) | normal CI | 6-16 ms |
Every function takes a `Deadline`; none writes to or reorders the user's data (a test compares the frame
before/after). Estimator validation on synthetic data with known truth (`tests/test_stats.py`, plus the
scratch runs in the commit): the distinct interval contained the truth in 9/9 distributions (uniform from 12
to 5M distinct, zipf, heavy-tailed mix); Chao1 under-estimates skewed columns about 2x; the upper bounds are
loose where the sample cannot rule out rare unseen values (e.g. 12 groups of 5M rows -> upper bound 103k),
which costs little RAM; join output rows were within 1-5% for uniform fan-out and 0.8% for zipf after the
heavy-key correction (without it the zipf interval missed the truth by 2.6x).

### What Tier 1 changes in the models
- **groupby** was still the unverified first-draft model; it is now derived (probes `p_gb*.py`): the peak is
  the key factorization (same curve as `astype("category")`: text 24 -> 83 B/row, numeric 16 -> 58 as groups/rows
  goes 0 -> 1; categorical keys ~10 B/row) or, at high group counts, the result frame (48 + 8 x columns B/row at
  G = n); value columns do not matter below that. So **Tier 0 groupby changed too** (first-draft bias in 4a: 2.57 dev / 1.53 exposed-v1; now 1.49 on all of dev).
- **astype -> category** uses the same curve at the estimated distinct fraction and its bounds (x0.8 / x1.25 for
  the n-dependence seen at n = 1M/3M/6M); **-> str** uses the sampled pymalloc class sizes and the cached-int share.
- **merge**: `out_rows` (from the 4a explicit input) and the copy-elision flag now come from the key sample; added
  from the source and dev: the sort-based non-unique-right path, a hash engine over the **left** keys for
  `how="right"`, and +24 B per output row for `how="outer"` (key coalescing). These two also change Tier 0.
- **drop_duplicates**: survivors, per-key distinct (table sizes, the 2^63 id-compress test from the sum of
  log2 distinct) and **null key columns** come from data; the null term was the 4a under-prediction.
- **read_csv**: `parse_peak_bytes` with measured rows/columns/text columns/string length and the parser-chunk
  uniqueness; unusual options (`sep`, `usecols`, `dtype`...) stay at Tier 0.
- **Time**: the first attempt gave Tier 1 a narrower band (0.5x..2x of expected, chosen a priori from the ~40%
  session variance). On dev it cut time coverage from 94% to 69% and put 13% of actuals above `high` (read_csv time
  coverage 12%): the first-draft time formulas are biased by 0.4x-2.8x, more than the variance. It was **reverted**:
  Tier 1 keeps the Tier 0 band (0.25x..4x, far wider than the measured variance) until the time models are
  calibrated. So Tier 1 does not improve time estimates; stated plainly.

### Dev: Tier 0 vs Tier 1 (RAM; `docs/benchmarks/tier1-dev/tier1_vs_tier0.md`; 109 valid points)
Under-prediction (actual above `expected`) and over-prediction are reported separately in the full tables
(`under_share/under_fold`, `over_share/over_fold`, `above_high`, `below_low`).
| operation | bias T0 -> T1 | median err | coverage | width (mean (high-low)/expected) | actual above `high` (dangerous) |
|---|---|---|---|---|---|
| groupby | 1.49 -> 0.89 | 0.49 -> 0.14 | 100% -> 90% | 1.71 -> 0.84 | 0% -> 10% (1 of 10) |
| merge | 1.79 -> 1.04 | 0.79 -> 0.06 | 93% -> 93% | 3.67 -> 0.56 | 0% -> 0% |
| read_csv | 1.57 -> 1.22 | 0.57 -> 0.22 | 100% -> 100% | 2.65 -> 0.59 | 0% -> 0% |
| astype | 1.00 -> 1.00 | 0.12 -> 0.01 | 100% -> 94% | 1.10 -> 0.79 | 0% -> 6% (1 of 16) |
| drop_duplicates | 1.08 -> 1.09 | 0.17 -> 0.11 | 100% -> 100% | 1.01 -> 0.73 | 0% -> 0% |
| sort_values, concat, matmul, np.sort | unchanged (no Tier 1 statistics apply) | | | | |
| **ALL** | 1.01 -> 1.00 | 0.08 -> 0.06 | 99% -> 97% | **1.48 -> 0.72** | **0% -> 2% (2 of 109)** |
Tier 1 was used on 100% of drop_duplicates, groupby, merge and read_csv points (81% of astype: numeric casts have
no statistic), narrowed the range on 57% of all points and widened it on 1%. Over-prediction on dev is mostly gone
for groupby/merge (over_share 0.80 -> 0.40 and 0.86 -> 0.79 at folds near 1.05); read_csv still over-predicts by 22%
(its `expected` is a point estimate whose probe error band is +-20%).
**Time (dev):** coverage 94% -> 95%, width 3.85 -> 3.85, median error 0.48 -> 0.48: no change, by design.
**Overhead (warm, per cell; budget 250 ms for Tier 0+1):** Tier 0 median 4 ms (max 17); Tier 1 median 22 ms, p90 109 ms,
**max 201 ms**, 0 of 124 over 250 ms (drop_duplicates 109 / 178 / 201 ms, merge 98 / 130 / 137, groupby 31 / 68 / 83,
astype 24 / 46 / 64, read_csv 22 / 27 / 30: median / p90 / max). Before time-fitting the row hash, 20% of
drop_duplicates calls exceeded 250 ms (max 1.2 s): a categorical column re-hashed its million categories on every call.

**Where Tier 1 made things worse on dev (9 points, 2 dangerous):** `astype/str_to_category_zipf` 1M (fold 0.71 -> 0.41,
actual 63 MB vs 26 MB expected) and `groupby/two_keys_mean_realistic` 1M (0.96 -> 0.61): both at n = 1M and both
about +33 MB above any probe-derived value, a fixed overhead I could not reproduce in isolated probes (the same
columns at 3M and 10M are within the range); both are "realistic" real-like-distribution frames. Of the other seven,
six are over-predictions that grew within the range (folds 1.16-1.22: the narrower Tier 1 range moved `expected` to the
curve while the actual sat 15-20% below it) and one (`astype/str_to_category_zipf` 3M, 0.63) is an under-prediction
that stayed inside the range.

### What was tuned on dev, and what is checked on val-v3
Tuned or chosen after seeing dev (so dev numbers above are not evidence of generalization): the factorize bands
(x0.8 / x1.25), merge's high band (x1.15) and its right/outer/non-unique terms (each found as a dev under-prediction,
then read from the pandas source and probed), the Tier 1 time-band reversal, the time-fitting of the hashing
samples, the skew-aware join estimator (first version missed a zipf case), and the stratified-sampler fix. Derived
from probes or source before looking at dev: the factorize curve, the result-phase formula, the null term, the
read_csv structure (4a). **val-v3 will check:** every claim in the table above, the under-prediction counts, the
widths and the overhead. Nothing was changed after looking at val-v3 because it has not been looked at.

### Run and evaluate val-v3 (project owner)
```
python -m benchmarks plan   --suite full --splits val-v3 --mem-limit-gb 2.5 --max-size 10000000
python -m benchmarks full   --splits val-v3 --tiers 0,1 --out benchmarks/results/val-v3 \
                            --mem-limit-gb 2.5 --max-size 10000000 --no-report
python -m benchmarks status benchmarks/results/val-v3          # counts only
python -m benchmarks evaluate benchmarks/results/val-v3 --val --reason "4b held-out check of Tier 1"
```
`plan` reports 105 points, 95 runnable under the 2.5 GiB cap (10 skipped). Expected time: about 28 min of measurement
(dev took 13 s/point) plus ~4 s/point for the two prediction tiers, plus a one-time generation of the ~100 cached
inputs (several minutes; the 10M-row string frames dominate): **plan on 45-70 minutes**. Close other programs (>= 6 GiB
free) and do not run tests meanwhile. The report is `benchmarks/results/val-v3/validation_report.md` (with the Tier 0 vs
Tier 1 comparison) and `tier1_val/`; tell me when it exists and I will look at it, once.

### Next steps
1. Read the val-v3 report; fix only what is **structural** and re-derive from the source; anything tuned afterwards needs
   a new validation group (val-v4), since val-v3 will have been seen.
2. The unexplained +33 MB at n = 1M for real-like frames; a fixed per-operation overhead term is the likely shape.
3. Phase 6: calibrate the time models (Tier 1 cannot narrow time until then) and the working-set-dependent per-element cost.
4. Wire `stats.text_profile` into a model that actually has a string-object term (read_csv/astype use their own samples);
   no RAM formula of a pointer-copy operation depends on object sharing, so the 4a "shared-string feature" has no consumer yet.


## Phase 4b.2: diagnose the val-v3 failures, repair Tier 1 ranges, fix the planner

**Status: done on development data; NOT validated.** val-v3 was read by the developer and a reviewer, so it
is dev from split version 4 on (reclassification recorded in the access log). The held-out check is the
new `val-v4` (40 configurations), **not run**. `test-v2` stayed sealed and unrun. Nothing below is a claim
of generalisation: the fixes were derived from the failures of val-v3 and checked against those same
points, so the "after" numbers on them are in-sample.

- [x] 0. Split version 4: val-v3 -> dev (kept as `provenance["val-v3"]`, 36 cases); new `val-v4` (40 configurations,
  seeds >= 401, no non-default generator value, join ratio or array dtype/pattern shared with dev incl. val-v3 or
  test-v2; tests pin it; same leak protection as val-v3). Families: astype -> category at card 6000 / 15000 / 40000 /
  150000 / 0.12 / 400 (long strings) and int -> category, float / int -> str; groupby low-cardinality text (3, 0.003),
  two keys (60, 6000), int 40000, zipf 1.5, 0.9; merge overlap 20-95% with fan-out 1.1-10 and right sides 0.15x-3x
  (inner / left / right / outer, zipf, text keys); drop_duplicates null-heavy full frame and subsets of float / text /
  category + datetime columns, wide numeric, no-null, int subset; sort_values, concat, read_csv, np.sort, matmul as
  regression families. The stored val-v3 rows were copied into `benchmarks/results/dev-v4-before/` (dev results +
  val-v3 actuals and the old predictions) with `maintenance migrate-val3`.
- [x] 1. Diagnosis: `docs/benchmarks/val-v3-diagnosis.md` (evidence per cause, probes in
  `docs/benchmarks/val-v3-diagnosis/probes/`). **Causes found:**
  1. *There is no fixed offset* (first-call overhead is below 0.5 MiB at n = 5k..200k). The "~35-40 MiB at n = 1M"
     (astype card12000, groupby `str_card0p04`, `two_keys_card800`, and the two 4b dev points) is a **missing formula
     term**: the hash table is presized for `min(n, 2**20 + 7)` entries and its pages become resident only when keys
     hash into them. Random strings touch all of it; the Phase 4a curve had been measured on sequential keys, which
     cluster into a few pages (same n and U: 48 vs 86 MiB). The Tier 1 statistics were right (distinct counts exact,
     sd <= 0.7% over 10 seeds).
  2. merge `inner_overlap25_fanout6`: the output-row estimate was right (3%); **a formula term was missing**: with
     non-unique right keys one factorizer sees both sides, so the table holds the union of the keys (+ sorters and
     counts). That is also why Tier 1 landed *below* Tier 0.
  3. drop_duplicates `null_heavy_full` 10M: **not a model failure.** My evaluator scored a kill by the *total-RSS* cap as
     an actual equal to the cap; the true incremental peak is >= 1.8 GiB (RSS at kill minus baseline), inside Tier 1's
     range. The defect was the planner, which admitted a point whose baseline + `high` exceeds the cap. The
     per-nullable-column cost is 8 B/row exactly, as modelled; the 8-13% under-prediction of wide frames at 0.5-1M rows
     (4a, unexplained) stays.
- [x] 2. Fixes (derivations in the docstrings, regression tests pinned to probes, `tests/test_hash_table_model.py`):
  `factorize_peak_bytes` (base + resident table pages + uniques; replaces the n = 2M `FACTORIZE_KNOTS` curve) for astype and
  groupby, `stats.hash_scatter` (khash string / int64 hash replicas, 9-11 ms) for the key layout, merge sort-path
  union table with `left_distinct` / overlap from `join_profile`. Validated on 12 + 11 isolated probes (held-out 11:
  random text 0.99-1.00, random ints 0.94-0.98, clustered keys 0.83-1.01 measured/model; it over-predicts clustered
  keys, never under-predicts by more than 1%); merge 27 probes 1.02 (0.83-1.17). Fitted constants: `CLUSTER_FILL`
  (3 probes), `COMBO_COEXIST` (4 probes), merge sort-path coefficients (27 probes): all from probe grids, none from a
  benchmark point.
- [x] 3. Range policy. **Criterion committed before any number was computed** (commit "Pre-register the Tier 1
  range-policy selection criterion"; `benchmarks/range_policy.py`): above_high <= 3% per point and <= 5% per
  configuration under leave-one-configuration-out, then the narrowest mean width. Candidates on dev (191 valid points,
  81 configurations; `docs/benchmarks/tier1-v2/range_policy.md`): **A** the model's own Tier 1 range: coverage 98.4%,
  above_high 0.5% (1 point; 1.2% of configurations), below_low 1.0%, width 0.65: admissible. **C** `[T1 low, T0 high]`:
  admissible, above_high 0.0%, but width 1.84 (2.8x wider). **B / D** (expected x per-operation residual quantiles
  q(1-a), q(a), a = 0.90-0.99, LOCO; D capped at Tier 0's high): not admissible (above_high 3.7-6.3%, per
  configuration 6.2-9.9%; the residuals of other configurations do not predict the next one's). **Winner: A.** So the
  policy did not change the range: the model fixes did (A on the old predictions: above_high 4.2%, 7.4% of
  configurations, width 0.72). `nexus.ranges` keeps the hook for C / D (empty table = A, inactive); if val-v4 breaks A,
  C is the fallback to try first. **Honesty:** A passes on data that informed the model fixes; the held-out result is
  what counts.
- [x] 4. Planner (`benchmarks/planner.py`; `full` predicts first, `--no-model-planning` restores the old rule): skip
  when `baseline + high > cap` (baseline = 100 MiB + 1.02 x estimated input bytes, a least-squares fit on the 218
  measured dev baselines: 55 MiB + 1.017x, residual p95 +23 MiB, max +44 MiB; `high` = Tier 1's if it used statistics,
  else Tier 0's). On the 241 existing development points (`docs/benchmarks/tier1-v2/planner.md`, cap 2.5 GiB): the one
  point killed by the cap (null_heavy 10M, planned 2.9 GiB) is skipped before running; **3 of 218 points that measured
  fine would now be skipped** (drop_duplicates `mixed_dup0` and `mixed_dup50` at 10M, planned 2.7 GiB, measured total
  2.0-2.1 GiB; read_csv `wide_numeric` at 3M, planned 2.7 GiB, measured 1.6 GiB): the price of using an upper bound.
  Points the old static rule skipped have no prediction and are unchanged.
- [x] 5. Time is coarse. Models untouched. The user-facing text and the report show time as a bucket (under 0.1 s,
  0.1-1 s, 1-10 s, 10-60 s, 1-10 min, over 10 min) with the measured variation (repeats of one point spread by a median
  of 9% and a p90 of 30% of the median, 156 points >= 0.1 s). On dev (140 valid time points, Tier 1) the expected
  bucket equals the measured one for 76%, is within one bucket for 100%, and the measured bucket lies inside the
  low..high buckets for 100%. **Phase 6 inputs (time model biases, val-v3 Tier 1, median expected/actual):** read_csv 0.36
  (under), groupby 2.24 (over), astype 2.20 (over), float32 matmul 2.84 (over; all matmul 2.19), concat 1.25; the
  first-draft Tier 1 time band is deliberately unchanged (0.25x .. 4x).
- [x] 6. Dev predictions re-run (actuals reused; `benchmarks/results/tier1-v2`, docs in `docs/benchmarks/tier1-v2/`).
  Tier 1 RAM, dev original (109 points), before -> after: err_med 6% -> 3%, coverage 97% -> 99%, above_high 2% -> 0%,
  width 72% -> 67% (groupby above_high 10% -> 0%, astype 6% -> 0%; merge p90 error 10% -> 19%: the sort-path term moved
  points that were 4-5% low to up to 22% high). Former val-v3 (81 points, in-sample): err_med 4% -> 3%, p90 25% -> 16%,
  coverage 91% -> 98%, above_high 7% -> 1%, width 72% -> 64%. Tier 1 analysis overhead: warm median 25 ms, p90 131 ms,
  max 200 ms (drop_duplicates; merge 196 ms), 0 of 219 over the 250 ms budget (the scatter statistic adds ~10 ms per key).

### Corrections to earlier statements (mine)
- The 297c09f rule "a memory-limit kill is an actual >= the cap" was wrong: the cap is on the child's *total* RSS. The
  incremental peak is >= `rss_at_kill - baseline` (baseline extrapolated from the same case's measured sizes). With
  the corrected rule the null_heavy 10M point is **inside** Tier 1's range (bound ~1.8-1.9 GiB vs high 2.07 GiB), so the
  "above-high, dangerous" reading of it in the val-v3 report (Tier 1 above_high 9%) is retracted; the corrected
  former-val-v3 figure, before the fixes, is 7%. Test and report text updated.
- The 4b note "+33 MB at n = 1M ... a fixed overhead I could not reproduce" was the table-residency term above, not an overhead.

### Run val-v4 (project owner; NOT run)
```
python -m benchmarks plan   --suite full --splits val-v4 --mem-limit-gb 2.5 --max-size 10000000
python -m benchmarks full   --splits val-v4 --tiers 0,1 --out benchmarks/results/val-v4 \
                            --mem-limit-gb 2.5 --max-size 10000000 --no-report
python -m benchmarks status benchmarks/results/val-v4          # counts only
python -m benchmarks evaluate benchmarks/results/val-v4 --val --reason "4b.2 held-out check of the repaired Tier 1"
```
`plan` reports 119 points, 105 under the static rule (14 skipped); the model-based planner will additionally skip the
points whose baseline + `high` exceeds 2.5 GiB (it predicts before measuring). Expected time **45-70 minutes**: ~95-105
points x ~13 s of measurement (about 20-25 min), ~4 s per point for the two prediction tiers (~7 min), and a one-time
generation of ~100 cached inputs (the 10M-row string frames dominate; 10-25 min). Close other programs (>= 6 GiB free)
and do not run tests meanwhile. The report is `benchmarks/results/val-v4/validation_report.md`. Read it once; if val-v4
shows failures, fix only what is structural and create `val-v5`.

### Next steps
1. val-v4 (above). The success criterion to hold the result to, stated now: Tier 1 above_high <= 3% per point on val-v4,
   every operation family covered, and no family that works on dev failing on val-v4.
2. Unexplained: drop_duplicates 8-13% under-prediction on 9-column frames at 0.5-1M rows (4a), the +-17% of the merge
   sort path between fan-out 2 and 6, read_csv over-prediction on nulls/dates (1.4x on val-v3).
3. Phase 6: calibrate the time models (inputs above); Tier 1 may then narrow time ranges.


## Phase 4b.3: val-v4 failed; astype bug, sanity guard, merge diagnosis, global range fallback

**Status: done on development data; NOT validated.** There is no held-out validation group in split version 5
and none was created or run in this phase; `test-v2` is sealed and unrun. Details and evidence:
`docs/benchmarks/val-v4-diagnosis.md`; tables in `docs/benchmarks/tier1-v3/`.

### val-v4 outcome (the one held-out check of the 4b.2 models)
Tier 1 RAM, 93 valid points: median error 4%, p90 28%, coverage 92%, **above_high 5.4% (5 points; criterion: <= 3%)**,
below_low 2%. The criterion FAILED. The five points: 3 x astype `float_to_str_nulls` (Tier 1 expected 0: a bug) and 2 x
merge `inner_overlap20_fanout10` (fold 0.79 / 0.83). The other families did not regress (groupby 2% / 17%,
sort / matmul / numpy.sort / read_csv as before). The OOM `high` rule had one false negative at 2048 MB (the
astype zero estimate). val-v4 is dev from split version 5 (access log, `provenance["val-v4"]`, results in
`benchmarks/results/dev-v5`). The 4b.2 claim "the repaired Tier 1 meets the criterion" is **not supported**.

- [x] 1. astype root cause: pandas 3 keeps a null as a null in `astype(str)`, so the sampled lengths were NaN, the
  estimate NaN, and `build` turned `max(0.0, nan)` into 0. Fixed (null share modelled: a null costs no string object;
  66.6 MiB measured = 69.8 B/row vs 69.4 modelled), `build` now refuses non-finite figures, regression tests,
  and a 40-cell audit of every Tier 1 path (`tests/test_tier1_audit.py`). Stored predictions of all 360 dev points:
  0 non-finite, 0 non-positive (before: 3). int / datetime / float all checked (int cannot hold nulls).
- [x] 2. Sanity guard (`nexus/guard.py`): reject a Tier 1 estimate (Tier 0 kept, reason in `Estimate.note`) if it failed,
  is NaN / infinite, has a non-positive expected RAM or time, or its expected RAM is more than 2x outside Tier 0's
  [low, high]. Counted on all 360 dev points before adopting the range condition: the strict "outside Tier 0's range"
  fired on 3 of 211 Tier 1 estimates, exactly the three zeros, and on 0 correct points; I nevertheless widened it to 2x
  because Tier 0 does not know about nulls (datetime with 4% nulls -> str: correct 69.5 B/row vs Tier 0 low 70.5; the
  strict rule rejects it, regression test). After the re-run the guard rejected 0 of 360 on dev.
- [x] 3. merge diagnosis (20 inner points, `merge_inner_table.md`): output-row estimates are right everywhere
  (0.96-1.03); under-prediction (fold 0.79-0.89) occurs in all 6 non-unique-right points with M / n_left <= 0.14 and in no
  other point; not low overlap, not fan-out, not output size alone. 4b.2 **partly patched a symptom**: the union-table
  term is real (pandas 3.1 `_factorize_keys` source: right keys first, then left keys into the same table), but its
  coefficients came from a grid whose own 0.83-1.17 scatter is this residual. **Mechanism of the residual not found**
  (probes pf1-pf4: peak 65 / 49 / 59 MiB for fan-out 2 / 6 / 10 at fixed n, reproducible; factorize alone flat; join step
  below the setup peak; table residency identical). Known limitation: up to ~20% low at Tier 1 expected for non-unique right
  keys with M / n_left <= ~0.15. No constant fitted.
- [x] 4. Range policy B (candidate C: `[Tier 1 low, Tier 1 expected, Tier 0 high]`) adopted globally
  (`nexus.ranges.UPPER_IS_TIER0_HIGH`). Pre-registered criterion on all 284 dev points: A (own range) above_high 1.1% (1.7%
  of 120 configurations), coverage 97.5%, width 0.64 -> admissible and still the criterion's winner; C 0.0% / 0.0%, 98.6%,
  width 1.78: adopted by decision (the only candidate with 0 points above high). val-v4 alone after the astype fix: A 2.2%
  (the 2 merge points), C 0.0%. Per operation C's width cost: astype x2.1, drop_duplicates x1.2, groupby x3.9, **merge
  x9.1 (above_high 8.1% -> 0%)**, read_csv x5.2, others x1.0; overall x2.9. Per-operation alternatives (C only for merge;
  a merge high from M / n_left; A everywhere with merge as a documented limitation) are **hypotheses needing a fresh
  split**. The stored dev predictions are the models' own ranges (A); C is applied in the pipeline and was scored from them.
- [x] 5. The one OOM false negative at 2048 MB (`high` rule): `v4/astype/float_to_str_nulls|n=10000000` (actual 665 MiB +
  input 1,689 MiB = 2,354 MiB; Tier 1 high = 0, Tier 0 high 839 MiB would have warned). The planner would NOT have
  caught it (baseline 939 MiB + Tier 1 high 0). After the fix: Tier 1 649 / 662 / 675 MiB, NEXUS warns, dev OOM table at
  2048 MB `high`: 0 false negatives, recall 100% at every limit 64-4096 MB (322 valid points), precision 75% at 2048.
  Planner caveat: its baseline uses the estimated, not the deep-measured, input size (object-heavy frames).
- [x] 6. Large-size gap: 8 of 283 valid RAM points exceed 1 GiB (drop_duplicates 2, read_csv 6; astype, groupby, merge,
  numpy.sort, matmul, concat, sort_values 0), maximum 1.51 GiB; 37 of 360 dev points were skipped by the cap (merge 20,
  drop_duplicates 7, astype 3, groupby 3, read_csv 2, matmul 1, sort_values 1). Everything multi-GiB is extrapolated.
  Commands for a >= 32 GB Linux machine (install, calibrate, plan, run, evaluate; NOT run):
  `docs/benchmarks/large-size-linux.md`.
- [x] 7. Dev re-run with the fixed code (`benchmarks/results/tier1-v3`, commit of the run recorded in the CSV), docs
  in `docs/benchmarks/tier1-v3/`. Before -> after on the val-v4 slice (Tier 1): coverage 92% -> 96%, above_high 5% -> 2%,
  p90 28% -> 24%. Split version 5 (val-v4 -> dev; `supersede_to_v5`, `maintenance migrate-val4`; the protected-group guards are tested with a
  temporary split that has a fake val case), `load_split` now resolves the path per call.

### Phase 6 inputs (not changed in 4b.3)
- **Time:** concat under-predicted (val-v4 bias 0.19x, 60% of points above `high`; val-v3 was 1.25x over, so the bias
  depends on the frame: category-heavy concat), groupby over-predicted (3.34x val-v4, 2.24x val-v3), astype over-predicted
  (1.41x, 2.20x), read_csv under-predicted (0.31x, 0.36x), float32 matmul over-predicted (2.84x). Shown to the user as buckets.
- **RAM:** concat of category-heavy frames is 23% low (`v4/concat/two_category_heavy` 10M: 595 MiB expected, 785 measured);
  merge sort path up to ~20% low when M / n_left <= 0.15 (unexplained); drop_duplicates 8-13% low on 9-column frames at
  0.5-1M rows (unexplained, 4a); read_csv over-predicts 1.2-1.4x on null / date columns.

### Next steps
1. A held-out split is needed before any claim; it must be created and frozen BEFORE it is run, and the 4b.3 changes
   (astype nulls, guard, policy C) are the frozen model state it would test.
2. Run the Linux large-size job (above) to replace the extrapolation above 4M rows.
3. Phase 6: time-model calibration; the merge residual; concat category-heavy RAM.


## Phase 4c: Tier 2, sandboxed sample dry runs with scaling extrapolation

**Status: implemented and evaluated on DEVELOPMENT data only (every number below is dev: dev + exposed-v1 + val-v3 +
val-v4; nothing is held out; no validation split was created or run; test-v2 sealed).** Tier 0 / Tier 1 models, the guard
and range policy C are untouched. Tier 2 is opt-in (`Pipeline(tier=2)`); the IPython session still runs Tier 0-1.
Evidence: `docs/benchmarks/tier2-dev/` (`README.md`, `config-a/`, `config-b/`, `probes/`).

### What was built (`src/nexus/`)
`dryrun_safety.py` (allowlist over the AST -> `Recipe`), `dryrun_sample.py` (nested samples), `dryrun_io.py` +
`_dryrun_child.py` (hand-over files, recipe executor, the sandbox child), `dryrun_fit.py` (scaling laws),
`dryrun.py` (orchestration, escalation, `tier2_estimate`), `Estimate.note` / `Estimate.diagnostics`, `Pipeline(tier=2)`.
Tests: 139 in `tests/test_dryrun_safety.py` (31 safe + 72 unsafe / adversarial snippets: aliasing, chains, lambdas, walrus,
imports, `eval`, shadowed `pd` / `str`, subclasses, in-place calls, URLs, magics) and `tests/test_dryrun.py` (fits,
nested / coordinated sampling invariants, sandbox timeout / memory cap / crash, end-to-end sort, escalation, and a
**spawned daemon process that starts the sandbox**, the Windows constraint). Full suite and lint green.

### Design decisions, with the alternatives
| # | decision | alternatives considered | why |
|---|---|---|---|
| 1 | sandbox = a fresh interpreter via `subprocess` (`python -m nexus._dryrun_child`), hard wall-clock timeout and RSS cap enforced by the parent killing it | `multiprocessing` spawn; threads | `multiprocessing` children cannot start children from a daemon process (the benchmark's prediction worker is one) and under Windows `spawn` re-imports the kernel's `__main__`; threads share the address space with the user's objects |
| 2 | samples handed over as raw `.npy` files in a private temp dir (strings pickled), loaded into ordinary memory by the child | memory-mapped files; shared memory | a memory map is counted as resident when touched, which would put the input into the measured peak; shared memory cannot hold Python strings and behaves differently on Windows / POSIX; file cost is small next to a few-MiB sample |
| 3 | the child executes a `Recipe` (data), never the source text | `exec` / `eval` of the cell in the child | nothing the user wrote is evaluated anywhere; unknown means unsafe |
| 4 | sampling per operation (table in `dryrun_sample.py`): key-hash for merge (both frames, same predicate), groupby and drop_duplicates (equal rows hash alike); row samples (order kept) for astype / sort_values / concat / np.sort; leading rows of a and columns of b (scale x, work ~ x^2) for matmul; lines from 8 byte offsets for read_csv | plain row samples everywhere | a row sample thins both merge sides independently (matches vanish, the output ~ x^2 instead of x) and removes duplicates (tested: a row sample sees >95% unique where the real frame has 71%) |
| 5 | **sample sizes: A = 4% of the rows (40k..250k) declared first; B = 10% (40k..1M) evaluated as the alternative; default = B**, 4 nested sizes (1/8, 1/4, 1/2, 1 of the largest) | 1% / 2% / 4% with a 250k cap | A left 142 of 322 RAM fits below the measurement floors; B: 137 -> 236 RAM fits (time 145 -> 173) at a similar overhead (median 2.2 s vs 2.0 s). **This choice was made after seeing dev results (a configuration-level choice, not per point) and is not validated.** The default can be switched back with `NEXUS_DRYRUN_FRACTION` / `NEXUS_DRYRUN_ROW_CAP` |
| 6 | three laws with an intercept, `y = a + b f(n)`, `a, b >= 0`; FORWARD cross-validation (fit smaller samples, predict the next); candidate laws within max(2x best, best + 0.05) all enter the range; range = exp(-1.28 sigma) .. exp(+1.64 sigma) with sigma = CV x log2(target / largest sample) | leave-one-out; AIC | extrapolation is the task; a wrong exponent costs a constant factor per doubling so the spread must grow with the distance |
| 7 | refuse (no estimate) when < 3 sizes clear the floors, the value does not grow (x1.3), or the best forward-CV error > 25% | answer anyway | an unreliable fit is worse than Tier 1 |
| 8 | floors 1 MiB RAM / 2 ms time (allocator chunking, timer and first-call jitter; probe: first call of a 50k-row sort 1.8-9.4 ms vs 1.5 ms warm) | 4 MiB / 10 ms (first draft: it rejected every sample of a 1.5M-row merge in the pilot, before any dev evaluation) | the CV gate, not the floor, carries reliability |
| 9 | text keys above 6M rows are not hashed ("no sample"), 15 dev points | hash any size (~1.5 s per 10M strings) | overhead budget; listed as a failure, not tuned |
| 10 | escalate to Tier 2 only if RAM `high` > 50% of the available RAM, or the range is wide (>= 100% of expected) AND the expected run time >= 5 s | always | a dry run costs ~2.2 s whatever the cell does; on dev it was cheaper than the real run for 13% of the points |
| 11 | **no combination of Tier 1 and Tier 2 is adopted**; `hull` (Tier 2 expected, union of ranges) and `geomean` are reported | a per-operation switch | a per-operation choice made on dev needs a fresh split |

### Evaluation (dev; configuration B; `docs/benchmarks/tier2-dev/config-b/tier2_vs_tier1.md`)
Qualifying cells: 259 of 322 points with Tier 1 predictions got a dry run that fitted something (RAM 236, time 173);
the rest: no fit above the floors (53 RAM), unreliable CV (12), no growth (6), unsafe / not sampled (the text-key limit
above, 15). Medians of |expected / actual - 1| on the points where the Tier 2 fit was accepted (`err_med`; coverage in brackets):

| op | RAM Tier 1 | RAM Tier 2 | time Tier 1 | time Tier 2 |
|---|---|---|---|---|
| astype | 1% (100%) | 15% (60%) | 67% (97%) | **21%** (78%) |
| drop_duplicates | 11% (100%) | 13% (89%) | 28% (97%) | 32% (79%), bias 0.70 |
| groupby | 1% (100%) | 14% (76%) | 95% (79%) | **33%** (50%), bias 0.67, above_high 43% |
| merge | 8% (97%) | 13% (79%) | 38% (100%) | **16%** (90%) |
| read_csv | 22% (100%) | **15%** (74%) | 66% (100%) | **4%** (100%) |
| sort_values | 1% (100%) | 3% (96%) | 38% (95%) | 31% (85%), above_high 15% |
| concat | 8% (100%) | 9% (100%) | 44% (100%) | 32% (80%) (5 fits) |
| matmul | 3% (100%) | 45% (44%), bias 0.55 | 6% (100%) | 50% (50%), bias 0.62 |
| numpy.sort | 0% (100%) | 0% (100%) | 21% | 25% (3 fits) |
| ALL | 3% (100%) | 13% (78%) | 53% (96%) | **25%** (80%), above_high 11% |

* **Time** is where Tier 2 helps: the first-draft time models are off by 0.3x-3x, a measured sample is not. read_csv
  (Tier 1 under-predicted 0.36x) is fixed (median error 66% -> 4%, bias 1.02), astype / groupby / merge roughly halve.
  The cost: Tier 2's own time ranges are very wide (median width 16x of expected overall, up to 78x for merge) and
  under-cover for groupby, sort_values, drop_duplicates and matmul; the `hull` keeps 99% coverage at width ~20x.
* **RAM**: Tier 2 never beats Tier 1's median on the operations Tier 1 models structurally (astype, groupby, merge,
  sort, concat, matmul); it is comparable only for read_csv and drop_duplicates, and its ranges cover 78% vs 100%.
  `geomean` of both improves over Tier 2 alone but not over Tier 1 (10% vs 3%).
* **Merge residual (target 1)**: of the 8 non-unique-right / small-output points (incl. both failing configurations)
  Tier 2 fitted RAM for 6 and was within 3-24% on 4 (v3 overlap25_fanout6 1M x1.03 / 3M x1.24; v4 overlap35_fanout7 1M x1.04 /
  3M x1.05, where Tier 1 was x0.86-0.89 and x1.85), but x11.2 on `overlap20_fanout10` 1M (outside its own range) and x1.86 on
  `inner_overlap10` 3M; no fit for `overlap20_fanout10` 3M. So Tier 2 **can** see what Tier 1 misses, **unreliably**: a
  sampled merge shows the real sort-based path, but one 1M-row sample table is not the 3M-row one. Under config A it fitted 1 of 8.
* **Overhead**: median 2.2 s (max 13.7 s, concat; the hashing of text keys and the writing of samples), 3.8x the median real
  run time; the dry run was cheaper than the real run for **13%** of the points (merge 0%, drop_duplicates 24%, groupby 29%).
  By input size the median overhead is 1.9 / 2.3 / 2.5 s at 1M / 3M / 10M rows against median run times of 0.18 / 0.51 / 0.89 s:
  **on dev it never pays for time at these sizes**; break-even needs a cell that runs longer than ~5 s (`MIN_RUN_S`), i.e.
  larger inputs than the 2.5 GiB machine can hold (`docs/benchmarks/large-size-linux.md`), or a RAM-risk case.
* **Where Tier 2 is NOT worth it / fails**: (a) RAM of hash-table operations with few distinct keys: samples show a fully
  resident table of ~75-87 B/row that falls as the real table saturates at 2^20 entries; probe (3M rows, 12,000 distinct
  strings, config A sizes) extrapolated **277 MiB for random keys vs a real 109 MiB (x2.55)**, and for sequential keys (real 71 MiB) the fit
  was refused (CV 0.26): the presize cap and the key layout (4b.2) cannot be represented by the three laws, and key-hash sampling
  thins dense keys; Tier 1 models exactly this; (b) matmul (BLAS thread scaling: time bias 0.62, above_high 50%) and
  numpy.sort / cheap row-wise ops (too cheap to clear floors); (c) cells under ~5 s; (d) cells that are not a single
  supported operation: **63 of 322** dev points got no usable Tier 2 estimate (unsafe or unsampled cells, 15 of them the text-key limit; the rest unreliable fits); real notebook cells are mostly chains; (e) text keys > 6M rows.
* **Fixed costs and cold start**: the intercept absorbs them; the first call of a tiny sample can be 1.8-9.4 ms vs 1.5 ms
  warm (probe), which is why 2 ms is the time floor.

### Hypotheses (need a fresh split; not adopted)
(1) use Tier 2 time only for read_csv, astype, merge, groupby (median error halves or better) and keep Tier 1 for the rest;
(2) use Tier 2 RAM only for read_csv; (3) gate Tier 2 on its CV error (fits with CV < ~0.1); (4) a Tier 2 that fits only the
non-hash part and takes the table from Tier 1; (5) a presize-aware extrapolation (fit the sample sizes above 2^20 only,
needs larger samples).

### Next steps
1. A held-out split must be frozen before anything about Tier 2 is claimed.
2. Run the Linux large-size job and rerun `tier2_eval` there: the regime where a ~2 s dry run is cheap compared with the cell.
3. Phase 5 (risk and suggestions) can consume Tier 1 now; Tier 2 time for read_csv / merge / groupby is the useful part.


## Phase 4d: the adaptive controller, val-v5, and the ablation

**Status: controller implemented exactly as pre-registered; evaluated on DEVELOPMENT data only (replay); NOT validated.**
`val-v5` is frozen and was NOT run. Tier 0, Tier 1, the guard, policy B and the Tier 2 estimator are untouched;
`test-v2` is sealed. Pre-registration (committed before any Phase 4d number): `docs/benchmarks/phase4d-preregistration.md`.

- [x] 0. Pre-registration (rules R0-R4, success criteria S1-S5, failure statement, minimum evidence), commit `2611658`.
  The groupby multiplier 1.5 = 1 / 0.667, the Tier 2 groupby time bias already reported in Phase 4c.
- [x] 1. `nexus/controller.py`: R1 Tier 2 RAM only raises `high` to its expected value; R2 time from Tier 2 for read_csv /
  astype / merge, groupby with `high` x1.5, everything else Tier 1 (bucket); R3 escalation only on (a) RAM high > 50% of free
  RAM, (b) Tier 1 time >= 5 s, (c) Tier 1 fell back on its time budget with a wide Tier 0 range, AND safe AND the dry-run
  memory budget (need = 200 MiB + f x (inputs + RAM high), budget = 25% of free RAM, child cap = min(budget, 8 GiB)); fail
  closed with a recorded reason; 60 s total budget; every Estimate carries tier + reason in `note` and the decision in
  `diagnostics["controller"]`. `Pipeline(tier=2)` uses it (the Phase 4c always-escalate path stays for the evaluation).
  35 mocked-model tests: each trigger, no-trigger, unsafe cells, free RAM low / unknown, budget exhaustion, child timeout /
  died / memory_limit through the real dry run, an exception in the dry run, a property test that no RAM bound is ever
  lowered, and a **stress test with 10 MiB of free RAM: no child process is started, the estimate is Tier 1 with "fail closed",
  the frame is unchanged**.
- [x] 2. Multi-statement coverage (`docs/benchmarks/phase4d-dev/multistatement.md`, 51 realistic cells, analyzer NOT loosened):
  **6 of 51 accepted (12%)**: the 5 single-operation controls and a `%time`-prefixed cell. Rejected: 17 more than one statement,
  15 method chain / computed receiver, 7 non-literal argument (a variable such as `keys`), 3 other statements (import, def,
  loop, with), 1 column assignment, 1 in-place call, 1 operation outside the allowlist. 0 of 8 variable-argument, 0 of 7
  intermediate-assignment, 0 of 9 chain, 0 of 6 filter, 0 of 5 pipeline cells pass. Seven relaxation PROPOSALS (resolve literal
  names, per-statement dry runs, whitelisted chains, pure wrappers, literal filters, literal agg dicts, whitelisted imports) with
  their risks are listed; none implemented. **Most real notebook cells never reach Tier 2.**
- [x] 3. `val-v5` (split version 6, digest-frozen, leak-protected like val-v3 / val-v4): 47 configurations (merge 9 incl. 5
  non-unique-right small-output shapes, drop_duplicates 7 null-heavy, astype 9 incl. card 9k / 45k / 200k and nulls, groupby 8,
  sort 3, concat 3 incl. category-heavy, read_csv 3, matmul 2, np.sort 3), seeds >= 501, no knob value / seed / array shape shared
  with any dev split or test-v2 (tests pin it); row sizes 3M / 10M / 30M, np.sort 100M-400M, matmul 8000-16000: 141 points, 27 with
  > 2 GiB of inputs, 140 runnable under a 24 GiB cap. Group constants refactored (val-v3 / val-v4 are provenance labels). The runner
  now records kernel, distribution, CPU model, swap, and the machine calibration (`meta.json`), and `--require-calibrated` refuses to
  run without it; paths are `pathlib` throughout. `evaluate --val` appends the controller section with S1-S5 verdicts
  (MET / FAILED / INCONCLUSIVE).
- [x] 4. Controller replay on dev (`docs/benchmarks/phase4d-dev/controller_vs_tier1.md`, 322 points; **all dev**). Tier 1 alone
  vs controller, ALL operations:

  | free RAM | Tier 2 attempted | Tier 2 used | fail-closed | unsafe | RAM above_high | RAM err_med | time err_med | time within one | overhead med (s) / of real run |
  |---|---|---|---|---|---|---|---|---|---|
  | 2.5 GiB (dev cap) | 14% | 8% (25) | 2% (6) | 2% (5) | 0% -> 0% | 3% -> 3% | 53% -> 44% | 100% -> 100% | 2.7 s / 4.1x |
  | 8 GiB | 4% | 2% (6) | 0 | 1 | 0% -> 0% | 3% -> 3% | 53% -> 52% | 100% -> 100% | 2.3 s / 1.1x |
  | 32 GiB | 2% | 0 | 0 | 1 | 0% -> 0% | identical | identical | 100% -> 100% | 6.1 s / 0.6x (8 cells, trigger (b) on ops without a Tier 2 time rule) |

  Per operation at 2.5 GiB: merge time err 38% -> 20% (46% of points use Tier 2), read_csv 68% -> 44% (33% use it; at 8 GiB 25%),
  everything else unchanged; RAM unchanged in every scenario (above_high 0%, width 178% both). Triggers at 2.5 GiB: (a) 47, (a)+(b) 4, (b) 4. **What this says:** on
  dev, whose cells run 0.2-0.9 s, trigger (b) almost never fires, trigger (a) fires only because the free-RAM scenario is
  small (policy B's `high` is Tier 0's wide high), so the controller is mostly "Tier 1 kept" and its measurable gain is the time
  of merge / read_csv under a small RAM. It never made RAM worse (no bound lowered, above_high 0% both). The dry run cost 2-6 s
  and exceeded the real run time at the median (4.1x at 2.5 GiB): where it fires only because of RAM risk the overhead is not the
  point; where it fires for time (b) on a long cell it is 0.6x. **WHAT-IF (not pre-registered), always escalate when safe, 32 GiB:**
  Tier 2 used on 112 of 322, time err_med 53% -> 28%, time coverage 92% -> 88%, RAM above_high 0% but width 178% -> 189%, overhead 2.0 s / 8.5x of the
  real run: Tier 2 time is better but not cheap on short cells.
- [x] 5. VM runbook written (`docs/benchmarks/val-v5-linux-runbook.md`): install, `nexus-calibrate-machine --force` first
  (recorded), plan (`--mem-limit-gb 24 --max-size 400000000`), full run with `--tiers 0,1,2 --require-calibrated`, `evaluate --val`.
  Expected 20-30 h wall-clock, tens of dollars (estimates, not measurements). **Not run.**

### Design decisions and alternatives
| decision | alternative | why |
|---|---|---|
| the controller is a pure function of (Tier 0, Tier 1, free RAM, stored dry run), replayed from stored dry runs | re-run the dry runs live on dev | the dry runs already exist (360 points); a live rerun would cost ~35 min and add noise without testing the rules |
| (c) = Tier 1 fell back on its time budget AND a wide Tier 0 range | "the cell is expected to exceed the analysis budget" read as an input-size test | the pre-registered reading needs no new statistic; it never fired on dev (the 250 ms budget was never exhausted) |
| RAM cross-check raises `high` to Tier 2's EXPECTED value | raise to Tier 2's `high` | Tier 2's `high` is 2-5x wider than its expected (ranges up to 450%) and would raise on every point |
| free-RAM scenarios (2.5 / 8 / 32 GiB) declared up front | the dev machine's actual free RAM per point | the dev machine's free RAM at run time (~2 GiB) would put every point under the (a) trigger |
| for val-v5 the replay uses each point's recorded free RAM at its start | a fixed scenario | the controller would have seen exactly that value |

### Next steps
1. Run val-v5 on the Linux VM (runbook); read the report once; S1-S5 as pre-registered decide. Fewer than 20 escalated points makes
   S3 inconclusive; many 10M+ text-key cells are "no sample" (text keys above 6M rows are not hashed), which limits it.
2. If the controller is validated: relaxations P1 / P2 (resolve literal names, per-statement dry runs) are the only route to
   Tier 2 on real notebook cells (12% accepted today), each needs its own safety review and a fresh split.
3. Phase 5 (risk and suggestions) can consume Tier 1 / policy B and the controller's recorded tier and reason.


## Phase 4e: de-risk val-v5 and measure real-cell coverage

**Status: done; val-v5 NOT run; models, controller and the val-v5 split content untouched; test-v2 sealed.**

- [x] 1. **Pre-registration Amendment 1** (dated 2026-11-18, commit `3134216`, appended to
  `docs/benchmarks/phase4d-preregistration.md`; the original text is unchanged; written before val-v5 ran).
  (a) The original S4 ("no harm") covered RAM only (controller above_high <= Tier 1's, no bound lowered) and said nothing
  numeric about time or width: S4 is now five numeric checks: RAM above_high count <= Tier 1's; no RAM bound lowered; RAM
  width <= 1.25x Tier 1's; time within-one >= Tier 1's minus 1 pp; share of points above `time_high` <= Tier 1's plus 2 pp
  (thresholds fixed by principle, not from dev). (b) Run priority: P1 merge, groupby, astype, drop_duplicates, read_csv;
  P2 concat, sort_values; P3 np.sort, matmul (skippable); S1-S5 are evaluated on the groups that COMPLETED and the report
  lists which did (a group is complete when every point has a final status). (c) Partial runs: verdicts only for completed
  groups (union and per group), incomplete groups excluded and listed as counts, minimum evidence on the union, "val-v5 NOT
  EVALUATED" if P1 is incomplete. Implemented in `benchmarks/controller_eval.py` (`criteria`, `completion`,
  `validation_section`, used by `evaluate --val`) and in the suite (val-v5 points are ordered by priority, cases and sizes kept).
- [x] 2. **Linux smoke test: NOT possible here.** WSL2 has only the stopped `docker-desktop` helper distribution; the Docker
  client exists but the daemon is not running; I did not start Docker Desktop or pull images. Instead the Linux / POSIX
  branches were tested with fakes (`tests/test_linux_branches.py`, 11 tests: VmRSS / VmHWM, ru_maxrss fallback, clear_refs
  reset and its failure, faults, /etc/os-release, /proc/cpuinfo, no `CREATE_NO_WINDOW`, no fork); no portability bug found.
  Exact Docker / WSL2 commands (incl. a 2 GiB cgroup run of the instrument validation): `docs/benchmarks/phase4e/linux-smoke.md`.
  **Found and fixed:** a runner killed mid-write left a torn CSV row that crashed or corrupted the next resume
  (`ResultStore` now drops torn rows; harness bug, not a model change).
- [x] 3. **Pilot and resume.** `python -m benchmarks full ... --pilot N` runs the first N points (priority order, whole cases
  so the largest sizes are timed), writes `pilot.json` (seconds per point, mean, extrapolated hours for the rest: mean of
  same-size pilot points, scaled linearly in rows / quadratically in the matmul dimension for sizes not reached, low / high
  from the fastest / slowest point) and logs a summary; pilot points are real results and are not repeated by the full run.
  Tests (10, `tests/test_pilot_resume.py`): priority order, extrapolation, `--pilot` end to end, torn rows (incl. a quoted
  newline), and **a real runner process killed mid-run then resumed**: the finished point's row is byte-identical, no
  duplicates, every row has the header's width, missing predictions filled in. Runbook updated (pilot + interrupted runs).
- [x] 4. **Real-cell coverage study** (`benchmarks/realworld/coverage.py`; static: JSON + `ast.parse` + the unchanged
  analyzers over stand-in operands; never executes cell code, no downloads; 7 tests incl. a notebook full of side-effecting
  cells that must not run). Per cell: supported operation detected (Tier 0/1 model exists), Tier 2 safety verdict and reason;
  aggregates by operation and by reason; a counting-only ranking of the relaxation proposals P1-P7 (+ P8: bare imported names
  such as `read_csv(...)`). On the 51 handwritten cells it reproduces the Phase 4d verdicts exactly (6 of 51 accepted): a supported
  operation is detected in 49 (96%), Tier 2 accepts 12%; ranking: P2 per-statement 15 (35% of the rejected supported-operation
  cells), P3 chains 8 (19%), P5 filters 4 (9%), P1 literal names 3 (7%), P4 wrappers 2, P6 agg dict 2 (`docs/benchmarks/phase4e/
  coverage_handwritten51.md`). **These are handwritten cells, not real notebooks: no real notebook has been analysed yet.**
  Command: `python -m benchmarks.realworld.coverage <folder of .ipynb> --out docs/benchmarks/phase4e/real`.

### Next steps
1. Give me the notebook folder and run the coverage command; decide on relaxations (still proposals, each needing a safety
   review and a fresh split) only from real counts.
2. Run the Linux commands (or Docker) before the VM; then the one-hour pilot (`--pilot 12`), then the full val-v5 run.

## Phase 5: risk engine and rule-based suggestions

**Status: done on dev; held-out suggestion run NOT executed; Tier 0/1/2, guard, range policy B and controller untouched;
test-v2 and val-v5 sealed and unrun. Nothing was tuned on held-out data.** Pre-registration: `docs/benchmarks/phase5-preregistration.md`
(committed `aa95a21` before any Phase 5 number existed; Amendment 1 written after reading dev run 1).

- [x] 0. Pre-registration (risk classes, margin 0.85, confidence floor 0.30, HIGH_RISK on `expected > headroom`, UNKNOWN never OK,
  time as bucket only, R1-R4, B2 thresholds 20% / 64 MiB, S1-S5, held-out design).
- [x] 1. `nexus/risk.py` (`classify`, `assess`, `RiskReport`); `ResourceSnapshot` gained optional `swap_free` / `rss`. 20 tests:
  zero free RAM, huge swap, cgroup below host RAM, low confidence, guard fallback, no estimate, partly covered cell, non-finite.
  Session prints WARN / HIGH_RISK by default, everything in verbose.
- [x] 2. `nexus/suggestions/` (7 rules, conservative liveness, textual patches that keep comments, magics refused). Refusal battery
  30 cells (all refused), acceptance battery 15 (all accepted with the right label), preserving results verified equal.
- [x] 3. Re-estimation on a virtual state with the frozen models; filters and ranking as pre-registered; hidden candidates kept
  only for evaluation (`keep_hidden`).
- [x] 4. `%nexus status | explain | suggestions | apply <n>` (apply prints, never runs or edits).
- [x] 5. Suggestion benchmark `benchmarks/suggestions/` (split v3: 40 configurations, 21 dev / 19 held-out, sha256 per family,
  digest-checked; held-out access gated and logged to `docs/benchmarks/phase5-heldout-access-log.md`).
- [x] 6. Risk evaluation on dev, stored data only (`python -m benchmarks.risk_eval benchmarks/results/tier1-v3 --out docs/benchmarks/phase5-risk-dev`).

### Risk engine on dev (stored Tier 1 predictions, simulated limits 64 MB - 4 GiB; dev, not validation)
**ERRATUM (2026-11-21, Phase 6b): the numbers in this paragraph were computed on policy-A Tier 1 ranges, not policy B.** On
policy B (`docs/benchmarks/phase5-risk-policyB/`): R1 100% MET, R2 pooled 25.0% but per operation merge 58.8% and read_csv 78.0% > 50%:
**R2 FAILED per operation (merge, read_csv)**; R3 98.6% MET; R4 0 UNKNOWN. **The risk engine therefore does not meet all of its
pre-registered criteria.** Candidate risk-v2 fixes are hypotheses for a fresh split after the held-out runs (dated note in
`docs/benchmarks/phase5-risk-policyB/README.md`). The paragraph below is kept as it was written.
R1 recall 100% (1119/1119, Wilson lower 99.7%) PASS; R2 pooled false alarms 14.0% (per limit 56% at 64 MB, 46%, 41%, 12%, 10%, 5%
at 2048 MB; per op 0-44%, read_csv highest, no op above the 50% bar) PASS; R3 HIGH_RISK precision 98.6% PASS; R4 0 UNKNOWN, 0
missed crashes. Caveats: at 4096 MB there are 0 positives (no claim); numpy.sort has 16 positives; the false-alarm rate is high at
the smallest limits where few points are negative; this is dev data and the single baseline of the existing OOM table.

### Suggestions on dev (`docs/benchmarks/phase5-suggestions-dev/`)
Run 1: S2, S3, S4 FAILED (one `downcast_numeric` on merge: predicted -27% RAM, measured +47%). Fixed by refusing merge for that
rule (Amendment 1). Run 2 (same dev configurations): S1 PASS (0 preserving bugs), S2 PASS (0 of 15 harmful, 0 increases), S3 PASS
(n=11, median |error| 10.0 pp, p90 33.2 pp, bias +7.2 pp), S4 PASS (12 of 15 = 80.0%, exactly at the bar). **These passes follow a fix
made after reading run 1 on the same data.** Honest limits: only 19 of 40 dev cells were risky (pre-registered >= 30 NOT met); 15 shown
suggestions; rule-level claims for avoid_copy (4), downcast (3) and read_csv (6) only; `select_columns` and `key_dtype` have 1 shown
each and their predictions are optimistic (46% predicted vs 13-17% measured), the frozen Tier 0 model overstates column savings.
`text_to_category` produced no risky cell; `delete_unreferenced` produced no suggestion (not measured for peak). Hidden candidates
(filtered out) were not measured beyond those listed.

### Held-out suggestion run (executed afterwards; outcome in "Phase 5b" below)
*Written before the run, kept as it was:* it had not been executed when Phase 5 was committed.
```
python -m benchmarks.suggestions run --heldout --reason "Phase 5 held-out check of the rule-based suggestions (S1-S4)"
python -m benchmarks.suggestions evaluate --heldout --reason "Phase 5 held-out check of the rule-based suggestions (S1-S4)" --out docs/benchmarks/phase5-suggestions-heldout
```
Run it once on the frozen state; afterwards the 19 configurations are dev data. Needs ~3 GB free RAM; ~30 min.

### Next steps
Phase 6 (calibration); a risk validation split on a large Linux machine with positives at 4 GiB+; improve the column-saving prediction
(needs a model change, out of scope here); more risky suggestion cells.

## Phase 5b: consequences of the held-out suggestion check

**Status: the held-out suggestion run was executed once on the frozen Phase 5 state and read (2026-11-18; access log:
`docs/benchmarks/phase5-heldout-access-log.md`). Verdict: S1 and S2 PASSED, S3 and S4 FAILED. The 19 held-out configurations are now dev
data. Tier 0/1/2, guard, range policy B, controller, risk engine thresholds, the 20% / 64 MiB filter thresholds, `test-v2` and `val-v5` are
untouched; the held-out benchmark was NOT re-run and nothing was retuned.** Report: `docs/benchmarks/phase5-suggestions-heldout/suggestions_heldout.md`.

### Held-out outcome, as it came out (pre-registered S1-S4, Part B4)
| criterion | result | verdict |
|---|---|---|
| S1 no `preserving` bug | 0 cases | PASS |
| S2 do no harm (>10% more RAM) | 0 of 12 shown; 0 measured increases among all candidates | PASS |
| S3 predicted vs measured saving (target median <= 15 pp, p90 <= 35 pp) | n=9, signed bias 2.2%, median 5.5, p90 39.0 | **FAIL** (p90) |
| S4 shown with measured saving >= 20% and >= 64 MiB (target >= 80%) | 9 of 12 = 75.0% | **FAIL** |

12 candidates were measured and all 12 were shown (36 cells run, 15 risky). S3 has n=9 because the three `avoid_copy` suggestions have no
predicted saving (see item 3) and are not in it.

### Attribution by rule (per-suggestion table of the report)
Every S3 and S4 failure belongs to one rule, `select_columns`, which produced the three suggestions of the configurations
`downcast_numeric/M1/num8`, `key_dtype/M1/k_wide` (both filed under other rule families by configuration, produced by the
`select_columns` rule) and `select_columns/M2/w6`:

| suggestion (rule `select_columns`) | predicted | measured | error (pp) |
|---|---|---|---|
| downcast_numeric/M1/num8@7.9M | 56.2% | 18.6% | 37.6 |
| key_dtype/M1/k_wide@7.1M | 58.8% | 14.6% | 44.2 |
| select_columns/M2/w6@11.2M | 45.8% | 12.6% | 33.2 |

The other six (all `read_csv_options`) predicted 90.0-91.0% and measured 90.2-96.6% (errors 0.2-5.6 pp). The three `avoid_copy`
suggestions measured 71-83% and have no prediction. All three `select_columns` suggestions measured below the 20% bar, so they are exactly
the three S4 failures. Dev showed the same pattern (predicted 46%, measured 13%; run 2 of Phase 5 above), so the held-out result confirms
a bias that was already visible, it is not a new surprise.

**Post-hoc subset, not a pass.** Without the three `select_columns` suggestions, S3 over the remaining six points (median ~3 pp, p90
~5.6 pp) and S4 (9 of 9 = 100%) would meet the numbers. That subset was chosen after reading the result, so it does **not** count as passing
S3 or S4. The Phase 5 suggestion layer FAILED its pre-registered held-out check; what changes below is the consequence, not a re-score.

### 2. `select_columns` disabled by default (post-hoc decision)
Decision taken after the held-out failure, not pre-registered: `SelectColumnsRule.enabled_by_default = False`. Evidence: dev predicted 46%
vs measured 13%; held-out predicted 46-59% vs measured 13-19% on three suggestions. Enable it explicitly with `NEXUS_ENABLE_RULES=select_columns`,
`%nexus rule enable select_columns` (per session, `%nexus rule disable ...` to undo) or `suggest(..., enable={"select_columns"})`;
when on, its saving figure is an over-estimate (documented in the rule's docstring). The suggestion benchmark worker opts in explicitly so the
stored measurements stay reproducible. Test: `test_select_columns_is_off_by_default_and_opt_in_works`. The rule's safety logic (S1, S5) is unchanged
and passed.

### 3. `avoid_copy`: why no predicted saving, and what the interface says now
`avoid_copy` has no frozen operation model (a copy is not an estimated operation), so its candidate carries `descriptor_saving` (the size of the
avoided copy) and `engine._finish` returns early on that path: it applies only the 64 MiB floor and leaves `saving_frac = 0.0`, never calling
`meaningful()`. So the pre-registered 20%-of-peak condition (B2) was **not applied** to `avoid_copy` or `delete_unreferenced` suggestions: no
before-estimate of the cell's peak exists to take a fraction of. They passed on bytes alone, and the held-out report shows "predicted n/a".
(Amendment 1 said "thresholds still apply"; that was only true for the bytes threshold, which is a gap between the text and the code.) The
measured savings (71-83%) were far above the bar, so no harm resulted here, but the filter was weaker than stated.
Fix without changing a threshold: the interface (`nexus/suggestions/format.py`) now says "no estimate of saving" for every suggestion whose saving is
not a model re-estimate, and names what the number is (the size of the avoided copy; freed headroom for delete). Recorded as Amendment 2 in the
pre-registration. Nothing was re-run.

### 4. `%nexus suggestions` and `%nexus explain`
Both now print, for every suggestion, a line `what changes:` with the plain-words meaning of its label (`SEMANTICS_WORDS` in `suggestions/base.py`),
the existing detail, and either the re-estimated peak with the predicted saving or "no estimate of saving". `%nexus explain` appends the
suggestions of the last cell. Note on the wording: the repository had no pre-defined text for `changes_results`; the wording used is
"the result is not the same as before: later cells that use it, or use what it removes, may fail or give different answers" (tested).
If a different exact wording is required it is one dict entry.

### 5. Probe, not a fix: where is the peak of a merge made? (`docs/benchmarks/probes/`)
`merge_peak_probe.py`, results `merge_peak_probe_results.md` / `.json`. **Hypothesis tested:** the frozen model's column-bytes-proportional saving
overstates because the merge peak has a large width-independent part (join indexers, key factorisation / hash table, selection copies); dropping
columns only removes the width-dependent part. Refuted if the measured saving tracks the dropped share of the bytes.
Setup: template M1 mirrored (left = k, v + payload; right = k, w, x0, x1; every left row matches one right row), 4 column mixes (float6, float2,
int6, mixed with 2 string columns), 0.5/1/2M left rows, right of 1,000 or 500,000 rows, three variants (full, selected inside the measured region,
narrowed in setup), OS peak (median of 3, `nexus.measure`) plus tracemalloc stage peaks and live allocation sites. Only pandas 3.1.1 /
numpy 2.5.5 on the Windows development machine.

Findings (probe, not validated claims):
- The peak did **not** follow the dropped bytes: with 50-90% of the input bytes dropped the OS peak was the same within 0-1% in 20 of 24
  configurations (e.g. 2M rows, 500k right: 80 MiB in all three variants for all four mixes); in the other three (2M rows, right 1,000) the
  selection saved 9% (62 -> 56 MiB) and in the mixed 2M/1,000 case the two measurements were censored.
- tracemalloc places the peak in `pandas.core.reshape.merge._factorize_keys` (hash-table construction and lookup arrays, about 32 + 15 + 15 MiB at
  2M rows, ~40-44 B per left row), identical for all three variants. The result's payload is not what sets the peak here.
- So the hypothesis is **supported** in this regime: the peak is a function of rows, not of the width of the carried columns. The measured
  13-19% saving in the benchmark is not reproduced either (0-9% here).
Limits: probe peaks are 20-88 MiB, below the benchmark's 200+ MiB regime and near the instrument's 64 MiB floor, so differences of a few MiB
are not resolved; only N:1 joins with a unique right key; no duplicate-key (many-to-many) merges, where the result can dominate and the saving
may be real; groupby (the other half of the rule) was not probed; one pandas version.

### 6. Phase 6 inputs (added; the 4b.3 list above stays)
1. **`select_columns` saving model:** the frozen Tier 0 merge / groupby column-saving is too optimistic (46-59% predicted vs 13-19% measured, dev
   and held-out); the probe says the merge peak is row-driven (`_factorize_keys`, ~40-44 B/row) and independent of payload width for N:1 joins.
   Needs a model with a width-independent term and a check on many-to-many joins and on groupby, at >= 200 MiB, before the rule is enabled again.
2. **concat time** (under-predicted, val-v4 0.19x), **groupby / astype time** (over-predicted 3.34x / 1.41x on val-v4): see 4b.3 list.
3. **Category-heavy concat RAM** (23% low, `v4/concat/two_category_heavy`).
4. **`avoid_copy` savings:** no model; measured 71-83% of the peak while the copy's own size is the only number available. Needs an estimate
   of the unmodified cell's peak so the 20% condition can be applied, then a re-check on a fresh split.
5. Make the pre-registered filter apply to descriptor-sized savings (needs item 4) and re-check on a fresh held-out set; the Phase 5 held-out
   set is now dev, so a new suggestion split must be created and frozen before any new claim.

### Next steps
Phase 6 (calibration) with the inputs above; a new frozen suggestion split for any further S1-S4 claim.


## Phase 6: calibration (time models, time ranges, two RAM gaps), freeze

**Status: done on DEV only (LOCO; one Windows laptop on mains power); frozen as tag `models-frozen-v1`. test-v2 and val-v5
sealed and unrun; no real notebook or real-notebook data used. Machine transfer is untested until val-v5.** Pre-registration
`docs/benchmarks/phase6-preregistration.md` (commit `a34747a`, before any Phase 6 number) and Amendment 1 (commit `b385fe1`,
power state; written after the first comparison was read, disclosed there). Results: `docs/benchmarks/phase6/README.md`,
full tables `docs/benchmarks/phase6/phase6_dev.md`, probes `docs/benchmarks/phase6/probes/`.

- [x] 0. Pre-registration: targets (a)-(d), LOCO protocol, split-conformal ranges, min. 8 configurations, learned-model
  margin 10%, failure statement, machine-transfer risk. Amendment 1: every prediction used for fitting is made with a profile
  measured on mains; F recomputed on a mains v2 profile; clarifications (configurations with valid points; policy B applied to
  the stored F's policy-A RAM rows; one candidate for both tiers; learned model must pass at both tiers).
- [x] 1. Machine profile format 3 (`nexus.machine`, `nexus.calibrate`, 41 s): curves over the working set (cold copy and
  streaming read 256 KiB-256 MiB; factorize per row vs distinct keys 100-3M, int and str; object take vs distinct objects;
  argsort / np.sort per n log n vs n; float64 / float32 BLAS vs product size) plus first touch, page-fault cost, CSV field
  costs by type, astype-to-str by source, single-thread BLAS. Measured only on dedicated primitives. Provenance: content id,
  versions, power state at start and end (the CLI refuses to measure on battery). Required input: without a calibrated
  format-3 profile the generic profile (reference machine x2 slower) is used and estimates carry "uncalibrated machine" and
  ranges widened x3. A repeat measurement agreed within a median ratio of 1.00 (worst curve point 0.77 / 1.25).
- [x] 2. Derived time models (`nexus/models/_time.py`); every mechanism probed first (`probes/README.md`, re-run on mains):
  hash cost by distinct count (int 4.7 -> 74 ns/row, str 27 -> 407 ns/row, G = 100 -> 3M) plus the G log G sort of the uniques
  in groupby / astype("category") (explains groupby 2.6x over and astype under at high cardinality); concat of categoricals with
  DIFFERENT categories materialises `str` pointers (12-14 ns per row and column vs < 1 ns; the category-heavy concat was 5-11x
  under), with an object-take cost that follows the distinct objects (5 -> 65 ns); read_csv per field by type (9-14 ns numeric,
  154-188 ns text or dates; dates are read as text); astype(str) by source (float 368 ns, datetime 177, int 92-97); float32 BLAS
  2.6-3.0x float64. Tier 0 (distinct counts unknown) uses the geometric middle of the extremes. Only the per-operation residual
  was fitted (LOCO).
- [x] 3. Ranges: LOCO split-conformal on log residuals per operation and tier (90% nominal); generic band (95%, flagged) for
  matmul (6 configurations) and numpy.sort (3 with valid time); Tier 2 by normalised scores of its own range.
- [x] 4. Learned residual (gradient-boosted trees, scikit-learn extra): **NOT included** (Tier 1 median log error -7.2%, needs
  -10%; it passed at Tier 0 with -15.6%). Negative result documented.
- [x] 5. RAM: policy B unchanged. Derived and adopted: concat Tier 1 for categoricals with differing categories
  (`moved - codes + 8 n c + 8 n`; OS-peak probe 539 / 831 MiB measured vs 554 / 858 derived; dev Tier 1 median error 7.7% ->
  5.8%, p90 15.7% -> 10.7%; above_high stays 0). Not derived, documented: the select_columns saving (probe: 5% for a unique N:1
  join whose peak is key factorisation, 66% with fan-out, 56% with half overlap; the suggestion re-estimate uses the Tier 0 merge
  model, which charges a left copy; the N:1 probe peaked at 184 MiB, just under the 200 MiB bar). Nothing re-enabled.
- [x] 6. Calibration artifact `src/nexus/calibration/calibration-v1.json` (format 1; provenance: data hashes, git commit
  `b385fe1` = the parent of the commit that ships it, machine profile id `987c455be3cc`, versions, date, 41 fitted parameters
  each with what it was fitted on); loader `nexus/timecal.py` (absent / unreadable / other format: x3 widened band + "no time
  calibration"; pandas outside 3.1: warning once, x2 widened, "unvalidated pandas version"); `nexus-calibrate` CLI (refits from a
  results folder and applies the pre-registered range fallback mechanically; `--local` is opt-in and local only).
  Pandas-internals probe tests (`tests/test_pandas_mechanisms.py`, marker `pandas_mechanisms`: merge left-copy elision, concat of
  categoricals, sorted uniques, read_csv dates as text, hash cost vs distinct count, presized-table page residency, object-take
  cost) and a CI job over pandas 2.0.3 / 2.1.4 / 2.2.3 / 3.0.* / 3.1.1 (only 3.1.1 validated; the rest informational). **Run here
  only on pandas 3.1.1 (9 / 9 pass); no result is claimed for the other versions.**
- [x] 7. Dev evaluation (`python -m benchmarks.phase6_eval --frozen benchmarks/results/tier2-dev-b --derived
  benchmarks/results/phase6-dev-mains --frozen-mains docs/benchmarks/phase6/f_mains.csv --out docs/benchmarks/phase6`).
- [x] 8. Freeze: tag `models-frozen-v1`, `docs/benchmarks/frozen-manifest.md`; held-out paths call `benchmarks.frozen.require_frozen`.

### Pre-registered targets on dev (LOCO; F = frozen models recomputed on a mains profile)
* **(a) time estimates: MET** by the selected D+m. Tier 1: median rel. error 52% -> 25%, p90 146% -> 89%, median log error 0.64 ->
  0.25, same bucket 153 -> 181 points, within one 100% -> 100%. Tier 0: median 53% -> 33%, p90 164% -> 194% (worse), same bucket
  151 -> 154, within one 100%. **Against the stored F (old profile, power unknown) neither D nor D+m met (a) at Tier 0 (159 vs
  158 / 154 same-bucket points) and F would have been kept; the outcome rests on Amendment 1.**
* **(b) ranges: PARTLY MET.** Tier 1 coverage after: astype 95%, drop_duplicates 95%, merge 92% (met); groupby 87%, read_csv 82%,
  sort_values 77%, concat 75% (not met). Tier 0: astype, drop_duplicates 95%, groupby 94%, merge 92% (met); read_csv 82%,
  sort_values 77%, concat 75% (not met). Fallback as pre-registered: concat and sort_values (both tiers) and read_csv Tier 1 keep the
  0.25x-4x band around the calibrated expected value (flag "time range not calibrated"); groupby Tier 1 and read_csv Tier 0 keep
  the conformal range. Generic band: matmul, numpy.sort 100%. Width: Tier 1 3.85 -> 2.10, Tier 0 3.85 -> 4.57. Overall Tier 1
  coverage 89%; 11 of 109 configurations have every point outside the range (listed in the report). Tier 2: coverage 80% -> 93%
  (astype 92%, groupby 93%, merge 95%, read_csv 93%), at a width cost (astype 1.3x -> 11x, groupby 1.3x -> 36x, merge 78x ->
  97x; read_csv 7.3x -> 1.9x); drop_duplicates / sort_values / concat Tier 2 ranges explode (> 2,500x) but are not used at run time.
* **(c) RAM: MET.** above_high 0% at both tiers, per point and per configuration, before and after; coverage unchanged; width
  unchanged except concat Tier 1 1.00 -> 0.85 and merge Tier 1 5.13 -> 5.23 (see regressions).
* **(d) regressions, each with a decision** (vs the mains F):
  - Tier 0 p90 rel. error: astype 102% -> 226%, drop_duplicates 80% -> 171%, read_csv 178% -> 770%, sort_values 94% -> 372%,
    merge 68% -> 82%, ALL 164% -> 194%; Tier 0 median: groupby 82% -> 86%, merge 27% -> 39%; Tier 0 same bucket: groupby 23 -> 15,
    merge 21 -> 20, sort_values 20 -> 18. **Keep**: the candidate is selected for both tiers by the pre-registered rule; the cause
    is Tier 0's geometric middle over unknown distinct counts / column types, now a per-row cost spanning 10-20x (Tier 0 is the
    fallback tier; Tier 1 is what the session runs).
  - sort_values Tier 1 p90 94% -> 372%, same bucket 20 -> 18; concat Tier 1 median 35% -> 38%. **Keep, range falls back to the
    band**; the sort cost of object-heavy frames is not derived (the take of object columns uses the unknown-distinct middle):
    Phase 7 input.
  - read_csv Tier 0 / Tier 1 coverage 94% -> 82%. **Tier 1: band kept (coverage 100%); Tier 0: conformal kept** (band 76%).
  - RAM merge Tier 1 width 5.13 -> 5.23: **keep**; one point whose Tier 1 statistics now finished inside the budget, no model change.

### What was fitted, on what; what was derived; what stays uncalibrated
* Fitted (all on the dev split, 211 valid time points in 109 configurations per tier, LOCO for every reported number; shipped
  values on all configurations): one time residual per (tier, model) (D+m; values 0.32-2.8 at Tier 0, 0.70-1.70 at Tier 1, 1.0 for
  matmul / np_sort), conformal log-quantiles per (tier, model) with >= 8 configurations, the generic band per tier, the Tier 2 score
  exponent per operation (148 accepted fits in 89 configurations) and its generic value. Listed with sizes in the artifact
  (`fitted_parameters`).
* Derived (no fitted constant): every time term of `_time.py` (machine primitives at the working set the step touches); the concat
  Tier 1 RAM for differing categories.
* Not calibrated: time ranges of concat and sort_values (both tiers) and read_csv Tier 1 (band kept by the pre-registered rule);
  matmul and numpy.sort (generic band); the select_columns saving model; Tier 2 RAM; every other RAM model (policy B as before);
  everything off this machine.

### Found on the way (outside this phase's scope; not fixed)
* **Phase 5 risk evaluation used policy-A Tier 1 RAM ranges.** `benchmarks/risk_eval.py` replays the stored `tier1-v3` rows, whose
  Tier 1 `ram_high` is the model's own range for 194 of 323 points (policy B is applied in the pipeline since `c95f674`, after that
  run). The R1-R4 figures reported in Phase 5 as "policy B" are therefore policy A; under B, `high` is larger (recall can only rise,
  false alarms too). Needs a re-run of `risk_eval` on policy-B rows (e.g. `phase6-dev-mains`) before any claim.
* The stored F of 2026-11-16 was made with a profile 30-40% slower than this machine on mains (power state unknown).
* The concat Tier 1 statistic exceeds the 250 ms budget at 10M rows with 3 x 500k categories (Tier 0 kept there).

### Held-out runs (NOT run): exact commands; any model change after the freeze invalidates their held-out status
val-v5 (Linux VM, >= 32 GB; `docs/benchmarks/val-v5-linux-runbook.md`):
```bash
git checkout models-frozen-v1 && python -m benchmarks.frozen check     # must report no problems
pip install -e ".[dev,bench]" && nexus-calibrate-machine --force       # on the VM, mains / server power
CAP=24
python -m benchmarks plan --suite full --splits val-v5 --mem-limit-gb $CAP --max-size 400000000
nohup python -m benchmarks full --splits val-v5 --tiers 0,1,2 --out benchmarks/results/val-v5 \
      --mem-limit-gb $CAP --max-size 400000000 --require-calibrated --no-report > val-v5.log 2>&1 &
python -m benchmarks evaluate benchmarks/results/val-v5 --val \
      --reason "held-out check of models-frozen-v1 (Phase 4d S1-S5; Phase 6 time calibration)"
```
Phase 8a real-notebook test: **no accuracy harness exists yet.** The available held-out command is the static coverage study,
which now refuses to run unless the tree is the frozen stack and records the tag commit:
```bash
git checkout models-frozen-v1 && python -m benchmarks.frozen check
python -m benchmarks.realworld.coverage <folder of .ipynb> --heldout --out docs/benchmarks/phase8a/coverage
```
Any Phase 8a measurement harness written later must call `benchmarks.frozen.require_frozen()` before reading real data; it is a
code change, so it cannot be added after the tag without a new freeze. **Any model change after the freeze invalidates the
held-out status of both runs** (a new freeze, a new tag and new held-out groups would be needed).

### Next steps
1. Run val-v5 on the Linux VM from the tag (commands above); read once.
2. Write the Phase 8a accuracy harness (calls the freeze guard) BEFORE touching real notebooks; freezing it means a new tag.
3. Phase 7 inputs: sort_values time of object-heavy frames; Tier 0 time where distinct counts are unknown; a cheaper concat
   category comparison; the select_columns re-estimate at Tier 1 (left-copy elision); re-run the Phase 5 risk evaluation on
   policy-B rows.

## Phase 6b: housekeeping around the freeze

**Status: done. The tag `models-frozen-v1` (commit `c3e3ee0`) is unchanged; no model, calibration artifact, profile format,
policy or threshold changed; test-v2, val-v5 and real notebooks untouched.**

- [x] 1. **Freeze guard narrowed to a manifest-based check** (`benchmarks/frozen.py`): it compares the SHA-256 (LF) of every
  file that defines the predictions with the tag's own copy and aborts if one differs, is missing, or a new file matches a
  frozen pattern (tests for all three). Frozen: the operation models, analyzer, state, Tier 1 statistics, registry, pipeline,
  deadlines, guard, range policy, controller and Tier 2, risk engine, time calibration, time buckets, machine profile format
  and measurement, the calibration artifact and reference profile, the suggestion thresholds (38 files at the tag). **Added on
  2026-11-21 at the user's request:** `src/nexus/measure.py` and `tests/test_measure_validation.py` (40 files). Outside:
  docs, benchmarks and evaluation scripts, CI, `.gitignore`, other tests, `pyproject.toml`, UX modules, the Phase 8a harness.
  `docs/benchmarks/frozen-manifest.md` lists the files and hashes and records that the scope changed after the tag;
  `git diff models-frozen-v1` on all 40 files is empty. **A new evaluation harness (Phase 8a) no longer needs a new freeze.**
- [x] 2. `.gitignore`: notebooks ignored except `examples/**/*.ipynb` (commit `c438517`); the guard passes.
- [x] 3. `nexus-calibrate-machine` now runs `nexus/calibrate_cli.py` (the frozen `calibrate.py` is unchanged): refuses only on
  positively detected battery (unless `--allow-battery`), warns and records `power: unknown` without a battery sensor or on a
  sensor error (VMs, servers); 10 tests with faked power sources. Benchmark runs record `power` in `meta.json`.
- [x] 4. **Risk engine re-evaluated on policy-B ranges** (`docs/benchmarks/phase5-risk-policyB/`): R1 recall 100% MET; R2 pooled
  false alarms 25.0% (<= 30%) but **R2 FAILED per operation: merge 58.8%, read_csv 78.0% (> 50%)**; R3 HIGH_RISK precision
  98.6% MET; R4 0 UNKNOWN MET. **The risk engine does not meet all of its pre-registered criteria.** Errata added to the Phase 5
  section and the Phase 5 pre-registration. Candidate risk-v2 fixes (incl. a per-operation policy for read_csv) are dated
  hypotheses for a fresh split AFTER the held-out runs, never on held-out data.
- [x] 5. **Tier 1 fallback rate under scarce CPU** (`docs/benchmarks/phase6b/fallback_rate.md`, `benchmarks/fallback_rate.py`;
  information only): on the 249 dev points of the six operations with Tier 1 statistics, fallbacks to Tier 0 on the 250 ms
  budget: 16 cores 1 (0.4%); 2 dedicated cores 2 (1%); 2 cores with 2 competing busy loops 28 (11%: concat 41%, merge 22%,
  drop_duplicates 19%, others 0%). The merge fallbacks are the fan-out / low-overlap joins, where Tier 0's median RAM error is
  55% vs 8% at Tier 1 (policy B keeps the high). **Confounded: the 2-core run was on battery and the contended run started on
  battery and ended on mains (run at the user's instruction).**
- [x] 6. **Phase 6 pre-registration Amendment 2** (commit `9fa3b8f`, before any VM run): val-v5 time on the Linux machine is a
  transfer test; success = time bucket within-one >= 95%; same-bucket, errors and bias reported without a bar; bias shifts
  reported, not corrected.

### Needs a decision
1. **R2 failed:** keep the frozen risk engine (and say so in every report) or plan risk-v2 on a fresh split after the held-out
   runs; any change is a new freeze.
2. Whether the Tier 1 budget (250 ms, frozen) should become CPU-aware in a later version: under contention 22% of the merge
   points lose the statistics that carry their RAM estimate.
3. Phase 8a: write the accuracy harness (now outside the freeze) before any real notebook is opened.
