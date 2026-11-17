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

**Status: implemented and evaluated on dev. NOT yet validated: `val-v3` has not been run or looked at.**
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
