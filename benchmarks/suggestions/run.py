"""Run and evaluate the suggestion benchmark (Phase 5, pre-registration B3 / B4).

For every cell (configuration x rows): measure the original cell's peak RAM in fresh spawned processes
(inputs loaded from disk, the validated ``nexus.measure`` instrument), keep it only if it is "risky"
(>= 200 MiB), ask the NEXUS engine for suggestions (in a child, read-only), measure each candidate's
peak, and compare outputs in a separate child. Rows go to ``results.jsonl`` (resumable). The dev run
and the held-out run use the same code; the held-out run is opt-in and prints only ids and status.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from benchmarks.suggestions import cases, split, workers
from nexus.measure import OK, measure_call

MIB = 2**20
RISKY_MIN = 200 * MIB
MEANINGFUL_FRAC, MEANINGFUL_BYTES = 0.20, 64 * MIB
HARM_FACTOR = 1.10
CACHE = Path(__file__).resolve().parents[1] / ".cache" / "suggestions"
RESULTS = Path(__file__).resolve().parents[1] / "results" / "suggestions"
ACCESS_LOG = (
    Path(__file__).resolve().parents[2] / "docs" / "benchmarks" / "phase5-heldout-access-log.md"
)
CAP_BYTES = int(2.4 * 2**30)


def _cells(keys: tuple[str, ...]) -> list[tuple[cases.Config, int]]:
    wanted = set(keys)
    return [(c, n) for c in cases.all_configs() if c.key in wanted for n in c.sizes]


def cell_id(c: cases.Config, n: int) -> str:
    return f"{c.key}@{n}"


def _prepare(c: cases.Config, n: int) -> tuple[dict[str, str], str]:
    """Cache the inputs of a cell on disk; returns ({frame name: pickle path}, cell source)."""
    shape = cases.SHAPES[c.shape]
    base = CACHE / f"{c.shape}_{n}"
    base.mkdir(parents=True, exist_ok=True)
    frames: dict[str, str] = {}
    source = cases.TEMPLATES[c.template]
    if shape.csv_cols:
        path = base / "data.csv"
        if not path.exists():
            cases.build_csv(shape, n, str(path))
        return {}, source.replace("PATH", repr(str(path)))
    if not (base / "left.pkl").exists():
        for name, df in cases.build_frames(shape, n).items():
            df.to_pickle(base / f"{name}.pkl")
    for p in sorted(base.glob("*.pkl")):
        frames[p.stem] = str(p)
    return frames, source


def _measure(source: str, frames: dict[str, str]) -> dict[str, Any]:
    m = measure_call(
        workers.run_cell, setup=workers.load_env, setup_args=({"frames": frames, "source": source},),
        summarize=workers.summarize, repeats=3, max_rss_bytes=CAP_BYTES, run_timeout_s=600,
    )  # fmt: skip
    ok = [r for r in m.runs if r.status == OK]
    return {
        "status": m.status, "delta": m.delta_bytes, "censored": m.censored, "bound": m.bound_bytes,
        "time_s": m.time_s, "spread": m.ram_spread, "repeats_ok": len(ok),
        "avail_start": min((r.avail_start_bytes for r in ok), default=None),
    }  # fmt: skip


def _child(
    func: Any, frames: dict[str, str], source: str, summarize: Any = workers.as_info
) -> dict[str, Any]:
    m = measure_call(func, setup=workers.load_env, setup_args=({"frames": frames, "source": source},),
                     summarize=summarize, repeats=1, max_rss_bytes=CAP_BYTES, run_timeout_s=900)  # fmt: skip
    return m.info if m.status == OK else {"error": m.status}


def _done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.add(r["row_id"])
    return out


def _append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def run(
    heldout: bool = False,
    reason: str = "",
    results: Path = RESULTS,
    limit: int | None = None,
    base_only: bool = False,
) -> int:
    if base_only and heldout:
        raise SystemExit("--base-only is for dev design checks only")
    sp = split.load()
    keys = sp.heldout if heldout else sp.dev
    if heldout and not reason:
        raise SystemExit("--heldout needs --reason (it is logged)")
    out_dir = results / ("heldout" if heldout else "dev")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "results.jsonl"
    done = _done(path)
    env = {"date": str(date.today())}
    count = 0
    for c, n in _cells(keys):
        cid = cell_id(c, n)
        if f"{cid}|base" in done:
            continue
        if limit is not None and count >= limit:
            break
        count += 1
        t0 = time.time()
        frames, source = _prepare(c, n)
        if c.family == "delete_unreferenced":
            row = _delete_cell(c, n, cid, frames, source)
            _append(path, row)
            _log(heldout, cid, "done", t0)
            continue
        base = _measure(source, frames)
        risky = base["status"] == OK and not base["censored"] and (base["delta"] or 0) >= RISKY_MIN
        _append(path, {"row_id": f"{cid}|base", "kind": "base", "cell": cid, "config": c.key, "family": c.family,
                       "template": c.template, "shape": c.shape, "n": n, "source": source, "base": base,
                       "risky": risky, **env})  # fmt: skip
        if not risky or base_only:
            _log(heldout, cid, f"not risky ({base['status']})", t0)
            continue
        info = _child(workers.suggest_child, frames, source)
        for i, s in enumerate(info.get("suggestions", [])):
            if s["kind"] != "peak":
                continue
            mod = _measure(s["modified_source"], frames)
            ver = (
                _child(workers.verify, frames, source + "\0" + s["modified_source"])
                if mod["status"] == OK
                else {}
            )
            _append(path, {"row_id": f"{cid}|s{i}", "kind": "suggestion", "cell": cid, "config": c.key,
                           "family": c.family, "template": c.template, "n": n, "source": source,
                           "suggestion": s, "base": base, "mod": mod, "verify": ver, **env})  # fmt: skip
        _log(heldout, cid, f"{len(info.get('suggestions', []))} candidates", t0)
    return 0


def _delete_cell(
    c: cases.Config, n: int, cid: str, frames: dict[str, str], source: str
) -> dict[str, Any]:
    """delete_unreferenced frees headroom, not the cell's peak: only the rule's output is recorded."""
    info = _child(workers.suggest_child, frames, source)
    sugs = [s for s in info.get("suggestions", []) if s["rule"] == "delete_unreferenced"]
    return {"row_id": f"{cid}|base", "kind": "delete", "cell": cid, "config": c.key, "family": c.family,
            "template": c.template, "n": n, "source": source, "suggestions": sugs}  # fmt: skip


def _log(heldout: bool, cid: str, status: str, t0: float) -> None:
    if heldout:  # held-out: only ids, status and elapsed time
        status = status.split(" ")[0]
    print(f"[suggestions] {cid}: {status} ({time.time() - t0:.0f} s)", flush=True)


# -- evaluation -----------------------------------------------------------------------------------
def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _measured(row: dict[str, Any]) -> dict[str, Any] | None:
    """Measured peaks and saving of one suggestion row; None when the baseline is unusable."""
    b, m = row["base"], row["mod"]
    if b["status"] != OK or b["censored"] or b["delta"] is None or m["status"] != OK:
        return None
    orig = float(b["delta"])
    if m["censored"] or m["delta"] is None:  # the OS peak counter cannot see below the load peak
        mod, lower_bound = float(m["bound"]), True
    else:
        mod, lower_bound = float(m["delta"]), False
    return {"orig": orig, "mod": mod, "saving": orig - mod, "saving_frac": (orig - mod) / max(orig, 1.0),
            "lower_bound": lower_bound, "harm": (not lower_bound) and mod > HARM_FACTOR * orig,
            "increased": (not lower_bound) and mod > orig}  # fmt: skip


def _predicted(s: dict[str, Any]) -> float | None:
    if s["before"] is None:
        return None
    return float(s["saving_frac"])


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    sug = [r for r in rows if r["kind"] == "suggestion"]
    base = [r for r in rows if r["kind"] == "base"]
    items = []
    for r in sug:
        s, meas = r["suggestion"], _measured(r)
        if meas is None:
            continue
        v = r.get("verify", {})
        items.append({**r, "meas": meas, "v": v, "pred_frac": _predicted(s), "shown": s["shown"]})
    shown = [i for i in items if i["shown"]]
    bugs = [i for i in items if i["suggestion"]["semantics"] == "preserving"
            and i["v"].get("comparable") and not i["v"].get("identical")]  # fmt: skip
    harm = [i for i in shown if i["meas"]["harm"]]
    inc = [i for i in items if i["meas"]["increased"]]
    err = [i["meas"]["saving_frac"] - i["pred_frac"] for i in shown
           if i["pred_frac"] is not None and not i["meas"]["lower_bound"]]  # fmt: skip
    meaningful = [i for i in shown if i["meas"]["saving"] >= MEANINGFUL_BYTES
                  and i["meas"]["saving_frac"] >= MEANINGFUL_FRAC]  # fmt: skip
    return {"base": base, "items": items, "shown": shown, "bugs": bugs, "harm": harm, "increased": inc,
            "err": err, "meaningful": meaningful}  # fmt: skip


def _pct(x: float) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1%}"


def _quant(v: list[float], q: float) -> float:
    return float(pd.Series(v).quantile(q)) if v else math.nan


def report(rows: list[dict[str, Any]], title: str, source: str) -> str:
    a = analyse(rows)
    err_abs = [abs(e) for e in a["err"]]
    n_cells = len(a["base"])
    n_risky = len([b for b in a["base"] if b["risky"]])
    shown, items = a["shown"], a["items"]
    s1 = not a["bugs"]
    s2 = not a["harm"]
    med, p90 = _quant(err_abs, 0.5), _quant(err_abs, 0.9)
    s3 = bool(err_abs) and med <= 0.15 and p90 <= 0.35
    share = len(a["meaningful"]) / len(shown) if shown else math.nan
    s4 = bool(shown) and share >= 0.8
    lines = [
        f"# {title}\n",
        f"Source: `{source}`. Pre-registered criteria: `docs/benchmarks/phase5-preregistration.md` Part B4. "
        "RAM = peak above baseline of the cell in fresh spawned processes (median of 3), inputs loaded from disk. "
        "Saving fractions are relative to the unmodified cell's measured peak. A modified run whose peak the OS "
        "counter cannot resolve (censored) gives only a LOWER BOUND on the saving and is excluded from S3.\n",
        "## Verdicts\n",
        f"* cells run: {n_cells}; risky (original peak >= 200 MiB): {n_risky}; candidates measured: {len(items)}; shown by the filters: {len(shown)}.",
        f"* **S1 no `preserving` bug:** {'PASS' if s1 else 'FAIL'} ({len(a['bugs'])} cases).",
        f"* **S2 do no harm (shown, >{HARM_FACTOR - 1:.0%} more RAM):** {'PASS' if s2 else 'FAIL'} ({len(a['harm'])} of {len(shown)} shown; "
        f"any measured increase among ALL candidates, shown or not: {len(a['increased'])}).",
        f"* **S3 predicted vs measured saving (pp of the original peak):** {'PASS' if s3 else 'FAIL' if err_abs else 'NOT EVALUATED'} - "
        f"n={len(err_abs)}, signed bias {_pct(_quant(a['err'], 0.5))}, median |error| {_pct(med)}, p90 |error| {_pct(p90)} "
        "(targets <= 15% and <= 35%).",
        f"* **S4 shown suggestions with a measured saving >= 20% and >= 64 MiB:** {'PASS' if s4 else 'FAIL' if shown else 'NOT EVALUATED'} "
        f"({len(a['meaningful'])} of {len(shown)} = {_pct(share)}; target >= 80%).\n",
    ]
    lines.append("## Per rule (shown suggestions)\n")
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i in items:
        by[i["family"]].append(i)
    lines.append(
        "| rule family | candidates | shown | measured saving, shown (median) | predicted, shown (median) | harm | bugs |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for fam in sorted(by):
        g = by[fam]
        sh = [i for i in g if i["shown"]]
        ms = [i["meas"]["saving_frac"] for i in sh]
        ps = [i["pred_frac"] for i in sh if i["pred_frac"] is not None]
        note = "" if len(sh) >= 3 else " (fewer than 3 shown: no rule-level claim)"
        lines.append(f"| {fam} | {len(g)} | {len(sh)}{note} | {_pct(statistics.median(ms)) if ms else 'n/a'} | "
                 f"{_pct(statistics.median(ps)) if ps else 'n/a'} | {sum(i['meas']['harm'] for i in sh)} | "
                 f"{sum(1 for i in a['bugs'] if i['family'] == fam)} |")  # fmt: skip
    lines.append("\n## Every measured candidate\n")
    lines.append(
        "| cell | rule | label | shown (why not) | predicted saving | measured saving | measured vs original MiB | outputs identical | dtype changes | max abs err |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for i in sorted(items, key=lambda x: (x["cell"], x["suggestion"]["rule"])):
        s, m, v = i["suggestion"], i["meas"], i["v"]
        lb = ">=" if m["lower_bound"] else ""
        why = "yes" if s["shown"] else f"no: {s['hidden_reason']}"
        lines.append(f"| {i['cell']} | {s['rule']} | {s['semantics']} | {why} | {_pct(i['pred_frac'])} | {lb}{_pct(m['saving_frac'])} | "
                 f"{m['orig'] / MIB:.0f} -> {'<=' if m['lower_bound'] else ''}{m['mod'] / MIB:.0f} | "
                 f"{v.get('identical', 'n/a')} | {len(v.get('dtype_changes', []))} | {v.get('max_abs_err', 'n/a')} |")  # fmt: skip
    lines.append(f"\n## `preserving` suggestions whose output differed ({len(a['bugs'])})\n")
    lines += [f"* {i['cell']} / {i['suggestion']['rule']}: {i['v']}" for i in a["bugs"]] or ["none"]
    lines.append(f"\n## Candidates that INCREASED measured RAM ({len(a['increased'])})\n")
    lines += [
        f"* {i['cell']} / {i['suggestion']['rule']} ({'shown' if i['shown'] else 'hidden by: ' + i['suggestion']['hidden_reason']}): "
        f"{i['meas']['orig'] / MIB:.0f} -> {i['meas']['mod'] / MIB:.0f} MiB"
        for i in a["increased"]
    ] or ["none"]
    deletes = [r for r in rows if r["kind"] == "delete"]
    lines.append("\n## delete_unreferenced (not measured for peak: it frees headroom)\n")
    lines += [
        f"* {r['cell']}: {[s['title'] for s in r['suggestions']] or 'no suggestion'}"
        for r in deletes
    ] or ["none"]
    return "\n".join(lines) + "\n"


def evaluate_dev(results: Path = RESULTS, out: Path | None = None) -> str:
    path = results / "dev" / "results.jsonl"
    rows = _rows(path)
    sp = split.load()
    if any(r["config"] in set(sp.heldout) for r in rows):
        raise SystemExit("held-out configurations found in the dev results: refusing to evaluate")
    text = report(rows, "Suggestion benchmark: DEV configurations", str(path))
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "suggestions_dev.md").write_text(text, encoding="utf-8")
    return text


def evaluate_heldout(reason: str, results: Path = RESULTS, out: Path | None = None) -> str:
    if not reason.strip():
        raise SystemExit("evaluating the held-out part needs --reason (it is logged)")
    path = results / "heldout" / "results.jsonl"
    rows = _rows(path)
    sp = split.load()
    if any(r["config"] not in set(sp.heldout) for r in rows):
        raise SystemExit("non-held-out configurations found in the held-out results")
    text = report(rows, "Suggestion benchmark: HELD-OUT configurations", str(path))
    ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACCESS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"- {date.today()}: held-out suggestion results read. Reason: {reason}\n")
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "suggestions_heldout.md").write_text(text, encoding="utf-8")
    return text
