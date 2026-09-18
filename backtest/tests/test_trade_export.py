"""The trade exporter's three ways of lying, each pinned.

Every test here has been watched go RED by mutating the line it guards (root rule 12) — the
mutation is named in each docstring, because none of these can be made to fail by accident.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backtest.tools.trade_export import _entry_time, finished_trades


class _Trade:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _frame(n=5):
    idx = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame({"close": range(n)}, index=idx)


def test_epoch_stamp_wins_over_bar_index():
    """A strategy that fills in BOTH must be read by its timestamp, not its index.

    RED by making `_entry_time` check `entry_index` first: the trade then reports bar 0's
    time, which is a different day, and every conditioning bucket is drawn off the wrong bar.
    """
    df = _frame()
    when = pd.Timestamp("2026-03-02 11:30")
    t = _Trade(entry_ms=int(when.value // 1_000_000), entry_index=0, r=1.0)
    assert _entry_time(t, df) == when


def test_bar_index_used_when_there_is_no_stamp():
    """RED by deleting the `entry_index` branch — the trade silently disappears instead."""
    df = _frame()
    assert _entry_time(_Trade(entry_index=3, r=1.0), df) == df.index[3]


def test_unstamped_trade_is_dropped_never_dated_to_bar_zero():
    """A trade with no usable time must vanish, not land on the first bar (root rule 1).

    RED by returning `df.index[0]` instead of None from `_entry_time`: the row comes back,
    dated to a bar the trade has nothing to do with, and nothing downstream can tell.
    """
    df = _frame()
    assert _entry_time(_Trade(r=1.0), df) is None
    assert finished_trades(_Book([_Trade(r=1.0)]), df) == []


def test_out_of_range_index_is_dropped():
    """An index past the end of the replayed frame is not a time. RED by dropping the bounds
    check — pandas raises, or worse, a negative index reads from the END of the frame."""
    df = _frame()
    assert _entry_time(_Trade(entry_index=99, r=1.0), df) is None
    assert _entry_time(_Trade(entry_index=-1, r=1.0), df) is None


def test_a_strategy_with_no_trade_list_refuses():
    """Silence here would export an empty file that looks like "no trades taken".

    RED by returning [] instead of raising — an eight-year replay then reports zero trades
    and the study concludes the strategy never fires.
    """
    with pytest.raises(AttributeError):
        finished_trades(object(), _frame())


def test_rows_carry_r_and_are_not_reordered():
    df = _frame()
    book = _Book([_Trade(entry_index=1, r=2.5, dir=1), _Trade(entry_index=0, r=-1.0, dir=-1)])
    rows = finished_trades(book, df)
    assert [r["r"] for r in rows] == [2.5, -1.0]
    assert rows[0]["entry_utc"] == df.index[1].isoformat()


class _Book:
    """Stands in for a strategy's execution layer — the only thing the exporter reads."""

    def __init__(self, trades):
        self.execution = self
        self.trades = trades
