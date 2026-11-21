# Phase 8a harness validation (synthetic notebooks only; no real notebook opened or run)

Harness: `benchmarks/realworld/run_notebook.py`; synthetic notebooks: `benchmarks/realworld/synthetic.py`; checks:
`tests/test_realworld_harness.py` (8 tests, all passing on Windows 11, mains power, 2026-11-22). Manual CLI run of the six
notebooks: outcomes below. Records hold cell hashes, operation names, shapes / dtype counts and numbers only (a test asserts
that no cell code or error message appears in them).

| synthetic notebook | what it contains | what the harness must record | result |
|---|---|---|---|
| `syn_alloc` | a 400 MiB array; then `del` + a 100 MiB array; then an 800 MiB array | valid 400 MiB and 800 MiB within 10%; the middle cell CENSORED (below the historical peak / floor), never zero | 400.0 MiB and 800 MiB valid; middle censored; sampler <= OS peak |
| `syn_ops` | groupby, merge, astype, sort_values, drop_duplicates, concat, to_csv, read_csv on generated frames | a primary (Tier 2 controller) and a secondary (Tier 0) estimate, risk class and suggestions per cell; no code in the log | all recorded; concat of the same frame twice gets no estimate (the model needs two distinct frames: a real limitation, kept) |
| `syn_fail` | a failing cell, a `!` shell cell, a normal cell | error type only (`ValueError`), shell cell skipped (never executed), run continues | as expected |
| `syn_watchdog` | a 1.6 GiB allocation under a 700 MiB cap | kernel killed, RAM actual = observed peak as a LOWER BOUND, notebook stopped | as expected |
| `syn_timeout` | a 30 s sleep under a 3 s cell timeout | timeout recorded, no time actual, notebook stopped | as expected |
| `syn_consecutive` | six failing cells | stop after 5 consecutive failures | as expected |
| refusals | battery power; a frozen file differing from the tag | `SystemExit` before anything is written; `NotFrozenError` naming the file before anything is written | as expected (tests) |

Known limits of the harness (stated before the real run):
* Windows' peak counter cannot be reset, so only cells that raise the kernel's historical peak get a RAM actual: in a long
  notebook most cells after the first large allocation are CENSORED. On Linux the counter is reset per cell.
* The 2 ms sampler under-reads short peaks (376 vs 400 MiB on `syn_alloc`); it is only a cross-check and a watchdog.
* One run per cell (no repeat spread); the first read of a file is cold, later reads warm.
* The kernel is an IPython `InteractiveShell` in a spawned process, not an ipykernel (not installed); display / widget
  output is discarded.
