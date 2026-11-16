"""Runner integration: tiny real run in spawned processes, then resume behaviour."""

from __future__ import annotations

import csv

from benchmarks.runner import RunConfig, run_suite
from benchmarks.suite import BASE, FrameInput, GridPoint


def tiny_point(n: int = 3000) -> GridPoint:
    return GridPoint(
        id=f"t/drop_duplicates|n={n}",
        case="t/drop_duplicates",
        op="drop_duplicates",
        source="df.drop_duplicates()",
        size=n,
        inputs=(FrameInput(BASE.with_(n_rows=n)),),
        repeats=2,
        footprint_factor=3.0,
    )


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_run_then_resume_fills_missing_predictions(tmp_path):
    out = tmp_path / "results" / "t"
    cfg = RunConfig(suite="small", out_dir=out, calibrate=False)
    actuals, preds = run_suite(cfg, [tiny_point()])
    a, p = read(actuals), read(preds)
    assert len(a) == 1 and a[0]["status"] == "ok" and a[0]["instrument"] == "os-peak-v2"
    assert a[0]["pandas"] and a[0]["numpy"] and a[0]["pyarrow"] and a[0]["os"] and a[0]["cpu"]
    assert a[0]["pandas_str_default"] and a[0]["text_dtype"] == "object"
    assert len(p) == 1 and p[0]["has_estimate"] == "True" and p[0]["os"]
    assert float(a[0]["input_bytes"]) > 0 and float(a[0]["input_resident_bytes"]) >= 0

    stamp = a[0]["time_s_all"]
    run_suite(cfg, [tiny_point()])  # everything done: nothing re-measured
    assert read(actuals)[0]["time_s_all"] == stamp and len(read(preds)) == 1

    preds.unlink()  # lost predictions are regenerated without re-measuring the actual
    run_suite(cfg, [tiny_point()])
    assert len(read(actuals)) == 1 and read(actuals)[0]["time_s_all"] == stamp
    assert len(read(preds)) == 1
