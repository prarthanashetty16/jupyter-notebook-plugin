"""Model-based footprint planning: skip a point when baseline + NEXUS's upper bound exceeds the cap."""

from __future__ import annotations

import csv
import json

from benchmarks import runner
from benchmarks.planner import MIB, baseline_bytes, best_high, decide
from benchmarks.runner import RunConfig, run_suite
from benchmarks.suite import BASE, FrameInput, GridPoint

GB = 2**30


def _pred(tier, high, used=True, has=True):
    feats = json.dumps({"tier1": {"used": used}}) if tier == 1 else "{}"
    return {"has_estimate": str(has), "ram_high": str(high), "features": feats}


def test_baseline_follows_the_dev_fit_with_margin():
    assert baseline_bytes(0) == 100 * MIB
    assert baseline_bytes(760_000_000) == int(100 * MIB + 1.02 * 760_000_000)


def test_best_high_prefers_a_tier_1_estimate_that_used_statistics():
    assert best_high({0: _pred(0, 900), 1: _pred(1, 400)}) == (400, "tier1")
    assert best_high({0: _pred(0, 900), 1: _pred(1, 400, used=False)}) == (900, "tier0")
    assert best_high({0: _pred(0, 900)}) == (900, "tier0")
    assert best_high({1: _pred(1, 5, has=False)}) == (None, "none")
    assert best_high({}) == (None, "none")


def test_a_point_the_static_rule_let_through_but_the_model_says_cannot_fit_is_skipped():
    # the null-heavy drop_duplicates at 10M rows: ~760 MB of input (planned 2.3 GB by the old rule),
    # Tier 1 high 2.2 GB, cap 2.5 GiB: baseline 0.9 GB + 2.2 GB = 3.1 GB > cap  -> killed in the run
    d = decide(760_000_000, {1: _pred(1, 2_218_733_568)}, int(2.5 * GB))
    assert d.skip and d.high_source == "tier1" and "planned footprint" in d.reason
    assert not decide(760_000_000, {1: _pred(1, 900 * MIB)}, int(2.5 * GB)).skip


def test_without_any_estimate_the_static_rule_decides_alone():
    d = decide(10**9, {}, GB)
    assert not d.skip and d.high_source == "none"


def _point(n=2000):
    return GridPoint(id=f"x/dd|n={n}", case="drop_duplicates/mixed_dup0", op="drop_duplicates",
                     source="df.drop_duplicates()", size=n, inputs=(FrameInput(BASE.with_(n_rows=n)),),
                     repeats=1, footprint_factor=3.0)  # fmt: skip


def test_runner_skips_before_measuring_and_keeps_the_prediction(tmp_path, monkeypatch):
    real = runner.run_prediction
    calls = {"actual": 0}

    def huge_high(point, tier, source, cache_dir, cap, env):
        row = real(point, tier, source, cache_dir, cap, env)
        return {**row, "ram_high": str(10 * GB)}

    def never(*args, **kwargs):
        calls["actual"] += 1
        raise AssertionError("must not be measured")

    monkeypatch.setattr(runner, "run_prediction", huge_high)
    monkeypatch.setattr(runner, "run_actual", never)
    out = tmp_path / "results" / "t"
    run_suite(
        RunConfig(suite="small", out_dir=out, calibrate=False, mem_limit_bytes=GB), [_point()]
    )
    assert calls["actual"] == 0
    rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    assert rows[0]["status"] == "skipped_cap" and "planned footprint" in rows[0]["error"]
    assert len(list(csv.DictReader((out / "predictions.csv").open(encoding="utf-8")))) == 1


def test_runner_measures_a_point_whose_upper_bound_fits(tmp_path):
    out = tmp_path / "results" / "t"
    run_suite(
        RunConfig(suite="small", out_dir=out, calibrate=False, mem_limit_bytes=4 * GB), [_point()]
    )
    rows = list(csv.DictReader((out / "actuals.csv").open(encoding="utf-8")))
    assert rows[0]["status"] == "ok"
    assert (
        len(list(csv.DictReader((out / "predictions.csv").open(encoding="utf-8")))) == 1
    )  # not twice
