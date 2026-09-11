"""Shared platform lock gate for VPS-backed job triggers.

One physical terminal per platform — a single NT8 Strategy Analyzer and a single
MT5 Strategy Tester. So each platform runs at most one job at a time (backtest,
sweep, or optimization), but the two platforms are fully independent: an MT5 job
never blocks an NT8 job and vice versa.

Every endpoint that starts or re-fires a VPS job calls `ensure_platform_idle()`
with the job's runner before creating it. This is the single source of truth for
the lock — gates must not read `lab_progress.json` (that file is for the progress
bar only and is shared across both platforms).

It is also the one place an NT8 job is refused while NinjaTrader is switched off on
purpose (`services/nt8_switch.py`) — every trigger already passes through here, so a
refusal written once covers backtests, sweeps, optimizations and their retries, before
a run row exists to fail.
"""

from fastapi import HTTPException
from services import lab_db, nt8_switch

_LABELS = {"mt5": "MT5", "python": "Python"}


def ensure_platform_idle(runner: str) -> None:
    """Raise 503 if NT8 is switched off for an NT8 job, 409 if the platform is busy."""
    # Anything that is not MT5 or Python is NT8 — the same fallback `has_running_job` uses.
    # ⚠ Only `True` refuses: `None` (the box not asked yet) lets the job try, as before.
    if runner not in _LABELS and nt8_switch.switched_off() is True:
        raise HTTPException(503, f"{nt8_switch.off_reason()} NT8 jobs can't run until it's back.")
    if lab_db.has_running_job(runner):
        label = _LABELS.get(runner, "NT8")
        raise HTTPException(409, f"An {label} job is already running — wait for it to finish.")
