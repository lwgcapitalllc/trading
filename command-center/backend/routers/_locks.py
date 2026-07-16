"""Shared platform lock gate for VPS-backed job triggers.

One physical terminal per platform — a single NT8 Strategy Analyzer and a single
MT5 Strategy Tester. So each platform runs at most one job at a time (backtest,
sweep, or optimization), but the two platforms are fully independent: an MT5 job
never blocks an NT8 job and vice versa.

Every endpoint that starts or re-fires a VPS job calls `ensure_platform_idle()`
with the job's runner before creating it. This is the single source of truth for
the lock — gates must not read `lab_progress.json` (that file is for the progress
bar only and is shared across both platforms).
"""
from fastapi import HTTPException

from services import lab_db


_LABELS = {"mt5": "MT5", "python": "Python"}


def ensure_platform_idle(runner: str) -> None:
    """Raise 409 if the platform for `runner` already has a job running."""
    if lab_db.has_running_job(runner):
        label = _LABELS.get(runner, "NT8")
        raise HTTPException(409, f"An {label} job is already running — wait for it to finish.")
