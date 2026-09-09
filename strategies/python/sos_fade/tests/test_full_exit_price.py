"""`full_exit_price()` — the price this strategy closes the WHOLE position at, or None.

Part of the live contract (`strategies/python/live_contract.py` → `EXECUTION_ATTRS`). The bridge
hands the answer to the broker so the exit fills AT that price instead of at market on the next
bar close, which on a 15-minute clock is up to a whole bar of drift from the price the backtest
booked.

🔴 **THE RULE LIVES HERE RATHER THAN IN `algos/live/`, AND THESE TESTS ARE WHY THAT MATTERS.**
Which share the first rung takes depends on what KIND of trade is open — a re-entry after a
stop-out and one into a gap read different settings, and on the live bot those are **100 and 0**.
A copy of that branch in the live layer would be a second implementation free to drift from the
one that actually books the fills.

⚠ **The dangerous direction is answering a PRICE when the rung leaves a runner**: a venue
take-profit closes the entire position, so that would delete size the strategy is still managing.
Most cases here are therefore about when it must say None.

Every test was watched RED by mutation — see this package's CLAUDE.md.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution, _Pending

from .test_execution_ticks import Dec, Sig


def _long_in(ex, entry=99.5, sl=99.0, tp1=100.5, tp2=101.0, qty=100.0):
    """A long at 99.5, first rung at 100.50."""
    ex._pend_long = _Pending(dir=1, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True


def _ex(**over):
    return Execution(SosFadeConfig(**over), initial_capital=10_000.0)


def test_FLAT_has_no_target_even_while_the_LAST_trades_price_is_still_in_the_field():
    """🔴 THE FIXTURE IS THE TEST HERE, AND THE FIRST VERSION OF IT PROVED NOTHING.

    It asserted `None` on a FRESH object — where `_tp1` is 0.0, so *flat* and *no price* are the
    same assertion and the mutation that deletes the flat guard survived it. That is the scale-of-1
    trap this repo already records: a test whose inputs cannot distinguish the behaviours it names.

    `_finalise_trade` does NOT clear `_tp1` (checked, not assumed — it is assigned only in the
    constructor and at the entry fill), so a strategy that has traded and gone flat really is
    carrying its last trade's target. That is the state this reproduces, and without the guard the
    method would hand that stale price to the broker for whatever opens next.

    MUTATION: delete the `_pos_dir == 0` check and this goes red.
    """
    ex = _ex(exec_tp1_pct=100.0)
    _long_in(ex)
    ex._pos_dir = 0  # closed, exactly as `_finalise_trade` leaves it — target price and all
    assert ex._tp1 == 100.5, "the fixture must carry a stale target or it tests nothing"
    assert ex.full_exit_price() is None


def test_a_rung_that_takes_the_WHOLE_position_answers_its_price():
    ex = _ex(exec_tp1_pct=100.0)
    _long_in(ex)
    assert ex.full_exit_price() == 100.5


def test_a_rung_that_leaves_a_RUNNER_answers_None():
    """🔴 The destructive direction. A venue take-profit closes the entire position, so a price
    here would bank size the strategy is still riding."""
    ex = _ex(exec_tp1_pct=50.0)
    _long_in(ex)
    assert ex.full_exit_price() is None


def test_the_LIVE_bots_primary_answers_None_because_it_banks_nothing_at_a_price():
    """`exec_tp1_pct` is 0 on the armed bot: every primary rides its stop. This is the case that
    must NOT acquire a target, and it is the one running today."""
    ex = _ex(exec_tp1_pct=0.0)
    _long_in(ex)
    assert ex.full_exit_price() is None


def test_a_RECLAIM_re_entry_answers_its_price_where_the_primary_would_not():
    """🔴 THE TRADE THIS FEATURE EXISTS FOR. Same config, same open position — only the KIND of
    trade differs, and it flips the answer. A live-layer copy reading the shared setting would
    answer None here and the exit would go on closing at market.

    MUTATION: read `exec_tp1_pct` instead of the re-entry's own field and this goes red.
    """
    ex = _ex(exec_tp1_pct=0.0, exec_secondary=True, exec_rec_tp1_pct=100.0)
    _long_in(ex)
    ex._entry_kind, ex._entry_src = "secondary", "reclaim"
    assert ex.full_exit_price() == 100.5


def test_a_GAP_re_entry_answers_None_on_the_very_same_config():
    """The other half of the pair, and the reason the two must not be made to agree: the live bot
    banks 100% on a reclaim and 0% on a gap, measured opposite ways."""
    ex = _ex(exec_tp1_pct=0.0, exec_secondary=True, exec_rec_tp1_pct=100.0,
             exec_sec_tp1_pct=0.0)
    _long_in(ex)
    ex._entry_kind, ex._entry_src = "secondary", "gap"
    assert ex.full_exit_price() is None


# ── `planned_full_exit_price` — the same question about an order that has NOT filled ──────────
#
# 🔴 **THE RUNG IS PRICED OFF THE FILL, WHICH IS NOT KNOWN WHEN THE ORDER IS PLACED, SO THIS
# ANSWER IS AN ESTIMATE — AND THE TESTS BELOW ARE ABOUT WHICH DIRECTION IT IS WRONG IN.** A limit
# fills at its price or BETTER, a better fill is a SMALLER risk, and a smaller risk puts the rung
# NEARER the entry. So the estimate always sits at or BEYOND the price this strategy will bank at,
# which means the broker's target cannot fire before the strategy's own trigger. That one-way
# property is what makes it safe to send at all, and two tests here pin it in both directions.


def _plan(dir_=1, edge=99.5, sl=99.0, tp1=100.5, tp2=101.0, **over):
    return _Pending(dir=dir_, edge=edge, qty=100.0, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1, **over)


def _reclaim(**over):
    """The live bot's shape: re-entries on, the reclaim trigger banking the lot at 3.25R."""
    cfg = dict(exec_secondary=True, exec_rec_tp1_pct=100.0, exec_rec_tp_r=3.25,
               exec_tp1_pct=0.0)
    cfg.update(over)
    return _ex(**cfg)


def test_a_RESTING_reclaim_answers_the_rung_it_would_bank_at():
    """The trade this feature exists for. Edge 99.5, stop 99.0, so 1R is 0.5 and the rung is
    3.25R beyond the edge — a price the bridge can put on the order alongside the stop."""
    ex = _reclaim()
    assert ex.planned_full_exit_price(
        _plan(kind="secondary", src="reclaim")) == 99.5 + 3.25 * 0.5


def test_the_PLAN_and_the_FILLED_TRADE_agree_when_the_fill_lands_on_the_limit():
    """🔴 THE ANTI-DRIFT TEST, AND THE REASON BOTH ANSWERS CALL ONE FUNCTION.

    The bridge sends the planned price with the order and the strategy books the real one at the
    fill. If those two rules were written out separately — which is what copying the arithmetic
    into `algos/live/` would have meant — nothing would ever compare them, and they would agree
    until the day somebody changed one.

    MUTATION: price the plan off anything but `_first_rung` and this goes red.
    """
    ex = _reclaim()
    pend = _plan(kind="secondary", src="reclaim")
    planned = ex.planned_full_exit_price(pend)
    assert ex._open_position(pend, pend.edge, Sig(), Dec(), kind="secondary") is True
    assert ex.full_exit_price() == planned


def test_a_BETTER_fill_moves_the_real_target_NEARER_so_the_estimate_can_never_fire_early_LONG():
    """🔴 THE SAFETY PROPERTY, and it is the whole argument for sending an estimate at all.

    A buy limit fills at its price or LOWER. A lower fill is a SMALLER risk, so the 3.25R rung
    lands NEARER. The estimate therefore sits ABOVE the price the strategy banks at, the strategy
    exits first, and the broker's target is never reached — the harmless direction.

    MUTATION: price the plan off the STOP distance to the fib rather than the edge, or drop the
    market-entry refusal, and the direction stops holding.
    """
    ex = _reclaim()
    pend = _plan(kind="secondary", src="reclaim")
    estimate = ex.planned_full_exit_price(pend)
    gapped = 99.0 + 0.2      # filled 0.3 better than the 99.5 limit
    assert ex._open_position(pend, gapped, Sig(), Dec(), kind="secondary") is True
    real = ex.full_exit_price()
    assert real < estimate, "a better long fill must pull the rung DOWN, toward the entry"


def test_a_BETTER_fill_moves_the_real_target_NEARER_so_the_estimate_can_never_fire_early_SHORT():
    """The mirror, and it is here because *nearer* means HIGHER for a short — the direction that
    reads backwards and is the one an eyeball check gets wrong."""
    ex = _reclaim()
    pend = _plan(dir_=-1, edge=100.0, sl=100.5, tp1=99.0, tp2=98.5,
                 kind="secondary", src="reclaim")
    estimate = ex.planned_full_exit_price(pend)
    gapped = 100.2           # filled 0.2 better than the 100.0 limit
    assert ex._open_position(pend, gapped, Sig(), Dec(), kind="secondary") is True
    real = ex.full_exit_price()
    assert real > estimate, "a better short fill must pull the rung UP, toward the entry"


def test_a_MARKET_re_entry_answers_None_because_its_fill_can_land_either_side():
    """🔴 THE ONE CASE THE SAFETY PROPERTY ABOVE DOES NOT COVER, so it is refused rather than
    estimated. A market re-entry fills at the NEXT bar's open, which can be worse than the arming
    price as easily as better — and a worse fill puts the real rung FURTHER out, leaving the
    estimate NEARER, which is the direction that closes a trade early at a price this strategy
    never chose.

    ⚠ The live bot rests a limit for its reclaim, so this refusal costs it nothing today.

    MUTATION: delete the market check and this goes red.
    """
    ex = _reclaim(exec_rec_entry_mode="Market")
    assert ex.planned_full_exit_price(
        _plan(kind="secondary", src="reclaim", market=True)) is None


def test_a_plan_whose_rung_leaves_a_RUNNER_answers_None():
    """Same rule as the open-position answer: a venue target closes the ENTIRE position."""
    ex = _reclaim(exec_rec_tp1_pct=50.0)
    assert ex.planned_full_exit_price(_plan(kind="secondary", src="reclaim")) is None


def test_the_LIVE_bots_PRIMARY_answers_None_because_it_banks_nothing_at_a_price():
    """🔴 THE FIRST VERSION OF THIS PROVED NOTHING AND A MUTATION WALKED THROUGH IT.

    It asserted `None` on a config where the shared percentage was ALSO 0, so *read the primary's
    rule* and *read the secondary's rule and fall through* gave the same answer — the arithmetic
    version of a fixture that cannot express the defect. Deleting the kind check left it green.

    The config here is the pair that separates them: a SECONDARY banks the lot, a PRIMARY banks
    nothing. Same settings as the unnamed-secondary test above, same order price, and the only
    thing that differs is the KIND — which flips the answer.

    MUTATION: stop reading `kind` in the percentage rule and this goes red.
    """
    ex = _reclaim(exec_sec_tp1_pct=100.0, exec_sec_tp_r=2.0)
    assert ex.planned_full_exit_price(_plan(kind="secondary")) is not None, \
        "the fixture must make a SECONDARY answer a price or it separates nothing"
    assert ex.planned_full_exit_price(_plan()) is None


def test_an_UNNAMED_secondary_is_still_priced_as_a_secondary():
    """🔴 THE REASON THE ORDER CARRIES ITS OWN KIND RATHER THAN THE BRIDGE GUESSING.

    A re-entry whose trigger did not name itself has `src=None` — and so does every primary. Read
    off the trigger alone the two are one value (rule 1), and this order would be priced by the
    primary's rules. It is a secondary because it SAYS so.

    MUTATION: derive the kind from `src` instead of reading the field and this goes red.
    """
    ex = _reclaim(exec_sec_tp1_pct=100.0, exec_sec_tp_r=2.0)
    assert ex.planned_full_exit_price(
        _plan(kind="secondary")) == 99.5 + 2.0 * 0.5


def test_a_target_that_is_not_BEYOND_the_entry_answers_None():
    """A rung already behind the entry is not a target — a venue would refuse the order over it
    or fill it on the spot. Reached here with the fib rung on the wrong side of the limit."""
    ex = _reclaim(exec_rec_tp_r=-1.0)      # fall back to the frozen fib rung
    assert ex.planned_full_exit_price(
        _plan(kind="secondary", src="reclaim", tp1=99.4)) is None


def test_NO_order_answers_None_rather_than_raising():
    """The bridge asks about whichever slot it is reconciling, and an empty slot is routine."""
    assert _reclaim().planned_full_exit_price(None) is None
