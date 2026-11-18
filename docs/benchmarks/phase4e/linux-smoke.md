# Linux smoke test (Phase 4e)

## What was available on the development machine (Windows 11)

* **WSL2:** installed, but the only distribution is `docker-desktop` (the Docker Desktop helper, state *Stopped*); there
  is no general-purpose distribution with Python.
* **Docker:** client 29.4.3 installed; the daemon is NOT running (`docker info`: cannot connect to
  `dockerDesktopLinuxEngine`). I did not start Docker Desktop or pull any image without being asked.
* **Result:** the instrument validation suite and the unit tests were NOT run on Linux. What was done instead: the
  Linux / POSIX branches of the platform layer are exercised on Windows with fakes (`tests/test_linux_branches.py`, 11
  tests): `VmRSS` / `VmHWM` parsing from `/proc/<pid>/status` (kiB), the fallback to psutil + `ru_maxrss` (KiB on Linux,
  bytes on macOS) when /proc is unreadable, `reset_peak` writing `5` to `/proc/self/clear_refs` and returning False when it
  is not writable (containers, gVisor), page faults through `resource`, the distribution / CPU model read from
  `/etc/os-release` and `/proc/cpuinfo`, the sandbox starting without `subprocess.CREATE_NO_WINDOW`, and a scan that no
  module uses fork or imports `resource` at import time. No portability bug was found there; none of this replaces a
  run on Linux.
* **Found and fixed (a harness bug, not a model change):** a runner killed mid-write left a torn last CSV row that made
  the next resume crash (`upgrade_header` zipped a short row) or count a fragment as a finished point. `ResultStore` now
  drops a torn row on load (the tests kill a real runner mid-run).

## Exact commands to run the suite on Linux

Docker (Docker Desktop must be running; this downloads the `python:3.12-slim` image once). `git archive` avoids sending
the multi-GB result / cache folders into the container:

```bat
cd c:\dev\NEXUS
git archive --format=tar HEAD | docker run --rm -i -m 4g python:3.12-slim bash -c "mkdir /w && tar -x -C /w && cd /w && pip install -q -e '.[dev,bench]' && python -m pytest tests -q -p no:cacheprovider"
```

The instrument validation and the cgroup branch specifically (2 GiB container limit):

```bat
git archive --format=tar HEAD | docker run --rm -i -m 2g --memory-swap 2g python:3.12-slim bash -c "mkdir /w && tar -x -C /w && cd /w && pip install -q -e '.[dev,bench]' && python -m pytest tests/test_measure_validation.py tests/test_measure.py tests/test_state.py tests/test_linux_branches.py tests/test_dryrun.py tests/test_pilot_resume.py -v && python -c \"from nexus.state import ResourceProbe; print(ResourceProbe().snapshot()); from nexus.measure import reset_peak, read_memory; print(reset_peak(), read_memory())\""
```

Expect `reset_peak()` True (Docker allows `/proc/self/clear_refs`; if False the measurements are censored, never wrong),
the cgroup limit of 2 GiB in the snapshot, and every test passing. Any failure is a Linux portability bug to fix (not a
model change).

WSL2 instead of Docker:

```powershell
wsl --install -d Ubuntu-22.04          # once; reboot if asked
wsl -d Ubuntu-22.04 -- bash -lc "sudo apt-get update && sudo apt-get install -y python3-venv python3-dev build-essential git && cd /mnt/c/dev/NEXUS && python3 -m venv ~/nexus-venv && . ~/nexus-venv/bin/activate && pip install -e '.[dev,bench]' && python -m pytest tests -q"
```

(`/mnt/c` is slower and the editable install writes `egg-info` into the repo; the Docker route does not touch it.)
