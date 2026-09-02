"""Closing a trade because a PERSON asked — `Execution.request_close`.

🔴 **THE PARITY GATE CANNOT COVER ANY OF THIS, AND THAT IS WHY THE FILE EXISTS.** The Pine has
no such lever, nothing in `backtest/` calls it, and `compare_strategy.py` never enters the
branch — so a green gate says the change is INERT, which is a real and necessary property and
is not the same as the feature working. Rule 14, in its exact stated form: a green gate says
nothing about a branch neither side entered. Everything this lever does is pinned here instead.

Why the instruction goes to the STRATEGY and not to the broker: closing by hand at the terminal
leaves the emulator holding a position the account no longer has, and the bridge halts on the
next bar. A partial close by hand is worse — nothing notices, and every later size is computed
against a book that does not exist.

The fixtures are `test_execution.py`'s, via `test_time_stop.py`: a long that fills at 103.82 on
bar 1, stop 100.0, TP1 105.0, TP2 106.18, one bar every 15 minutes. The drift bars sit between
the breakeven stop and TP1, so nothing price-driven can close the position and the only thing
that can is the lever under test.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from mpc_sos_fade import Execution  # noqa: E402
from mpc_sos_fade.tests.test_execution import _cfg, _sig, _seq_long_ready, _seq_flat  # noqa: E402


def _open_long(ex):
    """Place on bar 0, fill on bar 1. Returns with a live long at 103.82."""
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    assert ex._pos_dir > 0, "fixture drifted — no position to close"


def _drift(ex, first, count):
    last = None
    for i in range(first, first + count):
        last = ex.step(_sig(i, 104.2, 104.6, 103.95, 104.3), _seq_flat())
    return last


# ── the lever itself ──────────────────────────────────────────────────────────
def test_a_commanded_close_exits_on_the_NEXT_bar_at_its_open():
    """A market order here is subject to the same one-bar delay every other order is — the bar
    that decided it has already closed. Same rule the time stop and the opposite-break close
    were measured against, so a commanded exit is not a new fill model."""
    ex = Execution(_cfg())
    _open_long(ex)
    _drift(ex, 2, 3)

    assert ex.request_close("aaron asked") is True
    ex.step(_sig(5, 104.2, 104.6, 103.95, 104.3), _seq_flat())      # decides
    ex.step(_sig(6, 104.11, 104.5, 104.0, 104.2), _seq_flat())      # fills at THIS open

    assert ex._pos_dir == 0
    assert ex.trades[0].exit_price == 104.11


def test_the_record_says_a_PERSON_asked_and_not_which_rule_fired():
    """🔴 The tag is the only thing `_close_at` keeps — the reason argument is discarded — and
    the opposite-break close already uses "CLOSE". Sharing it would make *somebody asked* and
    *structure broke against us* the same value in the record, so any later study of why trades
    ended would be quietly wrong. Caught by reading `_close_at`, before this test was written."""
    ex = Execution(_cfg())
    _open_long(ex)
    _drift(ex, 2, 3)
    ex.request_close()
    _drift(ex, 5, 2)

    assert ex.trades[0].exit_reason == "L-CMD"


def test_it_outranks_the_time_stop_so_the_record_names_the_person_not_the_clock():
    """Both are due on the same bar. An operator instruction is not a competing opinion — if
    the clock relabelled it, the one exit somebody can be asked about becomes unattributable."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    _open_long(ex)
    _drift(ex, 2, 3)

    ex.request_close()
    _drift(ex, 5, 2)        # bar 5 is 60 min after the fill — the time stop is due too

    assert ex.trades[0].exit_reason == "L-CMD"


# ── what it must NOT do ───────────────────────────────────────────────────────
def test_asking_while_FLAT_refuses_rather_than_latching():
    """A request that quietly waited would fire on whatever the strategy opened next — a trade
    the person asking had no opinion about. The False is what lets the caller say
    "nothing to close" instead of reporting a close that has not happened."""
    ex = Execution(_cfg())

    assert ex.request_close() is False

    _open_long(ex)
    _drift(ex, 2, 4)
    assert ex._pos_dir > 0, "a stale request closed a trade nobody asked about"
    assert ex.trades == []


def test_asking_TWICE_before_the_next_bar_is_still_one_close():
    ex = Execution(_cfg())
    _open_long(ex)
    _drift(ex, 2, 3)

    ex.request_close("first")
    ex.request_close("second")
    _drift(ex, 5, 2)

    assert len(ex.trades) == 1
    assert ex._pos_dir == 0


def test_a_trade_NOBODY_asked_about_is_untouched():
    """The inertness control, and it is the property the parity gate leans on: every lab run
    and every parity run leaves this lever alone, so the strategy must behave exactly as it did.
    It fails the mutation that closes unconditionally, which would redden the gate too — but a
    gate needing a real TradingView export is not something a suite can run."""
    ex = Execution(_cfg())
    _open_long(ex)
    _drift(ex, 2, 10)

    assert ex._pos_dir > 0
    assert ex.trades == []
