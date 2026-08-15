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

🔴 THE FLOOR IS PER-RUN, NOT PER-CHART-TIMEFRAME. A run may load more than one feed, and
each feed has its own measured floor — so the window is bounded by the LATEST of them.
Until 2026-08-15 everything here asked only about the chart timeframe, and a run with
`exec_secondary` on (which also loads 1m) sailed through a pre-flight that had never heard
of the 1m floor: measured on run `50331c7cbe96`, Vantage XAUUSD M15 reaches 2018-09-13 and
M1 only 2018-09-14, so the picker offered a date this module then blessed and the runner
refused at 8%. **The pre-flight promised in the paragraph above was not being kept.** Which
feeds a run loads is `run_feeds`' question, and it is now the only thing that answers it —
for the runner and for this module alike, so the two cannot disagree again.

⚠ Therefore PASS `params` at every call site. Omitting it silently asks the narrower
question — the exact shape of the bug — and the answer looks perfectly correct.

Only the `python` runner is bounded here. NT8 (futures via NinjaTrader) and MT5 both pull
history from their own terminals, not through `backtest.data`, so their depth is a
different question with a different answer — claiming a Vantage gold floor applies to an
NT8 futures run would be a lie in the more dangerous direction.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import config as cfg

from services.run_feeds import required_timeframes

_MONOREPO = Path(cfg.MONOREPO_ROOT)
if str(_MONOREPO) not in sys.path:
    sys.path.insert(0, str(_MONOREPO))


def limits_for(
    instrument: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
    refresh: bool = False,
    params: Any = None,
) -> Optional[dict]:
    """The MEASURED history limit for this run shape, or None when unbounded/unknown.

    The floor is probed off the live terminal and cached per broker, so switching the
    terminal to a deeper or shallower broker changes this answer on its own — nothing here
    assumes Vantage. `refresh=True` forces a re-probe (~15s) for when a broker back-fills.

    🔴 The answer is the LATEST floor across every feed `run_feeds` says this run loads —
    a window is only legal if EVERY feed can serve it, so the binding constraint is the
    shallowest history, not the chart's. `timeframe_minutes` reports the feed that set the
    floor, which is often not the one the caller asked about; `note` then explains it, so
    a picker that jumps a day says why rather than looking broken.

    Shape (consumed by the frontend as `HistoryLimit`):
        {instrument, runner, timeframe_minutes, earliest_date, broker, verified, source, note}
    """
    if runner != "python":
        return None
    from backtest.data.history import describe

    chart_min = required_timeframes(bar_type, bar_value)[0]
    metas = [
        m
        for m in (
            describe(instrument, tf, refresh=refresh)
            for tf in required_timeframes(bar_type, bar_value, params)
        )
        if m
    ]
    if not metas:
        return None
    # An unmeasurable feed yields no meta at all, so `metas` can be a SUBSET of the feeds.
    # That is reported rather than papered over: a floor built from two of three feeds is
    # not the run's floor, and calling it one is how a guess gets a measured label.
    meta = max(metas, key=lambda m: m["earliest_date"])
    note = meta.get("note", "")
    if meta.get("timeframe_minutes") != chart_min:
        note = (
            f"{note} This run also loads {meta.get('timeframe_minutes')}m bars, whose history "
            f"is shallower than the {chart_min}m chart's — so the later date is the one that "
            f"binds."
        ).strip()
    return {
        "instrument": meta.get("symbol", instrument),
        "runner": runner,
        "timeframe_minutes": meta.get("timeframe_minutes", chart_min),
        "earliest_date": meta["earliest_date"],
        "broker": meta.get("broker", ""),
        "verified": meta.get("verified", ""),
        "source": meta.get("source", ""),
        "note": note,
    }


def validate_window(
    instrument: str,
    start_date: str,
    end_date: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
    params: Any = None,
) -> None:
    """Raise `ValueError` if the window starts before the broker's real history.

    Checks EVERY feed the run loads, not just the chart's — see `limits_for`. Routers turn
    this into a 400. Deliberately a plain `ValueError` so this module stays importable
    outside FastAPI (scripts, tests) without dragging in HTTPException.
    """
    if runner != "python":
        return
    from backtest.data.history import HistoryFloorError, assert_window

    for tf in required_timeframes(bar_type, bar_value, params):
        try:
            assert_window(instrument, tf, start_date, end_date)
        except HistoryFloorError as exc:
            raise ValueError(str(exc)) from exc
