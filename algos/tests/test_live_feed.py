"""The bar feed: shape, and the two rules that keep the engines honest.

Rule 1 — never hand over the FORMING bar. The engines are state machines; a bar whose high
later extends can promote a swing that then cannot be un-promoted.
Rule 2 — never skip a bar. A hole in the stream is a different market history, so the feed has
to be able to say how far behind it is (`gap_bars`) rather than quietly resuming.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "live"))
import feed as live_feed  # noqa: E402


def _raw(times, base=100.0):
    """A `BotMT5.get_candles`-shaped frame: a `time` column of tz-aware UTC timestamps."""
    return pd.DataFrame(
        {
            "time": pd.DatetimeIndex(times, tz="UTC"),
            "open": [base + i for i in range(len(times))],
            "high": [base + i + 1 for i in range(len(times))],
            "low": [base + i - 1 for i in range(len(times))],
            "close": [base + i + 0.5 for i in range(len(times))],
        }
    )


class _FakeBot:
    """Stands in for BotMT5 — returns a scripted frame and records what was asked for."""

    symbol = "XAUUSD"

    def __init__(self, frame):
        self.frame = frame
        self.calls = []

    def get_candles(self, tf, count, symbol=None):
        self.calls.append(count)
        return self.frame.tail(count).reset_index(drop=True)


@pytest.fixture(autouse=True)
def _fake_mt5(monkeypatch):
    """`_tf_const` imports MetaTrader5, which does not exist off Windows."""
    import types

    m = types.ModuleType("MetaTrader5")
    m.TIMEFRAME_M15 = 15
    monkeypatch.setitem(sys.modules, "MetaTrader5", m)


def test_to_canonical_drops_the_forming_bar():
    df = live_feed.to_canonical(_raw(["2026-07-30 10:00", "2026-07-30 10:15", "2026-07-30 10:30"]))
    assert len(df) == 2
    assert df.index[-1] == pd.Timestamp("2026-07-30 10:15", tz="UTC")


def test_to_canonical_shape_matches_what_iter_bars_expects():
    df = live_feed.to_canonical(_raw(["2026-07-30 10:00", "2026-07-30 10:15"]))
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.dtypes.unique().tolist() == [float]


def test_to_canonical_survives_nothing():
    """Empty, not None and not a partial — a caller must always be able to len() it."""
    for empty in (None, pd.DataFrame(), _raw(["2026-07-30 10:00"])):
        assert live_feed.to_canonical(empty).empty


def test_new_bars_returns_only_unseen_ones():
    frame = _raw(["10:00", "10:15", "10:30"], base=100)
    frame["time"] = pd.DatetimeIndex(
        ["2026-07-30 10:00", "2026-07-30 10:15", "2026-07-30 10:30"], tz="UTC"
    )
    bot = _FakeBot(frame)
    f = live_feed.BarFeed(bot, "M15")
    first = f.new_bars()
    assert len(first) == 1 and first.index[-1] == pd.Timestamp("2026-07-30 10:15", tz="UTC")
    assert f.new_bars().empty  # nothing has closed since


def test_mark_seen_stops_warmups_last_bar_being_replayed_live():
    """Warmup already stepped every bar it loaded. Without mark_seen the first poll would hand
    the last one back and the engines would see it twice."""
    frame = _raw(["2026-07-30 10:00", "2026-07-30 10:15", "2026-07-30 10:30"])
    frame["time"] = pd.DatetimeIndex(
        ["2026-07-30 10:00", "2026-07-30 10:15", "2026-07-30 10:30"], tz="UTC"
    )
    bot = _FakeBot(frame)
    f = live_feed.BarFeed(bot, "M15")
    warm = f.history(10)
    f.mark_seen(warm)
    assert f.new_bars().empty


def test_gap_bars_counts_what_was_missed():
    times = pd.date_range("2026-07-30 10:00", periods=6, freq="15min", tz="UTC")
    frame = _raw(list(times))
    frame["time"] = times
    bot = _FakeBot(frame)
    f = live_feed.BarFeed(bot, "M15")
    f.last_bar_time = pd.Timestamp("2026-07-30 10:15", tz="UTC")
    # newest CLOSED bar is 11:00 (11:15 is forming) → 3 fifteen-minute bars behind
    assert f.gap_bars() == 3


def test_gap_bars_is_zero_when_current():
    times = pd.date_range("2026-07-30 10:00", periods=3, freq="15min", tz="UTC")
    frame = _raw(list(times))
    frame["time"] = times
    f = live_feed.BarFeed(_FakeBot(frame), "M15")
    f.last_bar_time = pd.Timestamp("2026-07-30 10:15", tz="UTC")
    assert f.gap_bars() == 0


def test_unknown_timeframe_is_a_loud_error():
    with pytest.raises(ValueError, match="Unknown timeframe"):
        live_feed.timeframe_seconds("M7")


def test_timeframe_seconds_are_right():
    assert live_feed.timeframe_seconds("M15") == 900
    assert live_feed.timeframe_seconds("H4") == 14400
