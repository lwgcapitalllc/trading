"""BarSource — the one entry point the replay loop calls for bars.

load(symbol, timeframe, start, end):
    1. Resolve the base timeframe to pull (the target itself if the broker serves
       it, else the largest served divisor).
    2. Serve base bars cache-first; on a miss fetch the whole [start, end] from
       the MT5 agent, cache it, and record the fetched range.
    3. Resample up to the target timeframe if base != target.
    4. Slice to [start, end] and return.

The agent is injected, so tests run against a fake with no network. In the lab
the default agent hits localhost:8766 through the SSH tunnel.
"""

from __future__ import annotations

import pandas as pd

from .cache import BarCache
from .coverage import RangeCoverage
from .history import HistoryFloors, assert_bar_spacing
from .mt5_agent import Mt5Agent
from .resample import resample_up
from .timeframes import resolve_base_tf, to_minutes


class BarSource:
    def __init__(self, agent: Mt5Agent | None = None, cache: BarCache | None = None):
        self.agent = agent if agent is not None else Mt5Agent()
        self.cache = cache if cache is not None else BarCache()
        self.coverage = RangeCoverage(self.cache.dir)
        # Built from OUR agent, not the module-level shared one, so an injected fake in a
        # test probes the fake — a floor check that reached the real terminal from a unit
        # test would be both slow and non-deterministic.
        self.floors = HistoryFloors(agent=self.agent, cache_dir=self.cache.dir)

    def load(
        self, symbol: str, timeframe: str | int, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Return canonical OHLC bars for the target timeframe over
        [start_date, end_date] inclusive (dates as YYYY-MM-DD).

        Raises `history.HistoryFloorError` when the window starts before the broker's
        real history for this timeframe, or when the bars that came back are not the
        timeframe requested. **Both checks live here, not in the callers** — MT5 answers
        a too-early request with COARSER bars mislabelled as what you asked for, and a
        backtest fed those produces a clean, confident, fictional result. Every consumer
        (the lab, the optimizer, the CLI tools) reads bars through this method, so this
        is the one place that can protect all of them. The floor is MEASURED per broker,
        never hardcoded — see `history.py` for the evidence and the probe.
        """
        target_min = to_minutes(timeframe)
        self.floors.assert_window(symbol, target_min, start_date, end_date)
        base_tf, base_min = resolve_base_tf(target_min)

        base_bars = self._load_base(symbol, base_tf, start_date, end_date)
        # Checked at the BASE timeframe — that is what the broker actually served, and
        # resampling up would smooth a substitution into a plausible-looking frame.
        assert_bar_spacing(base_bars, base_min, symbol)
        if base_min == target_min:
            bars = base_bars
        else:
            bars = resample_up(base_bars, target_min, base_min)
        return _slice(bars, start_date, end_date)

    def _load_base(
        self, symbol: str, base_tf: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Cache-first base-bar load. Fetches only the sub-ranges of [start, end] that are not
        already recorded as fetched, merges them into the cache, and returns the whole file.

        A stale FEED_VERSION forces a refetch and DROPS the recorded coverage. Both halves are
        required: `cache.load` already refuses to read a stale file, so honouring the old coverage
        would return an empty frame forever instead of re-pulling — the coverage says "we have
        this" while the cache says "not in a form you can use", and the caller gets nothing.

        🔴 **This asked `covered()` and refetched the WHOLE window on False until 2026-08-06,
        and that turned the deliberate never-mark-today rule into a 72x tax.** `_covered_end`
        will not mark today as covered, on purpose — a day still filling looks exactly like a
        complete one — so a window ending today is *never* fully covered, and every single
        request re-pulled the entire history to obtain the one missing day. **Measured on the
        live cache: 27.8s for 2020-01-01 → today against 0.39s for the same span ending
        yesterday, on every chart open, backtest and sweep reaching the live edge.**

        Asking for the GAPS keeps the rule and drops the tax. Note the two are not alternatives:
        the clamp is what keeps the recent edge honest, and this is what makes honouring it cheap.
        """
        if self.cache.is_stale(symbol, base_tf):
            self.coverage.reset(symbol, base_tf)
        for gap_start, gap_end in self.coverage.missing(symbol, base_tf, start_date, end_date):
            fetched = self.agent.bars(symbol, base_tf, gap_start, gap_end)
            # MERGES, never overwrites (`BarCache.save`) — which is what makes a partial fetch
            # safe. Overwriting would let a one-day tail pull delete six years of cached bars.
            self.cache.save(symbol, base_tf, fetched)
            # Record what CAME BACK, never what was asked for — see `_covered_end`.
            covered_to = _covered_end(fetched, gap_end)
            if covered_to >= gap_start:
                self.coverage.record(symbol, base_tf, gap_start, covered_to)
        return self.cache.load(symbol, base_tf)


def _covered_end(fetched: pd.DataFrame, end_date: str) -> str:
    """The last date this fetch may honestly claim to have covered.

    🔴 **This exists because recording the REQUESTED window silently truncated every later
    run.** `_load_base` used to `coverage.record(start_date, end_date)` straight after the
    fetch, whatever came back. Ask for bars up to a date the broker does not have yet — which
    every `--end today` and every `end = last_bar + 1 day` does — and that date is marked
    fetched forever. The next request reads as a cache HIT and returns a frame that stops
    where the old fetch stopped, with no error, no warning, and no way to tell from the
    result. **Measured on the live cache 2026-08-04: the sidecar claimed history through
    2026-08-06 while the file held nothing past 2026-08-03 03:45**, and the agent was serving
    the missing 170 bars on request the whole time.

    That is this repo's recurring shape — the system quietly answers a NARROWER question than
    the one asked — and it is the same failure as the hardcoded history floor, arriving from
    the other end of the window.

    Two clamps, and the second is the one that is easy to miss:

    1. **Never past the last bar returned.** If the data stops earlier than the request, the
       request over-reached.
    2. **Never into today.** A day that is still filling looks identical to a complete one from
       the bars alone — a frame ending 00:15 on the last day is either "the broker stops here"
       or "it is 00:20 right now", and nothing in the frame distinguishes them. So the recent
       edge is never marked covered and simply refetches until it is genuinely in the past.

    A window that ends in the past is unaffected, so no historical run does extra work. The cost
    is one agent call per run that reaches the live edge, which is the correct price for never
    handing a backtest a short frame it cannot detect.
    """
    import datetime as _dt

    end = end_date
    if not fetched.empty:
        last = str(pd.Timestamp(fetched.index[-1]).date())
        if last < end:
            end = last
    yesterday = str(_dt.date.today() - _dt.timedelta(days=1))
    return min(end, yesterday)


def _slice(bars: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """Inclusive [start_date, end_date] slice (end_date's whole day included)."""
    if bars.empty:
        return bars
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return bars.loc[(bars.index >= start) & (bars.index < end)]
