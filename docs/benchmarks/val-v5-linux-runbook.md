# Running val-v5 on a Linux VM (>= 32 GB RAM) — commands only, NOT run

`val-v5` is the held-out validation group (split version 6, frozen with a digest, 47 configurations, 141 grid points,
~175 GiB of cached inputs). It is the held-out Linux check of **`models-frozen-v3`** (Mode B of the Phase 7
pre-registration). **The acceptance criteria are those of `docs/benchmarks/phase7-preregistration.md`, sections 2 and 4**
(see "Acceptance criteria" below); the Phase 4d controller criteria S1-S5 (`docs/benchmarks/phase4d-preregistration.md`)
are LEGACY: the report still prints them, but they are not the v3 acceptance verdict. Nothing may change between now
and the run. Read the report ONCE (`evaluate --val` logs the access in `docs/PROGRESS.md`); afterwards val-v5 is dev data.

## Machine

Ubuntu 22.04+ / Debian 12 (Python 3.11 or 3.12: pandas 3.1.1 needs Python >= 3.11; Python 3.10 resolves pandas 2.x, which is unsupported; > 1 vCPU: the v3 read_csv model follows pandas' parallel reader), **>= 32 GB RAM** (64 GB comfortable), 8+ vCPUs,
**>= 300 GB free disk** for the input cache (`benchmarks/.cache`; the inputs alone are ~175 GiB), swap OFF, nothing
else running. Memory cap to use: **24 GiB** on a 32 GB machine (the harness kills a child above it; 48 on 64 GB).
Max size to use: **400000000** (`--max-size` filters every point: np.sort goes to 400M elements, row cases to 30M rows,
matmul dimensions to 16000; the per-case size lists in the suite bound the rest).

## Install

```bash
sudo apt-get update && sudo apt-get install -y git python3-venv python3-dev build-essential
git clone <your NEXUS repository URL> nexus && cd nexus
git checkout main                                                  # main at/after the commit adding benchmarks/phase7_verdict.py;
                                                                   # its 46 frozen files are byte-identical to models-frozen-v3
git rev-parse HEAD; git rev-parse models-frozen-v3^{}                # record both (the tag is 6e18e33)
python -m benchmarks.frozen check                                   # must print no problems (exit 0)
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,bench]"
python -c "import pandas, numpy, psutil; print(pandas.__version__, numpy.__version__)"
sudo swapoff -a; free -g; df -h .                                   # swap off, RAM and disk as expected
python -m pytest tests -q                                           # ~1 min; NOT while the benchmark runs
```

**Which checkout (Phase 7d).** Run from `main`, not from the bare tag: the Phase 7 acceptance verdict (`benchmarks/phase7_verdict.py`), the R1-R3 replay and the CI fixes were added after the tag, outside the freeze. The freeze guard below proves the model is v3: it compares the 46 frozen files with `models-frozen-v3` and must report 0 problems.

**Freeze guard (Phase 6; v3 since Phase 7d).** `full --splits val-v5` and `evaluate --val` abort unless the tracked files outside `docs/` are
identical to the tag `models-frozen-v3` (`benchmarks/frozen.py`); the tag commit is recorded in `meta.json` and in the
report. Any model change after the freeze invalidates the held-out status of the run. Run on mains / server power: the
calibration refuses to measure on battery.

**Profile check (Phase 6d).** Held-out runs also call `benchmarks.heldout_env.require_profile(<results folder>)`. Every
invocation refuses on battery power. The FIRST invocation of a run (no `heldout_profile` entry in
`benchmarks/results/val-v5/meta.json` yet) requires, on a machine other than the reference laptop, a profile measured in
this session by `nexus-calibrate-machine --force` (not `--quick`, not on battery, at most 12 h earlier) and PINS it: the
profile id and a hash of the profile file go into `meta.json` (`heldout_profile`). Every LATER invocation of the same run
(the full run after `--pilot`, a resume after an interruption, however many hours later) requires that SAME profile and
ignores its age. **Do NOT re-run `nexus-calibrate-machine` between the pilot and the full run or before a resume**: a new
profile (a new id, or the same id with a changed file) makes the run abort, because its rows would mix two profiles. Keep a
copy right after calibrating (`cp ~/.cache/nexus/machine.json ~/machine.val-v5.json`; the path is `$NEXUS_MACHINE_PROFILE`
if set, else `$XDG_CACHE_HOME/nexus/machine.json`). If the profile was lost or changed, copy that file back, or start a NEW
run in a new results folder after a fresh calibration. The profile id and the power state are also written into every result row (`profile_id`, `power`).

## Calibrate the machine FIRST (recorded)

```bash
nexus-calibrate-machine --force            # per-machine throughputs; writes the profile
nexus-calibrate-machine --show | tee calibration.txt
```
The runner records the profile in `benchmarks/results/val-v5/meta.json` (`machine_calibration`) and, with
`--require-calibrated`, refuses to start without one. Every result row also records the OS (`os`, `kernel`,
`os_release`), CPU model, CPU count, RAM, swap, and the Python / pandas / numpy versions.

## Plan, run, evaluate

```bash
CAP=24                                                              # GiB; 24 on 32 GB, 48 on 64 GB
python -m benchmarks plan --suite full --splits val-v5 --mem-limit-gb $CAP --max-size 400000000
#   historical estimate (computed with the v1 models, Phase 4d): at 24 GiB, 141 points, 140 would run, 1 skipped
#   (the 28 GiB merge at 30M rows). NOT a pass criterion: the v3 planner may differ; record the counts it prints.

nohup python -m benchmarks full --splits val-v5 --tiers 0,1,2 --out benchmarks/results/val-v5 \
      --mem-limit-gb $CAP --max-size 400000000 --require-calibrated --no-report > val-v5.log 2>&1 &
python -m benchmarks status benchmarks/results/val-v5               # from a second shell: counts only
```
Resumable (re-run the same `full` command). `--tiers 0,1,2` stores Tier 0 and Tier 1 predictions and a Tier 2 dry
run for every qualifying point; the controller is replayed from those at evaluation time (its decisions depend
only on the stored estimates, the free RAM recorded at each point's start and the stored dry run). The planner
predicts first and skips points whose baseline + `high` cannot fit the cap.

```bash
python -m benchmarks evaluate benchmarks/results/val-v5 --val --reason "held-out check of models-frozen-v3"
# -> benchmarks/results/val-v5/validation_report.md : Tier 0 / Tier 1 report, the Tier 0 vs Tier 1 comparison,
#    the LEGACY Phase 4d "Controller" section (S1-S5), the risk-engine replay (R1-R3) and, at the end, the
#    authoritative "Phase 7 acceptance verdict" section (benchmarks/phase7_verdict.py)
```

## One-hour pilot BEFORE the full run (recommended)

The run order is priority order (Amendment 1 of the pre-registration): P1 merge, groupby, astype, drop_duplicates,
read_csv; then P2 concat, sort_values; then P3 np.sort, matmul (skippable). The first N points are whole cases at
3M / 10M / 30M rows, so a pilot of 12 also times the largest sizes.

```bash
python -m benchmarks full --splits val-v5 --tiers 0,1,2 --out benchmarks/results/val-v5 \
      --mem-limit-gb $CAP --max-size 400000000 --require-calibrated --no-report --pilot 12
cat benchmarks/results/val-v5/pilot.json     # seconds per pilot point + the estimate for the remaining points
```
`--pilot N` runs only the first N points, writes `pilot.json` (per-point seconds, their mean, and the extrapolated hours
for the rest: the mean of the pilot points of the same size, scaled linearly in rows for sizes the pilot did not reach and
quadratically in the dimension for matmul; low / high from the fastest / slowest point) and logs a one-line summary.
Pilot points are REAL val-v5 measurements: the full run resumes and does not repeat them. Nothing is read until
`evaluate --val`. If the budget runs short, stop after P1 or P2: the report lists which groups completed and judges only
those; if P1 is incomplete it says "val-v5 NOT EVALUATED".

## Interrupted runs

Kill or reboot at any time and re-run the same `full` command: finished points are kept byte for byte, a point cut off
mid-measurement is measured again, a prediction missing for a measured point is filled in, and a half-written CSV row is
dropped on load (tested by killing a real runner mid-run).

## Expected runtime and cost class (estimates, not measurements)

The development machine needed ~13 s per measured point at <= 10M rows; at 30M rows loading the inputs (pickled
string columns) and the operation both scale with the data, so plan on **~20-30 hours** wall-clock on an 8-vCPU / 64 GB VM:
~423 measured runs (141 points x 3 repeats, ~60 s on average at the large sizes, ~7 h), the one-off generation of the
cached inputs (~175 GiB; string-heavy 30M-row frames dominate, ~4-6 h), and three prediction passes per point that each
reload the inputs plus a Tier 2 dry run (~12-15 h; the dry run adds 2-15 s per point, text keys above 6M rows are not
sampled and give "no sample"). **Cost class: tens of dollars** at on-demand prices for a 64 GB general-purpose instance
(roughly 0.5-1.0 USD/h) plus the disk; a spot instance or a Colab High-RAM runtime lowers it but can be interrupted
(the run resumes). A cheaper partial run, `--max-size 10000000`, takes about a third of the time but does NOT reach the
multi-GiB regime that the criteria are about (S3 would be inconclusive).

## Acceptance criteria (Phase 7 pre-registration, sections 2 and 4: authoritative)

The report's last section, "Phase 7 acceptance verdict", computes these from the val-v5 results; each bar is quoted with
its 95% bound:

| criterion | bar | bound quoted |
|---|---|---|
| RAM above_high per POINT (Tier 1, policy B as displayed) | <= 3% | one-sided 95% Clopper-Pearson upper bound |
| RAM above_high per CONFIGURATION (a case with any point above high) | <= 3% | the same |
| time within one bucket (order-of-magnitude buckets) | >= 95% | Wilson 95% lower bound |
| R1 recall (risk replay) | >= 98% pooled and at every limit with >= 20 positives | - |
| R2 false alarms (risk replay) | pooled <= 30% and per operation <= 50%; a failure is reported as a REPEAT failure | - |
| R3 HIGH_RISK precision (risk replay) | >= 75% (no claim with < 20 HIGH_RISK points) | - |

* Fewer than 30 valid points (configurations: fewer than 10) make a criterion **INCONCLUSIVE**, never a pass.
* **Whole-v3 failure** ("`models-frozen-v3` FAILED its held-out check"): RAM per point or per configuration, time, or
  R1 FAILED. **Item failure** (the claim is withdrawn): R2 or R3.
* The pre-registration does NOT specify a tier for the time criterion. The verdict row uses Tier 1 as a PROVISIONAL
  INTERPRETATION (the extension default and the tier the RAM criterion names), not a pre-registered requirement. Tier 0
  time is reported in its own row with the same statistics and no verdict, and the report says whether the two tiers
  agree on the 95% bar.
* The **uncovered-operation rule** (amendment 1) does NOT apply to val-v5: its points are single operations. It
  belongs to the multi-statement groups.
* An incomplete run (fewer points with results than planned) is labelled INCOMPLETE in the verdict, which then covers
  only the measured points.
* Use the reason string `held-out check of models-frozen-v3`.

## LEGACY: the Phase 4d criteria S1-S5 (still printed, NOT the v3 acceptance verdict)


Phase 4d judged the controller against S1-S5 (RAM above_high <= 3% per point and <= 5% per configuration; time
bucket within one >= 95%; overhead <= 50% / 100% of the real run time for trigger-(b) escalations; no harm; safety). With
fewer than 20 points escalated by trigger (a) or (b) the overhead and escalated-time claims are INCONCLUSIVE, not passed.
A failed criterion is reported as failed; do not re-tune on val-v5 and re-claim: it becomes dev data and a new group is
needed.
