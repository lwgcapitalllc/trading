"""
Tests for `services/candle_overlays.py` — the candlestick-pattern candle repaint.

These pin the LAYER'S OWN rules — which anchor gets a mark, which bar of the window it lands on,
and what it refuses — not the pattern detection, which is the canonical engine's and is proven
against a real TradingView export by `engines/candlesticks/tools/compare_candles.py`.

⚠ Every fixture below builds its bars so a REAL pattern fires where the test needs one, and asserts
that it did. A test that placed a mark by mocking the engine would pass against a layer that reads
the wrong bar, which is the one thing worth checking here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.candle_overlays import (  # noqa: E402
    GROUP_CANDLES,
    _deepest_bar,
    _reversal_span,
    build_candle_overlays,
)

_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

_MIN = 60_000
_T0 = 1_600_000_000_000


def _bar(i: int, o: float, h: float, l: float, c: float) -> dict:
    return {"time": _T0 + i * 15 * _MIN, "open": o, "high": h, "low": l, "close": c}


def _flat(n: int, start: int = 0, price: float = 100.0) -> list[dict]:
    """Featureless filler. Small real bodies with no pattern in them — deliberately not doji-flat,
    since a zero-range bar IS a doji and would seed marks the test never asked for."""
    out = []
    for i in range(n):
        o = price + (i % 2) * 0.9
        c = o + 0.6
        out.append(_bar(start + i, o, max(o, c) + 0.4, min(o, c) - 0.4, c))
    return out


def _hammer_at(i: int, price: float = 100.0) -> dict:
    """A Hammer: tiny body at the top, long lower wick, almost no upper wick."""
    return _bar(i, price, price + 0.1, price - 6.0, price + 0.05)


def _candles_with_hammer(at: int, total: int = 60) -> list[dict]:
    bars = _flat(total)
    bars[at] = _hammer_at(at)
    # The hammer must be the LOW of its neighbourhood, or the layer's "adverse extreme" is elsewhere
    # and the test would be checking the wrong thing for the wrong reason.
    return bars


def _fired(candles: list[dict], at: int) -> bool:
    from candlesticks import CHART_PRESET, CandlestickEngine

    cs = CandlestickEngine(**CHART_PRESET)
    hit = False
    for i, c in enumerate(candles):
        ev = cs.update(i, c["open"], c["high"], c["low"], c["close"])
        if i == at:
            hit = bool(ev.detected)
    return hit


# ── the fixture itself has to be real ────────────────────────────────────────────────


def test_the_fixture_really_fires_a_pattern_where_the_tests_place_one():
    """Guards every test below. If the hammer stops being a hammer, they would all go green by
    drawing nothing, and none of them would say why."""
    candles = _candles_with_hammer(40)
    assert _fired(candles, 40), "fixture no longer fires a pattern — every test below is vacuous"


# ── which anchors produce a mark ─────────────────────────────────────────────────────


def test_no_anchor_means_no_marks_at_all():
    """The whole point of the layer: five of these patterns fire on 5-9% of ALL bars, so without
    the anchor filter it would paint roughly one bar in twelve and say nothing."""
    candles = _candles_with_hammer(40)
    assert build_candle_overlays(candles, []) == []


def test_an_anchor_on_the_pattern_bar_marks_that_bar():
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(candles, [(candles[40]["time"], "long", None)])
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"]
    assert out[0]["group"] == GROUP_CANDLES
    assert out[0]["label"]


def test_an_anchor_with_no_pattern_in_its_window_draws_nothing():
    """No pattern at the turn is a real answer, and the honest one — never a mark on the nearest
    bar that happens to have something."""
    candles = _candles_with_hammer(40)
    # Anchor far from the hammer, in flat filler.
    out = build_candle_overlays(candles, [(candles[10]["time"], "long", None)])
    assert out == []


def test_an_anchor_outside_the_loaded_candles_is_dropped():
    candles = _candles_with_hammer(40)
    before = candles[0]["time"] - 10 * 15 * _MIN
    after = candles[-1]["time"] + 10 * 15 * _MIN
    assert build_candle_overlays(candles, [(before, "long", None), (after, "long", None)]) == []


# ── which bar of the window it lands on ──────────────────────────────────────────────


def test_price_running_further_before_it_turns_marks_the_turn_not_the_anchor():
    """Aaron's rule: 'if not, then price went down a little more and reversed, plot it there.'"""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(candles, [(candles[38]["time"], "long", None)])
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"], "the mark should be on the reversal, not the anchor"


def test_EVERY_pattern_in_the_span_is_marked_not_only_the_one_at_the_turn():
    """Aaron's ask, and the reason this layer stopped picking a winner: *"you don't only have to give
    me the deepest candle — you could give me all the candles that would have shown a possible
    reversal all the way up to the deepest one … I could see, wow, I could have taken a trade at
    0.702 or 0.786."* A doji sits on the anchor bar and the hammer at the low is two bars later;
    BOTH are entries he could have taken, so both are drawn.

    ⚠ Watch it go red by marking only the turn — that is exactly what this used to do."""
    bars = _flat(60)
    bars[38] = _bar(38, 100.0, 100.5, 99.5, 100.0)  # a doji, well above the low
    bars[40] = _hammer_at(40)  # the turn
    assert _fired(bars, 38) and _fired(bars, 40), "both bars must fire or this proves nothing"
    out = build_candle_overlays(bars, [(bars[38]["time"], "long", None)])
    assert [o["t"] for o in out] == [bars[38]["time"], bars[40]["time"]]


def test_a_pattern_COMPLETING_just_after_the_turn_is_still_that_turns_reversal():
    """🔴 The span used to stop AT the turn, and that threw the answer away on four setups in ten.
    ✅ **MEASURED on 194 real anchors: 37.1% carry a pattern on the turn bar and a further 40.2%
    complete 1-2 bars after it** — because a pattern is reported on the bar it COMPLETES and the
    engine's longest run to three bars, so the bar that MADE the extreme is usually the pattern's
    first bar. Reported as *"it's not showing the deepest candle pattern that would have been the
    most perfect entry."*"""
    bars = _flat(60)
    # ⚠ Plain bearish bodies either side, for the reason the fixture two tests down records: a lone
    # bearish bar among bullish filler makes its NEIGHBOURS a Morning/Evening Star.
    for j in range(36, 42):
        bars[j] = _bar(j, 101.5, 101.9, 100.5, 100.9)
    bars[40] = _bar(40, 100.0, 100.05, 90.0, 90.05)  # the turn — a long body, no pattern
    # ⚠ Its low must stay ABOVE bar 40's, or the hammer becomes the turn itself and the test is no
    # longer about a pattern completing after one.
    bars[42] = _hammer_at(42, 97.0)  # ...the reversal, completing 2 bars later
    assert not _fired(bars, 40), "the turn bar must be quiet or this proves nothing"
    assert _fired(bars, 42)
    out = build_candle_overlays(bars, [(bars[38]["time"], "long", bars[55]["time"])])
    assert [o["t"] for o in out] == [bars[42]["time"]]
    assert out[0]["deepestOf"] == [0], (
        "it IS the turn's reversal, so it is that span's deepest mark"
    )


def test_nothing_is_marked_PAST_the_confirmation_WINDOW():
    """The window is the longest pattern's length minus one and must not become a free-for-all: far
    past the turn price is moving the setup's way, and a reversal candle there is a different
    subject. ⚠ This is what stops `_CONFIRM_BARS` being read as a tuning dial."""
    bars = _flat(60)
    bars[40] = _hammer_at(40)  # the turn (the low of the whole window)
    bars[45] = _bar(45, 100.0, 100.5, 99.5, 100.0)  # a doji 5 bars later, well above the low
    assert _fired(bars, 40) and _fired(bars, 45), "both bars must fire or this proves nothing"
    out = build_candle_overlays(bars, [(bars[38]["time"], "long", bars[55]["time"])])
    assert [o["t"] for o in out] == [bars[40]["time"]]


def test_the_window_does_not_reach_past_its_own_length():
    """A pattern four bars past the anchor is outside the short window and must not be claimed."""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(candles, [(candles[36]["time"], "long", None)], window=3)
    assert out == []


def test_two_anchors_resolving_to_one_candle_produce_ONE_mark():
    """A block and the trade it preceded routinely land on the same reversal; that is one candle,
    not two stacked repaints of it."""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(
        candles,
        [(candles[38]["time"], "long", None), (candles[39]["time"], "long", None)],
    )
    assert len(out) == 1


# ── direction is a PREFERENCE, not a filter ──────────────────────────────────────────
#
# Aaron, 2026-08-08, on a Bearish Engulfing marking a LONG that WON: *"we should have plotted a
# bullish candle if one was present."* The three tiers are aligned → neutral → opposing, and the
# fixture below is the realistic shape of that: the source Pine gates its DIRECTIONAL rules on a
# 117-bar trend, so in an uptrend the bullish rules cannot fire at all — which is exactly why the
# reference trade's mark was bearish. The tier that rescues it is the NEUTRAL one.


def _uptrend(n: int = 200, price: float = 100.0) -> list[dict]:
    """A long, gentle uptrend — enough bars for `trend=117` to have an opinion, which every
    DIRECTIONAL pattern in the preset needs before it will fire at all."""
    out, p = [], price
    for i in range(n):
        o, c = p, p + 0.4
        out.append(_bar(i, o, max(o, c) + 0.3, min(o, c) - 0.3, c))
        p = c
    return out


def _neutral_and_opposing(with_neutral: bool = True) -> list[dict]:
    """Bar 152 = a Bearish Engulfing at the neighbourhood LOW. Bar 150 = a neutral Doji + Hammer,
    two bars shallower. On a LONG, the neutral bar must win despite being further from the turn."""
    bars = _uptrend()
    if with_neutral:
        b = bars[150]["open"]
        bars[150] = _bar(150, b, b + 0.1, b - 6.0, b + 0.05)
    prev = bars[151]
    bars[151] = _bar(
        151, prev["close"], prev["close"] + 2.0, prev["close"] - 0.2, prev["close"] + 1.8
    )
    prev = bars[151]
    bars[152] = _bar(
        152, prev["close"] + 0.5, prev["close"] + 0.7, prev["open"] - 9.2, prev["open"] - 9.0
    )
    return bars


def test_a_neutral_candle_and_an_OPPOSING_one_are_both_drawn():
    """The reference defect is gone by construction rather than by ranking: selecting one candle is
    what let a Bearish Engulfing be the sole mark on a long that WON. Both bars are setups he could
    have read, so both are drawn and each is named for itself."""
    bars = _neutral_and_opposing()
    assert _fired(bars, 150) and _fired(bars, 152), "both bars must fire or this proves nothing"
    assert bars[152]["low"] < bars[150]["low"], "152 must be the adverse extreme of the window"
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None)])
    assert [(o["t"], o["patternDir"]) for o in out] == [
        (bars[150]["time"], 0),
        (bars[152]["time"], -1),
    ]


def test_with_NOTHING_but_an_opposing_candle_it_is_still_marked():
    """The half worth defending: *'if not, it will show me why I was wrong.'* Direction orders the
    NAME on a bar and must never decide whether the bar is painted — remove the neutral candle and
    the bearish one is still the answer."""
    bars = _neutral_and_opposing(with_neutral=False)
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None)])
    assert len(out) == 1
    assert out[0]["t"] == bars[152]["time"]
    assert out[0]["patternDir"] == -1


def test_a_bar_carrying_BOTH_is_named_after_the_one_pointing_the_setups_way():
    """7.4% of bars carry more than one pattern, so `label` is a CHOICE. Naming the opposing one on
    a bar that also printed a neutral reversal is the same defect one level down."""
    bars = _uptrend()
    prev = bars[151]
    bars[151] = _bar(
        151, prev["close"], prev["close"] + 2.0, prev["close"] - 0.2, prev["close"] + 1.8
    )
    prev = bars[151]
    # Engulfs the bar before AND has a long lower wick with a small body — Bearish Engulfing + Hammer.
    bars[152] = _bar(
        152, prev["close"] + 0.5, prev["close"] + 0.7, prev["open"] - 9.0, prev["open"] - 0.5
    )
    out = build_candle_overlays(bars, [(bars[152]["time"], "long", None)])
    assert len(out) == 1
    assert set(out[0]["patterns"]) == {"Bearish Engulfing", "Hammer"}, "fixture must carry both"
    assert out[0]["label"] == "Hammer"
    assert out[0]["patternDir"] == 0


def test_a_pattern_pointing_AGAINST_the_setup_is_still_marked():
    """The 'why I was wrong' half, and Aaron's explicit ask: a bullish candle at a short is the
    explanation for the loss, and hiding it would remove the more useful reading."""
    candles = _candles_with_hammer(40)
    # Same bars, read as a SHORT setup. The hammer is neutral-to-bullish and the layer must still
    # mark it — what changes is only which end of the window counts as the turn.
    out = build_candle_overlays(candles, [(candles[40]["time"], "short", None)])
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"]


# ── a winner is searched over its hold ───────────────────────────────────────────────


def test_a_winning_hold_finds_a_turn_far_beyond_the_short_window():
    """MEASURED on the live lab: a winner's adverse extreme is a median 2 bars past entry but p90
    is 27, so a fixed short window finds the real turn on barely half of them."""
    candles = _candles_with_hammer(40)
    entry, exit_ = candles[20]["time"], candles[55]["time"]
    assert build_candle_overlays(candles, [(entry, "long", None)]) == [], (
        "short window should miss it"
    )
    out = build_candle_overlays(candles, [(entry, "long", exit_)])
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"]


def test_a_pattern_mid_hold_IS_drawn_even_though_it_is_far_from_the_turn():
    """The counterpart of the test above, and the rule that replaced the old ±2-bar tolerance: a
    pattern 20 bars before the turn is not "the reversal", but it IS a level the retracement offered
    on the way down, which is the whole question. ⚠ The tolerance used to DELETE it — the span
    covers it now, and the marks between the entry and the turn are the answer he asked for."""
    bars = _flat(60)
    bars[30] = _hammer_at(30)  # a pattern, mid-hold
    # ⚠ A lone bearish bar after bullish filler makes its NEIGHBOURS a Morning/Evening Star — a
    # three-bar pattern is a property of the bars AROUND the one you are placing — so the turn is
    # built with plain bodies either side and asserted quiet.
    for j in range(46, 56):
        bars[j] = _bar(j, 101.5, 101.9, 100.5, 100.9)  # plain bearish bodies
    bars[50] = _bar(50, 100.0, 100.05, 80.0, 80.05)  # one long body, almost no wick
    assert _fired(bars, 30), "the mid-hold pattern must really fire or this test is vacuous"
    for j in range(48, 53):
        assert not _fired(bars, j), f"bar {j} is at the turn and must carry NO pattern"
    out = build_candle_overlays(bars, [(bars[20]["time"], "long", bars[55]["time"])])
    assert [o["t"] for o in out] == [bars[30]["time"]]


def test_an_exit_before_the_entry_degrades_to_the_short_window():
    """A malformed hold must not drop a real setup — it still gets the answer it can have."""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(
        candles,
        [(candles[40]["time"], "long", candles[10]["time"])],
    )
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"]


# ── the payload ──────────────────────────────────────────────────────────────────────


def test_the_mark_carries_the_bars_own_OHLC():
    """The frontend REDRAWS the candle rather than boxing it, so all four prices have to be here —
    a box hugging high→low would hide the bar it is meant to point at."""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(candles, [(candles[40]["time"], "long", None)])
    c = candles[40]
    assert (out[0]["open"], out[0]["high"], out[0]["low"], out[0]["close"]) == (
        c["open"],
        c["high"],
        c["low"],
        c["close"],
    )


def test_the_mark_names_the_pattern_and_counts_the_rest():
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(candles, [(candles[40]["time"], "long", None)])
    assert out[0]["label"] in out[0]["patterns"]
    # ⚠ `extra` (a COUNT of the others) is gone. It rendered as "Hammer +1", which reads as a claim
    # about the pattern rather than about the bar — reported as *"how could a pattern have more than
    # one name?"* The chart joins `patterns` instead, so the tag answers the question itself.
    assert "extra" not in out[0]
    assert out[0]["patternDir"] in (-1, 0, 1)


def test_marks_come_out_in_time_order():
    """The panel clips by time range, so an unordered list would make that a scan rather than a
    bisect — and a reader stepping through them would jump about."""
    bars = _flat(120)
    for at in (30, 60, 90):
        bars[at] = _hammer_at(at)
    anchors = [(bars[at]["time"], "long", None) for at in (90, 30, 60)]
    out = build_candle_overlays(bars, anchors)
    assert len(out) == 3
    assert [o["t"] for o in out] == sorted(o["t"] for o in out)


# ── it must never take the chart down ────────────────────────────────────────────────


@pytest.mark.parametrize("candles", [[], [_bar(0, 1, 1, 1, 1)]])
def test_too_few_candles_returns_empty_rather_than_raising(candles):
    assert build_candle_overlays(candles, [(_T0, "long", None)]) == []


def test_the_engine_defaults_are_NOT_used__the_chart_preset_is():
    """The engine mirrors its source Pine (trend 5 / doji 0.05); the CHART is read against Aaron's
    brother's inputs (117 / 0.01). Pinning this stops a future tidy-up quietly repointing the layer
    at the defaults, which would make the chart stop matching the indicator beside it."""
    from candlesticks import CHART_PRESET

    assert CHART_PRESET["trend"] == 117
    assert CHART_PRESET["doji_size"] == 0.01
    assert len(CHART_PRESET["patterns"]) == 11


# ── which candle gets NAMED, and how the outcome flips it ────────────────────────────
#
# Aaron, 2026-08-08, off two screenshots of WINNERS named with the opposing candle (a long reading
# `Won · Bearish Engulfing`, a short reading `Won · Bullish Harami`): *"if I won it should default
# to the BEST candle that helped or COULD HAVE HELPED signal the reversal (typically the deepest
# CORRECT with trade direction). If I lost it should default to the candle that signaled why I
# lost. If I missed the trade it should default to the DEEPEST CORRECT candle that I could have
# used to enter. I should see BULLISH candle for long trades or BEARISH candle for short trades."*
#
# ⚠ Every one of these was WATCHED RED against HEAD, where the pick was nearest-the-turn over the
# whole span and the ordering was setup-aligned regardless of outcome.


def _preferred_and_nearer_opposing():
    """A span holding a candle pointing the SETUP's way, and an opposing one NEARER the turn.

    That is the shape the defect needs: rank on nearness and the opposing one wins, which is
    exactly what put a Bearish Engulfing on a long that won.
    """
    return _neutral_and_opposing()


def test_a_WINNER_is_named_after_the_candle_pointing_its_own_way():
    """The reported defect, stated as a rule. The bar at the turn is bearish and a NEUTRAL bar sits
    further from it — on a winning long the neutral one is the better answer, and the opposing one
    must not win merely by sitting closer."""
    bars = _neutral_and_opposing()
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = [o for o in out if o["deepestOf"]]
    assert len(deepest) == 1
    assert deepest[0]["patternDir"] != -1, "a winning LONG must not be named by a bearish candle"
    assert deepest[0]["t"] == bars[150]["time"]


def test_a_LOSER_is_named_after_the_candle_that_BEAT_it():
    """The other half of the same rule, and the one that inverts: *"if I lost it should default to
    the candle that signaled why I lost."* Same bars, same side — only the outcome changes — and
    the bearish candle is now the answer rather than the thing to avoid."""
    bars = _neutral_and_opposing()
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "loss")])
    deepest = [o for o in out if o["deepestOf"]]
    assert len(deepest) == 1
    assert deepest[0]["patternDir"] == -1
    assert deepest[0]["t"] == bars[152]["time"]


def test_the_outcome_changes_the_NAME_and_never_what_is_PAINTED():
    """The guard on the whole idea: this is a preference, exactly as the within-bar ordering is.
    Both readings of the same span draw the same candles — only `deepestOf` moves."""
    bars = _neutral_and_opposing()
    anchor = (bars[150]["time"], "long", None)
    won = build_candle_overlays(bars, [(*anchor, "win")])
    lost = build_candle_overlays(bars, [(*anchor, "loss")])
    assert [o["t"] for o in won] == [o["t"] for o in lost]
    assert [o["patternDir"] for o in won] == [o["patternDir"] for o in lost]


def test_a_MISS_is_named_like_a_winner_not_like_a_loss():
    """A miss was never entered, so the question is *which candle could I have entered on* — the
    winner's question. Filing it as a loss would name it after the candle that beat a trade nobody
    took."""
    bars = _neutral_and_opposing()
    anchor = (bars[150]["time"], "long", None)
    miss = build_candle_overlays(bars, [(*anchor, "miss")])
    won = build_candle_overlays(bars, [(*anchor, "win")])
    assert [o["deepestOf"] for o in miss] == [o["deepestOf"] for o in won]


def test_an_anchor_with_no_outcome_reads_as_a_WIN():
    """An older caller keeps the aligned preference rather than silently switching every trade it
    draws to the loser rule."""
    bars = _neutral_and_opposing()
    bare = build_candle_overlays(bars, [(bars[150]["time"], "long", None)])
    won = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    assert [o["deepestOf"] for o in bare] == [o["deepestOf"] for o in won]


def test_a_NEUTRAL_candle_is_preferred_over_an_OPPOSING_one():
    """MEASURED on the reference run: 59 of 194 spans hold no directional candle at all, so a
    two-tier `preferred or anything` pool picks the opposing bar whenever it sits nearer the turn.
    The neutral tier is not a rounding case here — it is most of the layer."""
    bars = _neutral_and_opposing()
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = next(o for o in out if o["deepestOf"])
    assert deepest["patternDir"] == 0


def test_with_ONLY_an_opposing_candle_it_is_still_the_deepest():
    """The fallback, and it must not be dropped to nothing: a setup whose only candles point the
    other way still has a deepest one, and reporting "no reversal candle" for a setup that plainly
    had one is the failure the layer's opposing tier exists to prevent."""
    bars = _neutral_and_opposing(with_neutral=False)
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = [o for o in out if o["deepestOf"]]
    assert len(deepest) == 1
    assert deepest[0]["patternDir"] == -1


def test_the_deepest_mark_names_itself_PER_ANCHOR():
    """One bar can be the deepest of two anchors wanting opposite directions, so the bar's single
    `label` is whichever anchor reached it first and is nobody's answer in particular. Each anchor
    gets its own name off `deepestNames`."""
    bars = _neutral_and_opposing()
    out = build_candle_overlays(
        bars,
        [
            (bars[150]["time"], "long", None, "win"),
            (bars[150]["time"], "long", None, "loss"),
        ],
    )
    named = {n: nm for o in out for n, nm in (o.get("deepestNames") or {}).items()}
    assert set(named) == {"0", "1"}, "both anchors must be named"
    assert named["0"] != named["1"], "a winner and a loser on one leg want different candles"


# ---------------------------------------------------------------------------
# "Deepest" is a PRICE, and an OPPOSING candle is never the NAME
#
# Two defects Aaron reported off the chart on 2026-08-08, from two different trades:
#
#   *"look at this trade on june 16 2026 — the deepest best entry was on a bearish engulfing yet
#    you did not highlight it."*  → the fallback ranked by TIME, so the LAST pattern bar in the span
#    won even when an earlier one sat deeper in the retracement.
#
#   *"how can I have won a short and the best candle be a bullish harami? Shouldn't it be a neutral
#    candle, no candle or best yet a bearish candle?"*  → the name fell through to an OPPOSING
#    candle whenever the span held nothing else.
#
# ⚠ All five were WATCHED RED against HEAD.


def _plant_bear_engulf(bars: list[dict], i: int, reach: float) -> None:
    """A Bearish Engulfing completing on bar `i`, whose HIGH reaches `reach` above the local price.

    On a SHORT, `reach` is how DEEP into the retracement that candle went — which is the whole
    subject here, and it is deliberately independent of WHEN the bar sits.
    """
    base = bars[i - 1]["open"]
    bars[i - 1] = _bar(i - 1, base, base + 2.0, base - 0.2, base + 1.8)
    prev = bars[i - 1]
    top = prev["close"] + reach
    bars[i] = _bar(i, prev["close"] + 0.5, top, prev["open"] - 9.2, prev["open"] - 9.0)


def _deep_early__shallow_late() -> list[dict]:
    """A short whose span holds two aligned candles: a DEEPER one early and a shallower one later,
    with the turn past both so nothing reaches it and the fallback is what decides.

    ⚠ The early bar is made deeper with a WICK rather than by position, because in a rising market
    a later bar is higher by default — which is exactly the confound that let a recency rule look
    correct for so long.
    """
    bars = _uptrend(200)
    _plant_bear_engulf(bars, 155, reach=24.0)  # deeper (higher), earlier
    _plant_bear_engulf(bars, 170, reach=0.7)  # shallower, later
    bars[185] = _bar(
        185, bars[185]["open"], bars[185]["high"] + 60.0, bars[185]["low"], bars[185]["close"]
    )
    return bars


def test_the_DEEPEST_candle_wins_the_name_not_the_most_RECENT_one():
    """MEASURED on the reference run's 2026-06-16 short: the span held three Bearish Engulfings and
    the LAST pattern bar was a Bearish Harami at high 4345.02, while the deepest aligned candle was
    a Bearish Engulfing at 4349.27 — $4.25 deeper, i.e. the better short entry, and the one Aaron
    named. Over that run's 166 anchors the deepest bar moves on 13 and the NAME changes on 8."""
    bars = _deep_early__shallow_late()
    out = build_candle_overlays(bars, [(bars[150]["time"], "short", bars[195]["time"], "win")])
    # Scoped to the ALIGNED tier, which is the pool the fallback actually chooses from — the
    # turn bar's own long wick prints a neutral pattern, and that bar is in a lower tier.
    aligned = [o for o in out if o["spans"] and o["patternDir"] == -1]
    assert len(aligned) >= 2, "the fixture must produce two aligned bars to choose between"
    deepest = next(o for o in out if o["deepestOf"])
    assert deepest["high"] == max(o["high"] for o in aligned), "deepest on a short is the HIGHEST"
    assert deepest["t"] != max(o["t"] for o in aligned), "and it is NOT simply the latest"


def test_deepest_is_measured_the_other_way_up_on_a_LONG():
    """A long retraces DOWNWARDS, so its deepest candle is the LOWEST. Driven straight at
    `_deepest_bar` because the directional patterns a full fixture would need cannot fire in the
    trend a long's retracement requires — the rule is what is under test, not the engine."""
    # ⚠ Bar 1 is the WIDER bar and bar 3 sits INSIDE it, which is what makes this check bite.
    # It was vacuous twice before landing on this shape: with the extremes split across the two
    # bars, a rule reading the wrong PRICE still returns the right index, because the comparator
    # is chosen by direction and only the key is wrong. Here bar 1 has both the lowest low and the
    # highest high, so reading `high` on a long picks bar 3 and reading `low` on a short picks
    # bar 3 — each mutation is separated by exactly one of these two assertions.
    bars = [_bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(5)]
    bars[1] = _bar(1, 100.0, 115.0, 90.0, 100.0)
    bars[3] = _bar(3, 100.0, 101.0, 95.0, 100.0)
    assert _deepest_bar(bars, [1, 3], "long") == 1, "a long's deepest is the LOWEST low"
    assert _deepest_bar(bars, [1, 3], "short") == 1, "a short's deepest is the HIGHEST high"


def test_an_OPPOSING_candle_is_never_the_name():
    """Aaron: *"Shouldn't it be a neutral candle, no candle or best yet a bearish candle?"* — so the
    preference ends at NEUTRAL and the honest answer below it is silence. MEASURED: 9 of the
    reference run's 166 anchors hold nothing but opposing candles, and every one of them used to be
    named after the candle arguing AGAINST the setup."""
    bars = _neutral_and_opposing(with_neutral=False)
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = next(o for o in out if o["deepestOf"])
    assert deepest["patternDir"] == -1, "the fixture must hold ONLY an opposing candle"
    assert (deepest.get("deepestNames") or {}).get("0") is None, "so it must not be NAMED"


def test_an_unnamed_span_is_still_PAINTED_and_still_the_deepest():
    """Withholding the NAME may never withhold the MARK: the opposing candle is half the point of
    the layer (*"it will show me why I was wrong"*), and dropping it from `deepestOf` would hide it
    behind the panel's "Only the deepest" setting."""
    bars = _neutral_and_opposing(with_neutral=False)
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = [o for o in out if o["deepestOf"]]
    assert len(deepest) == 1, "the span still has a deepest mark"
    assert deepest[0]["patterns"], "and it is still drawn, with its pattern list intact"


def test_a_span_holding_a_NEUTRAL_candle_is_still_named():
    """The floor is neutral, not aligned. 59 of the reference run's 194 spans hold no directional
    candle at all — ten of the source Pine's fifteen rules gate on a trend lookback — so raising the
    floor to aligned would strip the name off a third of the layer for no reason."""
    bars = _neutral_and_opposing(with_neutral=True)
    out = build_candle_overlays(bars, [(bars[150]["time"], "long", None, "win")])
    deepest = next(o for o in out if o["deepestOf"])
    assert (deepest.get("deepestNames") or {}).get("0") is not None


# ── the span covers the whole DRAWDOWN, not two bars past the extreme ────────────────


def _short_with_a_long_drawdown() -> tuple[list[dict], float]:
    """A short entered at 100 that runs against itself, tops out EARLY, then grinds sideways ABOVE
    the entry for a long time before finally dropping away.

    Two hammers: one inside `turn + _CONFIRM_BARS` and one much later but still in the drawdown.
    The second is the candle Aaron reported missing — on his 2026-06-18 short the turn is 02:00
    while the trade stays above its entry until 05:30, so the layer saw 9 bars of a 21-bar zone.
    """
    entry = 100.0
    bars = _flat(30, price=90.0)  # below the entry: context before the trade
    bars += [_bar(30 + i, 101.0, 101.6, 100.6, 101.2) for i in range(30)]  # the drawdown, adverse
    bars[32] = _bar(32, 108.0, 112.0, 107.9, 108.0)  # the adverse EXTREME, early in the zone
    bars[34] = _hammer_at(34, 101.0)  # inside turn + _CONFIRM_BARS (turn is 32)
    bars[50] = _hammer_at(50, 101.0)  # still above the entry, far past the extreme
    bars += _flat(20, start=60, price=80.0)  # price has left the band for good
    bars[70] = _hammer_at(70, 80.0)  # favourable side — must NOT be marked
    return bars, entry


def test_the_span_covers_the_WHOLE_drawdown_not_two_bars_past_the_extreme():
    """🔴 Watched RED against HEAD, where only the 35 hammer is drawn.

    Aaron, off the chart: *"In drawdown, you're supposed to map all the applicable candles in line
    with the order we trade. I've hovered over the candles which I think you've missed."* The zone
    a reader points at is the red band, which outlives the bar that made its high.
    """
    bars, entry = _short_with_a_long_drawdown()
    assert _fired(bars, 34) and _fired(bars, 50), "fixture must fire in BOTH halves of the zone"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "short", bars[79]["time"], "win", entry)],
    )
    times = {o["t"] for o in out}
    assert bars[34]["time"] in times, "the candle near the extreme was already drawn"
    assert bars[50]["time"] in times, "the one later in the drawdown is the reported gap"


def test_a_candle_past_the_drawdown_is_NOT_marked():
    """The span is the adverse band, never the whole hold. Once price is trading entirely on the
    favourable side the trade is winning, and a reversal candle there is a different subject —
    marking it would put navy candles all down a runner's profitable leg.

    ⚠ Non-vacuity is by MUTATION (dropping the band test from `_in_zone`), not by a fail-watch:
    HEAD draws nothing out there either, for the unrelated reason that its span stopped earlier.
    """
    bars, entry = _short_with_a_long_drawdown()
    assert _fired(bars, 70), "fixture must fire a pattern out past the zone"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "short", bars[79]["time"], "win", entry)],
    )
    assert bars[70]["time"] not in {o["t"] for o in out}


def test_an_anchor_with_NO_entry_price_keeps_the_turn_relative_span():
    """A 3/3 MISS opened no position, so it has no drawdown to cover — its span is the visit into
    the zone and already ends at the deepest point of that visit. Handing it an entry price it does
    not have would stretch it over whatever price did next.

    ⚠ It drives `_reversal_span` directly rather than going through a fixture, and that is what
    makes it bite: the first attempt asserted on the MARKS and passed under the mutation, because
    the substituted price happened to fall on the wrong side of one wick and cut the walk short
    anyway. The rule under test is the span, so the span is what is read.

    ⚠ A pin, proven by MUTATION (defaulting `entry` to the start bar's close), not a fail-watch.
    """
    bars, entry = _short_with_a_long_drawdown()
    _, hi_none, turn = _reversal_span(bars, 30, "short", 3, 79, None)
    _, hi_entry, _ = _reversal_span(bars, 30, "short", 3, 79, entry)
    assert hi_none == turn + 2, "with no entry price the span still ends at turn + _CONFIRM_BARS"
    assert hi_entry > hi_none, "and the same anchor WITH one reaches to the end of the drawdown"


# ── the zone is a PRICE band, not a stretch of time ──────────────────────────────────


def _long_that_drifts_up_then_dips_then_takes_off() -> tuple[list[dict], float]:
    """A long entered at 100 that drifts ABOVE its entry first, then dips into a real drawdown,
    then leaves the band for good and rallies away — Aaron's 2026-07-15 long in miniature.

    Four hammers, one in each region the rule has to tell apart:
      32 — above the entry, BEFORE the turn      (favourable: must not be marked)
      40 — inside the band, past turn + confirm  (the drawdown: must be marked)
      43 — two bars past the end of the drawdown (the takeoff: must not be marked)
      52 — far into the rally                    (must not be marked)
    """
    entry = 100.0
    bars = _flat(30, price=90.0)
    bars += [_bar(30 + i, 101.4, 102.0, 100.8, 101.6) for i in range(4)]  # above the entry
    bars += [_bar(34 + i, 99.0, 99.6, 98.2, 99.2) for i in range(8)]  # the drawdown
    bars += _flat(20, start=42, price=110.0)  # gone for good
    bars[32] = _hammer_at(32, 108.0)  # low 102 — favourable side
    bars[36] = _bar(36, 96.0, 96.4, 92.0, 96.1)  # the adverse EXTREME
    bars[40] = _hammer_at(40, 99.5)  # low 93.5 — deep in the band
    bars[41] = _bar(41, 99.8, 100.4, 99.7, 100.2)  # the last bar touching the entry
    bars[43] = _hammer_at(43, 112.0)  # low 106 — two bars past the drawdown
    bars[52] = _hammer_at(52, 112.0)  # low 106 — far into the rally
    return bars, entry


def test_a_candle_two_bars_past_the_drawdown_is_NOT_marked():
    """🔴 Watched RED against HEAD, which draws bar 43.

    THE REPORTED DEFECT. `_CONFIRM_BARS` was added to the end of the DRAWDOWN instead of to the
    TURN, so every trade got two free bars after price had already left the band — and on a trade
    that leaves the band into a rally those two bars ARE the rally. Aaron, off his 2026-07-15 long:
    *"it said won on inverted hammer but there is no inverted hammer near entry or within draw down
    … it is somewhere in between."* On that trade it was the only mark, so it named the chip.
    """
    bars, entry = _long_that_drifts_up_then_dips_then_takes_off()
    assert _fired(bars, 43), "fixture must fire a pattern two bars past the drawdown"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "long", bars[59]["time"], "win", entry)],
    )
    times = {o["t"] for o in out}
    assert bars[43]["time"] not in times, "two bars past the band is the takeoff, not the drawdown"
    assert bars[52]["time"] not in times, "and neither is the rest of the rally"


def test_a_favourable_candle_BEFORE_the_turn_is_NOT_marked():
    """🔴 Watched RED against HEAD, which draws bar 32.

    The other half of the same report, and no bound on the END could have caught it: the span opens
    at the ENTRY BAR, so a trade that runs into profit first and only later comes back to make its
    adverse extreme painted the whole excursion in between. MEASURED on run `e51d95f212e3`, that is
    196 of 255 stray marks, one of them 112 bars after its entry.
    """
    bars, entry = _long_that_drifts_up_then_dips_then_takes_off()
    assert _fired(bars, 32), "fixture must fire a pattern above the entry, before the turn"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "long", bars[59]["time"], "win", entry)],
    )
    assert bars[32]["time"] not in {o["t"] for o in out}


def test_the_candles_INSIDE_the_band_are_still_drawn():
    """The counterweight, and the reason the two tests above are not satisfied by drawing nothing:
    a pattern deep in the drawdown — past `turn + _CONFIRM_BARS`, so it qualifies on the band test
    alone — is exactly what this layer exists to show.
    """
    bars, entry = _long_that_drifts_up_then_dips_then_takes_off()
    assert _fired(bars, 40), "fixture must fire a pattern inside the band"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "long", bars[59]["time"], "win", entry)],
    )
    assert bars[40]["time"] in {o["t"] for o in out}


def test_a_pattern_completing_just_after_the_turn_is_still_marked():
    """The one exemption from the band test, and it is why this is not simply a price filter.

    A pattern is reported on the bar it COMPLETES, so a three-bar reversal that starts on the
    extreme finishes two bars later — on a sharp V that bar is already back above the entry. Cutting
    it costs the reversal candle itself: MEASURED over 166 anchors, a band-only rule leaves 40 trades
    with no mark against this rule's 21.

    ⚠ A pin, proven by MUTATION (dropping the `turn <= i <= turn + _CONFIRM_BARS` clause), not by a
    fail-watch — HEAD draws this bar too, for its own broader reason.
    """
    entry = 100.0
    bars = _flat(30, price=90.0)
    bars += [_bar(30 + i, 99.0, 99.5, 98.0, 99.2) for i in range(5)]  # in the band
    bars += _flat(25, start=35, price=110.0)  # straight out of it
    bars[34] = _bar(34, 96.0, 96.4, 92.0, 96.1)  # the extreme, last in band
    bars[35] = _hammer_at(35, 112.0)  # low 106 — turn + 1
    assert _fired(bars, 35), "fixture must fire a pattern one bar past the extreme"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "long", bars[59]["time"], "win", entry)],
    )
    assert bars[35]["time"] in {o["t"] for o in out}


# ── the zone stops at the EXIT, and re-opens whenever price comes BACK ────────────────


def _short_stopped_out_at_its_high() -> tuple[list[dict], float]:
    """A short at 100 that runs straight against itself and is stopped out on its worst bar — so the
    adverse extreme IS the exit. A hammer prints two bars later, after the position is closed."""
    entry = 100.0
    bars = _flat(30, price=90.0)
    bars += [_bar(30 + i, 101.0 + i, 102.6 + i, 100.6 + i, 102.2 + i) for i in range(5)]  # 30..34
    bars += _flat(25, start=35, price=106.0)
    bars[36] = _hammer_at(36, 108.0)  # two bars past the exit
    return bars, entry


def test_nothing_is_marked_after_the_trade_has_CLOSED():
    """🔴 Watched RED against HEAD, which draws bar 36.

    A stopped-out trade's adverse extreme is its FINAL bar, so `turn + _CONFIRM_BARS` lands after
    the position is closed — the allowance quietly reached into the next setup. Aaron, off his
    2026-05-11 short (stopped out 13:30, a `Hammer` painted at 14:00): *"Trade already lost. You
    already hit stop loss… I don't care what the candles after the trade. It has to be within the
    trade."*
    """
    bars, entry = _short_stopped_out_at_its_high()
    assert _fired(bars, 36), "fixture must fire a pattern after the exit"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "short", bars[34]["time"], "loss", entry)],
    )
    assert bars[36]["time"] not in {o["t"] for o in out}


def _short_that_dips_then_returns_to_its_entry() -> tuple[list[dict], float]:
    """A short at 100 that goes against itself, falls away into profit, then comes BACK to the entry
    later in the hold — the re-test, with a hammer on it — before dropping away for good."""
    entry = 100.0
    bars = _flat(30, price=90.0)
    bars += [_bar(30 + i, 101.0, 101.8, 100.4, 101.2) for i in range(4)]  # 30..33 in the band
    bars[32] = _bar(32, 103.0, 106.0, 102.8, 103.2)  # the adverse extreme
    bars += _flat(26, start=34, price=90.0)  # away, into profit
    bars[40] = _hammer_at(40, 100.0)  # back AT the entry: high 100.1
    return bars, entry


def test_a_candle_that_comes_BACK_to_the_entry_is_marked():
    """🔴 Watched RED against HEAD, whose zone was one contiguous excursion and stopped at the first
    favourable bar.

    A re-test of the entry is the setup asking the same question a second time, and the chart's own
    red box plainly covers it — so leaving it out reads as the layer skipping candles. Aaron, off
    his 2026-02-15 short: *"we came back up to entry. And there was at least three different candles
    you coulda highlighted there, and you didn't highlight any of them."*

    ⚠ This is why the zone is a PRICE band rather than a walk: no contiguous rule can include this
    bar without also swallowing the profitable stretch between it and the entry.
    """
    bars, entry = _short_that_dips_then_returns_to_its_entry()
    assert _fired(bars, 40), "fixture must fire a pattern on the re-test"

    out = build_candle_overlays(
        bars,
        [(bars[30]["time"], "short", bars[59]["time"], "win", entry)],
    )
    assert bars[40]["time"] in {o["t"] for o in out}
