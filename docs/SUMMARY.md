# NEXUS project summary

Jupyter users often run cells that allocate much more memory or take much longer than expected. NEXUS is an IPython
extension that analyzes a cell before it runs, inspects the data already in the kernel, and estimates peak RAM and
coarse wall time. It combines closed-form operation models, bounded statistics, an optional safe dry-run tier, a
cell-level peak model, a resource-aware risk check, and rule-based suggestions that users review themselves.

The project has built a working research prototype and an evaluation harness that compares estimates with OS-measured
peak RAM and elapsed time. The frozen v4 development evaluation covered 14 of 75 operation-bearing cells (18.7%),
below its preregistered 55% target. Its optimistic static coverage ceiling was 21 of 75 (28.0%). In a separate
multi-statement held-out group, 22 fully covered cells had no above-high cases; the one-sided 95% upper limits were
still about 12.7% of cells and 23.8% of configurations, so this is not proof of a generally safe bound.

The project is intentionally cautious: unsupported operations are left without estimates, partial cells show a lower
bound only, and suggestions are never applied automatically. Important limitations are frequent Tier 1 deadline
fallback on large inputs, time predictions that vary with the machine, errors in several held-out multi-statement
groups, one developer laptop, and mostly synthetic data. The Phase 8a notebook accuracy results were inconclusive
because there were too few valid points; the fresh Phase 8b notebook evaluation has not been run.

Future work should improve runtime operation coverage, make statistical analysis more deadline-stable, and evaluate
paired frozen versions on a broader, license-checked set of public notebooks. Any new model should be derived from
library behavior, tested with isolated probes, and checked on a fresh preregistered group.

Sources: [Phase 8 v4 manifest and limitations](benchmarks/frozen-manifest.md),
[Phase 8 coverage ceiling](benchmarks/phase8/coverage_ceiling.md),
[v4 multi-statement report](benchmarks/phase8/multicell_v4_heldout.md),
[Phase 8a report](benchmarks/phase8a/report.md), and [full evaluation](EVALUATION.md).
