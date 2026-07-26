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
        """Cache-first base-bar load. Refetches [start, end] from the agent when
        that window isn't already recorded as fetched, then merges and persists.

        A stale FEED_VERSION forces a refetch and DROPS the recorded coverage. Both halves are
        required: `cache.load` already refuses to read a stale file, so honouring the old coverage
        would return an empty frame forever instead of re-pulling — the coverage says "we have
        this" while the cache says "not in a form you can use", and the caller gets nothing.
        """
        if self.cache.is_stale(symbol, base_tf):
            self.coverage.reset(symbol, base_tf)
        if self.coverage.covered(symbol, base_tf, start_date, end_date):
            return self.cache.load(symbol, base_tf)
        fetched = self.agent.bars(symbol, base_tf, start_date, end_date)
        self.cache.save(symbol, base_tf, fetched)
        self.coverage.record(symbol, base_tf, start_date, end_date)
        return self.cache.load(symbol, base_tf)


def _slice(bars: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """Inclusive [start_date, end_date] slice (end_date's whole day included)."""
    if bars.empty:
        return bars
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return bars.loc[(bars.index >= start) & (bars.index < end)]
