"""Tick volume survives the bar pipeline, or is absent — never fabricated.

Added 2026-08-06 with the chart's session-VWAP layer, which is the first consumer here that needs
the bar's VOLUME. The agent dropped MT5's `tick_volume` at `_rates_to_bars`, `cache._normalize`
sliced the frame to OHLC and `resample_up` aggregated four columns, so the field was discarded
three times over on its way to a caller.

Every test here is about the SAME distinction, because it is the one that decides whether a VWAP
means anything: a bar with zero volume is a measurement (a dead session really does trade no
ticks), a bar with no volume is the absence of one, and a pipeline that turns the second into the
first hands the consumer a confident wrong average with no way to notice.
"""

import json

import numpy as np
import pandas as pd

from backtest.data.cache import FEED_VERSION, BarCache, _normalize
from backtest.data.resample import resample_up


def _bars(rows, *, volume=True):
    """rows = (time, o, h, l, c, v). Drop the volume column entirely when `volume` is False."""
    idx = pd.DatetimeIndex([r[0] for r in rows], name="time")
    data = {
        "open": [r[1] for r in rows],
        "high": [r[2] for r in rows],
        "low": [r[3] for r in rows],
        "close": [r[4] for r in rows],
    }
    if volume:
        data["volume"] = [r[5] for r in rows]
    return pd.DataFrame(data, index=idx, dtype="float64")


# --------------------------------------------------------------------------- resample


def test_volume_aggregates_by_sum_not_by_first_or_last():
    """The one arithmetic claim, and the one that would be plausible if it were wrong.

    Every price column takes an endpoint or an extreme; volume is the only one that ADDS. Reading
    it first/last/max keeps the number in the right order of magnitude and under-weights every
    resampled bar in a VWAP by roughly the resample ratio.
    """
    df = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11, 100),
            ("2026-01-05 09:05", 11, 13, 10, 12, 250),
            ("2026-01-05 09:10", 12, 14, 11, 13, 30),
        ]
    )
    out = resample_up(df, target_minutes=15, base_minutes=5)

    assert out.loc["2026-01-05 09:00", "volume"] == 380.0
    # Not any of the plausible-looking alternatives.
    assert out.loc["2026-01-05 09:00", "volume"] not in (100.0, 250.0, 30.0)


def test_a_window_holding_one_unknown_bar_is_unknown_rather_than_short():
    """pandas' default `sum` treats NaN as zero, which yields a short total that looks ordinary.

    A partly-known window has no honest total, and quietly reporting the known part is exactly the
    failure this file exists to pin: the consumer cannot tell that number from a real one.
    """
    df = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11, 100),
            ("2026-01-05 09:05", 11, 13, 10, 12, np.nan),
            ("2026-01-05 09:10", 12, 14, 11, 13, 30),
            ("2026-01-05 09:15", 13, 15, 12, 14, 40),
        ]
    )
    out = resample_up(df, target_minutes=15, base_minutes=5)

    assert np.isnan(out.loc["2026-01-05 09:00", "volume"])  # NOT 130.0
    assert out.loc["2026-01-05 09:15", "volume"] == 40.0  # a clean window is unaffected


def test_a_frame_with_no_volume_column_gets_none_invented():
    df = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11, None),
            ("2026-01-05 09:05", 11, 13, 10, 12, None),
            ("2026-01-05 09:10", 12, 14, 11, 13, None),
        ],
        volume=False,
    )
    out = resample_up(df, target_minutes=15, base_minutes=5)

    assert "volume" not in out.columns


def test_zero_volume_survives_as_a_measurement():
    """A dead session reports real zeros, and they must not be confused with the absent case."""
    df = _bars(
        [
            ("2026-01-05 09:00", 10, 12, 9, 11, 0),
            ("2026-01-05 09:05", 11, 13, 10, 12, 0),
            ("2026-01-05 09:10", 12, 14, 11, 13, 0),
        ]
    )
    out = resample_up(df, target_minutes=15, base_minutes=5)

    assert "volume" in out.columns
    assert out.loc["2026-01-05 09:00", "volume"] == 0.0


# --------------------------------------------------------------------------- cache


def test_normalize_carries_volume_and_types_it():
    df = pd.DataFrame(
        {
            "time": ["2026-01-05 09:00", "2026-01-05 09:15"],
            "open": [10, 11],
            "high": [12, 13],
            "low": [9, 10],
            "close": [11, 12],
            "volume": [100, 250],
        }
    )
    out = _normalize(df)

    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out["volume"].dtype == "float64"
    assert out["volume"].tolist() == [100.0, 250.0]


def test_normalize_does_not_invent_a_volume_column():
    df = pd.DataFrame(
        {
            "time": ["2026-01-05 09:00"],
            "open": [10],
            "high": [12],
            "low": [9],
            "close": [11],
        }
    )
    assert list(_normalize(df).columns) == ["open", "high", "low", "close"]


def test_a_cached_frame_round_trips_its_volume(tmp_path):
    cache = BarCache(tmp_path)
    cache.save(
        "XAUUSD.s",
        "M15",
        _bars(
            [
                ("2026-01-05 09:00", 10, 12, 9, 11, 100),
                ("2026-01-05 09:15", 11, 13, 10, 12, 250),
            ]
        ),
    )
    out = cache.load("XAUUSD.s", "M15")

    assert out["volume"].tolist() == [100.0, 250.0]


def test_the_feed_version_is_past_the_price_only_era(tmp_path):
    """A cache file written before tick volume existed must read as a MISS, not as data.

    A v2 file is not wrong, it is incomplete — and the distinction cannot survive a merge, because
    folding a v2 span and a v3 span into one file gives a volume column that is real for part of
    the history and NaN for the rest, which is precisely the shape a VWAP averages straight
    through. `FEED_VERSION` is the mechanism that already existed for this; the test pins that it
    was actually bumped, since forgetting to is silent.
    """
    assert FEED_VERSION >= 3

    cache = BarCache(tmp_path)
    cache.save("XAUUSD.s", "M15", _bars([("2026-01-05 09:00", 10, 12, 9, 11, 100)]))
    cache.meta_path("XAUUSD.s", "M15").write_text(json.dumps({"feed_version": 2}))

    assert cache.is_stale("XAUUSD.s", "M15") is True
    assert cache.load("XAUUSD.s", "M15").empty


def test_the_sidecar_records_whether_volume_ACTUALLY_ARRIVED(tmp_path):
    """The version says the cache CAN carry volume; this says whether this file DOES.

    The two come apart in exactly one window and it is a real one: `FEED_VERSION` is bumped in the
    repo, the VPS agent is deployed separately, and a fetch in between writes a current-version
    file holding no volume — which then never re-pulls, so the chart layer is silently absent for
    good. Recording what came back rather than what the version implies is this package's own rule.
    """
    cache = BarCache(tmp_path)

    cache.save("XAUUSD.s", "M15", _bars([("2026-01-05 09:00", 10, 12, 9, 11, 100)]))
    assert cache.has_volume("XAUUSD.s", "M15") is True

    cache.save("EURUSD", "M15", _bars([("2026-01-05 09:00", 1, 2, 0, 1, None)], volume=False))
    assert cache.has_volume("EURUSD", "M15") is False

    # A file from before the question was asked answers UNKNOWN, never False — the same
    # no-data-vs-cannot-ask rule the whole feature is built on.
    assert cache.has_volume("GBPUSD", "M15") is None


def test_a_stale_price_only_file_is_overwritten_rather_than_merged(tmp_path):
    """The merge is where a half-volumed file would be created, so the stale path must not take it."""
    cache = BarCache(tmp_path)
    cache.save(
        "XAUUSD.s",
        "M15",
        _bars(
            [
                ("2026-01-05 09:00", 10, 12, 9, 11, None),
                ("2026-01-05 09:15", 11, 13, 10, 12, None),
            ],
            volume=False,
        ),
    )
    cache.meta_path("XAUUSD.s", "M15").write_text(json.dumps({"feed_version": 2}))

    cache.save("XAUUSD.s", "M15", _bars([("2026-01-05 09:30", 12, 14, 11, 13, 300)]))
    out = cache.load("XAUUSD.s", "M15")

    # The price-only rows are GONE, so no row can carry an unknown volume beside a known one.
    assert len(out) == 1
    assert out["volume"].tolist() == [300.0]
    assert not out["volume"].isna().any()


# --------------------------------------------------------------------------- the agent's own bars


def test_the_vps_agent_sends_volume_with_every_bar():
    """`_rates_to_bars` reads MT5's `tick_volume`, which is the field a CFD actually has.

    A source test rather than a behavioural one: this function runs on the VPS against the real
    MetaTrader5 package, so it cannot be imported here — and the failure mode of dropping the
    field again is silent everywhere downstream (an absent volume simply removes the chart layer).
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "algos" / "markets" / "fx" / "tools" / "mt5_agent.py"
    ).read_text()
    body = src.split("def _rates_to_bars", 1)[1].split("\ndef ", 1)[0]

    assert '"volume"' in body, "the agent stopped sending a volume field"
    assert 'r["tick_volume"]' in body, (
        "volume must come from tick_volume, not real_volume (0 on a CFD)"
    )
