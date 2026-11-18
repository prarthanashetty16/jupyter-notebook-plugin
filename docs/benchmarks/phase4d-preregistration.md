# Phase 4d pre-registration: the adaptive controller and its success criteria

Written and committed BEFORE any number is computed in Phase 4d on any data. Frozen inputs: Tier 0, Tier 1,
the guard, range policy B (Tier 1 low / expected, Tier 0 high) and the Tier 2 estimator and its default
sample sizes (10% / 1M rows). The rules are chosen from principle and from the Phase 4c dev findings that are
already in `docs/PROGRESS.md` and `docs/benchmarks/tier2-dev/`; none is tuned on dev points. `test-v2` stays sealed.
The held-out check is `val-v5`, created in this phase and **not run** by me.

## Rules (`nexus/controller.py` implements exactly these)

**R0 Inputs and budgets.** The controller receives the cell, the namespace, the Tier 1 estimate (after guard and
policy B), the Tier 0 estimate and the machine's effective free RAM (`ResourceProbe`). Tiers 0-1 keep their 250 ms
analysis budget. The controller has its own total budget of **60 s** (`CONTROLLER_BUDGET_S`) for everything it
does beyond Tier 1; each sample run has a hard timeout of min(30 s, the budget left) and a memory cap (R3). It never
raises, never mutates user objects, and on ANY problem keeps the Tier 1 estimate and records why.

**R1 RAM.** Tier 1 (policy B) is the RAM estimate. A Tier 2 RAM fit is a cross-check that can only RAISE the high
bound: `high_final = max(high_tier1, expected_tier2)`. `low` and `expected` are never changed, no bound is ever
lowered. (Reason: Tier 2's RAM was worse than Tier 1 on every operation Tier 1 models structurally, but it saw the
non-unique-right merge residual that Tier 1 misses; a Tier 2 central estimate above Tier 1's whole range is a
contradiction worth surfacing, and a false alarm costs width, not safety.)

**R2 Time.** Only for operations whose Tier 2 time clearly beat Tier 1 on dev:
* `read_csv`, `astype`, `merge`: if the Tier 2 time fit was accepted, the time range is Tier 2's
  (low, expected, high).
* `groupby`: Tier 2's time range, with the high bound multiplied by **M = 1.5**. Derivation: on the development data
  (Phase 4c, configuration B, 14 accepted fits) Tier 2's groupby time bias (median expected / actual) is **0.667**, and
  43% of its points were above `high`; the safety multiplier is the reciprocal of that bias, 1 / 0.667 = 1.5, rounded
  to one decimal. Nothing else was fitted; `low` and `expected` are Tier 2's.
* all other operations (drop_duplicates, sort_values, concat, matmul, numpy.sort): time stays the Tier 0 / 1 estimate,
  presented as the coarse bucket (`nexus.timebuckets`). Tier 2's time was not better there (drop_duplicates bias
  0.70, matmul 0.62, sort_values above_high 15%).
The user-facing time is always the bucket plus the measured variation.

**R3 Escalation.** The controller dry-runs (Tier 2) a cell only if ALL hold:
1. at least one trigger: (a) Tier 1 RAM `high` > 50% of the effective free RAM; (b) Tier 1 expected time >= 5 s;
   (c) Tier 1 fell back to Tier 0 because the Tier 1 time budget was exhausted AND the Tier 0 RAM range is wide
   ((high - low) / expected >= 1.0), i.e. the statistics did not fit the analysis budget;
2. the cell passes the Tier 2 safety analyzer (`dryrun_safety.analyze_safety`) and its operation matches the
   recipe (unknown means unsafe);
3. the **dry-run memory budget** holds: budget `B = 0.25 x effective free RAM`; the dry run's expected need is
   `E = 200 MiB + f x (input bytes + Tier 1 RAM high)` with `f = min(0.10, 1,000,000 / rows)` (the sample fraction,
   `dryrun_sample.largest_sample`) and 200 MiB for the child interpreter with pandas; escalate only if `E <= B`.
   The child's RSS cap is `min(B, 8 GiB)`. **Fail closed**: if free RAM is unknown, or `E > B`, no child is started,
   the Tier 1 estimate is kept and the reason ("free RAM too low", "dry-run memory budget") is recorded.
No other trigger exists; in particular a wide range on a short cell does NOT escalate (a dry run costs ~2 s whatever
the cell does; on dev it was cheaper than the real run for 13% of the points).

**R4 Record.** Every Estimate the controller returns says in `note` which tier produced it and why
("Tier 1 kept: no trigger", "Tier 2 time used (merge)", "Tier 1 kept: fail closed: free RAM too low", ...), and
`diagnostics["controller"]` holds the triggers, the memory-budget figures, the rules applied and the dry-run overhead.

## Success criteria on held-out data (`val-v5`, Linux >= 32 GB, valid points only)

* **S1 RAM:** the controller's final RAM `above_high` <= **3%** per point and <= **5%** per configuration.
* **S2 time:** the expected time bucket (`nexus.timebuckets`) is within one bucket of the measured one for >= **95%**
  of the valid time points (all points, escalated or not).
* **S3 overhead:** for cells escalated by trigger (b), the dry run's wall time is <= **50%** of the cell's real run
  time at the median and <= **100%** at the 90th percentile; cells escalated only by (a) have no ratio criterion but
  must finish inside the 60 s budget.
* **S4 no harm:** controller above_high <= Tier-1-alone above_high on the same points; no RAM bound is ever lowered
  (also enforced by a test).
* **S5 safety:** zero kernel-affecting events in the harness (exception out of the controller, a child left running,
  a mutated input); every fail-closed or unsafe case carries a recorded reason.
* **Minimum evidence:** at least **20** points escalated by (a) or (b) are needed to judge S3 and the time claims
  for escalated cells. With fewer, those claims are INCONCLUSIVE (not passed); S1, S2, S4, S5 are judged on all points.

## What counts as failure

* S1 not met (above_high > 3% per point or > 5% per configuration): the RAM claim FAILS and Tier 1 / policy B is not
  validated at multi-GiB sizes.
* S2 not met: the time-bucket claim FAILS (with the per-operation breakdown reported).
* S3 not met: escalation by trigger (b) is not worth its cost; the 5 s threshold must be raised or the trigger removed.
* S4 not met: the controller is harmful and is not adopted.
* S5 not met: Tier 2 is withdrawn from the controller until the hole is closed.
Any failure is reported as a failure, not repaired and re-claimed on the same data: once read, `val-v5` is dev data and
a new group is required. A pass says only that the criteria held on this group.

## Dev evaluation (the only run allowed in this phase)

The controller is replayed on the 360 development points from the stored Tier 0 / Tier 1 / Tier 2 predictions
(`benchmarks/results/tier2-dev-b`), under three DECLARED free-RAM scenarios (2.5 GiB, the dev machine's cap; 8 GiB; 32 GiB),
and compared with Tier 1 alone. Every number is dev. Because dev cells are short (median 0.2-0.9 s), trigger (b) will
almost never fire there and the dev result is mostly "Tier 1 kept"; that is a finding, not a defect. A what-if row
that always escalates is reported separately and labelled as such.

---

## Amendment 1 (dated 2026-11-18; added BEFORE val-v5 was run; the text above is unchanged)

Nothing from val-v5 had been run or read when this amendment was written. The controller rules R0-R4 and S1-S3, S5 are
unchanged. S4 and the run order / partial-run reporting are made precise.

**(a) S4 "no harm vs Tier 1 alone", defined numerically.** The original S4 covered RAM only (controller `above_high` <=
Tier 1's, no RAM bound lowered). It did not say how "harm" is measured for time or for width. S4 is now the conjunction of,
on the valid points of the groups that completed (see (b)):
1. RAM: the number of points whose actual exceeds the controller's `high` is <= the number for Tier 1 alone (policy B) on
   the same points (original wording, kept);
2. RAM: no `low`, `expected` or `high` is lower than Tier 1's (0 points);
3. RAM width: mean (high - low) / expected of the controller <= **1.25 x** Tier 1's;
4. time: the share of points whose expected time bucket is within one bucket of the measured one is >= Tier 1's share
   **minus 1 percentage point**;
5. time: the share of points whose measured time is above the controller's `time_high` is <= Tier 1's share **plus 2
   percentage points**.
Any one failing means S4 FAILED. The thresholds (1.25x, 1 pp, 2 pp) are fixed here by principle (a controller may widen the
RAM range by a quarter at most; a bucket share is a ratio of a few dozen points, so 1 pp is one point of noise;
2 pp for the above-high share) and are not derived from dev data.

**(b) Run priority for val-v5.** The run may be cut short by budget, so the points run in this order (the runner orders
val-v5 points this way; within a priority group case by case, sizes ascending):
* P1: merge, groupby, astype, drop_duplicates, read_csv;
* P2: concat, sort_values;
* P3: numpy.sort, matmul (skippable if the budget runs out).
S1-S5 are evaluated on whatever priority groups COMPLETED, and the evaluation report must list which groups completed.
A group is completed when every point of it that the planner admits has a final status (ok, memory_limit or error; a
point skipped by the cap counts as final); a group with a point still pending is incomplete.

**(c) How a partial run is reported.** (i) The report states the completed groups and the points done / planned per group.
(ii) Each criterion is judged on the union of the completed groups and also per completed group; a verdict is MET / FAILED /
INCONCLUSIVE for those groups only, never for the whole of val-v5. (iii) Points of an incomplete group are listed as
descriptive counts and are excluded from every verdict (no partial group enters S1-S5). (iv) The minimum-evidence rule (20
escalated points) applies to the union of completed groups. (v) If P1 did not complete, the report says "val-v5 NOT
EVALUATED" and no criterion is judged. (vi) Whatever the outcome, val-v5 is read once; the next group must be a new one.
