"""
Tests for services/ob_overlays.py — the order-block layer on the price chart.

They pin the EMITTER: which blocks get drawn (only those live at a trade / blocked / missed anchor),
and the box geometry against the real span the Pine box held — which for an order block is a very
different rule from a fair value gap's. A gap box tracks the live bar; an OB box is a fixed
`OB_STUB` (30-bar) stub from its anchor candle, stretched out to the live bar only while price has
come back within one block-height of the zone, and deleted the bar the block dies.

⚠ **There is no "and the boxes ARE the Pine's blocks" half here, and that is a stated gap, not an
oversight.** `test_fvg_overlays.py` cross-checks every box against the Pine's own live gap arrays in
a real TradingView export. The three OB exports on disk (`engines/order_blocks/exports/`) all
predate the 2026-07-31 re-port — they carry six slots and no `cfg_ob_*` columns, so
`compare_ob.py` refuses them outright — and no post-re-port export is on this machine. What is
proven, and where:

  * the ENGINE is Pine-parity green on a real 21,691-bar 15m export and a 13,186-bar 5m one
    (`engines/order_blocks/CLAUDE.md` → Validation). Re-run `compare_ob.py` on the next real export.
  * these tests prove the emitter turns that engine's events into the boxes mpc would have drawn.

Feeds are built rather than typed out: every OB creation path needs ~30 bars of ATR warm-up plus a
base, a displacement and the engine's 10-bar read-late wait. The bullish feed is lifted from the
engine's own `_bullish_turn_feed`, so a change that stops it creating a block fails there too.
"""

import pytest

from services.ob_overlays import GROUP_OB, build_ob_overlays

BAR_MS = 15 * 60 * 1000


def _bar(o, h, lo, c):
    return (o, h, lo, c)


def _flat(n, price=100.0, rng=1.0):
    """Quiet bars — ATR(14) needs 13 of them before the engine can measure a displacement at all."""
    return [_bar(price, price + rng, price - rng, price) for _ in range(n)]


def _candles(rows):
    """[(o, h, l, c), …] → spec candles on a 15-minute grid, so bar index i sits at time i*BAR_MS."""
    return [
        {"time": i * BAR_MS, "open": o, "high": h, "low": lo, "close": c}
        for i, (o, h, lo, c) in enumerate(rows)
    ]


# A displaced bullish turn: warm-up, a small-bodied base whose dip prints a pivot low, a drive that
# clears well over one ATR, then bars holding clear so the read-late wait elapses. Hand-traced
# against the engine (`engines/order_blocks/tests/test_engine.py::_bullish_turn_feed`):
#
#   anchor candle  bar 31   top 100.3 / bottom 98.5
#   created on     bar 43   (turn_len 2 + turn_wait 10 after the pivot, so it lands in history)
#
# The base candle is deliberately SMALL — the height ceiling (2 x ATR) refuses an anchor that IS the
# move rather than its base, and a wider one here would silently test nothing.
_TURN = _flat(30, 100.0, 1.0) + [
    _bar(100.0, 100.5, 99.0, 100.0),      # 30  base
    _bar(100.0, 100.3, 98.5,  99.8),      # 31  the pivot low — the anchor candle
    _bar( 99.8, 100.2, 99.2, 100.1),      # 32  closes clear of the pivot body: base ends
    _bar(100.1, 100.4, 99.5, 100.3),      # 33  the pivot confirms
    _bar(100.3, 106.0, 100.2, 105.5),     # 34  the drive
]
_HOLD = _bar(105.5, 106.5, 104.8, 106.0)  # holds clear, never wicking back toward the zone

_ORIGIN, _CREATED = 31, 43
_TOP, _BOTTOM = 100.3, 98.5

# Never mitigated, price never comes back near it: bars 0…74.
_FEED = _candles(_TURN + [_HOLD] * 40)

# The same block, but the LAST bar dips back to within one block-height of the top: bars 0…70.
# `near` for a bull block is `low <= top + height` = 100.3 + 1.8 = 102.1, and 101.5 clears it.
_FEED_NEAR = _candles(_TURN + [_HOLD] * 35 + [_bar(105.5, 106.0, 101.5, 105.0)])

# The same block, killed on bar 55 by a close clean past its far edge (a bull block's far edge is
# its BOTTOM): bars 0…75.
_MITIGATED_ON = 55
_FEED_MITIGATED = _candles(
    _TURN + [_HOLD] * 20 + [_bar(105.0, 105.5, 97.0, 97.5)] + [_bar(97.5, 98.5, 96.5, 97.0)] * 20
)

# The bear mirror of _TURN — a pivot HIGH and a drive down. Anchor bar 31, top 101.5 / bottom 99.7.
_TURN_BEAR = _flat(30, 100.0, 1.0) + [
    _bar(100.0, 101.0, 99.5, 100.0),
    _bar(100.0, 101.5, 99.7, 100.2),      # 31  the pivot high — the anchor candle
    _bar(100.2, 100.8, 99.8,  99.9),
    _bar( 99.9, 100.5, 99.6,  99.7),
    _bar( 99.7,  99.8, 94.0,  94.5),      # 34  the drive
]
_HOLD_BEAR = _bar(94.5, 95.2, 93.5, 94.0)
_BEAR_TOP, _BEAR_BOTTOM = 101.5, 99.7

_FEED_BEAR = _candles(_TURN_BEAR + [_HOLD_BEAR] * 40)
# `near` for a bear block is `high >= bottom - height` = 99.7 - 1.8 = 97.9, and 98.5 clears it.
_FEED_BEAR_NEAR = _candles(_TURN_BEAR + [_HOLD_BEAR] * 35 + [_bar(94.5, 98.5, 94.0, 95.0)])


def _spans(overlays):
    """{(top, bottom): (first_bar_drawn, last_bar_drawn)} for readable assertions."""
    return {
        (ov["top"], ov["bottom"]): (ov["t0"] // BAR_MS, ov["t1"] // BAR_MS)
        for ov in overlays
    }


# ── What gets drawn ───────────────────────────────────────────────────────────

def test_no_trade_block_or_miss_means_no_order_blocks_at_all():
    """The layer exists to explain a signal. With nothing to explain it draws nothing — not every
    block in the run, which is what makes the chart readable at all. Measured on the shipped 161-
    trade run: 2,567 blocks created, 579 live at an anchor."""
    assert build_ob_overlays(_FEED, []) == []


def test_a_live_block_is_drawn_at_an_anchor():
    got = _spans(build_ob_overlays(_FEED, [50 * BAR_MS]))
    assert set(got) == {(_TOP, _BOTTOM)}


def test_an_anchor_before_the_block_exists_draws_nothing():
    """The engine reads a turn 12 bars late, so the block does not exist until bar 43 even though
    its anchor candle is bar 31. A layer that drew it at bar 40 would be showing the reader a level
    the indicator had not printed yet."""
    assert build_ob_overlays(_FEED, [40 * BAR_MS]) == []


def test_the_creation_bar_itself_counts_as_live():
    assert _spans(build_ob_overlays(_FEED, [_CREATED * BAR_MS])) == {(_TOP, _BOTTOM): (31, 61)}


def test_a_block_mitigated_on_the_anchor_bar_is_not_drawn():
    """mpc deletes the box on the bar the block is consumed, so on that bar there is nothing there
    to see. Same rule as the FVG layer's death bar."""
    assert build_ob_overlays(_FEED_MITIGATED, [_MITIGATED_ON * BAR_MS]) == []
    assert build_ob_overlays(_FEED_MITIGATED, [(_MITIGATED_ON + 5) * BAR_MS]) == []


def test_a_block_alive_at_the_anchor_is_drawn_even_though_it_dies_later():
    """What matters is what was on the chart WHEN the setup fired, not whether the zone survived
    the rest of the run."""
    assert _spans(build_ob_overlays(_FEED_MITIGATED, [50 * BAR_MS])) == {(_TOP, _BOTTOM): (31, 61)}


def test_anchors_outside_the_candle_window_are_ignored():
    assert build_ob_overlays(_FEED, [-BAR_MS, 10_000 * BAR_MS]) == []


def test_a_bearish_turn_draws_its_own_block():
    assert _spans(build_ob_overlays(_FEED_BEAR, [50 * BAR_MS])) == {(_BEAR_TOP, _BEAR_BOTTOM): (31, 61)}


# ── Box geometry — the Pine box's real span ───────────────────────────────────

def test_the_box_is_a_fixed_stub_running_forward_from_the_anchor_candle():
    """`left = origin`, `right = origin + OB_STUB`. This is the rule that most obviously differs
    from the gap layer, where a box tracks the live bar: an order block is a fixed-width zone by
    construction (mpc_assistant.pine:170-181), which is what makes a set of them scan as one family
    of levels rather than a ragged row."""
    (left, right), = _spans(build_ob_overlays(_FEED, [50 * BAR_MS])).values()
    assert (left, right) == (_ORIGIN, _ORIGIN + 30)
    assert right < 74, "the stub must not follow the live bar"


def test_price_returning_near_the_zone_stretches_the_box_past_the_stub():
    """`obNear` — price back within one block-height — is the one thing that extends the box, so it
    connects to the candles while the zone is in play. Bar 70 dips to 101.5, inside 100.3 + 1.8."""
    assert _spans(build_ob_overlays(_FEED_NEAR, [60 * BAR_MS])) == {(_TOP, _BOTTOM): (31, 70)}


def test_the_near_test_mirrors_for_a_bear_block():
    """A bull block is approached from ABOVE and a bear one from BELOW, so the near test reads the
    bar's low against the top on one side and its high against the bottom on the other. Getting the
    mirror wrong would leave every bear block frozen at its stub, which reads as a rendering bug
    rather than a wrong rule."""
    assert _spans(build_ob_overlays(_FEED_BEAR_NEAR, [60 * BAR_MS])) == {(_BEAR_TOP, _BEAR_BOTTOM): (31, 70)}


def test_the_box_keeps_the_span_it_last_held_even_though_it_outlives_the_block():
    """The stub deliberately runs PAST the live bar into empty space, so a block that dies on bar 55
    still had a box reaching to bar 61 on the last frame it was drawn. Emitting the death bar
    instead would trim every zone the reader actually saw."""
    (_, right), = _spans(build_ob_overlays(_FEED_MITIGATED, [50 * BAR_MS])).values()
    assert right == _ORIGIN + 30 > _MITIGATED_ON


def test_the_box_is_clamped_to_the_last_candle():
    """A stub running past the end of the data has nowhere to land — klinecharts anchors a box to
    candle timestamps, so an out-of-range right edge would be clamped onto the plot edge anyway.
    Cut the feed two bars after creation and the box has to end on the last bar, not 18 past it."""
    short = _candles(_TURN + [_HOLD] * 11)          # bars 0…45, block created on 43
    n = len(short)
    (_, right), = _spans(build_ob_overlays(short, [45 * BAR_MS])).values()
    assert right == n - 1


# ── The settings are mpc_assistant's ─────────────────────────────────────────

def test_the_style_is_mpcs_orange_outline_with_the_OB_tag():
    """One deep orange for BOTH directions, drawn as an outline with a whisper of fill — the
    blue/red directional experiment was tried and REVERTED in the Pine, so bull and bear look
    identical here exactly as they do on the indicator. The `OB` tag is what names the shape at 94%
    transparency, and it is RIGHT-aligned because the box's left edge is its anchor candle, where
    the price bars are."""
    bull, = build_ob_overlays(_FEED, [50 * BAR_MS])
    bear, = build_ob_overlays(_FEED_BEAR, [50 * BAR_MS])
    for ov in (bull, bear):
        assert ov["type"] == "box"
        assert ov["group"] == GROUP_OB
        assert ov["label"] == "OB"
        assert ov["labelAlign"] == "right"
        assert ov["style"] == {"color": "#E65100", "fillColor": "rgba(230,81,0,0.06)", "lineWidth": 1}
    assert bull["style"] == bear["style"], "mpc paints both directions the same — no direction cue"


def test_the_stub_width_is_configurable_for_a_parity_replay():
    assert _spans(build_ob_overlays(_FEED, [50 * BAR_MS], stub_bars=5)) == {(_TOP, _BOTTOM): (31, 36)}


def test_engine_settings_reach_the_engine():
    """The kwargs exist so a parity test can replay an export whose Pine build ran different
    constants. Demanding 99 ATRs of displacement must refuse the block outright — if it did not,
    the kwargs would be silently dropped and a parity replay would measure today's defaults while
    claiming to measure that build's."""
    assert build_ob_overlays(_FEED, [50 * BAR_MS], disp_mult=99.0) == []


# ── Failing safe ──────────────────────────────────────────────────────────────

def test_too_few_candles_is_not_an_error():
    assert build_ob_overlays(_candles(_flat(2)), [0]) == []


def test_a_broken_engine_does_not_take_the_chart_down(monkeypatch):
    """Best-effort, like every other layer on this chart: the reader came for the price bars, and a
    replay that raises must cost them one toggle rather than the whole panel."""
    import services.ob_overlays as mod

    class _Boom:
        def __init__(self, **kw):
            raise RuntimeError("engine exploded")

    monkeypatch.setitem(__import__("sys").modules, "order_blocks",
                        type("m", (), {"OrderBlockEngine": _Boom}))
    assert mod.build_ob_overlays(_FEED, [50 * BAR_MS]) == []
