"""BarSource orchestration: cache-first fetch, resample path, range slicing."""

import pandas as pd

from backtest.data.cache import BarCache
from backtest.data.source import BarSource
from backtest.data.timeframes import to_minutes


class FakeAgent:
    """Serves deterministic bars at the requested timeframe and counts calls."""

    def __init__(self):
        self.calls: list[tuple] = []

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((symbol, tf_name, start_date, end_date))
        minutes = to_minutes(tf_name)
        idx = pd.date_range(
            start=f"{start_date} 00:00",
            end=f"{end_date} 23:59",
            freq=f"{minutes}min",
            name="time",
        )
        n = len(idx)
        return pd.DataFrame(
            {
                "open": [1.0] * n,
                "high": [2.0] * n,
                "low": [0.0] * n,
                "close": [1.5] * n,
            },
            index=idx,
        )


def _source(tmp_path):
    agent = FakeAgent()
    return BarSource(agent=agent, cache=BarCache(tmp_path)), agent


def test_first_load_fetches_and_caches(tmp_path):
    src, agent = _source(tmp_path)
    bars = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    assert not bars.empty
    assert len(agent.calls) == 1
    assert agent.calls[0][1] == "M15"


def test_second_load_hits_cache_no_refetch(tmp_path):
    src, agent = _source(tmp_path)
    src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-10")
    src.load("XAUUSD.s", "M15", "2026-01-06", "2026-01-08")  # sub-range
    assert len(agent.calls) == 1  # served from cache the second time


def test_resample_reuses_the_base_cache(tmp_path):
    src, agent = _source(tmp_path)
    # Pull 15m first (base M15 fetched + cached).
    src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    # 45m resamples up from the SAME M15 base — no second fetch.
    out = src.load("XAUUSD.s", "45m", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 1
    assert not out.empty
    # 45m windows are 3× fewer than 15m over a full covered day.
    fifteen = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-05")
    fortyfive = src.load("XAUUSD.s", "45m", "2026-01-05", "2026-01-05")
    assert len(fortyfive) <= len(fifteen) // 3 + 1


def test_slice_is_inclusive_of_end_date(tmp_path):
    src, _ = _source(tmp_path)
    bars = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    assert bars.index.min() >= pd.Timestamp("2026-01-05 00:00")
    assert bars.index.max() < pd.Timestamp("2026-01-07 00:00")
    assert bars.index.max() >= pd.Timestamp("2026-01-06 00:00")


def test_slice_excludes_out_of_range_cached_bars(tmp_path):
    src, agent = _source(tmp_path)
    # Fetch a wide window into cache...
    src.load("XAUUSD.s", "M15", "2026-01-01", "2026-01-31")
    # ...then ask for a narrow slice — only in-range bars come back.
    narrow = src.load("XAUUSD.s", "M15", "2026-01-10", "2026-01-11")
    assert narrow.index.min() >= pd.Timestamp("2026-01-10 00:00")
    assert narrow.index.max() < pd.Timestamp("2026-01-12 00:00")
    assert len(agent.calls) == 1  # wide fetch covered the narrow ask
