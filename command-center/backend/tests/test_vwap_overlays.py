"""
Tests for services/vwap_overlays.py — the session-VWAP line on the price chart.

Two halves, and the second is the one that earns this file.

**The arithmetic** is checked against a hand-computed volume-weighted mean and against the trading-day
anchor rolling at 18:00 New York. It is deliberately thin: the maths is the canonical
`engines/vwap/` engine's and is proven at 100% Pine parity there, so restating it here would be a
second claim about one calculation.

**The REFUSALS** are the emitter's own contract and are where the danger is. A VWAP given bars with
no volume does not fail — it degenerates into a plain running mean of hlc3 and draws a smooth,
plausible, completely different line under the name VWAP, which would disagree with the one on the
TradingView chart it is supposed to reproduce. So most of what follows is about the distinction
between a bar that traded no ticks (a measurement, draw it) and a bar whose volume we do not have
(the absence of one, draw nothing), which is this repo's own standing rule arriving in a new layer.
"""

import math

import pytest

from services.vwap_overlays import INDICATOR_VWAP, build_vwap_indicator

BAR_MS = 15 * 60 * 1000
# 2026-01-05 00:00 UTC — a Monday, comfortably inside a single NY trading day.
T0 = 1767571200000


def _bars(rows, *, start=T0, step=BAR_MS):
    """rows = (high, low, close, volume). `volume=None` drops the key entirely for that bar."""
    out = []
    for i, (h, lo, c, v) in enumerate(rows):
        bar = {"time": start + i * step, "open": c, "high": h, "low": lo, "close": c}
        if v is not None:
            bar["volume"] = v
        out.append(bar)
    return out


def _flat(n, *, price=100.0, volume=10.0, start=T0):
    return _bars([(price + 1, price - 1, price, volume)] * n, start=start)


# --------------------------------------------------------------------------- the arithmetic


def test_the_value_is_the_volume_weighted_mean_of_hlc3():
    """Two bars, deliberately different weights, so a plain (unweighted) mean gives another answer.

    hlc3 is 100 on bar 1 and 200 on bar 2; at 1:3 volume the weighted mean is 175 and the
    unweighted one is 150 — so this cannot pass on an emitter that dropped the weighting.
    """
    ind = build_vwap_indicator(_bars([
        (100.0, 100.0, 100.0, 100.0),
        (200.0, 200.0, 200.0, 300.0),
    ]))

    assert [p["value"] for p in ind["series"]] == [100.0, 175.0]


def test_the_session_re_anchors_on_the_trading_day_roll():
    """18:00 New York is the boundary — the same one the liquidity engine's daily level uses.

    A running mean that never reset would carry the first day's 100 into the second and land
    between the two; re-anchoring gives the second day's own price exactly.
    """
    # 2026-01-05 22:00 UTC = 17:00 EST — still the previous trading day.
    before = 1767650400000
    bars = _bars([(100.0, 100.0, 100.0, 100.0)], start=before)
    # 23:00 UTC = 18:00 EST — the roll.
    bars += _bars([(200.0, 200.0, 200.0, 100.0)], start=before + 60 * 60 * 1000)

    ind = build_vwap_indicator(bars)
    assert [p["value"] for p in ind["series"]] == [100.0, 200.0]


def test_it_matches_the_canonical_engine_bar_for_bar():
    """The emitter must be a REPLAY of engines/vwap/, never a second implementation of a VWAP.

    A drift here is the shape this repo has met repeatedly — two places computing one number — and
    it would be invisible, because both answers look like a VWAP.
    """
    import sys
    from pathlib import Path

    engines = Path(__file__).resolve().parents[3] / "engines"
    if str(engines) not in sys.path:
        sys.path.insert(0, str(engines))
    from vwap import VwapEngine

    candles = _bars([
        (101.0, 99.0, 100.0, 10.0),
        (105.0, 100.0, 104.0, 30.0),
        (104.0, 98.0, 99.0, 5.0),
        (110.0, 103.0, 108.0, 250.0),
    ])
    engine = VwapEngine()
    expected = []
    for i, c in enumerate(candles):
        ev = engine.update(i, c["time"], c["high"], c["low"], c["close"], c["volume"])
        expected.append(round(ev.value, 5))

    got = [p["value"] for p in build_vwap_indicator(candles)["series"]]
    assert got == expected


# --------------------------------------------------------------------------- the shape it emits


def test_it_is_a_main_pane_series_that_starts_switched_off():
    ind = build_vwap_indicator(_flat(10))

    assert ind["name"] == INDICATOR_VWAP
    assert ind["pane"] == "main"
    # OFF on arrival, like every analysis layer added since the fair value gaps. A chart opens on
    # the run; each extra reading is something the reader asks for.
    assert ind["defaultOn"] is False
    assert len(ind["series"]) == 10


def test_every_point_carries_a_candle_time_in_order():
    candles = _flat(5)
    series = build_vwap_indicator(candles)["series"]

    assert [p["time"] for p in series] == [c["time"] for c in candles]


# --------------------------------------------------------------------------- the refusals


def test_no_volume_column_at_all_means_no_layer():
    """The honest answer for a feed that does not carry volume — absence removes the toggle, the
    same way the Blocked layer vanishes on a runner that cannot report refusals."""
    assert build_vwap_indicator(_bars([(101.0, 99.0, 100.0, None)] * 10)) is None


def test_one_bar_missing_its_volume_kills_the_whole_layer():
    """All-or-nothing, and this is the test that matters most.

    A part-way-refetched cache would otherwise produce a line that is a true VWAP over part of the
    history and a plain hlc3 mean over the rest, with the seam invisible — worse than no line,
    because the wrong half is not marked.
    """
    candles = _flat(20)
    del candles[7]["volume"]

    assert build_vwap_indicator(candles) is None


def test_a_nan_volume_is_missing_rather_than_zero():
    """NaN is what a merged cache produces for a span written before volume existed. Reading it as
    a zero-volume bar would weight that bar out of the average and answer confidently."""
    candles = _flat(20)
    candles[3]["volume"] = float("nan")

    assert build_vwap_indicator(candles) is None


def test_a_non_numeric_volume_is_refused_rather_than_coerced():
    candles = _flat(20)
    candles[3]["volume"] = "lots"

    assert build_vwap_indicator(candles) is None


def test_real_zero_volume_bars_still_DRAW():
    """The other side of the same rule, and the one a defensive fix would break.

    A dead session genuinely reports zero ticks. Treating zero as "unknown" would silently drop the
    layer on any run containing a quiet hour, which reads as the feature not existing.
    """
    candles = _flat(10)
    candles[4]["volume"] = 0.0
    candles[5]["volume"] = 0.0

    ind = build_vwap_indicator(candles)
    assert ind is not None
    assert len(ind["series"]) == 10


def test_a_session_with_no_volume_at_all_yields_no_line_rather_than_a_zero():
    """Pine's `ta.vwap` is `na` until the first traded tick — a divide by zero has no value, and
    emitting 0.0 would draw the line at the bottom of the pane."""
    assert build_vwap_indicator(_flat(10, volume=0.0)) is None


def test_no_candles_means_no_layer():
    assert build_vwap_indicator([]) is None


# --------------------------------------------------------------------------- the spec's candles


def test_the_spec_strips_volume_after_the_layers_have_read_it():
    """Volume is fetched for THIS layer and nothing in the browser plots it.

    On a full-history run that is ~156k numbers of payload, parse time and heap bought for nobody,
    so the spec carries the LINE and not the ingredients.
    """
    from services.chart_spec import _strip_volume

    candles = _flat(3)
    _strip_volume(candles)

    assert all("volume" not in c for c in candles)
    # …and the bars themselves are untouched.
    assert all({"time", "open", "high", "low", "close"} <= set(c) for c in candles)
