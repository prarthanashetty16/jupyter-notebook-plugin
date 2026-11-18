"""Sandbox child of a Tier 2 dry run: ``python -m nexus._dryrun_child <spec.json>``.

Loads one sample from disk, runs the recipe once (cold, like the benchmark's measured call) and
writes peak-RAM / time to the result file named in the spec. It touches only the files in its
private directory; the parent enforces the timeout and the memory cap by killing it.

RAM is the OS peak counter delta: ``peak after - resident before`` (see ``nexus.measure``). If the
operation never exceeded the peak reached while loading the sample (Windows cannot reset the
counter) the run is CENSORED: ``delta_bytes`` is null and ``bound_bytes`` the upper bound.
"""

from __future__ import annotations

import gc
import json
import sys
import time
import traceback
from pathlib import Path


def main(spec_path: str) -> None:
    spec = json.loads(Path(spec_path).read_text())
    out = Path(spec["result"])
    try:
        from nexus.dryrun_io import execute, load_object, result_rows
        from nexus.measure import read_memory, reset_peak

        root = Path(spec["dir"])
        objs = {name: load_object(root / name) for name in spec["objects"]}
        csv_path = str(root / "sample.csv") if spec.get("csv") else None
        gc.collect()
        reset = reset_peak()
        before = read_memory()
        t0 = time.perf_counter()
        result = execute(spec["recipe"], objs, csv_path)
        elapsed = time.perf_counter() - t0
        after = read_memory()
        rows = result_rows(result)
        if after.peak is None or before.peak is None:
            delta, censored, bound = None, True, None
        elif reset or after.peak > before.peak:
            delta, censored, bound = max(0, after.peak - before.rss), False, None
        else:
            delta, censored, bound = None, True, max(0, before.peak - before.rss)
        payload = {"status": "ok", "time_s": elapsed, "delta_bytes": delta, "censored": censored,
                   "bound_bytes": bound, "baseline_bytes": before.rss, "out_rows": rows}  # fmt: skip
    except BaseException as exc:  # report, never raise: the parent reads the file
        payload = {"status": "error", "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                   "trace": traceback.format_exc()[-400:]}  # fmt: skip
    out.write_text(json.dumps(payload))


if __name__ == "__main__":
    main(sys.argv[1])
