"""Tests for mpc_realign — weighted toward the failures that would be SILENT.

The two things that can go wrong here without raising anything are (a) the 15m aggregator
leaking a forming bar, which is lookahead that makes every result better, and (b) an
inherited A+ default arriving uninvited. Both get the most tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[2]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))
_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mpc_realign.config import RealignConfig  # noqa: E402
from mpc_realign.htf import HtfStructure  # noqa: E402
from mpc_realign.strategy import MpcRealignStrategy  # noqa: E402
from mpc_realign.tracker import RealignTracker  # noqa: E402

MIN = 60_000


# ── the aggregator: lookahead is the silent failure ──────────────────────────────

def _feed(h, bars):
    """bars = [(minute_offset, o,h,l,c)] -> list of (offset, published_or_None)."""
    return [(m, h.update(m * MIN, o, hi, lo, c)) for m, o, hi, lo, c in bars]


def test_a_15m_bar_is_not_published_until_its_bucket_is_over():
    """The whole no-lookahead argument. Three 5m bars fill :00-:10; NOTHING may be
    published until a bar from the NEXT bucket arrives, because until then the 15m bar is
    still forming and its break would be known before it could have happened."""
    h = HtfStructure(15)
    out = _feed(h, [(0, 1, 2, 0, 1), (5, 1, 2, 0, 1), (10, 1, 2, 0, 1)])
    assert [p for _, p in out] == [None, None, None], (
        "a forming 15m bar was published — this is lookahead")
    # only now, on the first bar of the NEXT bucket, may it appear
    assert h.update(15 * MIN, 1, 2, 0, 1) is not None


def test_the_published_bar_is_the_ohlc_of_its_whole_bucket():
    h = HtfStructure(15)
    _feed(h, [(0, 10, 12, 9, 11), (5, 11, 15, 8, 14), (10, 14, 14, 13, 13)])
    h.update(15 * MIN, 13, 13, 13, 13)
    # the engine consumed it; check the aggregator built the right bar
    assert (h._o, h._h, h._l, h._c) == (13, 13, 13, 13)   # now filling the NEXT bucket


def test_buckets_align_to_the_wall_clock_not_to_bar_arrival():
    """A counted three-at-a-time aggregation drifts after ANY gap — a weekend, a holiday,
    one missing bar — and then silently builds 15m bars straddling two real ones. Feeding
    a hole must not shift the boundary."""
    h = HtfStructure(15)
    h.update(0, 1, 1, 1, 1)
    h.update(5 * MIN, 1, 1, 1, 1)
    # a 40-minute hole, landing mid-bucket at :45
    assert h.update(45 * MIN, 1, 1, 1, 1) is not None, "the :00 bucket should have closed"
    assert h._bucket == 45 * MIN, "boundary must follow the clock, not the bar count"


def test_a_gap_does_not_publish_the_buckets_it_skipped():
    """Absence of bars is not a bar. Skipping :15 and :30 must publish ONE bar (the :00
    bucket), never three — inventing empty 15m bars would break structure on candles that
    never traded."""
    h = HtfStructure(15)
    h.update(0, 1, 1, 1, 1)
    published = [h.update(45 * MIN, 1, 1, 1, 1), h.update(50 * MIN, 1, 1, 1, 1)]
    assert sum(p is not None for p in published) == 1


# ── config: the inherited-default trap ───────────────────────────────────────────

def test_exec_secondary_is_pinned_off():
    """The parent defaults this True. Inherited, a replay returns a primary-only book
    while reporting itself as having 1m re-entries."""
    assert RealignConfig().exec_secondary is False


def test_turning_exec_secondary_on_is_refused_rather_than_ignored():
    import dataclasses
    with pytest.raises(ValueError, match="secondary"):
        dataclasses.replace(RealignConfig(), exec_secondary=True)


@pytest.mark.parametrize("field,bad", [
    ("realign_pattern", "nonsense"),
    ("realign_long_source", "fine"),
    ("realign_short_source", "coarse"),
])
def test_a_typo_in_a_choice_field_raises_instead_of_falling_back(field, bad):
    """A silently-defaulted trigger source would replay a whole strategy against a stream
    nobody chose and report it as theirs."""
    import dataclasses
    with pytest.raises(ValueError, match=field.split("_")[-1]):
        dataclasses.replace(RealignConfig(), **{field: bad})


def test_both_sides_default_to_the_swing_stream():
    """MEASURED by replay: shorts on `internal` give -13.26R against +20.22R on `swing`.
    The trigger scan said the opposite; the replay is the one that counts."""
    c = RealignConfig()
    assert (c.realign_long_source, c.realign_short_source) == ("swing", "swing")


# ── the engine pin that would silently kill half the strategy ────────────────────

def test_internal_structure_is_switched_back_on():
    """The parent pins show_internal=False. Inheriting it blanks the internal stream, and
    with `realign_short_source='internal'` the bot would simply never short — a wrong
    RESULT with no error anywhere."""
    assert MpcRealignStrategy.engine_config().show_internal is True


def test_run_dual_is_refused_because_this_strategy_is_single_frame():
    with pytest.raises(NotImplementedError, match="single-frame"):
        MpcRealignStrategy(RealignConfig()).run_dual(None, None)


# ── the tracker's arming rule ────────────────────────────────────────────────────

class _Ev:
    def __init__(self, **kw):
        for k in ("bull_bos", "bull_sos", "bear_bos", "bear_sos"):
            setattr(self, k, kw.get(k, False))
        self.broken_high_price = kw.get("broken_high_price")
        self.broken_low_price = kw.get("broken_low_price")


def test_a_bearish_sos_with_no_prior_bullish_trend_arms_nothing():
    """Step 1 is not decoration: without an established bullish external read there is no
    trend for the deviation to be a deviation FROM."""
    t = RealignTracker(RealignConfig())
    t.on_htf(_Ev(bear_sos=True, bear_bos=True, broken_high_price=100.0), 0, 100.0, None)
    assert t._armed == []


def test_a_bearish_sos_after_a_bullish_break_arms_a_long():
    t = RealignTracker(RealignConfig())
    t.on_htf(_Ev(bull_bos=True), 0, None, None)
    t.on_htf(_Ev(bear_sos=True, bear_bos=True, broken_high_price=100.0), MIN, 100.0, None)
    assert [a.dir for a in t._armed] == [+1]
    assert t._armed[0].target == 100.0


def test_an_armed_setup_dies_after_the_window():
    cfg = RealignConfig()
    t = RealignTracker(cfg)
    t.on_htf(_Ev(bull_bos=True), 0, None, None)
    t.on_htf(_Ev(bear_sos=True, bear_bos=True, broken_high_price=100.0), MIN, 100.0, None)
    past = int(cfg.realign_window_hrs * 3_600_000) + MIN * 2
    t.update(past, 100.0, 99.0, _Ev(), _Ev())
    assert t._armed == [], "a setup outlived its arming window"
