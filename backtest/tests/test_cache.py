"""On-disk bar cache: round-trip, merge/dedup, broker-symbol file naming, feed versioning."""

import json

import pandas as pd

from backtest.data.cache import FEED_VERSION, BarCache


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
    bars = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11),
            ("2026-01-05 09:05", 11, 13, 10, 12),
        ]
    )
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
    first = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11),
            ("2026-01-05 09:05", 11, 13, 10, 12),
        ]
    )
    cache.save("XAUUSD.s", "M5", first)
    # 09:05 corrected + a new 09:10 bar.
    second = _bars(
        [
            ("2026-01-05 09:05", 11, 99, 10, 50),
            ("2026-01-05 09:10", 12, 14, 11, 13),
        ]
    )
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


# ── FEED_VERSION staleness guard ──────────────────────────────────────────────
#
# Regression cover for the 2026-07-16 trap: the agent was fixed to return true UTC, but the cache
# still held broker-local bars, so compare_feeds.py reported the bug as unfixed against a correct
# agent. A stale HIT is silent; a miss is loud. These lock "stale reads as a miss".


def test_save_writes_the_current_feed_version(tmp_path):
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))
    assert cache.version_of("XAUUSD.s", "M5") == FEED_VERSION
    assert not cache.is_stale("XAUUSD.s", "M5")


def test_cache_written_under_an_older_version_reads_as_empty(tmp_path):
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))
    cache.meta_path("XAUUSD.s", "M5").write_text(json.dumps({"feed_version": FEED_VERSION - 1}))

    assert cache.is_stale("XAUUSD.s", "M5")
    assert cache.load("XAUUSD.s", "M5").empty, "stale bars must never be served"


def test_a_cache_with_no_sidecar_is_the_pre_fix_era_and_is_stale(tmp_path):
    """Caches on disk before the sidecar existed hold broker-local timestamps."""
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))
    cache.meta_path("XAUUSD.s", "M5").unlink()

    assert cache.version_of("XAUUSD.s", "M5") == 1
    assert cache.is_stale("XAUUSD.s", "M5") is (FEED_VERSION != 1)
    assert cache.load("XAUUSD.s", "M5").empty


def test_a_corrupt_sidecar_is_treated_as_stale_not_as_current(tmp_path):
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))
    cache.meta_path("XAUUSD.s", "M5").write_text("{not json")

    assert cache.is_stale("XAUUSD.s", "M5")
    assert cache.load("XAUUSD.s", "M5").empty


def test_saving_over_a_stale_cache_discards_the_old_rows(tmp_path):
    """The laundering guard: stale rows must not be merged into a file we then stamp current."""
    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M5", _bars([("2026-01-05 09:00", 10, 12, 9, 11)]))  # "broker-local"
    cache.meta_path("XAUUSD.s", "M5").write_text(json.dumps({"feed_version": FEED_VERSION - 1}))

    fresh = _bars([("2026-01-05 07:00", 20, 22, 19, 21)])  # "true UTC"
    cache.save("XAUUSD.s", "M5", fresh)

    loaded = cache.load("XAUUSD.s", "M5")
    pd.testing.assert_frame_equal(loaded, fresh)
    assert pd.Timestamp("2026-01-05 09:00") not in loaded.index, "stale row was laundered in"
    assert cache.version_of("XAUUSD.s", "M5") == FEED_VERSION


def test_missing_cache_is_not_reported_stale(tmp_path):
    """Staleness is about a file that EXISTS and disagrees — a plain miss is not stale."""
    assert not BarCache(tmp_path).is_stale("XAUUSD.s", "M5")
