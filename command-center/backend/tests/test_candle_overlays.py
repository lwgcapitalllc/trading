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
    bars[38] = _bar(38, 100.0, 100.5, 99.5, 100.0)   # a doji, well above the low
    bars[40] = _hammer_at(40)                        # the turn
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
    bars[42] = _hammer_at(42, 97.0)                  # ...the reversal, completing 2 bars later
    assert not _fired(bars, 40), "the turn bar must be quiet or this proves nothing"
    assert _fired(bars, 42)
    out = build_candle_overlays(bars, [(bars[38]["time"], "long", bars[55]["time"])])
    assert [o["t"] for o in out] == [bars[42]["time"]]
    assert out[0]["deepestOf"] == [0], "it IS the turn's reversal, so it is that span's deepest mark"


def test_nothing_is_marked_PAST_the_confirmation_WINDOW():
    """The window is the longest pattern's length minus one and must not become a free-for-all: far
    past the turn price is moving the setup's way, and a reversal candle there is a different
    subject. ⚠ This is what stops `_CONFIRM_BARS` being read as a tuning dial."""
    bars = _flat(60)
    bars[40] = _hammer_at(40)                        # the turn (the low of the whole window)
    bars[45] = _bar(45, 100.0, 100.5, 99.5, 100.0)   # a doji 5 bars later, well above the low
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
    bars[151] = _bar(151, prev["close"], prev["close"] + 2.0, prev["close"] - 0.2, prev["close"] + 1.8)
    prev = bars[151]
    bars[152] = _bar(152, prev["close"] + 0.5, prev["close"] + 0.7, prev["open"] - 9.2, prev["open"] - 9.0)
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
        (bars[150]["time"], 0), (bars[152]["time"], -1),
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
    bars[151] = _bar(151, prev["close"], prev["close"] + 2.0, prev["close"] - 0.2, prev["close"] + 1.8)
    prev = bars[151]
    # Engulfs the bar before AND has a long lower wick with a small body — Bearish Engulfing + Hammer.
    bars[152] = _bar(152, prev["close"] + 0.5, prev["close"] + 0.7, prev["open"] - 9.0, prev["open"] - 0.5)
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
    assert build_candle_overlays(candles, [(entry, "long", None)]) == [], "short window should miss it"
    out = build_candle_overlays(candles, [(entry, "long", exit_)])
    assert len(out) == 1
    assert out[0]["t"] == candles[40]["time"]


def test_a_pattern_mid_hold_IS_drawn_even_though_it_is_far_from_the_turn():
    """The counterpart of the test above, and the rule that replaced the old ±2-bar tolerance: a
    pattern 20 bars before the turn is not "the reversal", but it IS a level the retracement offered
    on the way down, which is the whole question. ⚠ The tolerance used to DELETE it — the span
    covers it now, and the marks between the entry and the turn are the answer he asked for."""
    bars = _flat(60)
    bars[30] = _hammer_at(30)                        # a pattern, mid-hold
    # ⚠ A lone bearish bar after bullish filler makes its NEIGHBOURS a Morning/Evening Star — a
    # three-bar pattern is a property of the bars AROUND the one you are placing — so the turn is
    # built with plain bodies either side and asserted quiet.
    for j in range(46, 56):
        bars[j] = _bar(j, 101.5, 101.9, 100.5, 100.9)      # plain bearish bodies
    bars[50] = _bar(50, 100.0, 100.05, 80.0, 80.05)        # one long body, almost no wick
    assert _fired(bars, 30), "the mid-hold pattern must really fire or this test is vacuous"
    for j in range(48, 53):
        assert not _fired(bars, j), f"bar {j} is at the turn and must carry NO pattern"
    out = build_candle_overlays(bars, [(bars[20]["time"], "long", bars[55]["time"])])
    assert [o["t"] for o in out] == [bars[30]["time"]]


def test_an_exit_before_the_entry_degrades_to_the_short_window():
    """A malformed hold must not drop a real setup — it still gets the answer it can have."""
    candles = _candles_with_hammer(40)
    out = build_candle_overlays(
        candles, [(candles[40]["time"], "long", candles[10]["time"])],
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
        c["open"], c["high"], c["low"], c["close"],
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
    out = build_candle_overlays(bars, [
        (bars[150]["time"], "long", None, "win"),
        (bars[150]["time"], "long", None, "loss"),
    ])
    named = {n: nm for o in out for n, nm in (o.get("deepestNames") or {}).items()}
    assert set(named) == {"0", "1"}, "both anchors must be named"
    assert named["0"] != named["1"], "a winner and a loser on one leg want different candles"
