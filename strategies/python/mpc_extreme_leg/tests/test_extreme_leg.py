"""Hand-traced tests for the rules that decide what this strategy trades.

Each one pins a rule that a plausible refactor would break silently. Every test in this file was
watched RED by mutating the line it covers — the mutation is named in the test's own docstring so
the next reader can repeat it in ten seconds rather than trusting this sentence. A test whose
mutation is not written down is a test nobody can check.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pytest

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mpc_extreme_leg import ExtremeLegConfig, MpcExtremeLegStrategy  # noqa: E402
from mpc_extreme_leg.execution import (  # noqa: E402
    BLK_ATR_NOT_READY,
    BLK_EXTREME_WRONG_SIDE,
    BLK_FRIDAY,
    BLK_NO_SWING,
    BLK_NONE,
    BLK_STOP_UNDER_FLOOR,
    BLK_SWING_WRONG_SIDE,
    BLK_TARGET_TOO_NEAR,
    ExtremeLegExecution,
)
from mpc_extreme_leg.htf import HtfStructure  # noqa: E402
from mpc_extreme_leg.strategy import LegState, _pine_round  # noqa: E402

NA = float("nan")


# ── the refusal ladder ───────────────────────────────────────────────────────
def _ladder(**over):
    """Run the ladder on a long candidate that would otherwise be accepted."""
    cfg = ExtremeLegConfig(**{k: v for k, v in over.items() if hasattr(ExtremeLegConfig, k)
                              or k in ExtremeLegConfig.__dataclass_fields__})
    args = dict(is_friday=False, target=110.0, entry=100.0, risk=2.0, r=5.0)
    args.update({k: v for k, v in over.items() if k in args})
    return MpcExtremeLegStrategy._ladder(cfg, args["is_friday"], args["target"], args["entry"],
                                         args["risk"], args["r"], above=True)


def test_a_clean_setup_is_not_refused():
    """The control. Without it every refusal below could be the ladder rejecting everything."""
    assert _ladder() == BLK_NONE


def test_the_calendar_is_checked_before_anything_else():
    """Friday wins even when the setup is ALSO broken another way.

    ⚠ The order is the rule, not an implementation detail — the refusal reason is what a reader
    uses to decide whether a filter is worth keeping, and a setup that reports 'target too near'
    when it was really a Friday makes the calendar filter look like it does nothing.
    RED by moving the Friday branch below the target check.
    """
    assert _ladder(is_friday=True, r=0.1) == BLK_FRIDAY


def test_a_missing_swing_refuses_rather_than_arming():
    """RED by deleting the isnan(target) branch — the comparison below then reads false and the
    setup is ACCEPTED with no target, which is the failure this branch exists for."""
    assert _ladder(target=NA) == BLK_NO_SWING


def test_a_swing_already_the_wrong_side_refuses():
    """RED by flipping `<=` to `<`, which lets a target sitting exactly on the entry through."""
    assert _ladder(target=100.0) == BLK_SWING_WRONG_SIDE
    assert _ladder(target=99.0) == BLK_SWING_WRONG_SIDE


def test_an_extreme_the_wrong_side_of_the_entry_refuses():
    """RED by dropping the `risk <= 0` branch: the size would then be computed off a negative
    stop distance and come back negative."""
    assert _ladder(risk=-1.0) == BLK_EXTREME_WRONG_SIDE


def test_the_stop_floor_is_inert_at_zero_and_refuses_above_it():
    """Zero must mean OFF rather than 'every stop clears it by definition'.
    RED by changing `min_stop_usd > 0 and ...` to `risk < min_stop_usd`, which refuses nothing at
    0 by luck rather than by decision — and starts refusing everything if the field goes negative.
    """
    assert _ladder(min_stop_usd=0.0, risk=0.01) == BLK_NONE
    assert _ladder(min_stop_usd=5.0, risk=2.0) == BLK_STOP_UNDER_FLOOR
    assert _ladder(min_stop_usd=5.0, risk=7.0) == BLK_NONE


def test_a_target_nearer_than_the_minimum_refuses():
    """RED by flipping `<` to `<=`, which refuses a setup sitting exactly on the threshold."""
    assert _ladder(min_r=2.0, r=1.9) == BLK_TARGET_TOO_NEAR
    assert _ladder(min_r=2.0, r=2.0) == BLK_NONE


def test_a_missing_average_range_declines_to_refuse_exactly_as_pine_does():
    """🔴 THE PARITY RULE, AND THE ONE MOST LIKELY TO BE 'FIXED' BY MISTAKE.

    With no ATR yet the stop, the risk and the R are all NaN. Pine evaluates every comparison
    against `na` as false, so the ladder declines to refuse and the refusal has to happen one layer
    down, in the order layer. Adding an isnan guard to any branch here would make this side refuse
    where the chart does not, and the gate would go red on the warm-up bars for a reason that looks
    like a logic bug. RED by adding `if math.isnan(risk): return BLK_EXTREME_WRONG_SIDE`.
    """
    assert _ladder(risk=NA, r=NA) == BLK_NONE


# ── the order layer ──────────────────────────────────────────────────────────
def _state(**kw):
    st = LegState(index=kw.pop("index", 10), ts_ms=kw.pop("ts_ms", 1_600_000_000_000))
    st.close = kw.pop("close", 100.0)
    for k, v in kw.items():
        setattr(st, k, v)
    return st


def _exec(**cfg):
    return ExtremeLegExecution(ExtremeLegConfig(**cfg), initial_capital=10_000.0)


def test_a_setup_with_no_average_range_refuses_instead_of_sizing_off_nothing():
    """The other half of the NaN rule. Pine reaches `strategy.entry` with an `na` quantity here;
    this side refuses and records why. RED by dropping the isfinite check in `enter`, which stores
    a position whose size is NaN and whose every later P&L is NaN too."""
    ex = _exec()
    st = _state(go_long=True, stop_long=NA, tp_long=105.0)
    assert ex.enter(st) is False
    assert ex.pos is None
    assert st.blk_long == BLK_ATR_NOT_READY
    assert ex.blocks and ex.blocks[-1].code == BLK_ATR_NOT_READY


def test_only_one_position_at_a_time():
    """RED by deleting the `self.pos is not None` guard. Every measurement this strategy has was
    made with one slot, and a second position changes the population all of them describe."""
    ex = _exec()
    assert ex.enter(_state(go_long=True, stop_long=98.0, tp_long=104.0)) is True
    first = ex.pos
    assert ex.enter(_state(index=11, go_short=True, stop_short=102.0, tp_short=96.0)) is False
    assert ex.pos is first


def test_the_entry_bar_cannot_stop_out_or_take_profit():
    """The bracket goes out at the entry bar's CLOSE, so it is live from the next bar.
    RED by changing `pos.entry_index >= index` to `>` in `resolve` — trades then close on the bar
    they opened, most often on exactly the fast bars this strategy enters on."""
    ex = _exec()
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.resolve(10, 1, high=110.0, low=90.0, open_=100.0)   # the entry bar itself
    assert ex.pos is not None and not ex.trades
    ex.resolve(11, 2, high=110.0, low=99.5, open_=100.0)   # the next bar takes the target
    assert ex.pos is None and ex.trades[-1].exit_reason == "target"


def test_a_bar_that_touches_both_ends_books_the_stop():
    """Bar data cannot say which came first, so the choice is between a guess that flatters the
    result and one that does not. RED by swapping the `if hit_stop` / `elif hit_tp` order."""
    ex = _exec()
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.resolve(11, 2, high=105.0, low=97.0, open_=100.0)
    assert ex.trades[-1].exit_reason == "stop"


def test_a_gap_through_the_stop_fills_at_the_open_not_at_the_stop():
    """The platform fills where the market actually was. RED by returning `pos.stop` instead of
    `min(pos.stop, open_)` — the backtest then books a loss the account could not have taken."""
    ex = _exec()
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.resolve(11, 2, high=96.0, low=90.0, open_=95.0)
    assert ex.trades[-1].exit_price == pytest.approx(95.0)


def test_breakeven_cannot_arm_on_the_entry_bar():
    """Pine gates it on `position_size != 0`, which is still 0 on the bar the order is placed.
    RED by dropping `pos.entry_index >= index` — at the shipped half-way exit a fast entry bar
    then arms and scratches the trade on the bar it opened."""
    ex = _exec(use_breakeven=True, be_arm_frac=0.5)
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.arm_breakeven(10, high=104.0, low=100.0)
    assert ex.pos.stop == pytest.approx(98.0) and ex.pos.be_armed is False
    ex.arm_breakeven(11, high=104.0, low=100.0)
    assert ex.pos.stop == pytest.approx(100.0) and ex.pos.be_armed is True


def test_breakeven_is_off_unless_it_is_switched_on():
    """RED by dropping `not cfg.use_breakeven` from the guard — a toggle that does nothing when
    off is worse than no toggle, because the page still claims it."""
    ex = _exec(use_breakeven=False, be_arm_frac=0.5)
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.arm_breakeven(11, high=104.0, low=100.0)
    assert ex.pos.stop == pytest.approx(98.0)


def test_r_is_measured_against_the_stop_the_trade_was_sized_to():
    """Not against the trailed stop it exited on. A breakeven exit must read about zero, not a win.
    RED by using `pos.stop` instead of `pos.open_stop` for the risk — a breakeven scratch then
    divides by zero or reports a fabricated multiple."""
    ex = _exec(use_breakeven=True, be_arm_frac=0.5)
    ex.enter(_state(index=10, go_long=True, stop_long=98.0, tp_long=104.0))
    ex.arm_breakeven(11, high=104.0, low=100.0)
    ex.resolve(12, 3, high=101.0, low=99.0, open_=100.5)
    t = ex.trades[-1]
    assert t.exit_reason == "stop"
    assert t.stop_distance == pytest.approx(2.0)
    assert t.r == pytest.approx(0.0, abs=1e-9)


# ── the arming state ─────────────────────────────────────────────────────────
@dataclass
class _Lvl:
    kind: str
    side: str


@dataclass
class _Liq:
    mitigated: List[_Lvl] = field(default_factory=list)


@dataclass
class _BS:
    liquidity: _Liq


def _sweeps(strategy, index, mitigated, bars_back=36):
    st = LegState(index=index)
    strategy._update_sweeps(_BS(_Liq(mitigated)), index, bars_back, st)
    return st


def test_two_families_must_agree_on_the_SAME_bar():
    """🔴 The count comes from the most recent sweep BAR, never from a running total.

    An accumulating count would make 'levels that must agree' mean something else entirely and
    would arm far more often. RED by changing the assignment to `self._low_fam += len(low_fams)`.
    """
    s = MpcExtremeLegStrategy(ExtremeLegConfig(min_families=2))
    a = _sweeps(s, 10, [_Lvl("daily", "low")])
    assert a.low_families == 1 and a.low_armed is False
    b = _sweeps(s, 11, [_Lvl("h4", "low")])
    assert b.low_families == 1 and b.low_armed is False        # NOT 2
    c = _sweeps(s, 12, [_Lvl("daily", "low"), _Lvl("h4", "low")])
    assert c.low_families == 2 and c.low_armed is True


def test_the_three_sessions_count_as_one_family():
    """Asia, London and New York are three levels but ONE kind of level. RED by counting levels
    instead of families — 'two kinds must agree' would then be satisfied by two sessions."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig(min_families=2))
    st = _sweeps(s, 10, [_Lvl("session", "low"), _Lvl("session", "low")])
    assert st.low_families == 1 and st.low_armed is False


def test_a_family_that_is_switched_off_does_not_arm_anything():
    """RED by dropping the `enabled[fam]` check — the toggles would render and do nothing."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig(use_weekly_level=False))
    st = _sweeps(s, 10, [_Lvl("weekly", "low")])
    assert st.low_families == 0 and st.low_armed is False


def test_an_arming_expires_and_the_two_sides_are_independent():
    """RED by dropping the `index - bar <= bars_back` term in `low_armed`, which would leave a
    side armed forever off one ancient sweep."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig())
    assert _sweeps(s, 10, [_Lvl("daily", "low")], bars_back=5).low_armed is True
    assert _sweeps(s, 15, [], bars_back=5).low_armed is True
    assert _sweeps(s, 16, [], bars_back=5).low_armed is False
    assert _sweeps(s, 16, [], bars_back=5).high_armed is False


def test_never_swept_and_expired_are_different_values():
    """Rule 1, in the one place this strategy can meet it: `None` means no level has EVER been
    taken on this side, which is not the same fact as one taken too long ago.
    RED by initialising the sweep bar to 0 — 'never' then reads as 'a very long time ago', which
    is a measurement where there is none."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig())
    st = _sweeps(s, 10, [])
    assert st.low_age is None and st.high_age is None
    st = _sweeps(s, 11, [_Lvl("daily", "low")])
    assert st.low_age == 0 and st.high_age is None


def test_the_weekly_close_reference_is_not_a_family():
    """The house liquidity engine also emits the previous week's CLOSE. This strategy's Pine never
    watches it, so it must not arm anything. RED by mapping `pwc` in `_FAMILY_OF`."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig())
    st = _sweeps(s, 10, [_Lvl("pwc", "close")])
    assert st.low_families == 0 and st.high_families == 0


# ── the arithmetic Pine does differently ─────────────────────────────────────
def test_rounding_is_half_away_from_zero_like_pine_not_half_to_even_like_python():
    """RED by using the built-in `round`: 2.5 comes back 2 and the lookback is one bar short.
    Both conversions this affects are exported by the twin so the gate can see it."""
    assert _pine_round(2.5) == 3 and round(2.5) == 2
    assert _pine_round(3.5) == 4 and _pine_round(0.5) == 1


def test_the_average_range_is_unknown_until_it_has_a_full_window():
    """Pine's `ta.atr` is `na` through its warm-up and this reproduces that, because the refusals
    it causes are part of what the two sides have to agree about.
    RED by seeding the average off however many bars have arrived — the warm-up bars then carry a
    real-looking stop that the chart never had."""
    s = MpcExtremeLegStrategy(ExtremeLegConfig(), atr_length=5)
    for i in range(4):
        s._update_atr(101.0 + i, 99.0 + i, 100.0 + i)
        assert math.isnan(s._atr)
    s._update_atr(105.0, 103.0, 104.0)
    assert not math.isnan(s._atr) and s._atr > 0


# ── the 15-minute half ───────────────────────────────────────────────────────
def test_a_period_is_published_on_the_first_bar_of_the_next_one():
    """The only non-repainting way to do it: the bar that closes a 15-minute candle cannot know it
    closed one until the next candle opens. RED by publishing on the third bar instead — the trend
    would then be read off a candle that is still forming."""
    h = HtfStructure(htf_minutes=15)
    bars = [(0, 1, 2, 0.5, 1.5), (300_000, 1.5, 3, 1.4, 2.5), (600_000, 2.5, 3.5, 2.0, 3.0),
            (900_000, 3.0, 3.2, 2.9, 3.1)]
    for ts, o, hi, lo, c in bars[:3]:
        h.update(ts, o, hi, lo, c)
        assert h.period_closed is False and h.done is None
    h.update(*bars[3])
    assert h.period_closed is True
    assert h.done == (1, 3.5, 0.5, 3.0)      # open of the first, extremes of all three


def test_the_higher_timeframe_bar_is_the_extremes_of_its_children():
    """RED by taking the last child's high instead of the running maximum."""
    h = HtfStructure(htf_minutes=15)
    for ts, o, hi, lo, c in ((0, 10, 20, 5, 15), (300_000, 15, 12, 1, 8), (600_000, 8, 9, 7, 9)):
        h.update(ts, o, hi, lo, c)
    h.update(900_000, 9, 9, 9, 9)
    assert h.done == (10, 20, 1, 9)


def test_the_structure_engine_field_this_reads_still_exists():
    """A rename upstream must fail LOUDLY on construction rather than scoring nothing.
    RED by deleting the guard and renaming `_ext` — the strategy then runs and takes no trades,
    which looks exactly like a market with no setups in it."""
    h = HtfStructure()
    assert hasattr(h._eng, "_ext") and hasattr(h._eng._ext, "ash")


# ── the config ───────────────────────────────────────────────────────────────
def test_a_requirement_that_can_never_be_satisfied_is_refused_at_construction():
    """RED by dropping the check — the strategy runs, takes nothing, and reads as a quiet market."""
    with pytest.raises(ValueError, match="can ever arm"):
        ExtremeLegConfig(min_families=3, use_h4_level=False, use_daily_level=False,
                         use_weekly_level=False)


def test_the_pines_hardcoded_constants_are_not_lab_settings():
    """🔴 They were config fields until the scanner was actually RUN and asked what it would draw.

    A field on the config becomes a row on the strategy page. These three have no Pine input, so no
    `cfg_*` column carries them and no gate could ever check one — a run that moved one would
    diverge from the chart with nothing anywhere to say so. RED by putting any of them back on
    `ExtremeLegConfig`.
    """
    fields = set(ExtremeLegConfig.__dataclass_fields__)
    assert not (fields & {"major_length", "htf_minutes", "atr_length"})
    # still reachable from a test, which is the whole reason they are keyword arguments
    assert MpcExtremeLegStrategy(atr_length=7).atr_length == 7


def test_a_misspelled_sizing_mode_is_refused_rather_than_silently_meaning_fixed():
    """RED by dropping the check: `size_mode` is compared against a literal in `_qty`, so any
    typo silently selects the OTHER branch and every position is one contract."""
    with pytest.raises(ValueError, match="size_mode"):
        ExtremeLegConfig(size_mode="risk %")


def test_a_profile_that_moves_fills_is_refused_rather_than_half_honoured():
    """RED by dropping the refusal — the run would report a trade list neither cost model
    produces, which is worse than either."""
    class _P:
        name = "moves_fills"
        bid_ask_fills = True
    with pytest.raises(ValueError, match="bid_ask_fills"):
        ExtremeLegExecution(ExtremeLegConfig(), profile=_P())


# ── the two cuts TradingView cannot make (2026-09-02) ────────────────────────────
#
# The market cut SHIPS ON; the news cut ships off. What these pin is that each is INERT while off,
# that they sit after every refusal the Pine can also make, that "could not ask" is not the same
# answer as "no", and that the pair which ships is the pair that was MEASURED to be worth it — a
# default nobody has re-measured is a guess with an authoritative face.

from ..execution import BLK_NEWS, BLK_TRANSITIONING  # noqa: E402
from ..filters import ALLOW, REFUSE, UNKNOWN, NewsCut, TransitioningCut  # noqa: E402


def test_the_shipped_cuts_are_the_ones_that_were_MEASURED_to_be_worth_it():
    """Mutation: flip either shipped default in config.py.

    🔴 Each of these is a DECISION with a number behind it, not a preference, and the two went
    opposite ways over 470,995 PU Prime M5 bars:
      market cut ON  — 132 trades/+57.10R/worst run 8.13R → 113/+58.53R/6.00R. Better on both.
      news cut  OFF  — it scored +51.45R with a DEEPER worst run of 8.87R, and could not answer
                       on 51 of 550 setups because the calendar does not cover the window.
    ⚠ Turning either one on costs something real: the chart cannot make these checks, so the
    parity gate can only ever prove the SHARED logic and says so on its verdict line.
    """
    cfg = ExtremeLegConfig()
    assert cfg.skip_transitioning is True, "measured better on BOTH money and worst run"
    assert cfg.skip_news is False, "measured worse on both, on 91% calendar coverage"


def test_a_cut_that_is_OFF_cannot_refuse_even_when_its_answer_is_yes():
    """Mutation: drop `cfg.skip_transitioning and` (or `cfg.skip_news and`) from the ladder.

    This is what keeps the decision stream bit-identical to the chart's while the cuts are off.
    Both answers are forced True here and both flags are off, so the ladder must still accept.
    """
    cfg = ExtremeLegConfig(min_r=1.0, skip_transitioning=False, skip_news=False)
    code = MpcExtremeLegStrategy._ladder(
        cfg, False, 110.0, 100.0, 5.0, 2.0, above=True, transitioning=True, news=True
    )
    assert code == 0


def test_each_cut_refuses_with_its_OWN_code_when_switched_on():
    """Mutation: return BLK_NONE from either new branch, or swap the two codes."""
    cfg_t = ExtremeLegConfig(min_r=1.0, skip_transitioning=True)
    assert MpcExtremeLegStrategy._ladder(
        cfg_t, False, 110.0, 100.0, 5.0, 2.0, above=True, transitioning=True
    ) == BLK_TRANSITIONING

    cfg_n = ExtremeLegConfig(min_r=1.0, skip_news=True)
    assert MpcExtremeLegStrategy._ladder(
        cfg_n, False, 110.0, 100.0, 5.0, 2.0, above=True, news=True
    ) == BLK_NEWS


def test_the_new_cuts_sit_AFTER_every_refusal_the_pine_can_also_make():
    """Mutation: move either new branch above the Friday check in `_ladder`.

    A Friday setup that is ALSO inside a news blackout must record Friday — the code the chart
    records. Ordering the new cuts first would change which of the Pine's own codes appears on a
    bar, so a gate run with the cuts off would still diverge. The whole design rests on this.
    """
    cfg = ExtremeLegConfig(min_r=1.0, skip_news=True, skip_transitioning=True)
    code = MpcExtremeLegStrategy._ladder(
        cfg, True, 110.0, 100.0, 5.0, 2.0, above=True, transitioning=True, news=True
    )
    assert code == BLK_FRIDAY


def test_a_news_cut_switched_on_with_a_zero_window_is_REFUSED_not_accepted():
    """Mutation: delete the zero-window check in `__post_init__`.

    On-but-inert is the state this repo keeps mistaking for on-and-finding-nothing. It would show
    as an active filter on the strategy page and refuse nothing in eight years.
    """
    with pytest.raises(ValueError, match="never refuse"):
        ExtremeLegConfig(skip_news=True, news_before_min=0, news_after_min=0)


def test_a_cut_counts_being_ASKED_not_only_saying_no():
    """Mutation: delete `self.asked += 1` from either cut.

    🔴 This is the bug the first run of `filters.py` actually had. A cut that was never wired and
    a cut asked two hundred times that allowed every one both print a zero — the run comes back
    identical to the baseline and reads as "nothing to refuse here". `asked` is what says the
    thing is connected at all.
    """
    cut = TransitioningCut()
    assert cut.asked == 0
    cut.ask()
    assert cut.asked == 1


def test_too_little_history_is_UNKNOWN_and_allows_rather_than_refusing():
    """Mutation: return REFUSE (or ALLOW) instead of UNKNOWN on a short frame.

    A filter that refused whenever it could not see would quietly become a different strategy for
    the first hours of every run. It allows — and the count is what stops that being silent.
    """
    cut = TransitioningCut()
    for _ in range(10):
        cut.on_bar(1.0, 2.0, 0.5, 1.5)
        cut.on_htf_bar(1.0, 2.0, 0.5, 1.5)
    assert cut.ask() == UNKNOWN
    assert cut.unknown_count == 1
    assert cut.refused == 0


def test_an_empty_calendar_is_UNKNOWN_never_ALLOW():
    """Mutation: return ALLOW when the store has no events.

    An empty calendar and a checked-and-clear calendar are different facts. Reading them the same
    way is what let a stale cache look like an active news filter for a month (2026-09-01).
    """
    cut = NewsCut(30, 30, "XAUUSD")
    cut._built = True
    cut._engine = None
    assert cut.ask(0, 0) == UNKNOWN
    assert cut.unknown_count == 1
    assert cut.refused == 0
    assert cut.asked == 1
