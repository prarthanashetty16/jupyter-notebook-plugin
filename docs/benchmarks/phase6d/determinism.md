# Tier 1 determinism (Phase 6d; information only, nothing changed)

30 stored dev points (<= 3,000,000 rows; 5 per operation with Tier 1 statistics), 10 repeats each, each a fresh prediction process (the benchmark's worker), mains power (power seen: ['mains']). Spread = (max - min) / median over the repeats of one point; CV = std / mean. Raw rows: `determinism.csv`.

| op | points | points whose fallback differs | median spread expected | max spread expected | median spread high | max spread high | median spread time | max spread time | median spread sample |
|---|---|---|---|---|---|---|---|---|---|
| astype | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| drop_duplicates | 5 | 0 | 0.00% | 1.01% | 0.00% | 0.00% | 0.00% | 0.36% | 12.25% |
| groupby | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| merge | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |
| pandas.concat | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.02% | 0.23% | - |
| pandas.read_csv | 5 | 0 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% |

Points whose Tier 0 fallback differs between repeats: 0 of 30

## Proposal for v3 (not implemented)

Seed the statistics sampler from the cell hash and fix the sample size per operation (independent of the time budget; the budget would only decide between that sample and no statistics). Repeated analyses of the same cell on the same data would then give identical estimates; the remaining variation would be the budget decision itself. This changes frozen files (`stats.py`, the models' Tier 1 code): a v3 freeze and a fresh evaluation are needed.

## Reading (written after the run)

- All 300 predictions ran (`ok`), all on mains. **No point's Tier 0 fallback differed between repeats (0 of 30).** The
  statistics took at most 0.17 s per run (merge / concat; median 0.02-0.14 s by operation), well inside the 250 ms budget at
  these sizes.
- RAM `expected` and `high` were identical across the 10 repeats for every point except one drop_duplicates point (spread of
  `expected` 1.0%); `high` never moved (policy B: the high is Tier 0's, which uses no sample). Time moved by at most 0.36%.
- The sample size does vary between repeats for drop_duplicates (median within-point spread 12%; 25.5k-200k rows overall),
  merge (one point) and astype (fixed per point here), but the estimates barely react to it.
- **Not covered:** sizes above 3M rows. The Phase 6c regression differences were traced to budget fallbacks at 10M rows,
  where the statistics come close to the budget; this check says nothing about that regime. The next measurement to make
  (information only) is the same repeat at 10M rows.
- The v3 proposal above stays a proposal; nothing in the sampler was changed.
