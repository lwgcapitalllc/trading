"""
Hand-traced tests for the candlestick-pattern engine.

These pin the ported Pine behaviour (indicators/candle_sticks.pine, "Candlestick Patterns
Identified", repo32, v6). Every bar below was worked out against the source expression by hand and
each test names the rule it satisfies, so a failure points at a term rather than at "the engine".

Two things they deliberately pin BESIDES the fifteen formulas:

  * the HISTORY GUARD — Pine compares `na` as false, so a rule reading `open[trend]`, `high[2]` or
    `ta.lowest(10)[1]` cannot fire before that history exists. Without this the first bars of every
    chart would sprout patterns that the Pine never draws.
  * the REGISTRY — a pattern with no detector, or a detector with no registry row, is caught at
    import; a config naming a pattern that does not exist RAISES rather than quietly matching
    nothing, because a silently-off confluence reads exactly like a filter that never triggers.

Full Pine<->Python parity is validated separately against a real TradingView export
(candlesticks/tools/compare_candles.py). These tests do not prove parity and must not be read as
doing so.

Run:  python3 -m pytest candlesticks/tests/ -q      (from engines/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ENGINES_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINES_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINES_ROOT))

from candlesticks import (
    CHART_PRESET,
    BEARISH,
    BULLISH,
    NEUTRAL,
    PATTERN_KEYS,
    CandlestickEngine,
    resolve_keys,
    spec_for,
)

TREND = 5      # the Pine default, and what every fixture below is built around


# ──────────────────────────────────────────────────────────────────────────────
# fixtures: an inert filler run, then the explicit setup bars
#
# Layout is fixed so `open[trend]` always lands on FILLER, never on a setup bar — that is what lets
# each test set the trend context with one number (`ctx`) and reason about the rest locally.
#   _bars2:  filler[0..10]  prev=11  target=12      -> open[trend=5] = bar 7  (filler)
#   _bars3:  filler[0..9]   b2=10  b1=11  target=12 -> open[trend=5] = bar 7  (filler)
# ──────────────────────────────────────────────────────────────────────────────
def _filler(n, price):
    """`n` identical inert bars at `price` — flat body, tiny range."""
    return [(price, price + 0.5, price - 0.5, price)] * n


def _bars2(ctx, prev, target):
    return _filler(11, ctx) + [prev, target]


def _bars3(ctx, b2, b1, target):
    return _filler(10, ctx) + [b2, b1, target]


def _run(bars, trend=TREND, doji_size=0.05, patterns=None):
    eng = CandlestickEngine(trend=trend, doji_size=doji_size, patterns=patterns)
    ev = None
    for i, (o, h, l, c) in enumerate(bars):
        ev = eng.update(i, o, h, l, c)
    return eng, ev


def _fired(bars, **kw):
    _, ev = _run(bars, **kw)
    return set(ev.keys)


# ──────────────────────────────────────────────────────────────────────────────
# 1-bar patterns
# ──────────────────────────────────────────────────────────────────────────────
def test_doji_fires_when_the_body_is_inside_the_tolerance_band():
    # |open - close| = 0.02 <= (high - low) * dojiSize = 2 * 0.05 = 0.10
    assert "doji" in _fired([(100.0, 101.0, 99.0, 100.02)])


def test_doji_does_not_fire_when_the_body_clears_the_band():
    # |open - close| = 0.50 > 0.10
    assert "doji" not in _fired([(100.0, 101.0, 99.0, 100.50)])


def test_doji_size_is_the_lever_not_a_hardcoded_constant():
    # The identical bar flips on the input alone: 0.5 <= 2 * 0.30 is true, <= 2 * 0.05 is not.
    bar = [(100.0, 101.0, 99.0, 100.50)]
    assert "doji" not in _fired(bar, doji_size=0.05)
    assert "doji" in _fired(bar, doji_size=0.30)


def test_hammer_fires_on_a_long_lower_wick_and_a_body_at_the_top():
    # h-l = 10 > 3*|o-c| = 3; (c-l)/rng = 0.900 > 0.6; (o-l)/rng = 0.800 > 0.6
    assert "hammer" in _fired([(108.0, 110.0, 100.0, 109.0)])


def test_hammer_does_not_fire_when_the_body_sits_low_in_the_range():
    # (c-l)/rng = 0.200 — the body is at the BOTTOM, so neither 0.6 test passes.
    assert "hammer" not in _fired([(101.0, 110.0, 100.0, 102.0)])


def test_inverted_hammer_fires_on_a_long_upper_wick_and_a_body_at_the_bottom():
    # (h-c)/rng = 0.800 > 0.6; (h-o)/rng = 0.900 > 0.6
    assert "inverted_hammer" in _fired([(101.0, 110.0, 100.0, 102.0)])


def test_hammer_and_inverted_hammer_are_emitted_NEUTRAL_as_the_pine_draws_them():
    # ⚠ This pins a decision, not an accident. The source plots both as a white diamond with no
    # trend filter, so the engine will not call them bullish. A consumer that wants them bullish
    # says so itself — see types.py. If this test is ever "fixed", the engine and the chart start
    # disagreeing about the same candle.
    assert spec_for("hammer").direction == NEUTRAL
    assert spec_for("inverted_hammer").direction == NEUTRAL
    assert spec_for("doji").direction == NEUTRAL


# ──────────────────────────────────────────────────────────────────────────────
# 2-bar patterns
# ──────────────────────────────────────────────────────────────────────────────
_PREV_BULL = (100.0, 111.0, 99.0, 110.0)     # close[1] > open[1], body 10
_PREV_BEAR = (110.0, 111.0, 99.0, 100.0)     # open[1] > close[1], body 10


def test_bearish_harami_needs_an_inside_bearish_body_after_an_up_bar():
    # o=108 > c=102 (down bar); o <= c1 (108<=110); o1 <= c (100<=102); body 6 < prev body 10;
    # open[trend]=90 < 108 (uptrend context)
    bars = _bars2(90.0, _PREV_BULL, (108.0, 109.0, 101.0, 102.0))
    assert "bearish_harami" in _fired(bars)


def test_bearish_harami_is_refused_by_the_trend_gate_alone():
    # The identical bar with the trend context inverted: open[trend]=120 is NOT < 108.
    bars = _bars2(120.0, _PREV_BULL, (108.0, 109.0, 101.0, 102.0))
    assert "bearish_harami" not in _fired(bars)


def test_bullish_harami_needs_an_inside_bullish_body_after_a_down_bar():
    # c=108 > o=102; c <= o1 (108<=110); c1 <= o (100<=102); body 6 < 10; open[trend]=120 > 102
    bars = _bars2(120.0, _PREV_BEAR, (102.0, 109.0, 101.0, 108.0))
    assert "bullish_harami" in _fired(bars)


def test_bearish_engulfing_needs_a_body_that_swallows_the_up_bar():
    # o=112 >= c1=110; o1=100 >= c=99; body 13 > prev body 10; open[trend]=90 < 112
    bars = _bars2(90.0, _PREV_BULL, (112.0, 113.0, 98.0, 99.0))
    assert "bearish_engulfing" in _fired(bars)


def test_bearish_engulfing_and_harami_are_mutually_exclusive_by_construction():
    # The two rules differ only in the direction of two inequalities, so one bar cannot be both.
    # Worth pinning: an engulfing mis-ported as `<=` would ALSO tag every harami, and a chart full
    # of extra arrows is far less obvious than a missing one.
    eng_bar = _bars2(90.0, _PREV_BULL, (112.0, 113.0, 98.0, 99.0))
    har_bar = _bars2(90.0, _PREV_BULL, (108.0, 109.0, 101.0, 102.0))
    assert "bearish_harami" not in _fired(eng_bar)
    assert "bearish_engulfing" not in _fired(har_bar)


def test_bullish_engulfing_needs_a_body_that_swallows_the_down_bar():
    # c=112 >= o1=110; c1=100 >= o=99; body 13 > prev body 10; open[trend]=120 > 99
    #
    # ⚠ `close[1] >= open` is the term to read twice. The intuitive transcription is `close[1] <=
    # open`, and a bar opening at 101 — INSIDE the prior body — satisfies that while failing the
    # real rule. This fixture was originally built that way and the engine correctly refused it.
    bars = _bars2(120.0, _PREV_BEAR, (99.0, 113.0, 98.0, 112.0))
    assert "bullish_engulfing" in _fired(bars)


def test_bullish_engulfing_is_refused_when_the_open_sits_inside_the_prior_body():
    # Identical geometry but open 101 > close[1] 100, so the prior body is not fully covered.
    bars = _bars2(120.0, _PREV_BEAR, (101.0, 113.0, 100.0, 112.0))
    assert "bullish_engulfing" not in _fired(bars)


def test_piercing_line_opens_below_the_prior_low_and_closes_past_its_midpoint():
    # prev bearish 110 -> 100, low 98. o=97 < low[1]; c=106 > midpoint 105; c < o1=110;
    # open[trend]=120 > 97
    prev = (110.0, 111.0, 98.0, 100.0)
    bars = _bars2(120.0, prev, (97.0, 107.0, 96.0, 106.0))
    assert "piercing_line" in _fired(bars)


def test_piercing_line_is_refused_when_the_close_stops_at_the_midpoint():
    # c = 105 is NOT > 100 + (110-100)/2. A strict `>` — half-way back is not a piercing line.
    prev = (110.0, 111.0, 98.0, 100.0)
    bars = _bars2(120.0, prev, (97.0, 107.0, 96.0, 105.0))
    assert "piercing_line" not in _fired(bars)


def test_bullish_kicker_gaps_up_off_a_down_bar_and_closes_higher():
    # o=112 >= o1=110; c=118 > o; open[trend]=120 > 112
    bars = _bars2(120.0, _PREV_BEAR, (112.0, 119.0, 111.0, 118.0))
    assert "bullish_kicker" in _fired(bars)


def test_bearish_kicker_gaps_down_off_an_up_bar_and_closes_lower():
    # o=95 <= o1=100; c=90 <= o; open[trend]=90 < 95
    bars = _bars2(90.0, _PREV_BULL, (95.0, 96.0, 88.0, 90.0))
    assert "bearish_kicker" in _fired(bars)


def test_shooting_star_needs_an_upper_wick_three_times_the_body_and_almost_no_lower_one():
    # o=112 > c1=110 (prev was an up bar); h-max(o,c) = 4 >= body*3 = 3; min(c,o)-l = 0.5 <= body 1
    bars = _bars2(100.0, _PREV_BULL, (112.0, 116.0, 110.5, 111.0))
    assert "shooting_star" in _fired(bars)


def test_shooting_star_is_refused_when_the_lower_wick_exceeds_the_body():
    # min(c,o) - l = 3.0 > body 1.0 — the same bar with the low dropped.
    bars = _bars2(100.0, _PREV_BULL, (112.0, 116.0, 108.0, 111.0))
    assert "shooting_star" not in _fired(bars)


def test_bullish_belt_opens_at_its_own_low_below_the_ten_bar_low():
    # lower = ta.lowest(10)[1] = 118 (the prev bar's low, the deepest of bars [1..10]).
    # low == open == 110 < 118; open < close; close 120 > midpoint of prev range (119.5);
    # open[trend] = 120 > 110
    prev = (120.0, 121.0, 118.0, 119.0)
    bars = _bars2(120.0, prev, (110.0, 121.0, 110.0, 120.0))
    assert "bullish_belt" in _fired(bars)


def test_bullish_belt_is_refused_when_the_open_is_not_below_the_ten_bar_low():
    # open 119 sits ABOVE lower = 118; every other term is unchanged.
    prev = (120.0, 121.0, 118.0, 119.0)
    bars = _bars2(120.0, prev, (119.0, 121.0, 119.0, 120.0))
    assert "bullish_belt" not in _fired(bars)


# ──────────────────────────────────────────────────────────────────────────────
# 3-bar patterns
# ──────────────────────────────────────────────────────────────────────────────
def test_evening_star_needs_a_gapped_up_middle_bar_and_a_down_close():
    # c[2]=110 > o[2]=100; min(o1,c1)=112 > c[2]; o=111 < 112; c=105 < o
    bars = _bars3(100.0, (100.0, 111.0, 99.0, 110.0), (112.0, 116.0, 111.0, 114.0),
                  (111.0, 112.0, 104.0, 105.0))
    assert "evening_star" in _fired(bars)


def test_morning_star_needs_a_gapped_down_middle_bar_and_an_up_close():
    # c[2]=100 < o[2]=110; max(o1,c1)=98 < c[2]; o=99 > 98; c=106 > o
    bars = _bars3(100.0, (110.0, 111.0, 99.0, 100.0), (98.0, 99.0, 94.0, 96.0),
                  (99.0, 107.0, 98.0, 106.0))
    assert "morning_star" in _fired(bars)


def test_morning_star_is_refused_when_the_middle_bar_does_not_clear_the_first_close():
    # max(o1,c1) = 101 is NOT < c[2] = 100 — the gap the pattern is made of never happened.
    bars = _bars3(100.0, (110.0, 111.0, 99.0, 100.0), (101.0, 102.0, 94.0, 96.0),
                  (102.0, 107.0, 98.0, 106.0))
    assert "morning_star" not in _fired(bars)


def test_hanging_man_needs_two_lower_highs_behind_it_as_well_as_the_wick():
    # h-l = 11 > 4*body = 2; (c-l)/rng = 0.954 >= 0.75; (o-l)/rng = 0.909 >= 0.75;
    # open[trend]=90 < 100; high[1]=95 < 100; high[2]=95 < 100
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 95.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    assert "hanging_man" in _fired(bars)


def test_hanging_man_is_refused_when_the_previous_high_reaches_the_open():
    # high[1] = 100 is NOT < open = 100. Same candle, one bar of context changed.
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 100.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    assert "hanging_man" not in _fired(bars)


def test_a_hanging_man_candle_is_also_a_hammer_and_the_engine_reports_both():
    # ⚠ Not a bug and not double-counting: the two rules read the SAME wick geometry and differ
    # only in the context Hanging Man additionally demands. The Pine plots both shapes on that bar,
    # so an engine that suppressed one would disagree with the chart. A consumer that wants one
    # answer per bar picks by direction, not by hoping only one fires.
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 95.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    fired = _fired(bars)
    assert "hanging_man" in fired and "hammer" in fired


# ──────────────────────────────────────────────────────────────────────────────
# the history guard — Pine's `na` compares false
# ──────────────────────────────────────────────────────────────────────────────
def test_a_trend_gated_pattern_cannot_fire_before_trend_bars_of_history_exist():
    # The same bullish-engulfing geometry with only ONE bar of context: `open[trend]` is `na` in
    # Pine, so the rule is false. A None read as 0.0 here would make 120 > 101 trivially true and
    # sprout an engulfing on the second bar of every chart ever loaded.
    bars = [_PREV_BEAR, (99.0, 113.0, 98.0, 112.0)]
    assert "bullish_engulfing" not in _fired(bars)


def test_the_same_pattern_fires_once_the_trend_history_is_there():
    bars = _bars2(120.0, _PREV_BEAR, (99.0, 113.0, 98.0, 112.0))
    assert "bullish_engulfing" in _fired(bars)


def test_shortening_trend_shortens_the_history_a_pattern_needs():
    # trend=1 makes `open[trend]` the previous bar's open (110), which is still > 101, so the same
    # two bars that were refused above now qualify.
    bars = [_PREV_BEAR, (99.0, 113.0, 98.0, 112.0)]
    assert "bullish_engulfing" in _fired(bars, trend=1)


def test_bullish_belt_cannot_fire_before_ten_bars_exist_behind_it():
    # It reads ta.lowest(10)[1] as well as open[trend], so it needs the DEEPER of the two — the one
    # rule where the trend input is not what bounds the warm-up.
    prev = (120.0, 121.0, 118.0, 119.0)
    short = _filler(6, 120.0) + [prev, (110.0, 121.0, 110.0, 120.0)]
    assert "bullish_belt" not in _fired(short)


def test_a_single_bar_can_still_produce_the_zero_history_patterns():
    # Doji / Hammer / Inverted Hammer read nothing behind them, so bar 0 is fair game on both sides.
    assert "hammer" in _fired([(108.0, 110.0, 100.0, 109.0)])


# ──────────────────────────────────────────────────────────────────────────────
# the confluence surface
# ──────────────────────────────────────────────────────────────────────────────
def test_detected_comes_out_in_the_pine_declaration_order():
    # Pins the ordering contract: a consumer taking "the first pattern on this bar" must get the
    # same one the chart lists first, whatever order the rules happen to be evaluated in.
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 95.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    _, ev = _run(bars)
    order = [PATTERN_KEYS.index(k) for k in ev.keys]
    assert order == sorted(order)


def test_matching_filters_by_key_and_by_direction():
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 95.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    _, ev = _run(bars)
    assert [p.key for p in ev.matching(direction=BEARISH)] == ["hanging_man"]
    assert [p.key for p in ev.matching(keys=("hammer",))] == ["hammer"]
    assert ev.matching(keys=("hammer",), direction=BEARISH) == []
    assert ev.bullish == []


def test_bars_since_counts_from_the_firing_bar_and_says_NEVER_rather_than_a_big_number():
    # ⚠ None, not a sentinel integer: "never fired" and "fired a long time ago" are different
    # answers, and a confluence window that collapsed them would silently treat one as the other.
    bars = _bars2(120.0, _PREV_BEAR, (99.0, 113.0, 98.0, 112.0))
    eng, _ = _run(bars)
    assert eng.bars_since("bullish_engulfing") == 0
    assert eng.bars_since("bearish_engulfing") is None
    eng.update(len(bars), 112.0, 113.0, 111.0, 112.5)
    assert eng.bars_since("bullish_engulfing") == 1


def test_narrowing_the_pattern_set_skips_rules_without_redefining_any_of_them():
    bars = _bars3(90.0, (92.0, 95.0, 91.0, 93.0), (93.0, 95.0, 91.0, 94.0),
                  (100.0, 101.0, 90.0, 100.5))
    assert _fired(bars, patterns=["hanging_man"]) == {"hanging_man"}
    assert "hanging_man" in _fired(bars)      # unchanged when the rest are enabled


def test_asking_a_disabled_pattern_for_its_age_raises_instead_of_answering_never():
    # "Never fired" and "not being evaluated" are different facts, and the reassuring one is wrong.
    eng = CandlestickEngine(patterns=["doji"])
    eng.update(0, 100.0, 101.0, 99.0, 100.02)
    with pytest.raises(KeyError):
        eng.bars_since("hammer")


# ──────────────────────────────────────────────────────────────────────────────
# the registry
# ──────────────────────────────────────────────────────────────────────────────
def test_an_unknown_pattern_key_raises_rather_than_matching_nothing():
    with pytest.raises(KeyError):
        spec_for("bullish_engulphing")            # a real typo, one letter out
    with pytest.raises(KeyError):
        CandlestickEngine(patterns=["bullish_engulphing"])


def test_resolve_keys_returns_registry_order_not_caller_order():
    assert resolve_keys(["hammer", "doji"]) == ("doji", "hammer")
    assert resolve_keys(None) == PATTERN_KEYS


def test_every_registry_row_has_a_direction_the_pine_actually_draws():
    assert len(PATTERN_KEYS) == 15
    assert len(set(PATTERN_KEYS)) == 15
    assert {spec_for(k).direction for k in PATTERN_KEYS} == {BULLISH, BEARISH, NEUTRAL}
    assert sum(1 for k in PATTERN_KEYS if spec_for(k).direction == BULLISH) == 6
    assert sum(1 for k in PATTERN_KEYS if spec_for(k).direction == BEARISH) == 6
    assert sum(1 for k in PATTERN_KEYS if spec_for(k).direction == NEUTRAL) == 3


def test_the_engine_defaults_still_MIRROR_the_pine_and_are_not_the_traded_preset():
    # 🔴 The load-bearing one. An engine mirrors its source Pine; a CONSUMER pins what it trades.
    # If these defaults ever drift to CHART_PRESET's values, this engine silently stops describing
    # candle_sticks.pine and the next person diffing the two finds an unrecorded fork.
    eng = CandlestickEngine()
    assert (eng.trend, eng.doji_size) == (5, 0.05)
    assert eng.enabled == PATTERN_KEYS
    assert (CHART_PRESET["trend"], CHART_PRESET["doji_size"]) != (eng.trend, eng.doji_size)


def test_the_traded_preset_builds_an_engine_and_names_only_real_patterns():
    eng = CandlestickEngine(**CHART_PRESET)
    assert (eng.trend, eng.doji_size) == (117, 0.01)
    assert len(eng.enabled) == 11
    # resolve_keys already raises on a typo; this pins that the preset went through it and came
    # back in REGISTRY order, so the preset cannot quietly reorder anyone's events.
    assert eng.enabled == resolve_keys(CHART_PRESET["patterns"])
    assert set(eng.enabled) < set(PATTERN_KEYS)


def test_the_pine_input_bounds_are_enforced_rather_than_silently_accepted():
    # Pine declares trend minval 1 and dojiSize minval 0.01. A zero doji tolerance is a DIFFERENT
    # rule ("open == close exactly") wearing the same name, so it is refused, not clamped.
    with pytest.raises(ValueError):
        CandlestickEngine(trend=0)
    with pytest.raises(ValueError):
        CandlestickEngine(doji_size=0.0)
