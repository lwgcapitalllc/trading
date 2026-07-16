"""Resample-up OHLC aggregation, gap handling, and alignment."""

import pandas as pd
import pytest

from backtest.data.resample import resample_up


def _bars(rows):
    idx = pd.DatetimeIndex([t for t, *_ in rows], name="time")
    data = {
        "open": [o for _, o, _, _, _ in rows],
        "high": [h for _, _, h, _, _ in rows],
        "low": [l for _, _, _, l, _ in rows],
        "close": [c for _, _, _, _, c in rows],
    }
    return pd.DataFrame(data, index=idx, dtype="float64")


def test_5m_to_15m_aggregates_ohlc_and_drops_empty_windows():
    df = _bars([
        ("2026-01-05 09:00", 10, 12, 9, 11),
        ("2026-01-05 09:05", 11, 13, 10, 12),
        ("2026-01-05 09:10", 12, 14, 11, 13),   # → 15m 09:00
        ("2026-01-05 09:15", 13, 15, 12, 14),
        ("2026-01-05 09:20", 14, 16, 13, 15),   # → 15m 09:15 (partial, 2 bars)
        # 09:25–09:44 missing (a gap, e.g. the daily break)
        ("2026-01-05 09:45", 20, 21, 19, 20),   # → 15m 09:45
    ])
    out = resample_up(df, target_minutes=15, base_minutes=5)

    assert list(out.index) == [
        pd.Timestamp("2026-01-05 09:00"),
        pd.Timestamp("2026-01-05 09:15"),
        pd.Timestamp("2026-01-05 09:45"),
    ]
    # The empty 09:30 window is dropped, not forward-filled.
    assert pd.Timestamp("2026-01-05 09:30") not in out.index

    first = out.loc["2026-01-05 09:00"]
    assert (first.open, first.high, first.low, first.close) == (10, 14, 9, 13)

    second = out.loc["2026-01-05 09:15"]
    assert (second.open, second.high, second.low, second.close) == (13, 16, 12, 15)

    third = out.loc["2026-01-05 09:45"]
    assert (third.open, third.high, third.low, third.close) == (20, 21, 19, 20)


def test_windows_align_to_epoch_clock():
    # A bar starting at 09:07 (off-grid) still lands in the 09:00 15m window.
    df = _bars([
        ("2026-01-05 09:07", 10, 11, 9, 10),
        ("2026-01-05 09:12", 10, 12, 8, 11),
    ])
    out = resample_up(df, 15, 5)
    assert list(out.index) == [pd.Timestamp("2026-01-05 09:00")]


def test_target_equals_base_is_identity_copy():
    df = _bars([("2026-01-05 09:00", 10, 12, 9, 11)])
    out = resample_up(df, 5, 5)
    pd.testing.assert_frame_equal(out, df)
    assert out is not df  # a copy, not the same object


def test_non_multiple_target_raises():
    df = _bars([("2026-01-05 09:00", 10, 12, 9, 11)])
    with pytest.raises(ValueError):
        resample_up(df, 15, 4)   # 15 is not a multiple of 4
    with pytest.raises(ValueError):
        resample_up(df, 5, 15)   # target below base


def test_empty_frame_returns_empty():
    df = _bars([]).astype("float64")
    out = resample_up(df, 15, 5)
    assert out.empty
