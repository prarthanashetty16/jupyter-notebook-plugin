# Memory-pressure check of the time measurements (Phase 4a, step 0)

Question: are the super-linear time slopes at 10M rows (1.3-1.5 on a log-log plot of time vs rows,
against 1.0-1.05 modelled) caused by the machine paging, i.e. are they an artifact of the 10M-row
points running under memory pressure?

## Instrument

`nexus.measure` now records, per run, the system's **available RAM at the start** and its minimum
while the operation ran, the child's **page faults** (all, and major ones on Unix) and the **rise of
swap/pagefile use**. The runner stores them in `actuals.csv` (`avail_start_bytes`, `avail_min_bytes`,
`page_faults_all`, `major_faults_all`, `swap_rise_all`). `python -m benchmarks.pressure <dir>`
screens a results directory. A run is **suspect** when (rules fixed before looking at the data):
available RAM at start or at its minimum was below the operation's own footprint (baseline + peak)
plus 1 GiB; or swap use rose by more than 64 MiB; or the child took more than 3x the page faults its
footprint explains (one soft fault per 4 KiB page); or (Unix) any major fault.
**Limit:** Windows (this machine) has no per-process hard-fault counter in psutil, so paging could
only be seen through available RAM, pagefile use and the soft-fault ratio.

The original full run (`benchmarks/results/full`) was recorded before this instrument existed, so
it cannot be screened retroactively. The points were therefore **re-measured** in three batches, on
the same machine, from the same cached inputs:

| session | scope | available RAM at start | points |
|---|---|---|---|
| 1 | drop_duplicates, sort_values, concat (all scenarios, all sizes) | 2.0-3.9 GiB | 46 |
| 1b | groupby, astype, merge, read_csv, np.sort, matmul (all scenarios, all sizes) | 3.3-4.8 GiB | 78 |
| 2 | the 6 flagged scenarios again | 3.3-5.0 GiB | 18 |

## Results

* **Swap/pagefile use never rose** (maximum rise 0.0 MiB at all 142 points); available RAM never fell
  below 876 MiB (lowest in session 1: drop_duplicates mixed, 10M rows; below 2.6 GiB never in
  session 2).
* 13 of the 124 points of sessions 1/1b were flagged, **12 of them among the 33 points at 10M rows
  or above a 1 GiB footprint, all in drop_duplicates, sort_values or concat** (session 1, measured
  while 2-4 GiB were free); none of the 78 groupby, astype, merge, read_csv, np.sort or matmul
  points was flagged. Reasons (a point can have several): available RAM below footprint + 1 GiB
  (12 points), available RAM at start below it (6), soft-fault ratio above 3x (4). In session 2,
  3 of the 6 re-measured 10M points were still flagged: sort_values/by_str on available RAM, and
  drop_duplicates mixed_dup0 and numeric_dup50 on the soft-fault ratio, which is a property of its
  hash-table allocation pattern (2-4 faults per page at every size, including 1M rows), not a
  pressure signal by itself.
* **RAM is not affected**: every re-measured RAM value (123 points of sessions 1/1b with a valid
  value) is within -1.1%/+3.7% of the original run (median 1.000), flagged or not. The RAM models were derived from these values and from isolated
  probes, which are independent of the machine's state.
* **Time is affected, mildly and mostly by ambient state**: session 1 was a uniform 1.28x slower than
  the original run at every size (median 1.24x below 3M rows, 1.29x at and above), for flagged and
  unflagged points alike, so most of it is not memory pressure. 10M-row points (seconds):

| point | original full run | session 1 (avail min MiB) | session 2 (avail min MiB) |
|---|---|---|---|
| drop_duplicates/mixed_dup0 | 15.83 | 17.99 (876, suspect) | 14.47 (3122, suspect: faults) |
| drop_duplicates/numeric_dup50 | 11.88 | 16.89 (1281, suspect) | 12.41 (3621, suspect: faults) |
| drop_duplicates/strings_dup50 | 15.01 | 19.76 (1985, suspect) | 14.57 (3708) |
| sort_values/by_int | 3.16 | 4.85 (1704, suspect) | 3.37 (3178) |
| sort_values/by_str | 12.71 | 18.58 (1695, suspect) | 14.93 (2603, suspect) |
| concat/mixed | 1.77 | 2.17 (2335, suspect) | 2.47 (3120) |

  When more RAM was free (session 2) the 10M times fall back to the original run's (sort by_int 3.37
  vs 3.16 s; session 1 under low RAM 4.85 s). The excess at 10M in session 1 beyond the common
  1.28x is roughly +15%. Between unflagged sessions the same point still differs by up to 40%
  (concat/mixed 1.77 vs 2.47 s): **absolute times are only reproducible to about +-40% across
  sessions on this machine**, so no time model should be judged on a single run.

## Verdict on the slopes

**The super-linear slopes do not disappear when suspect points are excluded.** Using only points
with no pressure signal (`pressure_slopes_session*.csv`, `slope_clean`): sort_values 1.30-1.58,
drop_duplicates 1.16-1.37, concat 0.83-1.74 (two-point fits; 1M-3M pairs are never suspect). In
session 2, three sizes entirely unflagged: sort_values/by_int 1.38, drop_duplicates/strings 1.37.

An independent check without any memory pressure (`probes/p_cache.py`, in process, arrays up to
61 MiB, 4 GiB free): per-element time rises with n for the primitives themselves,
`np.argsort` 21.5 -> 91.7 ns/element from 125k to 8M rows (slope 1.34; still 1.27 -> 4.0 after
dividing by log2 n), `Series.duplicated` 10.5 -> 45.4 ns (slope 1.35), a random gather 0.9 -> 14.7
ns (slope 1.61). The super-linearity is a cache/TLB-hierarchy effect of the working set growing,
not paging and not a different complexity class (sort is already modelled as n log n, which
accounts for ~1.05 of the 1.3-1.5).

**Consequence (step 6):** the time models were left unchanged. The measured slope needs a
per-element cost that depends on the working-set size (a cache model with machine-specific
breakpoints), which is machine calibration (Phase 6), not a derivation from pandas' algorithms.
Fitting an exponent to three sizes would be exactly the tuning this phase forbids.

Files: `pressure_session1.csv`, `pressure_session2.csv` (per point), `pressure_slopes_session*.csv`,
`pressure_10M_three_sessions.csv`.
