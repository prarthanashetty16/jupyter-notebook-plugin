"""Prediction-only v3 width baseline for an already measured val-v5 run."""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ACCESS_LOG = ROOT / "docs" / "benchmarks" / "phase8-heldout-access-log.md"


def _archive_v3(source: Path) -> Path:
    target = source / "v3"
    target.mkdir()
    data = subprocess.run(
        ["git", "archive", "--format=tar", "models-frozen-v3", "src/nexus"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        archive.extractall(target)
    return target / "src"


def _log_baseline(reason: str, point_count: int) -> None:
    ACCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACCESS_LOG.open("a", encoding="utf-8") as stream:
        stream.write(
            f"- {time.strftime('%Y-%m-%d %H:%M:%S')} | PREDICT v3 val-v5 baseline; "
            f"planned grid ids only ({point_count}); no actuals file read | reason: {reason}\n"
        )


def _prediction_rows(cache: Path, v3_src: Path, reason: str) -> list[dict[str, Any]]:
    sys.path.insert(0, str(v3_src))
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(v3_src), str(ROOT), str(ROOT / "src"), current_pythonpath) if part
    )

    from benchmarks.runner import default_mem_limit_bytes, env_info, run_prediction
    from benchmarks.suite import build_grid

    grid = build_grid("full", splits=("val-v5",))
    _log_baseline(reason, len(grid))

    from benchmarks.runner import _prepare

    cap = default_mem_limit_bytes()
    environment = env_info()
    rows = []
    for point in grid:
        point_id = str(point.id)
        path = _prepare(point, cache)
        source = point.source.format(csv=path) if "{csv" in point.source else point.source
        result = run_prediction(
            point,
            1,
            source,
            cache,
            cap,
            environment,
        )
        rows.append(
            {
                "point_id": point_id,
                "v3_has_estimate": bool(result.get("has_estimate")),
                "v3_ram_expected": result.get("ram_expected"),
                "v3_ram_high": result.get("ram_high"),
            }
        )
        print(f"[{len(rows)}/{len(grid)}] prediction complete", flush=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    from benchmarks.frozen import require_frozen
    from benchmarks.powerguard import power_record

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="val-v5 results directory")
    parser.add_argument(
        "--out",
        type=Path,
        help="baseline CSV path (default: <results>/validation/v3_predictions.csv)",
    )
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    require_frozen("models-frozen-v4")
    power_record(False, "heldout")
    results = args.results
    actuals = results / "validation" / "actuals.csv"
    if not actuals.exists():
        raise FileNotFoundError(f"no val-v5 actuals at {actuals}")
    output = args.out or results / "validation" / "v3_predictions.csv"
    if output.exists():
        raise FileExistsError(f"{output} exists; refusing to replace the baseline")

    with tempfile.TemporaryDirectory(prefix="nexus-v3-baseline-") as directory:
        v3_src = _archive_v3(Path(directory))
        rows = _prediction_rows(Path("benchmarks/.cache"), v3_src, args.reason)
    output.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output, index=False)
    print(f"wrote {len(rows)} v3 predictions to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
