"""The order-intent stream — does what the strategy ASKS FOR describe what it DID?

🔴 **This is the load-bearing question for the whole execution unification.** The live bridge is
going to act on this stream instead of re-deriving position state, so a stream that omits an
action, or describes a different quantity from the one booked, would put a bot and a backtest on
two different books — silently, which is the failure the bridge's six refusals exist to prevent.

⚠ **`fills` and `intents` answer different questions and must not be conflated.** `fills` is what
the emulator DID; an intent is what was WANTED. They correspond one-for-one today only because
the emulator fills everything it asks for — a broker will not, and that is the entire reason the
two are separate types.
"""

import dataclasses
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.intents import IntentKind  # noqa: E402
from strategies.python.sos_fade.config import SosFadeConfig  # noqa: E402
from strategies.python.sos_fade.execution import Decision, Execution, _Pending  # noqa: E402


class Sig:
    def __init__(self, index=0, time_ms=0, o=100.0, h=101.0, l=99.0, c=100.0):
        self.index, self.time_ms = index, time_ms
        self.open, self.high, self.low, self.close = o, h, l, c
        self.bull_sos = self.bear_sos = False
        self.ny_hour = 10


def _pend(direction, edge, sl, tp1, tp2, qty=100.0):
    return _Pending(dir=direction, edge=edge, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)


def _ex(**kw):
    return Execution(dataclasses.replace(SosFadeConfig(), **kw), initial_capital=10_000.0)


# ── an entry ──────────────────────────────────────────────────────────────────


def test_an_entry_asks_to_OPEN_the_size_that_was_actually_granted():
    """🔴 The quantity must be what the ACCOUNT granted, never what the strategy wanted.

    The account sizes before the fill and may shrink it. An intent carrying the desired size
    would put a number on the wire the account had already refused — and live, that is an order
    for more than the account can carry.

    MUTATION: emit `pend.qty` instead of `granted` and this stays green ONLY while the two are
    equal, which is why the assertion is against the booked fill rather than against 100.0.
    """
    ex = _ex()
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    dec = Decision(index=0)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), dec) is True

    opens = [i for i in dec.intents if i.kind is IntentKind.OPEN]
    assert len(opens) == 1
    entry_fills = [f for f in dec.fills if f.kind == "entry"]
    assert len(entry_fills) == 1
    # The instruction and the booking describe the SAME trade.
    assert opens[0].qty == entry_fills[0].qty
    assert opens[0].price == entry_fills[0].price
    assert opens[0].direction == 1
    assert opens[0].stop == 99.0


def test_a_refused_entry_asks_for_NOTHING():
    """An account that grants nothing means no trade — and therefore no instruction. An intent
    emitted here would be an order for a position the strategy is not holding.

    MUTATION: emit the intent before the `granted <= 0` return and this goes red.
    """
    ex = _ex()
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0, qty=0.0)
    dec = Decision(index=0)
    ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), dec)
    assert [i for i in dec.intents if i.kind is IntentKind.OPEN] == []


# ── the stop ──────────────────────────────────────────────────────────────────


# 🔴 **THE TWO STOP TESTS THAT WERE HERE HAVE BEEN DELETED, AND THAT IS THE POINT.**
# They asserted that a freshly-built Decision carried no stop instruction, and that a field
# exists on the object. Both are true of code that emits nothing at all, so neither could ever
# go red — they were test-shaped, not tests. The stop-on-change guard lives inline inside
# `step()`, which needs a whole bar pipeline to reach, and logic with no seam a test can grab is
# logic nobody checks. It gets a real seam and real tests in the next step rather than a
# reassuring green here.

# ── correspondence ────────────────────────────────────────────────────────────


def test_every_exit_fill_has_exactly_one_matching_close_instruction():
    """The correspondence stage 3 will rely on: nothing the emulator books may be missing from
    the stream, and the stream may not invent an action the emulator did not take.

    ⚠ Asserted as a MULTISET over (quantity, price), not as a set — two rungs banking the same
    size at the same price are two instructions, and a set would silently accept one.
    """
    ex = _ex(exec_tp1_pct=30.0, exec_tp2_pct=40.0)
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    dec = Decision(index=0)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), dec) is True

    dec2 = Decision(index=1)
    ex._exit_portion("L-TP1", 100.5, 30.0, Sig(index=1, o=100.0, h=101.0, l=99.2), dec2)

    exits = sorted((f.qty, f.price) for f in dec2.fills if f.kind == "exit")
    closes = sorted(
        (i.qty, i.price) for i in dec2.intents if i.kind is IntentKind.CLOSE_PORTION
    )
    assert exits == closes
    assert exits, "nothing exited — this test would pass for free"


# ── an add ────────────────────────────────────────────────────────────────────


def _scaled_in(mode="Trail", **kw):
    """A strategy holding a long, with an add armed and ready to fill at the next open."""
    ex = _ex(exec_scale_in=True, exec_scale_mode=mode, **kw)
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Decision(index=0)) is True
    ex._add_armed = True
    ex._add_pending = 40.0
    ex._add_pend_stop = 99.4
    return ex


def test_an_add_asks_to_ADD_the_lot_it_actually_bought():
    """🔴 The add is the ONE order shape with no `Fill` record — it is separate lots, so it never
    reaches `dec.fills`. A reader counting fills would conclude this strategy never scales in,
    and a live bridge built from `fills` alone would trade the base position and say nothing.

    MUTATION: delete the emission and this goes red; emit `_add_pending` after it is cleared and
    it goes red on the quantity.
    """
    ex = _scaled_in()
    dec = Decision(index=1)
    ex._fill_pending_add(Sig(index=1, time_ms=1, o=100.6, h=101.0, l=100.0), dec)

    adds = [i for i in dec.intents if i.kind is IntentKind.ADD]
    assert len(adds) == 1
    # The instruction describes the lot the strategy actually recorded buying.
    assert len(ex._add_lots) == 1
    assert adds[0].qty == ex._add_lots[0]["qty"]
    assert adds[0].price == ex._add_lots[0]["price"]
    assert adds[0].direction == 1


def test_an_add_that_does_not_fill_asks_for_NOTHING():
    """A resting add that price never reached bought nothing, so there is nothing to instruct.

    MUTATION: move the emission above the reached/return check and this goes red.
    """
    ex = _scaled_in(mode="Limit")
    ex._add_limit = 98.0          # price never comes down to it on this bar
    dec = Decision(index=1)
    ex._fill_pending_add(Sig(index=1, time_ms=1, o=100.6, h=101.0, l=100.0), dec)
    assert [i for i in dec.intents if i.kind is IntentKind.ADD] == []
    assert ex._add_lots == [], "nothing was bought — this test would pass for free otherwise"


def test_an_add_carries_NO_stop_of_its_own():
    """🔴 A PIN ON A DELIBERATE OMISSION, not an accident of the data.

    This lot shares the position's one ratcheting stop. Attaching a stop here would put a second
    source of truth for it on the wire — the exact duplication this seam removes.

    ⚠ The assertion is only worth anything because a stop genuinely EXISTS at this moment: the
    add was sized against one, and `_add_stop` is set by the very call under test. Asserting
    `is None` without that would be true of a strategy that has no stops at all.
    """
    ex = _scaled_in()
    dec = Decision(index=1)
    ex._fill_pending_add(Sig(index=1, time_ms=1, o=100.6, h=101.0, l=100.0), dec)

    assert ex._add_stop == 99.4, "the add WAS sized against a stop"
    assert ex._current_stop() is not None, "the position HAS a stop to share"
    add = next(i for i in dec.intents if i.kind is IntentKind.ADD)
    assert add.stop is None
