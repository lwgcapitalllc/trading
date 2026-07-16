"""On-disk bar cache: round-trip, merge/dedup, broker-symbol file naming."""

import pandas as pd

from backtest.data.cache import BarCache


def _bars(rows):
    idx = pd.DatetimeIndex([t for t, *_ in rows], name="time")
    return pd.DataFrame(
        {
            "open": [o for _, o, _, _, _ in rows],
            "high": [h for _, _, h, _, _ in rows],
            "low": [l for _, _, _, l, _ in rows],
            "close": [c for _, _, _, _, c in rows],
        },
        index=idx,
        dtype="float64",
    )


def test_save_then_load_round_trips(tmp_path):
    cache = BarCache(tmp_path)
    bars = _bars([
        ("2026-01-05 09:00", 10, 12, 9, 11),
        ("2026-01-05 09:05", 11, 13, 10, 12),
    ])
    cache.save("XAUUSD.s", "M5", bars)
    loaded = cache.load("XAUUSD.s", "M5")
    pd.testing.assert_frame_equal(loaded, bars)


def test_missing_returns_empty(tmp_path):
    cache = BarCache(tmp_path)
    out = cache.load("EURUSD", "M15")
    assert out.empty
    assert list(out.columns) == ["open", "high", "low", "close"]
    assert out.index.name == "time"


def test_merge_unions_and_incoming_wins_on_collision(tmp_path):
    cache = BarCache(tmp_path)
    first = _bars([
        ("2026-01-05 09:00", 10, 12, 9, 11),
        ("2026-01-05 09:05", 11, 13, 10, 12),
    ])
    cache.save("XAUUSD.s", "M5", first)
    # 09:05 corrected + a new 09:10 bar.
    second = _bars([
        ("2026-01-05 09:05", 11, 99, 10, 50),
        ("2026-01-05 09:10", 12, 14, 11, 13),
    ])
    cache.save("XAUUSD.s", "M5", second)

    loaded = cache.load("XAUUSD.s", "M5")
    assert list(loaded.index) == [
        pd.Timestamp("2026-01-05 09:00"),
        pd.Timestamp("2026-01-05 09:05"),
        pd.Timestamp("2026-01-05 09:10"),
    ]
    # incoming (corrected) bar wins.
    assert loaded.loc["2026-01-05 09:05"].high == 99
    assert loaded.loc["2026-01-05 09:05"].close == 50


def test_broker_symbol_is_filesystem_safe(tmp_path):
    cache = BarCache(tmp_path)
    p = cache.path("XAUUSD.s", "M15")
    assert p.name == "XAUUSD_s__M15.csv"


def test_bars_sorted_after_out_of_order_save(tmp_path):
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:10", 12, 14, 11, 13)]))
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))
    loaded = cache.load("XAUUSD.s", "M5")
    assert list(loaded.index) == [
        pd.Timestamp("2026-01-05 09:00"),
        pd.Timestamp("2026-01-05 09:10"),
    ]
