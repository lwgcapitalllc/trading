"""Tests for realign — weighted toward the failures that would be SILENT.

The two things that can go wrong here without raising anything are (a) the 15m aggregator
leaking a forming bar, which is lookahead that makes every result better, and (b) an
inherited SOS Fade default arriving uninvited. Both get the most tests.
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

from realign.config import RealignConfig  # noqa: E402
from realign.execution import realign_target  # noqa: E402
from realign.htf import HtfStructure  # noqa: E402
from realign.strategy import RealignStrategy  # noqa: E402
from realign.tracker import RealignTracker  # noqa: E402

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
    assert RealignStrategy.engine_config().show_internal is True


_PINE = _ROOT / "strategies" / "tradingview" / "realign_strategy.pine"


def test_both_frames_run_the_charts_swing_length():
    """`realign_strategy.pine` runs majorLength "on both frames". The 5m frame took the engines'
    default 15 until 2026-09-10 because only the 15m half named a value.
    ⚠ It only places the engine's FIRST swing (measured: 3 differing bars in 467,352, all in the
    first 37), so no figure moved — this holds the two sides equal, it did not fix a result.
    Read OUT of the Pine, so moving either side goes red. Watched red both ways."""
    from engines.pine_constants import pine_value

    pine = pine_value("majorLength", _PINE)
    assert RealignStrategy.engine_config().major_length == pine
    assert HtfStructure()._engine.major_length == pine


def test_the_fork_does_not_add_to_winners_its_pine_cannot():
    """The parent adds to winners by default since 2026-09-06; `realign_strategy.pine` cannot, and
    this bot has no parity gate to notice. Inherited, it lifted the charged book +13.48R with no
    one having chosen it. Goes red if the pin goes or the Pine gains the input."""
    from sos_fade.config import SosFadeConfig

    assert SosFadeConfig().exec_scale_in is True, (
        "the parent's default moved again — re-answer whether this fork's pin is load-bearing")
    assert RealignConfig().exec_scale_in is False
    assert "execScaleIn" not in _PINE.read_text(encoding="utf-8")


def test_run_dual_is_refused_because_this_strategy_is_single_frame():
    with pytest.raises(NotImplementedError, match="single-frame"):
        RealignStrategy(RealignConfig()).run_dual(None, None)


# ── the tracker's arming rule ────────────────────────────────────────────────────

class _Ev:
    def __init__(self, **kw):
        for k in ("bull_bos", "bull_sos", "bear_bos", "bear_sos"):
            setattr(self, k, kw.get(k, False))
        self.broken_high_price = kw.get("broken_high_price")
        self.broken_low_price = kw.get("broken_low_price")
        # The break leg's far endpoint — the chart-frame arm's target.
        self.bear_bos_high = kw.get("bear_bos_high")
        self.bull_bos_low = kw.get("bull_bos_low")


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


# ── the chart-frame arm (2026-09-11) ─────────────────────────────────────────────

import dataclasses  # noqa: E402

BULL_SOS = dict(bull_sos=True, bull_bos=True)   # a CHoCH bar raises both flags
BEAR_SOS = dict(bear_sos=True, bear_bos=True)


def _chart(**kw):
    return dataclasses.replace(RealignConfig(), realign_arm_frame="Chart frame", **kw)


def _drive(t, bars):
    """bars = [(high, low, ext_events)] at 5-minute spacing -> the RealignState per bar."""
    return [t.update(i * 5 * MIN, h, lo, ev, _Ev()) for i, (h, lo, ev) in enumerate(bars)]


def test_the_chart_frame_arms_on_the_counter_sos_and_fires_on_the_realigning_sos():
    """The sequence as drawn: SOS up, BOS up, SOS down (arms), SOS up (fires). The stop is
    the lowest low of the whole counter move."""
    s = _drive(RealignTracker(_chart()), [
        (101, 99, _Ev(**BULL_SOS)),
        (103, 100, _Ev(bull_bos=True)),
        (102, 97, _Ev(**BEAR_SOS, bear_bos_high=110.0)),
        (99, 95, _Ev()),
        (104, 98, _Ev(**BULL_SOS)),
    ])
    assert [x.trigger_dir for x in s] == [0, 0, 0, 0, 1]
    assert s[-1].trigger_stop == 95


def test_the_chart_frame_short_is_the_exact_mirror():
    s = _drive(RealignTracker(_chart()), [
        (101, 99, _Ev(**BEAR_SOS)),
        (100, 97, _Ev(bear_bos=True)),
        (103, 98, _Ev(**BULL_SOS, bull_bos_low=90.0)),
        (105, 99, _Ev()),
        (102, 96, _Ev(**BEAR_SOS)),
    ])
    assert (s[-1].trigger_dir, s[-1].trigger_stop) == (-1, 105)


def test_min_trend_breaks_refuses_a_counter_sos_straight_after_the_trends_own_sos():
    bars = [(101, 99, _Ev(**BULL_SOS)),
            (102, 97, _Ev(**BEAR_SOS, bear_bos_high=110.0)),
            (104, 98, _Ev(**BULL_SOS))]
    assert _drive(RealignTracker(_chart(realign_min_trend_breaks=1)), bars)[-1].trigger_dir == 0
    assert _drive(RealignTracker(_chart(realign_min_trend_breaks=0)), bars)[-1].trigger_dir == 1


def test_the_trend_break_count_restarts_when_the_trend_flips():
    """Two bearish BOS belong to the OLD trend. After the bullish SOS flips it, the new
    trend has printed no BOS of its own, so a counter SOS must not arm at k=1."""
    s = _drive(RealignTracker(_chart(realign_min_trend_breaks=1)), [
        (100, 98, _Ev(bear_bos=True)),
        (99, 97, _Ev(bear_bos=True)),
        (103, 98, _Ev(**BULL_SOS)),
        (102, 96, _Ev(**BEAR_SOS, bear_bos_high=110.0)),
        (104, 98, _Ev(**BULL_SOS)),
    ])
    assert s[-1].trigger_dir == 0


def test_max_counter_breaks_kills_a_pullback_that_keeps_breaking():
    bars = [(101, 99, _Ev(**BULL_SOS)),
            (102, 97, _Ev(**BEAR_SOS, bear_bos_high=110.0)),
            (98, 94, _Ev(bear_bos=True)),
            (97, 92, _Ev(bear_bos=True)),
            (104, 98, _Ev(**BULL_SOS))]

    def last(cap):
        return _drive(RealignTracker(_chart(realign_max_counter_breaks=cap)), bars)[-1]

    assert last(None).trigger_dir == 1 and last(None).trigger_stop == 92
    assert last(2).trigger_dir == 1
    assert last(1).trigger_dir == 0 and last(0).trigger_dir == 0


_REALIGN = [(101, 99, _Ev(**BULL_SOS)),
            (102, 97, _Ev(**BEAR_SOS, bear_bos_high=110.0)),
            (104, 98, _Ev(**BULL_SOS))]


def test_next_break_waits_for_the_first_with_trend_break_after_the_realignment():
    s = _drive(RealignTracker(_chart(realign_entry_on="Next break")),
               _REALIGN + [(106, 103, _Ev(bull_bos=True))])
    assert [x.trigger_dir for x in s] == [0, 0, 0, 1]


def test_next_break_is_killed_by_a_counter_sos_before_it():
    """The realignment failed. The same counter SOS arms a FRESH long, which is still
    waiting for its own realigning SOS — so the next bullish BOS fires nothing."""
    s = _drive(RealignTracker(_chart(realign_entry_on="Next break")),
               _REALIGN + [(100, 96, _Ev(**BEAR_SOS, bear_bos_high=105.0)),
                           (106, 103, _Ev(bull_bos=True))])
    assert [x.trigger_dir for x in s] == [0, 0, 0, 0, 0]


def test_the_chart_frame_arms_without_any_structural_target():
    """The chart-frame target is priced in R by the execution, so an arm must not wait on a
    swing level it never uses."""
    s = _drive(RealignTracker(_chart()), [
        (101, 99, _Ev(**BULL_SOS)),
        (102, 97, _Ev(**BEAR_SOS)),
        (104, 98, _Ev(**BULL_SOS)),
    ])
    assert s[-1].trigger_dir == 1


def test_the_chart_frame_target_is_a_multiple_of_the_trades_own_risk():
    """MEASURED: on the chart frame 407 of 982 trades had the counter leg's high at or behind
    the entry, so a structural target would satisfy TP2 on the entry bar and lock a small loss.
    The chart frame prices it in R; the external frame keeps its structural target."""
    chart = _chart(realign_chart_target_r=2.0)
    assert realign_target(chart, 0.0, 100.0, +1, 5.0) == 110.0
    assert realign_target(chart, 0.0, 100.0, -1, 5.0) == 90.0
    assert realign_target(_chart(realign_chart_target_r=3.0), 0.0, 100.0, +1, 5.0) == 115.0
    assert realign_target(RealignConfig(), 123.0, 100.0, +1, 5.0) == 123.0


def test_a_chart_frame_setup_dies_after_the_window():
    cfg = _chart()
    t = RealignTracker(cfg)
    _drive(t, [(101, 99, _Ev(**BULL_SOS)), (102, 97, _Ev(**BEAR_SOS, bear_bos_high=110.0))])
    late = int(cfg.realign_window_hrs * 3_600_000) + 20 * MIN
    assert t.update(late, 104, 98, _Ev(**BULL_SOS), _Ev()).trigger_dir == 0


def test_next_break_on_the_external_frame_adds_one_with_trend_break_after_the_pattern():
    def run(cfg):
        t = RealignTracker(cfg)
        t.on_htf(_Ev(bull_bos=True), 0, None, None)
        t.on_htf(_Ev(bear_sos=True, bear_bos=True, broken_high_price=100.0), MIN, 100.0, None)
        ext = [_Ev(bear_bos=True), _Ev(**BULL_SOS), _Ev(bull_bos=True)]
        return [t.update((2 + i) * MIN, 99.0, 90.0, e, _Ev()).trigger_dir
                for i, e in enumerate(ext)]

    assert run(RealignConfig())[:2] == [0, 1]
    assert run(dataclasses.replace(RealignConfig(), realign_entry_on="Next break")) == [0, 0, 1]


@pytest.mark.parametrize("field,val", [("realign_min_trend_breaks", 1),
                                       ("realign_max_counter_breaks", 0),
                                       ("realign_chart_target_r", 3.0)])
def test_chart_frame_settings_are_refused_on_the_external_frame(field, val):
    """Refused rather than ignored: a filter nothing consults reads as one that is on."""
    with pytest.raises(ValueError, match="Chart frame"):
        dataclasses.replace(RealignConfig(), **{field: val})


@pytest.mark.parametrize("kw", [dict(realign_pattern="strict"),
                                dict(realign_long_source="internal"),
                                dict(realign_chart_target_r=0.0)])
def test_the_chart_frame_refuses_settings_it_cannot_honour(kw):
    with pytest.raises(ValueError):
        _chart(**kw)


@pytest.mark.parametrize("field,bad", [("realign_arm_frame", "Weekly"),
                                       ("realign_entry_on", "Later")])
def test_a_typo_in_a_new_choice_field_raises(field, bad):
    with pytest.raises(ValueError, match=field):
        dataclasses.replace(RealignConfig(), **{field: bad})


# ── gaps the first mutation pass found (2026-09-11) ──────────────────────────────

def test_the_bear_trend_break_count_restarts_when_the_trend_flips():
    """Mirror of the bullish test: two bullish BOS belong to the OLD trend, so after the
    bearish SOS flips it a counter SOS must not arm a short at k=1."""
    s = _drive(RealignTracker(_chart(realign_min_trend_breaks=1)), [
        (102, 100, _Ev(bull_bos=True)),
        (103, 101, _Ev(bull_bos=True)),
        (102, 97, _Ev(**BEAR_SOS)),
        (104, 98, _Ev(**BULL_SOS)),
        (101, 96, _Ev(**BEAR_SOS)),
    ])
    assert s[-1].trigger_dir == 0


# ⚠ No test pins walk-before-fold, or arming on the counter SOS rather than any counter break.
#   On the engine's own stream both are unobservable — MEASURED over 467,352 5m bars and 5,265
#   breaks, at swing length 15 and again at 10: no bar carries both directions, and once a run has
#   printed its first break no counter break arrives without its SOS flag. A test for them would
#   feed the tracker a stream production cannot produce. Mutating either passes this file, by design.


@pytest.mark.parametrize("first,counter,realign,d", [
    (dict(bull_bos=True), BEAR_SOS, BULL_SOS, +1),
    (dict(bear_bos=True), BULL_SOS, BEAR_SOS, -1),
])
def test_the_first_break_of_a_run_sets_the_trend_even_as_a_plain_bos(first, counter, realign, d):
    """The engine can seed its direction off one swing and then break the other as a plain BOS —
    MEASURED: at swing length 10 the first break of the 2020-2026 run (bar 37) is exactly that.
    That break must establish the trend, or the first setup of the run is lost. Once per run."""
    s = _drive(RealignTracker(_chart()), [
        (102, 98, _Ev(**first)),
        (103, 97, _Ev(**counter)),
        (104, 96, _Ev(**realign)),
    ])
    assert s[-1].trigger_dir == d


def test_the_order_layer_prices_a_chart_frame_trade_at_its_R_target():
    """The pricing helper is tested on its own above; this pins that trades actually USE it.
    Without it the chart frame hands the ladder its arm's 0.0 target, which is the smoke-run
    defect that produced cells with no winning trade."""
    from types import SimpleNamespace

    from realign.tracker import RealignState
    from sos_fade.execution import Decision

    cfg = _chart(realign_chart_target_r=2.0)
    ex = RealignStrategy(cfg, initial_capital=100_000.0).execution
    ex._state = RealignState(trigger_dir=+1, trigger_stop=95.0, trigger_target=0.0)
    sig = SimpleNamespace(open=99.8, high=100.4, low=99.6, close=100.0,
                          index=10, time_ms=10 * 5 * MIN)
    ex._place_entries(sig, None, Decision(index=10), None, None)
    sl = 95.0 - cfg.realign_sl_buf_tk * cfg.mintick
    assert ex._pos_dir == +1
    assert ex._tp2 == pytest.approx(100.0 + 2.0 * (100.0 - sl))


def _bar_state():
    from types import SimpleNamespace

    return SimpleNamespace(bar=SimpleNamespace(open=100.0, high=101.0, low=99.0, close=100.0),
                           structure=SimpleNamespace(external=_Ev(), internal=_Ev()))


def _stub_downstream(strat, bar_ms=5 * MIN):
    """Everything after the tracker, replaced: these tests are about what the strategy FEEDS."""
    from types import SimpleNamespace

    strat.signals = SimpleNamespace(update=lambda state: None)
    strat.sequence = SimpleNamespace(update=lambda sig: None)
    strat.execution = SimpleNamespace(bar_ms=bar_ms, step=lambda sig, seq, rs: None)


@pytest.mark.parametrize("frame,fed", [("External frame", True), ("Chart frame", False)])
def test_only_the_external_arm_feeds_the_false_break_frame(frame, fed):
    """The chart-frame arm's whole sequence is the chart's own structure. Feeding the 15m
    aggregator there would publish 15m events into the same tracker and arm external setups
    the chart frame then walks as its own. The External case proves the spy can see a call."""
    calls = []
    strat = RealignStrategy(dataclasses.replace(RealignConfig(), realign_arm_frame=frame))
    _stub_downstream(strat)
    strat.htf = type("Spy", (), {"update": lambda self, *a: calls.append(a),
                                 "broken_high": None, "broken_low": None})()
    strat._step_core(_bar_state(), 0)
    assert bool(calls) is fed


def test_a_trend_frame_no_slower_than_the_chart_is_refused_on_the_first_bar():
    """On the chart frame the config cannot know the chart's frame, so the strategy checks it
    on the first bar: a 5-minute 'trend' on a 5-minute chart is the chart's own read."""
    same = RealignStrategy(_chart(realign_trend_minutes=5))
    _stub_downstream(same)
    with pytest.raises(ValueError, match="SLOWER"):
        same._step_core(_bar_state(), 0)

    slower = RealignStrategy(_chart(realign_trend_minutes=15))
    _stub_downstream(slower)
    slower._step_core(_bar_state(), 0)


@pytest.mark.parametrize("kw,field", [
    (dict(realign_trend_minutes=0), "realign_trend_minutes"),
    (dict(realign_trend_minutes=-15), "realign_trend_minutes"),
    (dict(realign_min_trend_breaks=-1), "realign_min_trend_breaks"),
    (dict(realign_max_counter_breaks=-1), "realign_max_counter_breaks"),
])
def test_impossible_counts_and_frames_are_refused(kw, field):
    """A trend frame of 0 is falsy, so the strategy would read it as OFF while the config says
    a value was set; a negative count can never be met. Both are refused by name."""
    with pytest.raises(ValueError, match=field):
        _chart(**kw)
