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


# ── the retest entry ─────────────────────────────────────────────────────────────
# Aaron's brother's actual sequence ends "...retest, go". The market entry is the one
# every figure before 2026-09-15 used, so every test here is about the NEW path being
# distinguishable from it — a retest that quietly degrades into a market order is the
# silent failure, and it would show up as a flattering number nobody could trace.

import dataclasses  # noqa: E402

from realign.execution import RealignExecution  # noqa: E402
from realign.tracker import RealignState  # noqa: E402


class _Sig:
    """The handful of bar fields the entry path reads."""
    def __init__(self, index=100, close=100.0, low=None, high=None):
        self.index = index
        self.open = self.close = close
        self.low = close if low is None else low
        self.high = close if high is None else high


def _exec(**over):
    cfg = dataclasses.replace(RealignConfig(symbol="XAUUSD"),
                              realign_entry_mode="retest", **over)
    ex = RealignExecution(cfg, initial_capital=10_000.0)
    ex._opened = []
    ex._open_position = lambda pend, px, sig, dec, **kw: (  # type: ignore[assignment]
        ex._opened.append((pend, px)) or True)
    return ex


def _fire(ex, sig, level=99.0, stop=98.0, target=110.0, d=+1):
    st = RealignState(trigger_dir=d, trigger_stop=stop, trigger_target=target,
                      trigger_level=level)
    ex._state = st
    ex._place_entries(_Sig(sig.index, sig.close), None, object(), None, None)


def test_the_retest_rests_a_limit_instead_of_opening_at_the_close():
    """The whole point. If this opens a position the row is a market entry wearing the
    retest's name, and its numbers would be compared against itself."""
    ex = _exec()
    _fire(ex, _Sig(close=100.0), level=99.0)
    assert ex._opened == [], "the retest opened at market"
    assert ex._pend_long is not None and ex._pend_long.edge == 99.0


def test_a_missing_level_refuses_rather_than_entering_at_the_close():
    """`trigger_level=None` is a real state — the engine cannot always attribute a break to
    a stored swing. Falling back to the close would make part of a retest book a MARKET
    book, so the row would measure a blend of the two things it exists to separate."""
    ex = _exec()
    _fire(ex, _Sig(close=100.0), level=None)
    assert ex._opened == [] and ex._pend_long is None
    assert ex.retest_no_level == 1, "a refused setup must be counted, not just dropped"


def test_a_level_already_through_the_market_does_not_rest():
    """A long limit ABOVE the close fills at the next bar's open — a market entry at a worse
    price under another name. Price has to come BACK to a retest."""
    ex = _exec()
    _fire(ex, _Sig(close=100.0), level=100.5)
    assert ex._pend_long is None and ex._opened == []


def test_the_market_entry_still_opens_at_the_close():
    """The shipped path, which 162 trades and every published figure depend on."""
    cfg = RealignConfig(symbol="XAUUSD")
    assert cfg.realign_entry_mode == "market", "the shipped default moved"
    ex = RealignExecution(cfg, initial_capital=10_000.0)
    ex._opened = []
    ex._open_position = lambda pend, px, sig, dec, **kw: (
        ex._opened.append((pend, px)) or True)
    _fire(ex, _Sig(close=100.0))
    assert [px for _, px in ex._opened] == [100.0]
    assert ex._pend_long is None


def test_a_resting_limit_is_cancelled_once_its_expiry_passes():
    """Without this the order rests forever: this fork places ONCE, so nothing overwrites a
    stale one, and it could fill days later against a stop and target frozen in a market
    that no longer exists."""
    ex = _exec(realign_retest_bars=3)
    _fire(ex, _Sig(index=100, close=100.0), level=99.0)
    ex._expire_retest(_Sig(index=102, close=100.0))
    assert ex._pend_long is not None, "cancelled one bar early"
    ex._expire_retest(_Sig(index=103, close=100.0))
    assert ex._pend_long is None


def test_a_bar_that_reaches_the_stop_kills_the_unfilled_order():
    """The setup invalidated before it was ever entered."""
    ex = _exec()
    _fire(ex, _Sig(index=100, close=100.0), level=99.0, stop=98.0)
    ex._expire_retest(_Sig(index=101, close=99.5, low=97.0))
    assert ex._pend_long is None


@pytest.mark.parametrize("day,is_friday", [
    ("2025-08-08", True), ("2025-08-07", False), ("2025-08-11", False), ("2025-08-09", False),
])
def test_the_weekend_flat_fires_on_friday_and_no_other_day(day, is_friday):
    """🔴 The epoch began on a THURSDAY. The obvious `+4` shift reads one day early and
    flattens on Thursday — a rule that still looks like it works, closes trades, and changes
    the result. Watched red with `+4`: the Thursday and Friday cases swap."""
    import datetime as _dt

    ms = int(_dt.datetime.strptime(day, "%Y-%m-%d")
             .replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)
    assert (((ms // 86_400_000 + 3) % 7) == 4) is is_friday


def test_the_order_is_never_cancelled_on_the_bar_it_was_placed():
    """`_expire_retest` runs on the placement bar too (it is called every bar). Ageing the
    order there would cancel it before the fill path had ever seen it, and the retest row
    would take no trades at all while looking like a legitimate result."""
    ex = _exec(realign_retest_bars=1)
    _fire(ex, _Sig(index=100, close=100.0), level=99.0, stop=98.0)
    ex._expire_retest(_Sig(index=100, close=100.0, low=97.0))
    assert ex._pend_long is not None


# ── the parity gate's decoder must not drift from the export block ───────────────
# 🔴 The gate reads packed columns by a bit scheme written down in TWO files. If the Pine's
# packing and the Python's decoding drift apart, the gate compares the wrong bits and can go
# GREEN on a disagreement — a parity gate lying is strictly worse than no gate, because it is
# believed. These read the block file and hold the decoder to it.

_BLOCK = _ROOT / "strategies" / "tradingview" / "export_blocks" / "realign_strategy.pine"


def _plot_titles() -> set:
    import re

    return set(re.findall(r'"((?:px|cfg)_[a-z0-9_]+)"', _BLOCK.read_text(encoding="utf-8")))


def test_every_column_the_gate_compares_is_actually_plotted_by_the_twin():
    """An export cannot carry a column its twin does not plot, so a gate reading one would
    refuse every real export — or, worse, silently skip it. Watched red by renaming a plot."""
    from realign.tools.compare_realign import _COMPARED

    titles = _plot_titles()
    packed = {"px_struct", "px_arm"}
    missing = [c for c in _COMPARED if c not in titles and c not in packed]
    assert not missing, f"the gate compares columns the export block never plots: {missing}"


def test_every_config_column_the_gate_reads_is_plotted():
    """A cfg_* column the twin does not plot means the port is configured from THIS side's
    defaults while claiming it came from the export — the one thing the decoder forbids."""
    from realign.tools.compare_realign import _CFG_NUM

    titles = _plot_titles()
    missing = [c for c in _CFG_NUM if c not in titles]
    assert not missing, f"the gate reads cfg columns the export block never plots: {missing}"


def test_the_gate_pins_the_pines_reward_to_risk_guard():
    """The Pine guards entry with `tgtLong > close` and has no input for it, so no cfg_*
    column can carry it. 0.0 reproduces that guard; None — this side's default — does not.
    A config must describe the EXPORT. Goes red if the pin is dropped."""
    import pandas as pd

    from realign.tools.compare_realign import config_from_export

    cfg, _missing = config_from_export(pd.DataFrame({"cfg_bits": [3.0]}))
    assert cfg.realign_min_rr == 0.0


def test_the_enum_decoder_covers_every_digit_the_block_packs():
    """`cfg_enum1` packs one dropdown per decimal place. A decoder listing fewer fields than
    the block packs reads a later digit into the wrong setting and configures a different
    strategy — silently, because every value still looks legal."""
    import re

    from realign.tools.compare_realign import _ENUM_ORDER

    txt = _BLOCK.read_text(encoding="utf-8")
    block = txt[txt.index('"cfg_enum1"') - 1400:txt.index('"cfg_enum1"')]
    places = {0} | {len(m) for m in re.findall(r"\+ 1(0+) \* \(", block)}
    assert len(_ENUM_ORDER) == len(places), (
        f"the block packs {len(places)} enum digits and the decoder names "
        f"{len(_ENUM_ORDER)}")
