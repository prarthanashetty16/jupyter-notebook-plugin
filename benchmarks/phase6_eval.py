"""Phase 6 dev evaluation (pre-registered: docs/benchmarks/phase6-preregistration.md).

    python -m benchmarks.phase6_eval --frozen benchmarks/results/tier2-dev-b \
        --derived benchmarks/results/phase6-dev --out docs/benchmarks/phase6

* F = the frozen models' stored Tier 0 / 1 predictions (band 0.25x .. 4x) and Tier 2 ranges;
* D = the derived models (machine profile v3) recomputed from the stored features of ``--derived``;
* D+m = D times the per-operation residual, fitted LOCO; ranges = LOCO split-conformal.
Everything is dev data (``load_joined`` refuses protected cases). Writes ``phase6_dev.md`` and CSVs.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from benchmarks.evaluate import load_joined, md_table
from nexus import calfit
from nexus.timebuckets import bucket_index

LEARN_MARGIN = 0.10  # pre-registered: >= 10% lower pooled median log error under LOCO
SIZE_BUCKETS = ((0, 64 * 2**20, "<64 MiB"), (64 * 2**20, 256 * 2**20, "64-256 MiB"),
                (256 * 2**20, math.inf, ">=256 MiB"))  # fmt: skip


def size_bucket(b: float) -> str:
    for lo, hi, name in SIZE_BUCKETS:
        if lo <= b < hi:
            return name
    return "?"


def time_metrics(d: pd.DataFrame, exp: str, lo: str | None, hi: str | None) -> dict[str, Any]:
    a, e = d["actual"], d[exp]
    rel = (e - a).abs() / a
    le = np.log(e / a).abs()
    eb, ab = e.map(bucket_index), a.map(bucket_index)
    out = {
        "n": len(d), "configs": d["case"].nunique(),
        "err_med": rel.median(), "err_p90": rel.quantile(0.9), "bias": (e / a).median(),
        "log_err_med": le.median(), "log_err_p90": le.quantile(0.9),
        "same": (eb == ab).mean(), "within_one": ((eb - ab).abs() <= 1).mean(),
        "same_n": int((eb == ab).sum()), "within_one_n": int(((eb - ab).abs() <= 1).sum()),
    }  # fmt: skip
    if lo and hi:
        out["coverage"] = ((d[lo] <= a) & (a <= d[hi])).mean()
        out["above_high"] = (a > d[hi]).mean()
        out["width"] = ((d[hi] - d[lo]) / e).mean()
    return out


def per_op(d: pd.DataFrame, exp: str, lo: str | None, hi: str | None) -> pd.DataFrame:
    rows = [{"op": op, **time_metrics(g, exp, lo, hi)} for op, g in d.groupby("op")]
    rows.append({"op": "ALL", **time_metrics(d, exp, lo, hi)})
    return pd.DataFrame(rows)


# -- data --------------------------------------------------------------------------------------
def frozen_rows(results: Path) -> pd.DataFrame:
    rows = calfit.load_time_rows(results)
    return rows[rows["tier"].isin([0, 1, 2])].copy()


def build_tier01(
    frozen: pd.DataFrame, derived_dir: Path, frozen_mains: Path | None = None
) -> pd.DataFrame:
    """One row per (point, tier) valid in both: F (recomputed on a mains profile when given; the
    stored figures are kept as ``fs_*``) and D's recomputed expected time."""
    der = calfit.tier01_frame(calfit.load_time_rows(derived_dir))
    f = frozen[frozen["tier"].isin([0, 1])][
        ["point_id", "tier", "time_low", "time_expected", "time_high"]
    ].rename(columns={"time_low": "fs_low", "time_expected": "fs_exp", "time_high": "fs_high"})
    if frozen_mains is not None:
        fm = pd.read_csv(frozen_mains).rename(
            columns={"f_exp_mains": "f_exp", "f_low_mains": "f_low", "f_high_mains": "f_high"}
        )
        f = f.merge(fm, on=["point_id", "tier"], how="inner")
    else:
        f = f.assign(f_exp=f["fs_exp"], f_low=f["fs_low"], f_high=f["fs_high"])
    d = der.merge(f, on=["point_id", "tier"], how="inner")
    d["size_bucket"] = d["input_bytes"].map(size_bucket)
    return d


# -- learned residual model (optional) ----------------------------------------------------------
def _learn_features(d: pd.DataFrame) -> pd.DataFrame:
    def frac(feats: str) -> tuple[float, float]:
        f = json.loads(feats)
        distinct = None
        for key in (
            "groups_fraction",
            "distinct_fraction",
            "key_fraction_range",
            "unique_fraction",
        ):
            v = f.get(key)
            if v is not None:
                distinct = v[1] if isinstance(v, list) else v
                break
        text = 0.0
        for num, den in (("n_text_keys", "n_keys"), ("text_cols", "n_cols")):
            if f.get(num) is not None and f.get(den):
                text = f[num] / f[den]
        if f.get("key_text"):
            text = 1.0
        return (-1.0 if distinct is None else float(distinct)), float(text)

    fr = d["features"].map(frac)
    x = pd.DataFrame({
        "log_size": np.log(d["size"].astype(float)),
        "log_bytes": np.log(d["input_bytes"].astype(float).clip(lower=1)),
        "log_expected": np.log(d["exp_cal"]),
        "distinct": fr.map(lambda t: t[0]), "text": fr.map(lambda t: t[1]),
        "tier": d["tier"].astype(float),
    })  # fmt: skip
    return pd.concat([x, pd.get_dummies(d["op"], prefix="op").astype(float)], axis=1)


def learned_loco(d: pd.DataFrame) -> pd.Series | None:
    """LOCO prediction of the remaining log residual; None if scikit-learn is not installed."""
    try:
        from sklearn.ensemble import GradientBoostingRegressor
    except ImportError:
        return None
    x = _learn_features(d)
    y = np.log(d["actual"] / d["exp_cal"])
    pred = pd.Series(0.0, index=d.index)
    for case in d["case"].unique():
        test = d["case"] == case
        model = GradientBoostingRegressor(
            n_estimators=200, max_depth=2, learning_rate=0.05, subsample=0.8, random_state=0
        )
        model.fit(x[~test], y[~test])
        pred[test] = model.predict(x[test])
    return pred


# -- RAM no-regression -------------------------------------------------------------------------
def policy_b(df: pd.DataFrame) -> pd.DataFrame:
    """Range policy B on stored rows: Tier 1 ``high`` = max(Tier 0 high, Tier 1 expected).

    The frozen run's stored Tier 1 rows hold each model's own Tier 1 range (policy A: the policy
    is applied in the pipeline since commit c95f674, after that run); the comparison needs B."""
    out = df.copy()
    t0 = out[out["tier"] == 0].set_index("point_id")["ram_high"]
    m = (out["tier"] == 1) & out["has_estimate"]
    hi0 = out.loc[m, "point_id"].map(t0)
    out.loc[m, "ram_high"] = np.maximum(
        hi0.fillna(out.loc[m, "ram_high"]), out.loc[m, "ram_expected"]
    )
    return out


def ram_check(frozen_dir: Path, derived_dir: Path) -> tuple[pd.DataFrame, int]:
    f = load_joined(frozen_dir)
    d = load_joined(derived_dir)
    keep = ["point_id", "tier", "op", "case", "ram_low", "ram_expected", "ram_high", "ram_value",
            "ram_class", "has_estimate"]  # fmt: skip
    f = policy_b(f)
    j = f[keep].merge(d[keep], on=["point_id", "tier"], suffixes=("_f", "_d"))
    j = j[(j["tier"].isin([0, 1])) & j["has_estimate_f"] & j["has_estimate_d"]]
    changed = int(
        (
            (j["ram_low_f"] != j["ram_low_d"])
            | (j["ram_expected_f"] != j["ram_expected_d"])
            | (j["ram_high_f"] != j["ram_high_d"])
        ).sum()
    )
    v = j[j["ram_class_f"] == "valid"]
    rows = []
    for (op, tier), g in [
        *v.groupby(["op_f", "tier"]),
        *(((("ALL", t), g) for t, g in v.groupby("tier"))),
    ]:
        a = g["ram_value_f"]
        row = {"op": op, "tier": int(tier), "n": len(g)}
        for s in ("f", "d"):
            row[f"above_high_{s}"] = (a > g[f"ram_high_{s}"]).mean()
            row[f"coverage_{s}"] = ((g[f"ram_low_{s}"] <= a) & (a <= g[f"ram_high_{s}"])).mean()
            row[f"width_{s}"] = (
                (g[f"ram_high_{s}"] - g[f"ram_low_{s}"]) / g[f"ram_expected_{s}"]
            ).mean()
            per_cfg = g.assign(_a=a > g[f"ram_high_{s}"]).groupby("case_f")["_a"].any()
            row[f"cfg_above_high_{s}"] = int(per_cfg.sum())
        rows.append(row)
    return pd.DataFrame(rows), changed


# -- regressions (pre-registered (d)) -----------------------------------------------------------
def regressions(before: pd.DataFrame, after: pd.DataFrame, label: str) -> list[str]:
    out = []
    b = before.set_index("op")
    for _, r in after.iterrows():
        if r["op"] not in b.index:
            continue
        o = b.loc[r["op"]]
        checks = [
            ("median rel_err", r["err_med"] - o["err_med"] > 0.02, f"{o['err_med']:.0%} -> {r['err_med']:.0%}"),
            ("p90 rel_err", r["err_p90"] - o["err_p90"] > 0.05, f"{o['err_p90']:.0%} -> {r['err_p90']:.0%}"),
            ("same bucket", r["same_n"] < o["same_n"], f"{o['same_n']} -> {r['same_n']} points"),
            ("within one", r["within_one_n"] < o["within_one_n"], f"{o['within_one_n']} -> {r['within_one_n']} points"),
        ]  # fmt: skip
        if "coverage" in r and "coverage" in o:
            inside = 0.88 <= o["coverage"] <= 0.95
            if inside and not 0.88 <= r["coverage"] <= 0.95:
                checks.append(("coverage", True, f"{o['coverage']:.0%} -> {r['coverage']:.0%}"))
        for name, bad, text in checks:
            if bad:
                out.append(f"{label} {r['op']}: {name} {text}")
    return out


def main(argv: list[str] | None = None) -> None:  # noqa: C901
    p = argparse.ArgumentParser()
    p.add_argument("--frozen", type=Path, required=True)
    p.add_argument("--derived", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frozen-mains", type=Path, help="F recomputed on a mains profile (CSV)")
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    frozen = frozen_rows(args.frozen)
    t01 = build_tier01(frozen, args.derived, args.frozen_mains)
    lines = [
        "# Phase 6 dev evaluation (DEV ONLY; LOCO; one Windows machine; machine transfer untested)",
        "",
    ]
    lines.append(f"Frozen: `{args.frozen}`; derived predictions: `{args.derived}`. {len(t01)} valid "
                 f"(point, tier) time rows, {t01['case'].nunique()} configurations.\n")  # fmt: skip

    # candidates
    cand_rows, loco = [], {}
    for tier in (0, 1):
        d = t01[t01["tier"] == tier]
        loco[(tier, "D")] = calfit.loco_tier01(d, use_residual=False)
        loco[(tier, "F")] = calfit.loco_tier01(
            d.assign(expected=d["f_exp"]), use_residual=False
        ).assign(expected=d["expected"].values)
        loco[(tier, "D+m")] = calfit.loco_tier01(d, use_residual=True)
        for name, exp in (("F (stored, old profile)", d["fs_exp"]), ("F", d["f_exp"]), ("D", d["expected"]),
                          ("D+m", loco[(tier, "D+m")]["exp_cal"])):  # fmt: skip
            m = time_metrics(d.assign(_e=exp.values), "_e", None, None)
            cand_rows.append({"tier": tier, "candidate": name, **m})
    cand = pd.DataFrame(cand_rows)
    meets = {}
    for k in ("D", "D+m"):
        meets[k] = all(
            (c := cand[(cand["tier"] == tier)].set_index("candidate")).loc[k, "within_one"] >= 0.95
            and c.loc[k, "same_n"] >= c.loc["F", "same_n"]
            for tier in (0, 1)
        )
    c1 = cand[cand["tier"] == 1].set_index("candidate")
    ok = [k for k, v in meets.items() if v]
    chosen_name = min(ok, key=lambda k: c1.loc[k, "log_err_med"]) if ok else "F"
    sel = {0: chosen_name, 1: chosen_name}
    lines += ["## 1. Candidate selection (pre-registered: lowest pooled LOCO median log error subject "
              "to within-one >= 95% and same-bucket not below F)", "",
              md_table(cand[["tier", "candidate", "n", "log_err_med", "log_err_p90", "err_med", "err_p90",
                             "bias", "same", "same_n", "within_one"]], ("err_med", "err_p90", "same", "within_one")),
              "", "Target (a) met at BOTH tiers: " + ", ".join(f"{k}: {'yes' if v else 'NO'}" for k, v in meets.items())
              + f". Selected (one candidate for the stack): **{chosen_name}**"
              + (" -> pre-registered outcome: time-model calibration FAILED, F kept." if chosen_name == "F" else ".")
              + "", ""]  # fmt: skip

    # per op before / after with calibrated ranges
    regs: list[str] = []
    tables = {}
    for tier in (0, 1):
        chosen = loco[(tier, sel[tier])]
        before = per_op(chosen, "f_exp", "f_low", "f_high")
        after = per_op(chosen, "exp_cal", "low_cal", "high_cal")
        tables[tier] = (before, after, chosen)
        regs += regressions(before, after, f"Tier {tier}")
        cols = [
            "op",
            "n",
            "configs",
            "err_med",
            "err_p90",
            "bias",
            "same",
            "within_one",
            "coverage",
            "width",
        ]
        lines += [f"## 2.{tier + 1} Tier {tier} time per operation: BEFORE (frozen F, band 0.25x-4x)", "",
                  md_table(before[cols], ("err_med", "err_p90", "same", "within_one", "coverage")), "",
                  f"AFTER (selected {sel[tier]}, LOCO conformal ranges)", "",
                  md_table(after[cols], ("err_med", "err_p90", "same", "within_one", "coverage")), ""]  # fmt: skip
        kinds = chosen.groupby("op")["range_kind"].first().to_dict()
        lines.append(
            "Range kind per operation: " + ", ".join(f"{k}: {v}" for k, v in kinds.items()) + "\n"
        )
        chosen.to_csv(args.out / f"tier{tier}_loco.csv", index=False)

    # coverage by configuration and size bucket (Tier 1)
    chosen = tables[1][2]
    cov_cfg = chosen.assign(
        hit=(chosen["low_cal"] <= chosen["actual"]) & (chosen["actual"] <= chosen["high_cal"])
    )
    by_cfg = cov_cfg.groupby(["op", "case"])["hit"].agg(["mean", "size"]).reset_index()
    by_size = cov_cfg.groupby(["op", "size_bucket"])["hit"].agg(["mean", "size"]).reset_index()
    by_size_all = cov_cfg.groupby("size_bucket")["hit"].agg(["mean", "size"]).reset_index()
    zero = by_cfg[by_cfg["mean"] == 0]
    lines += ["## 3. Tier 1 coverage by size bucket and by configuration", "",
              md_table(by_size_all.rename(columns={"mean": "coverage", "size": "n"}), ("coverage",)), "",
              md_table(by_size.rename(columns={"mean": "coverage", "size": "n"}), ("coverage",)), "",
              f"Configurations with every point outside the range: {len(zero)} of {len(by_cfg)}"
              + (": " + ", ".join(zero["case"]) if len(zero) else "") + "", ""]  # fmt: skip
    by_cfg.to_csv(args.out / "tier1_coverage_by_configuration.csv", index=False)

    # fitted residuals
    res_rows = []
    for tier in (0, 1):
        d = t01[t01["tier"] == tier]
        for op, g in d.groupby("op"):
            res_rows.append({"tier": tier, "op": op, "configs": g["case"].nunique(),
                             "D_bias": (g["expected"] / g["actual"]).median(),
                             "F_bias": (g["f_exp"] / g["actual"]).median(),
                             "residual_all": calfit.residual_multiplier(np.log(g["actual"] / g["expected"]))})  # fmt: skip
    lines += ["## 4. What the derivation explained: bias of F and D (median expected/actual) and the fitted "
              "residual (multiplier applied to D, fitted on all configurations)", "",
              md_table(pd.DataFrame(res_rows)), ""]  # fmt: skip

    # learned residual (both tiers: Amendment 1 (iv))
    learn_ok = True
    lines += [
        "## 5. Learned residual model (gradient-boosted trees on top of the selected candidate, LOCO)",
        "",
    ]
    for tier in (0, 1):
        ch = tables[tier][2]
        learned = learned_loco(ch)
        if learned is None:
            lines += ["scikit-learn not installed: not evaluated.", ""]
            learn_ok = False
            break
        base = np.log(ch["exp_cal"] / ch["actual"]).abs()
        new_exp = ch["exp_cal"] * np.exp(learned)
        new = np.log(new_exp / ch["actual"]).abs()
        mb = time_metrics(ch, "exp_cal", None, None)
        ml = time_metrics(ch.assign(_e=new_exp), "_e", None, None)
        gain = 1 - new.median() / base.median()
        ok = gain >= LEARN_MARGIN and new.quantile(0.9) <= base.quantile(0.9) and             ml["within_one_n"] >= mb["within_one_n"] and ml["same_n"] >= mb["same_n"]  # fmt: skip
        learn_ok = learn_ok and ok
        lines += [f"Tier {tier}: pooled median log error {base.median():.3f} -> {new.median():.3f} ({gain:+.1%}; needs "
                  f">= {LEARN_MARGIN:.0%}), p90 {base.quantile(0.9):.3f} -> {new.quantile(0.9):.3f}, same bucket "
                  f"{mb['same_n']} -> {ml['same_n']} points, within one {mb['within_one_n']} -> {ml['within_one_n']}: "
                  f"{'meets' if ok else 'does NOT meet'} the conditions.", ""]  # fmt: skip
    lines += [
        f"**Learned residual {'INCLUDED' if learn_ok else 'NOT included'}** (must meet the conditions at both tiers).",
        "",
    ]

    # Tier 2
    t2 = calfit.tier2_frame(frozen)
    t2l = calfit.loco_tier2(t2)
    b2 = per_op(t2l, "expected", "low", "high")
    a2 = per_op(t2l, "expected", "low_cal", "high_cal")
    regs += regressions(b2, a2, "Tier 2")
    cols = ["op", "n", "configs", "coverage", "above_high", "width"]
    lines += ["## 6. Tier 2 time ranges (accepted time fits; expected unchanged)", "", "BEFORE", "",
              md_table(b2[cols], ("coverage", "above_high")), "", "AFTER (LOCO conformal on normalised scores)", "",
              md_table(a2[cols], ("coverage", "above_high")), "",
              "Range kind: " + ", ".join(f"{k}: {v}" for k, v in t2l.groupby("op")["range_kind"].first().items()), ""]  # fmt: skip
    t2l.to_csv(args.out / "tier2_loco.csv", index=False)

    # RAM
    ram, changed = ram_check(args.frozen, args.derived)
    lines += ["## 7. RAM no-regression (policy B unchanged; stored F vs re-run D predictions)", "",
              f"(point, tier) rows whose RAM low / expected / high changed: **{changed}**.", "",
              md_table(ram, tuple(c for c in ram.columns if c.startswith(("above_high", "coverage")))), ""]  # fmt: skip
    for _, r in ram.iterrows():
        if r["above_high_d"] > r["above_high_f"] or r["cfg_above_high_d"] > r["cfg_above_high_f"]:
            regs.append(
                f"RAM tier {r['tier']} {r['op']}: above_high {r['above_high_f']:.1%} -> {r['above_high_d']:.1%}"
            )
        if r["width_d"] > r["width_f"] + 1e-9:
            regs.append(
                f"RAM tier {r['tier']} {r['op']}: width {r['width_f']:.2f} -> {r['width_d']:.2f}"
            )

    lines += ["## 8. Regressions (pre-registered (d)); decisions are in docs/PROGRESS.md", ""]
    lines += [f"- {r}" for r in regs] or ["- none"]
    (args.out / "phase6_dev.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = {
        "selected": sel,
        "learned_included": bool(learn_ok),
        "regressions": regs,
        "ram_rows_changed": changed,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
