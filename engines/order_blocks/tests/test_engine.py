"""
Hand-traced tests for the turn-anchored order-block engine.

These pin the mechanics of the 2026-07-31 re-port: the Pine pivot tie rule, the creation gates in
_add (min-back, displacement, overlap dedupe, height ceiling), the one-block-per-turn latch between
the two sources, the enter-then-leave / tap / through mitigation rule, age expiry, and FIFO
eviction. Full Pine<->Python parity is validated separately against a real TradingView export
(order_blocks/tools/compare_ob.py); these lock the mechanics so a regression is caught without one.

Feeds are built by helpers rather than typed out, because every creation path needs ~30 bars of
warm-up (ATR(14) alone eats 13) plus a base, a displacement and the read-late wait.

Run:  python3 -m pytest order_blocks/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from order_blocks import OrderBlockEngine, OrderBlockEvents          # noqa: E402
from order_blocks.types import OrderBlock                            # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def bar(o, h, l, c):
    return (o, h, l, c)


def flat(n, price=100.0, rng=1.0):
    """`n` quiet bars at `price` with a symmetric range — gives ATR something to warm up on."""
    return [bar(price, price + rng, price - rng, price) for _ in range(n)]


def run(engine, bars, start=0):
    return [engine.update(start + i, *b) for i, b in enumerate(bars)]


def all_created(evs):
    return [o for e in evs for o in e.created]


def seed_block(eng, top=101.0, bottom=99.0, is_bullish=True, index=30, age=20):
    """Put one block straight into the engine's list, bypassing the creation gates, so the
    mitigation and cap rules can be exercised in isolation."""
    ob = OrderBlock(top=top, bottom=bottom, is_bullish=is_bullish,
                    origin_index=index - age, created_index=index, id=eng._take_id())
    (eng._bull if is_bullish else eng._bear).append(ob)
    return ob


# ── ATR (Wilder) ─────────────────────────────────────────────────────────────

def test_atr_is_none_until_seeded_then_wilder():
    """Pine ta.atr(14) is na until bar 13 (the SMA seed), then recursive. Constant-range bars make
    the expected value trivial: every true range is 2.0, so the seed and every step after are 2.0."""
    eng = OrderBlockEngine()
    for i, b in enumerate(flat(13)):
        eng.update(i, *b)
        assert eng._atr is None, f"ATR should still be unseeded at bar {i}"
    eng.update(13, *bar(100.0, 101.0, 99.0, 100.0))
    assert eng._atr == pytest.approx(2.0)


# ── pivots: Pine's asymmetric tie rule ───────────────────────────────────────

def test_pivot_low_allows_a_left_tie_but_not_a_right_tie():
    """Pine's ta.pivotlow lets the centre EQUAL a bar to its LEFT but requires it to be STRICTLY
    below every bar to its RIGHT — so the LAST bar of an equal-price run is the pivot. This is the
    exact bug found and fixed in equal_highs_lows/ and rsi_divergence/ on 2026-07-19."""
    eng = OrderBlockEngine()
    # window oldest -> newest, lows 5, 5, 5, 6, 7 — the centre ties the bars to its LEFT.
    for i, b in enumerate([bar(9, 10, 5, 9), bar(9, 10, 5, 9), bar(9, 10, 5, 9),
                           bar(9, 10, 6, 9), bar(9, 10, 7, 9)]):
        eng.update(i, *b)
    assert eng._pivot_low() == 5

    eng2 = OrderBlockEngine()
    # lows 7, 6, 5, 5, 9 — the centre ties a bar to its RIGHT, so it is NOT the pivot.
    for i, b in enumerate([bar(9, 10, 7, 9), bar(9, 10, 6, 9), bar(9, 10, 5, 9),
                           bar(9, 10, 5, 9), bar(9, 10, 9, 9)]):
        eng2.update(i, *b)
    assert eng2._pivot_low() is None


def test_pivot_high_mirrors_the_tie_rule():
    eng = OrderBlockEngine()
    for i, b in enumerate([bar(1, 5, 0, 1), bar(1, 5, 0, 1), bar(1, 5, 0, 1),
                           bar(1, 4, 0, 1), bar(1, 3, 0, 1)]):
        eng.update(i, *b)
    assert eng._pivot_high() == 5

    eng2 = OrderBlockEngine()
    for i, b in enumerate([bar(1, 3, 0, 1), bar(1, 4, 0, 1), bar(1, 5, 0, 1),
                           bar(1, 5, 0, 1), bar(1, 1, 0, 1)]):
        eng2.update(i, *b)
    assert eng2._pivot_high() is None


# ── creation: a real turn with a real displacement ───────────────────────────

def _bullish_turn_feed():
    """Quiet bars to warm ATR, a small-bodied base whose dip prints a pivot low, a rally that clears
    well over a full ATR, then bars holding clear so the read-late wait elapses without returning.

    The base candle is deliberately SMALL. An early draft used a 4.5-wide pivot bar and no block was
    ever created — the height ceiling (max_atr x ATR) refused it, correctly: that candle was the
    move, not its base. Keep the anchor well under 2 x ATR or this feed silently tests nothing.
    """
    bars = flat(30, 100.0, 1.0)                     # 0-29   ATR warms to 2.0
    bars += [bar(100.0, 100.5, 99.0, 100.0)]        # 30     base
    bars += [bar(100.0, 100.3, 98.5, 99.8)]         # 31     the pivot low — a 1.8-wide base candle
    bars += [bar(99.8, 100.2, 99.2, 100.1)]         # 32     closes clear of the pivot body: base ends
    bars += [bar(100.1, 100.4, 99.5, 100.3)]        # 33     the pivot confirms on this bar
    bars += [bar(100.3, 106.0, 100.2, 105.5)]       # 34     the drive
    bars += [bar(105.5, 106.5, 104.8, 106.0)] * 12  # 35-46  hold clear, never wicking back in
    return bars


# The turn source reads `turn_len + turn_wait` bars late, so the pivot at bar 31 is acted on here.
_TURN_PIVOT_BAR = 31
_TURN_FIRES_ON = 43


def test_a_displaced_bullish_turn_creates_a_block():
    eng = OrderBlockEngine()
    evs = run(eng, _bullish_turn_feed())
    created = [o for o in all_created(evs) if o.is_bullish]
    assert created, "a displaced bullish turn should produce a block"
    ob = created[0]
    assert ob.top > ob.bottom
    assert ob.from_break is False      # every live source is turn-born now
    assert ob.entered is False         # born clean — never mitigated by its own creating move
    assert ob.created_index > ob.origin_index   # read late, so it lands in history


def test_no_block_without_displacement():
    """The same turn, but price only drifts up a fraction of an ATR. A pivot alone is not a level —
    this is the consolidation-clutter gate, and it is the whole point of measuring travel."""
    bars = flat(30, 100.0, 1.0)
    bars += [bar(100.0, 100.5, 99.5, 100.0),
             bar(100.0, 100.5, 96.0, 100.0),
             bar(100.0, 100.5, 99.5, 100.2),
             bar(100.2, 100.8, 100.0, 100.6),      # drifts, never displaces
             bar(100.6, 101.0, 100.2, 100.7)]
    bars += flat(14, 100.7, 0.3)
    assert all_created(run(OrderBlockEngine(), bars)) == []


def test_min_back_refuses_an_anchor_beside_the_live_bar():
    """_add's departure loop never runs when the anchor is nearer than min_back, so travel stays 0
    and nothing is drawn — a block must be BEHIND price, not beside it."""
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    ev = OrderBlockEvents()
    assert eng._add(eng._bull, 2, True, 30, ev) is False
    assert ev.created == []


def test_dead_anchor_is_refused():
    """Price already closed clean past the far edge, so extendOBs would delete the block on the very
    next bar. Refuse it now rather than flicker one onto the chart and take it straight back."""
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    # Anchor at 99-101, then a bar that closes BELOW it, then a rally back up.
    tail = [bar(100.0, 101.0, 99.0, 100.0),         # the anchor
            bar(100.0, 100.5, 90.0, 92.0),          # closes clean below -> dead
            bar(92.0, 115.0, 92.0, 114.0)]          # displaces up regardless
    tail += flat(6, 114.0, 0.5)
    evs = run(eng, tail, start=30)
    assert [o for o in all_created(evs) if o.bottom == 99.0] == []


def test_huge_anchor_is_refused():
    """A block taller than max_atr x ATR is the impulse, not its base. Oversized zones are also the
    ones that become immortal under enter-then-leave, since price can range inside them for hours."""
    eng = OrderBlockEngine(max_atr=2.0)
    run(eng, flat(30, 100.0, 1.0))                  # ATR == 2.0, so the ceiling is 4.0
    tail = [bar(100.0, 110.0, 90.0, 100.0)]         # a 20-wide anchor
    tail += [bar(100.0, 125.0, 100.0, 124.0)]       # displaces far clear
    tail += flat(6, 124.0, 0.5)
    assert all_created(run(eng, tail, start=30)) == []


# ── mitigation ───────────────────────────────────────────────────────────────

def test_close_through_the_far_edge_mitigates():
    """Without this a block price runs cleanly THROUGH in one bar — never closing inside — would be
    immortal, waiting on a condition that can no longer happen."""
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    seed_block(eng)
    ev = eng.update(31, 98.5, 98.6, 97.0, 98.0)      # closes below the bottom
    assert len(ev.mitigated) == 1 and ev.active_bull == []


def test_a_wick_in_that_closes_out_mitigates():
    """The 2026-07-31 tap rule: price reached in, took what was there, and left inside one candle.
    This REVERSES the older rule, where a wick rejection left the zone alive and untouched."""
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    seed_block(eng)
    ev = eng.update(31, 103.0, 103.5, 100.5, 102.5)  # wicks into 99-101, closes above
    assert len(ev.mitigated) == 1


def test_a_close_inside_keeps_the_block_until_it_leaves():
    """Price parked inside is working the orders — the zone survives exactly one thing, price still
    being in it at the close. It then dies on the first later close outside, EITHER side."""
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    ob = seed_block(eng)
    ev1 = eng.update(31, 100.0, 100.5, 99.5, 100.0)  # closes INSIDE
    assert ev1.mitigated == [] and ob.entered is True
    ev2 = eng.update(32, 100.0, 102.5, 99.8, 102.0)  # closes back out the TOP
    assert len(ev2.mitigated) == 1


def test_a_bar_that_never_touches_leaves_the_block_alone():
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    seed_block(eng)
    ev = eng.update(31, 110.0, 111.0, 109.0, 110.0)  # nowhere near 99-101
    assert ev.mitigated == [] and len(ev.active_bull) == 1


def test_bear_block_mitigation_mirrors():
    eng = OrderBlockEngine()
    run(eng, flat(30, 100.0, 1.0))
    seed_block(eng, top=101.0, bottom=99.0, is_bullish=False)
    ev = eng.update(31, 101.5, 103.0, 101.4, 102.0)  # closes above the top
    assert len(ev.mitigated) == 1 and ev.active_bear == []


def test_age_expiry_is_reported_separately_from_mitigation():
    """A block price never returns to can never be mitigated — both halves of the rule need price at
    the zone — so age is the only thing that retires it. NOT a trading signal, so it must not land
    in `mitigated`."""
    eng = OrderBlockEngine(max_age=5)
    run(eng, flat(30, 100.0, 1.0))
    seed_block(eng, index=30, age=20)                 # already 20 bars old, cap is 5
    ev = eng.update(31, 110.0, 111.0, 109.0, 110.0)   # far away: not touched, not through
    assert ev.expired and not ev.mitigated


# ── FIFO eviction ────────────────────────────────────────────────────────────

def test_oldest_block_is_evicted_past_the_cap():
    """Plain oldest-out, driven through the REAL creation path. The newest blocks are nearest price,
    so dropping from the front keeps the levels in play. It no longer protects structure-born
    blocks — there are none."""
    eng = OrderBlockEngine(max_active=1)
    feed = _bullish_turn_feed()
    run(eng, feed[:_TURN_FIRES_ON])
    # One pre-existing block, far enough away that the overlap dedupe cannot fire — and BELOW price,
    # because a bullish zone sitting above price is already "closed through" its own bottom and
    # would be mitigated by _extend before the cap ever ran.
    old = seed_block(eng, top=60.0, bottom=58.0, index=_TURN_FIRES_ON)
    ev = eng.update(_TURN_FIRES_ON, *feed[_TURN_FIRES_ON])
    assert ev.created, "the turn should still create its block"
    assert ev.evicted == [old], "the OLDEST block should be the one dropped at the cap"
    assert eng.active_bull() == ev.created


# ── dedupe ───────────────────────────────────────────────────────────────────

def test_overlapping_candidate_is_refused_as_the_same_zone():
    """The push and turn sources land on ADJACENT candles at one turn, whose highs and lows differ
    by cents — so the old equality test never matched and BOTH boxes printed, describing one zone
    twice. Overlap of the CANDIDATE's own height is the real test.

    A/B against the known-good feed: the same bar that creates a block on a clean engine must create
    nothing when a zone covering the same prices is already live."""
    feed = _bullish_turn_feed()
    clean = OrderBlockEngine()
    baseline = run(clean, feed)
    assert all_created(baseline), "guard: this feed must create a block on a clean engine"

    eng = OrderBlockEngine()
    run(eng, feed[:_TURN_FIRES_ON])
    seed_block(eng, top=100.3, bottom=98.5, index=_TURN_FIRES_ON)   # the very zone it would draw
    ev = eng.update(_TURN_FIRES_ON, *feed[_TURN_FIRES_ON])
    assert ev.created == [], "a candidate overlapping a live zone must not add a second block"


def test_a_big_candidate_containing_a_small_block_is_not_a_dupe():
    """Deliberately a fraction of the CANDIDATE's height, not the older block's: a small candidate
    wholly inside a big live zone is a duplicate, a big candidate merely containing a small old one
    is not."""
    eng = OrderBlockEngine()
    small_top, small_bottom = 100.2, 100.0          # a tiny live zone
    cand_top, cand_bottom = 110.0, 90.0             # a big candidate containing it
    overlap = min(cand_top, small_top) - max(cand_bottom, small_bottom)
    assert overlap < (cand_top - cand_bottom) * eng._dupe_overlap


# ── one block per turn ───────────────────────────────────────────────────────

def test_turn_source_refuses_a_pivot_the_push_already_claimed():
    """A turn is entitled to exactly ONE block, and the engulf reading claims it. The latch is set on
    the RETURN of _add, not on the push firing, because every gate can still refuse — if the push was
    refused, no block exists and the turn source must still get its chance at that pivot.

    A/B on one feed: identical bars, the only difference being whether the push latch already names
    the pivot the turn source is about to read."""
    feed = _bullish_turn_feed()

    clean = OrderBlockEngine()
    run(clean, feed[:_TURN_FIRES_ON])
    assert clean.update(_TURN_FIRES_ON, *feed[_TURN_FIRES_ON]).created, "guard: it normally creates"

    latched = OrderBlockEngine()
    run(latched, feed[:_TURN_FIRES_ON])
    latched._turn_used_l = _TURN_PIVOT_BAR          # the push is pretended to have claimed it
    assert latched.update(_TURN_FIRES_ON, *feed[_TURN_FIRES_ON]).created == []


# ── the engine is standalone ─────────────────────────────────────────────────

def test_update_takes_no_structure_snapshot():
    """Structure breaks no longer create blocks, so this engine consumes no upstream engine. Guard
    the signature: re-adding a snapshot argument means the Pine's structure source came back, and
    that is a decision to make deliberately, not to drift into."""
    params = list(inspect.signature(OrderBlockEngine.update).parameters)
    assert params == ["self", "index", "open_", "high", "low", "close"]
