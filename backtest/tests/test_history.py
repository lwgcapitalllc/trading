"""Measured history floors + the timeframe-substitution backstop.

The bug these guard against is not a crash — it is a backtest that runs perfectly and
answers with daily bars pretending to be 15m. So the tests assert on REFUSAL, on the fact
that the floor is MEASURED rather than assumed, and on the one thing that must never
regress: that a legitimate window still loads.

No network: a fake agent stands in for the terminal, with a settable history start, so the
probe is exercised for real against known ground truth.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backtest.data.history import (
    HistoryFloorError,
    HistoryFloors,
    assert_bar_spacing,
)

_PER_DAY = {1: 1379, 5: 276, 15: 92, 30: 46, 60: 23, 240: 6, 1440: 1}
_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class FakeAgent:
    """A terminal with a known intraday floor that SUBSTITUTES coarser bars before it —
    exactly the behaviour observed on Vantage, which is the whole reason this module exists.
    """

    def __init__(self, server="FakeBroker-Demo", intraday_from="2018-09-14",
                 daily_from="2007-06-21"):
        self._server = server
        self.intraday_from = dt.date.fromisoformat(intraday_from)
        self.daily_from = dt.date.fromisoformat(daily_from)
        self.calls = 0

    def status(self):
        return {"server": self._server, "account": 1, "mt5_connected": True}

    def bar_count(self, symbol, tf_name, start_date, end_date):
        self.calls += 1
        day = dt.date.fromisoformat(start_date)
        if day.weekday() >= 5 or day < self.daily_from:
            return 0
        minutes = _MINUTES[tf_name]
        if minutes >= 1440 or day >= self.intraday_from:
            return _PER_DAY[minutes]
        return 1        # the substitution: one DAILY bar, whatever was asked for


def _floors(agent, tmp_path):
    return HistoryFloors(agent=agent, cache_dir=tmp_path)


def _frame(start: str, periods: int, minutes: int) -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq=f"{minutes}min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


# ── probing finds the real floor ────────────────────────────────────────────────

def test_probe_finds_the_intraday_floor(tmp_path):
    f = _floors(FakeAgent(intraday_from="2018-09-14"), tmp_path)
    # Exact: the binary search brackets, then phase 2 scans forward to the first real day.
    assert f.floor("XAUUSD", 15) == dt.date(2018, 9, 14)


def test_probe_adapts_to_a_deeper_broker(tmp_path):
    """The whole point of measuring: a broker with more history must NOT be truncated."""
    f = _floors(FakeAgent(server="DeepBroker-Live", intraday_from="2012-03-05"), tmp_path)
    assert f.floor("XAUUSD", 15) == dt.date(2012, 3, 5)
    f.assert_window("XAUUSD", 15, "2013-01-01", "2020-01-01")   # would have been refused


def test_probe_adapts_to_a_shallower_broker(tmp_path):
    f = _floors(FakeAgent(server="ThinBroker-Demo", intraday_from="2024-01-08"), tmp_path)
    assert f.floor("XAUUSD", 15) == dt.date(2024, 1, 8)
    with pytest.raises(HistoryFloorError):
        f.assert_window("XAUUSD", 15, "2020-01-01")


def test_daily_floor_is_measured_separately_and_is_deeper(tmp_path):
    f = _floors(FakeAgent(), tmp_path)
    assert f.floor("XAUUSD", 1440) < f.floor("XAUUSD", 15)


def test_broker_suffix_is_the_same_instrument(tmp_path):
    f = _floors(FakeAgent(), tmp_path)
    assert f.floor("XAUUSD.s", 15) == f.floor("XAUUSD", 15)


# ── caching, and per-broker isolation ───────────────────────────────────────────

def test_result_is_cached_so_the_probe_runs_once(tmp_path):
    agent = FakeAgent()
    f = _floors(agent, tmp_path)
    f.floor("XAUUSD", 15)
    after_first = agent.calls
    assert after_first > 0
    f2 = _floors(agent, tmp_path)          # fresh instance, same cache dir
    f2.floor("XAUUSD", 15)
    assert agent.calls == after_first      # zero extra probes


def test_switching_broker_does_not_reuse_the_old_floor(tmp_path):
    """The requirement: swapping the terminal to another broker must re-measure, never
    inherit. Same symbol, same timeframe, same cache file — different server."""
    shallow = _floors(FakeAgent(server="A-Demo", intraday_from="2024-01-08"), tmp_path)
    deep = _floors(FakeAgent(server="B-Demo", intraday_from="2012-03-05"), tmp_path)
    a = shallow.floor("XAUUSD", 15)
    b = deep.floor("XAUUSD", 15)
    assert a.year == 2024 and b.year == 2012


def test_refresh_reprobes_when_a_broker_extends_history(tmp_path):
    agent = FakeAgent(intraday_from="2024-01-08")
    f = _floors(agent, tmp_path)
    assert f.floor("XAUUSD", 15).year == 2024
    agent.intraday_from = dt.date(2015, 6, 1)          # broker back-fills history
    assert f.floor("XAUUSD", 15).year == 2024          # cached — unchanged
    assert f.floor("XAUUSD", 15, refresh=True).year == 2015


# ── unknown / unreachable ───────────────────────────────────────────────────────

def test_unreachable_agent_yields_unknown_not_a_guess(tmp_path):
    class Dead:
        def status(self): raise RuntimeError("tunnel down")
        def bar_count(self, *a, **k): return 0
    f = _floors(Dead(), tmp_path)
    assert f.floor("XAUUSD", 15) is None      # None = unknown, never "unlimited"
    f.assert_window("XAUUSD", 15, "1999-01-01")   # cannot refuse what it cannot measure


def test_seed_is_not_applied_to_a_different_broker(tmp_path):
    """A seeded fallback exists for Vantage. It must never be imposed on another broker —
    that would truncate a deeper one and fictionalise a shallower one."""
    class NoBars(FakeAgent):
        def bar_count(self, *a, **k): return 0
    other = _floors(NoBars(server="SomeoneElse-Live"), tmp_path)
    assert other.floor("XAUUSD", 15) is None
    vantage = _floors(NoBars(server="VantageMarkets-Demo"), tmp_path)
    assert vantage.floor("XAUUSD", 15) == dt.date(2018, 9, 14)   # seed applies here only


# ── window assertion ────────────────────────────────────────────────────────────

def test_window_on_or_after_the_floor_is_allowed(tmp_path):
    f = _floors(FakeAgent(intraday_from="2018-09-14"), tmp_path)
    fl = f.floor("XAUUSD", 15)
    f.assert_window("XAUUSD", 15, fl.isoformat(), "2026-01-01")
    f.assert_window("XAUUSD", 15, "2022-05-01", "2026-01-01")


def test_window_before_the_floor_names_both_dates(tmp_path):
    f = _floors(FakeAgent(intraday_from="2018-09-14"), tmp_path)
    with pytest.raises(HistoryFloorError) as e:
        f.assert_window("XAUUSD", 15, "2015-01-01", "2015-03-01")
    msg = str(e.value)
    assert "2015-01-01" in msg and "2018-09" in msg


def test_malformed_start_date_is_refused(tmp_path):
    f = _floors(FakeAgent(), tmp_path)
    with pytest.raises(HistoryFloorError):
        f.assert_window("XAUUSD", 15, "not-a-date")


def test_describe_reports_how_it_knows(tmp_path):
    f = _floors(FakeAgent(server="FakeBroker-Demo"), tmp_path)
    d = f.describe("XAUUSD", 15)
    assert d["source"] == "probed"
    assert d["broker"] == "FakeBroker-Demo"
    assert d["earliest_date"] == f.floor("XAUUSD", 15).isoformat()
    assert d["timeframe_minutes"] == 15


# ── spacing backstop (pure) ─────────────────────────────────────────────────────

def test_daily_bars_labelled_as_15m_are_refused():
    """The actual production failure: Jan-2010 M15 returned 21 daily bars."""
    with pytest.raises(HistoryFloorError) as e:
        assert_bar_spacing(_frame("2010-01-04", 21, 1440), 15, "XAUUSD")
    assert "1440m" in str(e.value)


def test_hourly_bars_labelled_as_15m_are_refused():
    with pytest.raises(HistoryFloorError):
        assert_bar_spacing(_frame("2018-09-10", 23, 60), 15, "XAUUSD")


def test_genuine_15m_frame_passes():
    assert_bar_spacing(_frame("2022-05-02", 500, 15), 15, "XAUUSD")


def test_weekend_and_session_gaps_do_not_trip_it():
    """Real bars have big gaps (weekends, the daily close break). Only the MODAL spacing
    defines the timeframe, so those must pass."""
    a = _frame("2022-05-02 00:00", 96, 15)
    b = _frame("2022-05-09 00:00", 96, 15)
    assert_bar_spacing(pd.concat([a, b]), 15, "XAUUSD")


def test_bars_closer_than_the_timeframe_are_refused():
    assert_bar_spacing(_frame("2022-05-02", 200, 5), 5)
    with pytest.raises(HistoryFloorError):
        assert_bar_spacing(_frame("2022-05-02", 200, 5), 15)


def test_too_short_to_judge_is_not_refused():
    # Two bars cannot establish a modal spacing; refusing would break legitimate tiny
    # windows. The window assertion is what covers those.
    assert_bar_spacing(_frame("2022-05-02", 2, 15), 15)
    assert_bar_spacing(None, 15)
