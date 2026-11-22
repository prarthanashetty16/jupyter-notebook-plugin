"""Phase 6d profile-bug audit: prediction-only re-runs with the restored machine profile.

From Phase 6b (commit a948b01, 2026-11-21 23:05) until the restore (2026-11-22 14:17) every full test
run overwrote the user's machine profile with a 1-second quick profile measured on battery
(``tests/test_power.py`` called ``monkeypatch.undo()``). RAM and Tier 1 statistics do not depend on the
profile; time estimates do. This script re-runs ONLY predictions (no measurement) with the restored
profile and writes the corrected time next to the originals (nothing is deleted):

* stored prediction folders (``predictions.csv`` with features): time is recomputed from the stored
  features with the current models and the calibration artifact, as at run time, into
  ``predictions_time_restored_profile.csv``;
* the multi-statement dev cells (no stored features): the prediction is re-run in a fresh process into
  ``results_restored_profile.jsonl``.

    python -m benchmarks.profile_audit --out docs/benchmarks/phase6d/profile_audit.md
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from nexus import timecal
from nexus.machine import load_profile, reference_profile
from nexus.models.base import NoEstimateError
from nexus.pipeline import load_builtin_models
from nexus.registry import default_registry

RESULTS = Path("benchmarks/results")
PREDICTION_DIRS = ("fallback-cores2", "fallback-contended", "phase6c-dev")


def recompute_folder(folder: Path) -> dict[str, object]:
    load_builtin_models()
    models = {m.name: m for m in default_registry}
    p = pd.read_csv(folder / "predictions.csv", dtype=str, keep_default_na=False)
    p = p[p["has_estimate"] == "True"].copy()
    rows = []
    for _, r in p.iterrows():
        f = json.loads(r["features"])
        m = models[r["model"]]
        try:
            try:
                e = m.estimate(f, int(r["tier"]))
            except NoEstimateError:
                e = m.estimate(f, 0)
            e = timecal.calibrate(r["model"], e)
        except Exception:
            continue
        rows.append({"point_id": r["point_id"], "tier": r["tier"], "time_low": e.time_low,
                     "time_expected": e.time_expected, "time_high": e.time_high,
                     "stored_time_expected": float(r["time_expected"]), "ram_expected": e.ram_expected,
                     "stored_ram_expected": float(r["ram_expected"])})  # fmt: skip
    out = pd.DataFrame(rows)
    out.to_csv(folder / "predictions_time_restored_profile.csv", index=False)
    ratio = (out["stored_time_expected"] / out["time_expected"]).replace([math.inf], math.nan)
    meta = json.loads((folder / "meta.json").read_text())["machine_profile"]["meta"]
    return {
        "folder": folder.name, "rows": len(out), "profile_used": meta.get("timestamp"),
        "quick": meta.get("quick"), "power": meta.get("power"),
        "time_ratio_median": float(ratio.median()), "time_ratio_min": float(ratio.min()),
        "time_ratio_max": float(ratio.max()),
        "ram_rows_differing": int((out["ram_expected"] != out["stored_ram_expected"]).sum()),
    }  # fmt: skip


def rerun_multicell() -> dict[str, object]:
    from benchmarks.multicell.cases import Cell, Config, prepare, source
    from benchmarks.multicell.run import CACHE, predict
    from benchmarks.multicell.run import RESULTS as MC

    src_path = MC / "dev" / "results.jsonl"
    old = [json.loads(line) for line in src_path.open(encoding="utf-8")]
    new_rows, ram_diff, ratios = [], 0, []
    for r in old:
        t, s = r["config"].split("/")
        cell = Cell(Config(t, s), int(r["rows"]))
        paths = prepare(CACHE, s, cell.rows)
        pred = predict(paths, source(cell, paths))
        new_rows.append({**r, **{k: pred[k] for k in ("new", "v1", "mode", "flags")}})
        if (pred["new"] or {}).get("ram_expected") != (r["new"] or {}).get("ram_expected"):
            ram_diff += 1
        if pred["new"] and r["new"] and pred["new"]["time_expected"]:
            ratios.append(r["new"]["time_expected"] / pred["new"]["time_expected"])
    (MC / "dev" / "results_restored_profile.jsonl").write_text(
        "".join(json.dumps(x, default=str) + "\n" for x in new_rows), encoding="utf-8"
    )
    s = pd.Series(ratios)
    return {"folder": "multicell/dev", "rows": len(new_rows), "ram_rows_differing": ram_diff,
            "time_ratio_median": float(s.median()), "time_ratio_min": float(s.min()),
            "time_ratio_max": float(s.max())}  # fmt: skip


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.profile_audit")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    prof = load_profile()
    if prof is None or prof.profile_id != reference_profile().profile_id:
        raise SystemExit(
            "the machine profile is not the restored reference profile: restore it first"
        )
    results = [recompute_folder(RESULTS / d) for d in PREDICTION_DIRS]
    results.append(rerun_multicell())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
