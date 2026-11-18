# Large-size run on a >= 32 GB Linux machine (NOT run; commands only)

## Why

On the development machine (2.5 GiB harness cap) **only 8 of 283 valid RAM points exceed 1 GiB** and the
largest is 1.51 GiB. Per operation (valid points / > 1 GiB / > 512 MiB / largest): astype 49 / 0 / 5 / 0.90 GiB,
drop_duplicates 40 / 2 / 12 / 1.17, groupby 41 / 0 / 2 / 0.89, merge 37 / 0 / 3 / 0.83, numpy.sort 12 / 0 / 0 /
0.07, matmul 24 / 0 / 0 / 0.49, concat 27 / 0 / 8 / 0.82, read_csv 24 / 6 / 12 / 1.51, sort_values 29 / 0 / 9 / 0.78
(`dev-v5`, Tier 1 rows). The 10M-row points of the heavy operations were skipped by the cap (merge 20 of 57
points, drop_duplicates 7, astype 3, groupby 3, ...; 37 of 360 in all). Everything NEXUS says about
multi-GiB peaks, i.e. exactly the cases where an OOM warning matters, is therefore **extrapolated**
(table sizes beyond the 2^20-entry presize cap and the 2^22+ bucket regime are validated only by
probes at <= 4M rows). The run below measures them. It reuses the existing dev cases at larger sizes;
it does not touch `test-v2` and there is no held-out group in split version 5.

## Machine

Linux (Ubuntu 22.04+ / Debian 12), >= 32 GB RAM free (a 64 GB VM is comfortable; Colab "High-RAM" Linux
runtimes also work), swap OFF or small (`sudo swapoff -a`: paging would distort peaks), >= 150 GB free disk
for the input cache (estimate: the 30M-row inputs are 3-6 GB each, ~100 cached inputs; check with
`du -sh benchmarks/.cache`), Python 3.10-3.12, git. Nothing else running. On Linux the peak counter
(`VmHWM`) is reset after setup, so no point is censored by the setup peak.

## Install

```bash
sudo apt-get update && sudo apt-get install -y git python3-venv python3-dev build-essential
git clone <your NEXUS repository URL> nexus && cd nexus
git checkout <the commit you want measured>        # e.g. the Phase 4b.3 commit
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev,bench]"
python -c "import pandas, numpy, psutil; print(pandas.__version__, numpy.__version__)"
free -g; swapon --show                              # check free RAM, swap off
nexus-calibrate-machine                             # per-machine throughputs (once)
```

On Colab: `!git clone ...`, `%cd nexus`, `!pip install -e ".[dev,bench]"`, then run the commands below with `!`
(use a High-RAM runtime and keep the notebook open; a disconnect only pauses the resumable run).

## Plan, then run

Pick the cap well below free RAM (the harness kills a child whose TOTAL RSS exceeds it): 24 GiB on a 32 GB
machine, 48 on a 64 GB one.

```bash
CAP=24                                              # GiB
python -m benchmarks plan --suite full --splits dev --mem-limit-gb $CAP --max-size 30000000
nohup python -m benchmarks full --splits dev --tiers 0,1 --out benchmarks/results/large-linux \
      --mem-limit-gb $CAP --max-size 30000000 --no-report > large-linux.log 2>&1 &
python -m benchmarks status benchmarks/results/large-linux       # from a second shell; counts only
```

Resumable: re-run the same `full` command to continue. To measure only the sizes the 2.5 GiB machine could not
reach, copy the existing actuals first so those points are kept and only the missing ones run:

```bash
mkdir -p benchmarks/results/large-linux
cp <dev-v5 actuals.csv and predictions.csv> benchmarks/results/large-linux/    # optional, from this repo's results
```

(the results are not committed; copy `benchmarks/results/dev-v5/actuals.csv` from the Windows machine if wanted;
rows measured on another OS are different evidence, so prefer a clean directory for the Linux numbers.)

`numpy.sort` and `matmul` sizes: raise `--max-size 100000000` to include the 100M-element sorts (the
matmul dimensions are fixed by the suite, up to 8000).

Expected time: several hours on a 16-core VM (the 2.5 GiB machine needed ~13 s per point at <= 10M rows; 30M-row
points take several minutes each, and generating the cached inputs is a one-off cost of tens of minutes). The
log shows id, status and elapsed time per point.

## After the run

```bash
python -m benchmarks evaluate benchmarks/results/large-linux          # dev report (no protected group is involved)
python -m benchmarks.planner_report benchmarks/results/large-linux --cap-gb $CAP
python -m benchmarks.oom_misses benchmarks/results/large-linux --limit-mb 8192
python -m benchmarks.range_policy benchmarks/results/large-linux
```

Look at (a) how many valid points now exceed 1 / 4 / 16 GiB per operation, (b) Tier 1 above_high and
coverage on those points, and (c) whether the table-residency model (`factorize_peak_bytes`) and the merge
union term hold above 4M rows (3 doublings of the table beyond anything probed). Do not tune on the
result and then call it validated: it is development data; a new held-out split is needed for a claim.
