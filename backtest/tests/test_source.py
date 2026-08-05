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


# ── FEED_VERSION invalidation through the source ──────────────────────────────

def test_stale_cache_forces_a_refetch_and_does_not_strand_the_caller(tmp_path):
    """The 2026-07-16 trap, end to end. `cache.load` refuses a stale file, so if the recorded
    coverage were still honoured the caller would get an EMPTY frame forever instead of a
    re-pull. Coverage must be dropped alongside the cache."""
    import json

    from backtest.data.cache import FEED_VERSION

    agent = FakeAgent()
    cache = BarCache(tmp_path)
    source = BarSource(agent, cache)

    first = source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert not first.empty
    assert len(agent.calls) == 1

    # Second call is served from cache — no refetch.
    source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 1

    # Age the cache: same bars, older meaning.
    cache.meta_path("XAUUSD.s", "M5").write_text(json.dumps({"feed_version": FEED_VERSION - 1}))

    again = source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 2, "stale cache must trigger a refetch"
    assert not again.empty, "stale cache must not strand the caller with an empty frame"
    assert not cache.is_stale("XAUUSD.s", "M5"), "refetch must restamp the cache as current"


# ── coverage must record what CAME BACK, not what was asked for ──────────────────
# 🔴 Found 2026-08-04 on the live cache: the sidecar claimed history through 2026-08-06
# while the file held nothing past 2026-08-03 03:45, and the agent was serving the missing
# 170 bars on request the whole time. Recording the REQUEST marks a date fetched even when
# no data for it exists, and every later run then reads a cache HIT and gets a short frame
# with no error. A backtest cannot detect that from its own result.

class ShortAgent(FakeAgent):
    """Serves bars only up to `serves_to`, however far the request reaches.

    This is what a broker does at the live edge every single day: you ask through today and
    get back everything that exists, which stops somewhere earlier.
    """

    def __init__(self, serves_to: str):
        super().__init__()
        self.serves_to = serves_to

    def bars(self, symbol, tf_name, start_date, end_date):
        capped = min(end_date, self.serves_to)
        return super().bars(symbol, tf_name, start_date, capped)


def _yesterday() -> str:
    import datetime as dt
    return str(dt.date.today() - dt.timedelta(days=1))


def _days_ago(n: int) -> str:
    import datetime as dt
    return str(dt.date.today() - dt.timedelta(days=n))


def test_a_short_fetch_does_not_claim_the_dates_it_never_returned(tmp_path):
    agent = ShortAgent(serves_to=_days_ago(3))
    src = BarSource(agent=agent, cache=BarCache(tmp_path))
    src.load("XAUUSD", "15", _days_ago(10), _yesterday())
    assert not src.coverage.covered("XAUUSD", "M15", _days_ago(2), _yesterday())


def test_the_missing_tail_is_refetched_rather_than_served_short_forever(tmp_path):
    # The bug's real cost: the second run is the one that silently lies, because the first
    # run at least returned everything that existed at the time.
    agent = ShortAgent(serves_to=_days_ago(3))
    src = BarSource(agent=agent, cache=BarCache(tmp_path))
    src.load("XAUUSD", "15", _days_ago(10), _yesterday())

    agent.serves_to = _yesterday()          # the broker catches up
    got = src.load("XAUUSD", "15", _days_ago(10), _yesterday())
    assert str(got.index[-1].date()) == _yesterday()


def test_a_window_ending_in_the_past_still_caches_and_does_not_refetch(tmp_path):
    # The fix must not make every historical run pay for an extra agent call.
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    n = len(agent.calls)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    assert len(agent.calls) == n


def test_today_is_never_recorded_as_covered_even_when_bars_reach_it(tmp_path):
    # A day that is still filling looks identical to a complete one from the bars alone: a
    # frame ending 00:15 on the last day is either "the broker stops here" or "it is 00:20
    # right now", and nothing in the frame tells them apart.
    import datetime as dt
    today = str(dt.date.today())
    src, _ = _source(tmp_path)              # FakeAgent serves the whole requested window
    src.load("XAUUSD", "15", _days_ago(5), today)
    assert not src.coverage.covered("XAUUSD", "M15", today, today)


def test_a_fetch_that_returns_nothing_usable_records_no_coverage_at_all(tmp_path):
    # Requesting a window entirely in the future must not mark it fetched. Without the
    # start<=end guard the clamp would record an inverted interval, which _merge_intervals
    # would happily persist and covered() would then answer with nonsense.
    import datetime as dt
    src = BarSource(agent=ShortAgent(serves_to=_days_ago(3)), cache=BarCache(tmp_path))
    fut_a = str(dt.date.today() + dt.timedelta(days=5))
    fut_b = str(dt.date.today() + dt.timedelta(days=9))
    try:
        src.load("XAUUSD", "15", fut_a, fut_b)
    except Exception:
        pass
    assert not src.coverage.covered("XAUUSD", "M15", fut_a, fut_b)
