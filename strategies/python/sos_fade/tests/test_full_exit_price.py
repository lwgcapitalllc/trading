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
