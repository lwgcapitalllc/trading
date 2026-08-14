"""History limits — how early a backtest window may start, per instrument.

Thin shim over `backtest/data/history.py`, which is the CANONICAL source of the floors
(same bare-name-import pattern the regime and news engines use). Nothing here declares a
date; duplicating the floors would guarantee the UI and the data layer eventually
disagree, and the disagreement would surface as a run that passes validation and then
dies mid-flight — or worse, one that silently replays substituted bars.

Why the lab needs its own entry point at all: `BarSource.load` raises at FETCH time, by
which point a run row exists, a job lock is held, and the user is watching a progress
bar. This lets the router refuse with a 400 before any of that, and lets the date picker
disable the range up front.

Only the `python` runner is bounded here. NT8 (futures via NinjaTrader) and MT5 both pull
history from their own terminals, not through `backtest.data`, so their depth is a
different question with a different answer — claiming a Vantage gold floor applies to an
NT8 futures run would be a lie in the more dangerous direction.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import config as cfg

_MONOREPO = Path(cfg.MONOREPO_ROOT)
if str(_MONOREPO) not in sys.path:
    sys.path.insert(0, str(_MONOREPO))


def _tf_minutes(bar_type: str | None, bar_value: int | None) -> int:
    """job_spec bar_type/bar_value → minutes. Mirrors `python_runner._timeframe_minutes`."""
    bt = bar_type or "Minute"
    bv = int(bar_value or 15)
    if bt == "Day":
        return 1440
    if bt != "Minute":
        return 60
    return max(1, bv)


def limits_for(
    instrument: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
    refresh: bool = False,
) -> Optional[dict]:
    """The MEASURED history limit for this run shape, or None when unbounded/unknown.

    The floor is probed off the live terminal and cached per broker, so switching the
    terminal to a deeper or shallower broker changes this answer on its own — nothing here
    assumes Vantage. `refresh=True` forces a re-probe (~15s) for when a broker back-fills.

    Shape (consumed by the frontend as `HistoryLimit`):
        {instrument, runner, timeframe_minutes, earliest_date, broker, verified, source, note}
    """
    if runner != "python":
        return None
    from backtest.data.history import describe

    minutes = _tf_minutes(bar_type, bar_value)
    meta = describe(instrument, minutes, refresh=refresh)
    if not meta:
        return None
    return {
        "instrument": meta.get("symbol", instrument),
        "runner": runner,
        "timeframe_minutes": meta.get("timeframe_minutes", minutes),
        "earliest_date": meta["earliest_date"],
        "broker": meta.get("broker", ""),
        "verified": meta.get("verified", ""),
        "source": meta.get("source", ""),
        "note": meta.get("note", ""),
    }


def validate_window(
    instrument: str,
    start_date: str,
    end_date: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
) -> None:
    """Raise `ValueError` if the window starts before the broker's real history.

    Routers turn this into a 400. Deliberately a plain `ValueError` so this module stays
    importable outside FastAPI (scripts, tests) without dragging in HTTPException.
    """
    if runner != "python":
        return
    from backtest.data.history import HistoryFloorError, assert_window

    try:
        assert_window(instrument, _tf_minutes(bar_type, bar_value), start_date, end_date)
    except HistoryFloorError as exc:
        raise ValueError(str(exc)) from exc
