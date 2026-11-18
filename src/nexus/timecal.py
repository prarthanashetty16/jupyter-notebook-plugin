"""Apply the shipped time calibration to an estimate (Phase 6; RAM is never touched here).

The artifact (``nexus/calibration/calibration-v1.json``, written by ``nexus-calibrate``) holds, per
model and tier, a residual multiplier of the derived expected time and conformal log-quantiles of
the remaining error (``nexus.calfit``). Behaviour, as pre-registered (section 4 and 6):

* artifact present and valid: ``expected *= residual``; ``[low, high] = expected * exp(q_lo, q_hi)``
  (per operation, or the generic band with the flag "generic time range");
* artifact absent, unreadable or of another format: expected unchanged, the uncalibrated band
  (0.25x .. 4x) widened 3x each side, flag "no time calibration";
* machine not calibrated (``nexus.machine``): range widened 3x each side, flag
  "uncalibrated machine";
* installed pandas outside the artifact's validated versions: one warning per session, range
  widened 2x each side, flag "unvalidated pandas version" (RAM unchanged, flag shown).

A user-local artifact is used only when ``NEXUS_CALIBRATION=local`` (opt-in); another path can be
given as ``NEXUS_CALIBRATION=<file>``. Never raises: on any problem the estimate is returned with
the "no time calibration" behaviour.
"""

from __future__ import annotations

import functools
import json
import logging
import math
import os
import sys
import warnings
from dataclasses import replace
from importlib import resources
from pathlib import Path
from typing import Any

import pandas as pd

from nexus.machine import UNCALIBRATED_FLAG, machine
from nexus.models.base import Estimate

log = logging.getLogger("nexus")

ENV_VAR = "NEXUS_CALIBRATION"
ARTIFACT_NAME = "calibration-v1.json"
SUPPORTED_FORMAT = 1
UNCALIBRATED_BAND = (0.25, 4.0)
NO_ARTIFACT_WIDEN = 3.0
UNCALIBRATED_MACHINE_WIDEN = 3.0
UNVALIDATED_PANDAS_WIDEN = 2.0
FLAG_NO_ARTIFACT = "no time calibration"
FLAG_GENERIC = "generic time range"
FLAG_PANDAS = "unvalidated pandas version"
FLAG_BAND = "time range not calibrated"  # the dev coverage rule kept the 0.25x .. 4x band


def local_artifact_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "nexus" / ARTIFACT_NAME


def _read_artifact() -> tuple[dict[str, Any] | None, str]:
    choice = os.environ.get(ENV_VAR, "")
    try:
        if choice == "local":
            text, where = local_artifact_path().read_text(), "local"
        elif choice:
            text, where = Path(choice).read_text(), choice
        else:
            ref = resources.files("nexus.calibration").joinpath(ARTIFACT_NAME)
            text, where = ref.read_text(), "packaged"
        art = json.loads(text)
    except (OSError, ValueError) as exc:
        return None, f"artifact unreadable ({type(exc).__name__})"
    if not isinstance(art, dict) or art.get("format") != SUPPORTED_FORMAT:
        return None, f"artifact format {art.get('format') if isinstance(art, dict) else '?'} "
    return art, where


@functools.lru_cache(maxsize=1)
def artifact() -> dict[str, Any] | None:
    """The validated artifact, or None (absent, unreadable, outdated format)."""
    art, why = _read_artifact()
    if art is None:
        log.debug("nexus: no time calibration: %s", why)
    return art


def pandas_validated(art: dict[str, Any] | None, version: str | None = None) -> bool:
    if art is None:
        return True  # nothing validated: the "no time calibration" flag already says so
    parts = (version or pd.__version__).split(".")
    return f"{parts[0]}.{parts[1]}" in set(art.get("validated_pandas") or [])


@functools.lru_cache(maxsize=1)
def _warn_pandas_once(version: str) -> None:
    warnings.warn(
        f"nexus: pandas {version} is outside the versions the time calibration was validated on; "
        "time ranges are widened and marked 'unvalidated pandas version'",
        stacklevel=3,
    )


def _with_flags(est: Estimate, flags: list[str]) -> Estimate:
    merged = tuple(dict.fromkeys([*est.flags, *flags]))
    return replace(est, flags=merged)


def _widen(low: float, exp: float, high: float, factor: float) -> tuple[float, float, float]:
    return low / factor, exp, high * factor


def calibrate(model: str, est: Estimate) -> Estimate:
    """Calibrated Tier 0 / Tier 1 time of ``est`` from model ``model``."""
    try:
        return _calibrate(model, est)
    except Exception:
        log.debug("nexus: time calibration failed", exc_info=True)
        lo, e, hi = _widen(est.time_expected * UNCALIBRATED_BAND[0], est.time_expected,
                           est.time_expected * UNCALIBRATED_BAND[1], NO_ARTIFACT_WIDEN)  # fmt: skip
        return _with_flags(replace(est, time_low=lo, time_high=hi), [FLAG_NO_ARTIFACT])


def _calibrate(model: str, est: Estimate) -> Estimate:
    art = artifact()
    flags: list[str] = []
    exp = est.time_expected
    if art is None:
        lo, hi = exp * UNCALIBRATED_BAND[0], exp * UNCALIBRATED_BAND[1]
        lo, exp, hi = _widen(lo, exp, hi, NO_ARTIFACT_WIDEN)
        flags.append(FLAG_NO_ARTIFACT)
    else:
        tier = str(min(int(est.tier), 1))
        entry = (art.get("tier01") or {}).get(tier, {}).get(model)
        generic = (art.get("tier01_generic") or {}).get(tier) or {}
        if entry is None:  # a model the artifact was not fitted on
            q_lo, q_hi = generic["q_lo"], generic["q_hi"]
            flags.append(FLAG_GENERIC)
        else:
            exp = exp * float(entry.get("residual", 1.0))
            if entry.get("range") == "per-operation":
                q_lo, q_hi = entry["q_lo"], entry["q_hi"]
            elif entry.get("range") == "band":
                q_lo, q_hi = math.log(UNCALIBRATED_BAND[0]), math.log(UNCALIBRATED_BAND[1])
                flags.append(FLAG_BAND)
            else:
                q_lo, q_hi = generic["q_lo"], generic["q_hi"]
                flags.append(FLAG_GENERIC)
        lo, hi = exp * math.exp(q_lo), exp * math.exp(q_hi)
    lo, exp, hi = _common(lo, exp, hi, art, flags)
    return _with_flags(replace(est, time_low=lo, time_expected=exp, time_high=hi), flags)


def _common(
    lo: float, exp: float, hi: float, art: dict[str, Any] | None, flags: list[str]
) -> tuple[float, float, float]:
    if not machine().calibrated:
        lo, exp, hi = _widen(lo, exp, hi, UNCALIBRATED_MACHINE_WIDEN)
        flags.append(UNCALIBRATED_FLAG)
    if not pandas_validated(art):
        _warn_pandas_once(pd.__version__)
        lo, exp, hi = _widen(lo, exp, hi, UNVALIDATED_PANDAS_WIDEN)
        flags.append(FLAG_PANDAS)
    return min(lo, exp), exp, max(hi, exp)


def calibrate_tier2(model: str, low: float, expected: float, high: float) -> tuple[
    tuple[float, float, float], list[str]
]:  # fmt: skip
    """Calibrated Tier 2 time range (its own range raised to the fitted exponent ``q``)."""
    flags: list[str] = []
    try:
        art = artifact()
        if art is None:
            return _widen(low, expected, high, NO_ARTIFACT_WIDEN), [FLAG_NO_ARTIFACT]
        entry = (art.get("tier2") or {}).get(model)
        if entry is not None and entry.get("range") == "per-operation":
            q = float(entry["q"])
        else:
            q = float((art.get("tier2_generic") or {}).get("q", 1.0))
            flags.append(FLAG_GENERIC)
        e = max(expected, 1e-12)
        lo = e * (max(low, 1e-12) / e) ** q
        hi = e * (max(high, e) / e) ** q
        lo, e, hi = _common(lo, e, hi, art, flags)
        return (lo, e, hi), flags
    except Exception:
        log.debug("nexus: tier 2 time calibration failed", exc_info=True)
        return _widen(low, expected, high, NO_ARTIFACT_WIDEN), [FLAG_NO_ARTIFACT]
