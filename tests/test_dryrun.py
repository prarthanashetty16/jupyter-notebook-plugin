"""Tier 2: scaling fits, nested / coordinated sampling, the sandbox child and the pipeline hook."""

from __future__ import annotations

import json
import math
import multiprocessing
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nexus import dryrun, dryrun_sample
from nexus.dryrun_fit import CV_MAX, fit_scaling
from nexus.dryrun_io import load_object, save_frame
from nexus.dryrun_safety import analyze_safety
from nexus.models.base import Estimate
from nexus.pipeline import Pipeline

SIZES = [10_000, 20_000, 40_000, 80_000]
TARGET = 4_000_000


def _series(law, a, b, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    f = {"linear": lambda n: n, "nlogn": lambda n: n * math.log2(n), "quadratic": lambda n: n * n}[
        law
    ]
    return [(a + b * f(n)) * (1 + noise * rng.standard_normal()) for n in SIZES], f


# -- scaling fits ------------------------------------------------------------------------------------
@pytest.mark.parametrize("law", ["linear", "nlogn", "quadratic"])
def test_the_true_law_is_recovered_and_extrapolated(law):
    slope = {"linear": 50.0, "nlogn": 3.0, "quadratic": 1e-3}[law]
    ys, f = _series(law, 2e6, slope)
    fit = fit_scaling(SIZES, ys, TARGET)
    truth = 2e6 + slope * f(TARGET)
    assert fit.ok and fit.best == law
    assert fit.expected == pytest.approx(truth, rel=0.01)
    assert fit.low <= fit.expected <= fit.high


def test_noise_widens_the_range_and_the_range_contains_the_truth():
    widths = {}
    for noise in (0.0, 0.03):
        ys, f = _series("linear", 1e6, 50.0, noise, seed=3)
        fit = fit_scaling(SIZES, ys, TARGET)
        truth = 1e6 + 50.0 * TARGET
        assert fit.ok and fit.low <= truth <= fit.high
        widths[noise] = (fit.high - fit.low) / fit.expected
    assert widths[0.03] > widths[0.0]


def test_model_selection_uncertainty_is_in_the_range():
    """When two laws fit about equally well the range spans both extrapolations."""
    xs = SIZES
    ys = [2.0e6 + 3.0 * n * math.log2(n) * (1 + 0.01 * (-1) ** i) for i, n in enumerate(xs)]
    fit = fit_scaling(xs, ys, TARGET)
    assert fit.ok
    assert fit.high >= max(d["extrapolated"] for d in fit.laws.values() if d["cv"] <= 0.15) * 0.99


def test_the_further_the_extrapolation_the_wider_the_range():
    ys, _ = _series("linear", 1e6, 50.0, 0.02, seed=1)
    near, far = fit_scaling(SIZES, ys, 320_000), fit_scaling(SIZES, ys, 80_000_000)
    assert (far.high - far.low) / far.expected > (near.high - near.low) / near.expected


@pytest.mark.parametrize(
    ("ys", "why"),
    [
        ([5e6, 5.01e6, 4.99e6, 5.02e6], "no growth"),
        ([1.0, 9.0, 2.0, 30.0], "no law"),
        ([1.0, 2.0], "usable"),
    ],
)
def test_unreliable_data_gives_no_estimate(ys, why):
    fit = fit_scaling(SIZES[: len(ys)], ys, TARGET)
    assert not fit.ok and why in fit.reason


def test_a_target_inside_the_samples_is_refused():
    ys, _ = _series("linear", 0, 50.0)
    assert not fit_scaling(SIZES, ys, 50_000).ok


def test_the_fixed_cost_is_the_intercept_not_a_slope():
    ys = [4e6 + 100.0 * n for n in SIZES]
    fit = fit_scaling(SIZES, ys, TARGET)
    assert fit.laws["linear"]["intercept"] == pytest.approx(4e6, rel=0.01)
    assert fit.expected == pytest.approx(4e6 + 100.0 * TARGET, rel=0.01)


def test_cv_gate_is_forward_chaining_not_interpolation():
    # a curve that bends upward late: forward validation must see the miss
    ys = [100.0, 200.0, 400.0, 1200.0]
    fit = fit_scaling(SIZES, ys, TARGET)
    assert (not fit.ok) or fit.laws["linear"]["cv"] > 0.1
    assert CV_MAX < 0.5


# -- sampling ----------------------------------------------------------------------------------------
@pytest.fixture
def frames():
    rng = np.random.default_rng(5)
    n = 600_000
    keys = rng.integers(0, 40_000, n)
    left = pd.DataFrame({"k": keys, "a": rng.random(n), "s": rng.choice(["x", "y", "z"], n)})
    rkeys = rng.integers(0, 60_000, 200_000)
    right = pd.DataFrame({"k": rkeys, "c": rng.random(len(rkeys))})
    return left, right


def _plan(source, ns, tmp_path):
    verdict = analyze_safety(source, ns)
    assert verdict.safe, verdict.reasons
    return verdict.recipe, dryrun_sample.build_samples(verdict.recipe, ns, tmp_path)


def test_merge_sampling_is_coordinated_and_nested(frames, tmp_path):
    left, right = frames
    ns = {"left": left, "right": right, "pd": pd, "np": np}
    recipe, plan = _plan('left.merge(right, on="k")', ns, tmp_path)
    full_l, full_r = left["k"].value_counts(), right["k"].value_counts()
    prev_keys: set[int] = set()
    for k in range(len(plan.levels)):
        sl = load_object(tmp_path / f"level{k}" / "left")
        sr = load_object(tmp_path / f"level{k}" / "right")
        cl, cr = sl["k"].value_counts(), sr["k"].value_counts()
        # every sampled key keeps ALL its rows on BOTH sides
        assert (cl == full_l.loc[cl.index]).all() and (cr == full_r.loc[cr.index]).all()
        keys = set(cl.index) | set(cr.index)
        assert prev_keys <= keys  # nested
        prev_keys = keys
        assert set(cr.index) <= set(full_r.index)
    sizes = [lv.n_eff for lv in plan.levels]
    assert sizes == sorted(sizes) and sizes[-1] / sizes[0] == pytest.approx(8.0)


def test_merge_sample_preserves_fanout_and_output_scale(frames, tmp_path):
    left, right = frames
    ns = {"left": left, "right": right}
    recipe, plan = _plan('left.merge(right, on="k")', ns, tmp_path)
    full_out = len(left.merge(right, on="k"))
    sl = load_object(tmp_path / "level3" / "left")
    sr = load_object(tmp_path / "level3" / "right")
    t = plan.levels[-1].n_eff / len(left)
    assert len(sl.merge(sr, on="k")) / t == pytest.approx(
        full_out, rel=0.25
    )  # a row sample would be ~t x too small


def test_groupby_and_drop_duplicates_keep_whole_groups(frames, tmp_path):
    left, _ = frames
    _, plan = _plan('df.groupby("k")["a"].sum()', {"df": left}, tmp_path / "g")
    s = load_object(tmp_path / "g" / "level3" / "df")
    full = left["k"].value_counts()
    got = s["k"].value_counts()
    assert (
        got.sort_index() == full.loc[got.index].sort_index()
    ).all()  # every sampled group is complete
    rng = np.random.default_rng(9)
    base = pd.DataFrame({"x": rng.integers(0, 10**9, 500_000), "y": rng.integers(0, 50, 500_000)})
    dup = pd.concat(
        [base, base.sample(frac=0.4, random_state=1)], ignore_index=True
    )  # 28.6% duplicates
    _, plan = _plan("df.drop_duplicates()", {"df": dup}, tmp_path / "d")
    sample = load_object(tmp_path / "d" / "level3" / "df")
    assert len(sample.drop_duplicates()) / len(sample) == pytest.approx(
        len(dup.drop_duplicates()) / len(dup), abs=0.03
    )
    # a plain row sample would see far fewer duplicates (each partner survives with probability = the fraction)
    rows = dup.sample(n=len(sample), random_state=2)
    assert len(rows.drop_duplicates()) / len(rows) > 0.95


def test_row_samples_keep_order_and_are_uniform(frames, tmp_path):
    left, _ = frames
    ordered = left.assign(a=np.arange(len(left), dtype=float))
    _, plan = _plan('df.sort_values("a")', {"df": ordered}, tmp_path)
    s = load_object(tmp_path / "level3" / "df")
    assert s["a"].is_monotonic_increasing  # original order kept
    assert s["a"].mean() == pytest.approx(ordered["a"].mean(), rel=0.05)  # uniform over the frame
    assert plan.levels[-1].n_eff == len(s) and plan.target == len(ordered)


def test_samples_are_copies_and_never_touch_the_users_objects(frames, tmp_path):
    left, right = frames
    before = left.copy(deep=True)
    ns = {"left": left, "right": right}
    _plan('left.merge(right, on="k")', ns, tmp_path)
    pd.testing.assert_frame_equal(left, before)


def test_small_inputs_are_not_sampled(tmp_path):
    df = pd.DataFrame({"f": np.arange(100_000.0)})
    with pytest.raises(dryrun_sample.NoSampleError, match="run the cell"):
        _plan('df.sort_values("f")', {"df": df}, tmp_path)


def test_text_and_category_columns_survive_the_round_trip(tmp_path):
    df = pd.DataFrame({"s": ["a", None, "b"], "c": pd.Categorical(["u", "v", "u"]), "d": pd.to_datetime(["2020-01-01"] * 3),
                       "f": [1.0, np.nan, 2.0]})  # fmt: skip
    save_frame(df, tmp_path / "t")
    back = load_object(tmp_path / "t")
    pd.testing.assert_frame_equal(back, df.reset_index(drop=True), check_dtype=False)
    assert str(back["c"].dtype) == "category"


# -- the sandbox child ----------------------------------------------------------------------------------
def _spec(tmp_path, frames_dict, recipe):
    for name, fr in frames_dict.items():
        save_frame(fr, tmp_path / "lvl" / name)
    return {"dir": str(tmp_path / "lvl"), "objects": list(frames_dict), "recipe": recipe, "csv": False,
            "result": str(tmp_path / "res.json")}  # fmt: skip


RECIPE = {"kind": "sort_values", "operands": ["df"], "kwargs": {"by": "f"}, "extra": {}}


def test_child_measures_a_run(tmp_path):
    df = pd.DataFrame({"f": np.random.default_rng(0).random(300_000)})
    out = dryrun.run_child(_spec(tmp_path, {"df": df}, RECIPE), tmp_path / "spec.json", 60, 2**31)
    assert out["status"] == "ok" and out["time_s"] > 0 and out["out_rows"] == 300_000
    assert out["delta_bytes"] is None or out["delta_bytes"] > 0


def test_a_hung_child_is_killed_at_the_timeout(tmp_path):
    t0 = time.monotonic()
    out = dryrun.run_child(
        _spec(tmp_path, {"df": pd.DataFrame({"f": [1.0]})}, RECIPE),
        tmp_path / "s.json",
        0.05,
        2**31,
    )
    assert out["status"] == "timeout" and time.monotonic() - t0 < 15


def test_a_memory_hog_is_killed_at_the_cap(tmp_path):
    out = dryrun.run_child(
        _spec(tmp_path, {"df": pd.DataFrame({"f": [1.0]})}, RECIPE),
        tmp_path / "s.json",
        60,
        10 * 2**20,
    )
    assert out["status"] == "memory_limit"  # an interpreter with pandas is far above 10 MiB


def test_a_crashing_child_is_reported_not_raised(tmp_path):
    spec = _spec(tmp_path, {"df": pd.DataFrame({"f": [1.0]})}, {**RECIPE, "kind": "nonsense"})
    out = dryrun.run_child(spec, tmp_path / "s.json", 60, 2**31)
    assert out["status"] == "error" and "nonsense" in out["error"]
    spec["dir"] = str(tmp_path / "missing")
    assert dryrun.run_child(spec, tmp_path / "s2.json", 60, 2**31)["status"] == "error"
    (tmp_path / "bad.json").write_text("{not json")
    spec2 = {"result": str(tmp_path / "r2.json")}
    (tmp_path / "s3.json").write_text(json.dumps(spec2))
    assert dryrun.run_child(spec2, tmp_path / "s3.json", 60, 2**31)["status"] == "error"


def test_run_dryrun_never_raises_and_cleans_up(frames, tmp_path):
    left, right = frames
    ns = {"left": left, "right": right, "pd": pd, "np": np}
    before = left.copy(deep=True)
    res = dryrun.run_dryrun('left.merge(right, on="k")', ns, budget_s=0.001, tmp_root=str(tmp_path))
    assert res.reason and res.ram is None
    assert not list(tmp_path.iterdir())  # temp directory removed
    res = dryrun.run_dryrun("left.sort_values('a', inplace=True)", ns)
    assert "not safe" in res.reason
    pd.testing.assert_frame_equal(left, before)


def test_an_end_to_end_dry_run_fits_and_extrapolates_a_sort(tmp_path):
    rng = np.random.default_rng(2)
    n = 3_000_000
    df = pd.DataFrame({"f": rng.random(n), "g": rng.random(n), "h": rng.integers(0, 100, n)})
    before = df.copy(deep=True)
    res = dryrun.run_dryrun(
        "df.sort_values('f')", {"df": df, "pd": pd, "np": np}, tmp_root=str(tmp_path)
    )
    assert res.kind == "sort_values" and len(res.levels) == 4 and res.overhead_s < 40
    assert res.ram is not None and res.time is not None
    ok = [q for q in (res.ram, res.time) if q.ok]
    assert ok, (res.ram.reason, res.time.reason)
    for q in ok:
        assert q.low <= q.expected <= q.high and q.laws[q.best]["cv"] <= CV_MAX
    pd.testing.assert_frame_equal(df, before)


# -- the pipeline hook --------------------------------------------------------------------------------------
def test_tier2_estimate_replaces_only_what_was_fitted():
    base = Estimate(ram_low=1, ram_expected=2, ram_high=3, time_low=0.1, time_expected=0.2, time_high=0.4,
                    confidence=0.5, tier=1)  # fmt: skip
    good = dryrun.FitResult(True, "", 100.0, 80.0, 150.0, "linear", {"linear": {"cv": 0.05}})
    bad = dryrun.FitResult(False, "no growth")
    est = dryrun.tier2_estimate(
        dryrun.DryRunResult(kind="merge", sampling="s", ram=good, time=bad), base
    )
    assert est.tier == 2 and (est.ram_low, est.ram_expected, est.ram_high) == (80, 100, 150)
    assert (est.time_low, est.time_expected, est.time_high) == (
        0.1,
        0.2,
        0.4,
    )  # kept from the base estimate
    assert "no reliable fit" in est.note and est.diagnostics["ram"]["best_law"] == "linear"
    assert dryrun.tier2_estimate(dryrun.DryRunResult(reason="x", ram=bad, time=bad), base) is None


def test_escalation_only_when_it_can_matter():
    narrow = Estimate(
        ram_low=90,
        ram_expected=100,
        ram_high=110,
        time_low=1,
        time_expected=1,
        time_high=1,
        confidence=1,
        tier=1,
    )
    wide = Estimate(
        ram_low=10,
        ram_expected=100,
        ram_high=900,
        time_low=1,
        time_expected=1,
        time_high=1,
        confidence=1,
        tier=1,
    )
    assert not dryrun.should_escalate(narrow) and dryrun.should_escalate(wide)
    assert dryrun.should_escalate(
        narrow, available_bytes=150
    )  # the upper bound is near the free RAM
    assert not dryrun.should_escalate(narrow, available_bytes=10_000)


def test_pipeline_tier_2_skips_unsafe_and_tiny_cells_without_a_dry_run(monkeypatch):
    calls = []
    monkeypatch.setattr(dryrun, "run_dryrun", lambda *a, **k: calls.append(1))
    df = pd.DataFrame({"f": np.arange(2000.0), "g": np.arange(2000.0)})
    for source in ('df.sort_values("f", inplace=True)', 'df.sort_values("f")'):
        report = Pipeline(tier=2).run(source, {"df": df.copy(), "pd": pd, "np": np})
        assert all(e.estimate.tier <= 1 for e in report.estimates)
    assert (
        calls == [] or len(calls) <= 1
    )  # the safe cell may reach run_dryrun only if it was escalated


def test_pipeline_tier_2_runs_the_dry_run_when_forced(monkeypatch):
    seen = {}

    def fake(source, ns, **kw):
        seen["source"] = source
        good = dryrun.FitResult(True, "", 5e7, 4e7, 9e7, "linear", {"linear": {"cv": 0.05}})
        return dryrun.DryRunResult(kind="sort_values", sampling="s", ram=good, time=good)

    monkeypatch.setattr(dryrun, "run_dryrun", fake)
    df = pd.DataFrame({"f": np.arange(2000.0), "g": np.arange(2000.0)})
    report = Pipeline(tier=2, tier2_escalate="always").run(
        'df.sort_values("f")', {"df": df, "pd": pd, "np": np}
    )
    item = report.estimates[0]
    assert seen["source"] == 'df.sort_values("f")' and item.estimate.tier == 2
    assert item.features["tier2"]["kind"] == "sort_values"


# -- Windows / spawn constraints ----------------------------------------------------------------------------
def _spawned_dry_run(queue):
    """Runs inside a spawned DAEMON process (like the benchmark's measured prediction worker): a
    ``multiprocessing`` child could not start children here, a ``subprocess`` sandbox can."""
    df = pd.DataFrame({"f": np.random.default_rng(0).random(400_000)})
    out = dryrun.run_child(
        {
            "dir": "",
            "objects": [],
            "recipe": RECIPE,
            "csv": False,
            "result": str(Path(__file__).with_name("_never.json")),
        },
        Path(__file__).with_name("_never_spec.json"),
        60,
        2**31,
    )
    queue.put(out["status"])
    del df


def test_the_sandbox_starts_from_inside_a_spawned_daemon_process(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_spawned_dry_run, args=(q,), daemon=True)
    p.start()
    p.join(120)
    assert p.exitcode == 0
    assert (
        q.get(timeout=5) == "error"
    )  # the child started and reported (empty spec), nothing crashed the parent
    for name in ("_never.json", "_never_spec.json"):
        Path(__file__).with_name(name).unlink(missing_ok=True)
