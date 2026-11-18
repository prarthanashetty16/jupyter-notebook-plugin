# Tier 2 evaluation (Phase 4c) - DEVELOPMENT data only

Every number here is dev (dev + exposed-v1 + val-v3 + val-v4); nothing is held out and no validation split
exists. The interpretation and the design decisions are in the "Phase 4c" section of `docs/PROGRESS.md`.

* `config-a/` - 4% of the rows, at most 250k (declared first); all 360 dev points.
* `config-b/` - 10% of the rows, at most 1M (the default after this evaluation); all 360 dev points.
  Each holds `tier2_vs_tier1.md` (availability, RAM and time accuracy for Tier 1 / Tier 2 / `hull` / `geomean`,
  overhead, where it pays off, the merge residual points, the worst cases) and `points_tier2.csv` (one row per
  point with the dry run's reason, fits and overhead).
* `probes/p_sample_pitfalls.py` (+ `.out`) - key layout (random vs sequential keys), the presize cap and
  cold-start effects of samples (run under configuration A sizes).

Reproduce (nothing else running; ~35 min per configuration):

```
mkdir -p benchmarks/results/tier2-dev && cp <dev results with Tier 0/1 predictions> benchmarks/results/tier2-dev/
NEXUS_DRYRUN_FRACTION=0.04 NEXUS_DRYRUN_ROW_CAP=250000 \
  python -m benchmarks full --splits dev --tiers 2 --out benchmarks/results/tier2-dev --mem-limit-gb 2.5 --max-size 10000000 --no-report
python -m benchmarks.tier2_eval benchmarks/results/tier2-dev --out docs/benchmarks/tier2-dev/config-a
```
(default sizes = configuration B). The evaluation escalates every qualifying cell (`tier2_escalate="always"`); the
default session rule (`dryrun.should_escalate`) escalates far less often.
