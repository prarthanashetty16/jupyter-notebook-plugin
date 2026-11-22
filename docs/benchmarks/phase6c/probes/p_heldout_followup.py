"""Information only: prediction-only re-run of the 22 multicell held-out cells (no measurement).

Per cell, in a spawned child: Pipeline(tier=1) on the cached inputs, the per-operation terms
(peak range, output range, tier, args), the cell estimate (must equal the stored ``new``), and the
risk class of the frozen engine at a grid of simulated headrooms. Writes one JSON line per cell.
Run from the repository root (the 22 cells are dev data since the held-out evaluation):

    python docs/benchmarks/phase6c/probes/p_heldout_followup.py docs/benchmarks/phase6c/probes/p_heldout_followup.jsonl

Analysis of the output: ``docs/benchmarks/phase6c/heldout_followup.md``.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from benchmarks.multicell.cases import all_cells, prepare, source  # noqa: E402
from benchmarks.multicell.run import CACHE, load_inputs  # noqa: E402

MIB = 2**20
HEADROOMS_MIB = (64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384)


def child(q, paths, src):  # noqa: ANN001
    from nexus.cellpeak import cell_estimate
    from nexus.models._output import output_range
    from nexus.pipeline import Pipeline
    from nexus.risk import classify, combine

    ns = load_inputs(paths, src)
    rep = Pipeline(tier=1).run(src, ns)
    new, mode, _ = cell_estimate(src, rep.estimates)
    v1 = combine([e.estimate for e in rep.estimates])
    uncovered = len({id(o) for o in rep.ops} - {id(e.op) for e in rep.estimates})
    ops = []
    for o in rep.estimates:
        e = o.estimate
        out = output_range(o.model, o.features or {}, e)
        ops.append({
            "model": o.model, "tier": e.tier, "line": o.op.node.lineno,
            "src": ast_src(src, o.op.node), "peak": [e.ram_low, e.ram_expected, e.ram_high],
            "out": list(out) if out else None, "note": e.note,
        })  # fmt: skip
    covered = {id(e.op) for e in rep.estimates}
    missing = [ast_src(src, o.node) for o in rep.ops if id(o) not in covered]
    risk = {}
    for h in HEADROOMS_MIB:
        r = classify([e.estimate for e in rep.estimates], None, headroom=h * MIB,
                     uncovered=uncovered, drivers_from=rep.estimates or None, cell=new)  # fmt: skip
        risk[h] = r.risk.value
    q.put({
        "new": [new.ram_low, new.ram_expected, new.ram_high] if new else None,
        "v1": [v1.ram_low, v1.ram_expected, v1.ram_high] if v1 else None,
        "mode": mode, "uncovered": uncovered, "missing": missing, "ops": ops, "risk": risk,
    })  # fmt: skip


def ast_src(src: str, node) -> str:  # noqa: ANN001
    import ast

    s = ast.get_source_segment(src, node) or "?"
    return s if len(s) < 90 else s[:87] + "..."


def main() -> None:
    from benchmarks.multicell import split as split_mod

    stored = {
        json.loads(x)["id"]: json.loads(x)
        for x in open("benchmarks/results/multicell/heldout/results.jsonl", encoding="utf-8")
    }
    sp = split_mod.load()
    out = Path(sys.argv[1])
    ctx = mp.get_context("spawn")
    with out.open("w", encoding="utf-8") as fh:
        for cell in all_cells(set(sp.heldout)):
            paths = prepare(CACHE, cell.config.shape, cell.rows)
            src = source(cell, paths)
            q = ctx.Queue()
            p = ctx.Process(target=child, args=(q, paths, src))
            p.start()
            res = q.get(timeout=600)
            p.join()
            s = stored[cell.id]
            sn = [s["new"][k] for k in ("ram_low", "ram_expected", "ram_high")]
            sv = [s["v1"][k] for k in ("ram_low", "ram_expected", "ram_high")]
            res.update(id=cell.id, template=cell.config.template, shape=cell.config.shape,
                       rows=cell.rows, actual=s["actual"], same_new=res["new"] == sn,
                       same_v1=res["v1"] == sv)  # fmt: skip
            fh.write(json.dumps(res) + "\n")
            print(cell.id, "reproduced" if res["same_new"] and res["same_v1"] else "DIFFERS",
                  flush=True)  # fmt: skip


if __name__ == "__main__":
    main()
