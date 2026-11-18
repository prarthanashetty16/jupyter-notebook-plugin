"""Helper process for the kill-and-resume test: ``python -m tests._resume_worker <out_dir>``."""

from __future__ import annotations

import sys
from pathlib import Path

from benchmarks.runner import RunConfig, run_suite
from benchmarks.suite import BASE, FrameInput, GridPoint


def points(n: int = 4) -> list[GridPoint]:
    return [
        GridPoint(
            id=f"resume/case{i}|n=2000",
            case=f"drop_duplicates/mixed_dup{i}",
            op="drop_duplicates",
            source="df.drop_duplicates()",
            size=2000,
            inputs=(FrameInput(BASE.with_(n_rows=2000, seed=70 + i)),),
            repeats=1,
            footprint_factor=3.0,
        )
        for i in range(n)
    ]


if __name__ == "__main__":
    run_suite(
        RunConfig(suite="small", out_dir=Path(sys.argv[1]), calibrate=False, plan_with_model=False),
        points(),
    )
