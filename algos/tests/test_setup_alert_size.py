"""The lot size on the resting-limit message, and the three states behind it.

Aaron, 2026-09-03: *"I need to see how much lots are going to be traded."*

🔴 **The size may only ever be the number SENT TO THE BROKER.** The strategy sizes in instrument
UNITS (ounces for gold) and MT5 takes LOTS; a message that converted for itself would be a second
answer competing with `order_sizing`'s one seam — the defect that rested 54.82 lots on a $2,000
account, 221x the intent. So the alert layer is handed a lot count and never derives one, and
these tests pin that it renders what it is given and nothing else.

🔴 **THREE STATES, and flattening any two breaks a different message:**
  - no `lots_for` at all  -> there is no broker to ask (a backtest, `alert_rate.py`): SEND, no size
  - `lots_for` -> a float -> an order of that size is live at the broker: SEND with the size
  - `lots_for` -> None    -> asked, and NOTHING rests (refused/cancelled): SEND NOTHING

**Watched RED against HEAD**: `format_entry_zone` took no `lots` there, `SetupAlerts` took no
`lots_for`, and `OrderBridge` had no `resting_lots` — so each case fails at the signature. Because
"the argument is new" cannot tell a working rule from a present one, each behavioural guarantee
also names the mutation that reddens it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import alerts as live_alerts  # noqa: E402
from setup_alerts import SetupAlerts  # noqa: E402

from backtest.setups import RESTING, Confluence, SetupSnapshot  # noqa: E402


class Recorder:
    def __init__(self):
        self.sent = []

    def __call__(self, text, kind, reply_to=None):
        self.sent.append({"text": text, "kind": kind, "reply_to": reply_to})
        return len(self.sent)

    def heads(self):
        return [m["text"].split("\n")[0] for m in self.sent]


class FakeStrategy:
    def __init__(self, queue):
        self._queue = list(queue)
        self.execution = self

    def live_setups(self):
        return self._queue[0] if self._queue else []

    def drain_setups(self):
        return self._queue.pop(0) if self._queue else []


def _snap(**kw):
    base = dict(
        key="K1",
        strategy="Strat",
        symbol="XAUUSD",
        side=1,
        state=RESTING,
        confluences=(
            Confluence("Arm", True, "Day Low"),
            Confluence("SOS", True, "confirmed"),
            Confluence("Zone", True, "0.5-0.886 tagged"),
        ),
        zone=(100.0, 90.0),
        entry=95.0,
        stop=89.5,
        targets=(99.0, 103.0),
    )
    base.update(kw)
    return SetupSnapshot(**base)


def _resting_head(rec):
    return next((h for h in rec.heads() if "LIMIT RESTING" in h), None)


# ── the formatter renders what it is handed, and nothing when handed nothing ─────────────────
def test_the_size_appears_on_the_resting_message():
    """MUTATION: drop `lots` from the title in `format_entry_zone` and this reddens."""
    text = live_alerts.format_entry_zone(_snap(), 2, 0.35)
    assert "0.35 lots" in text.split("\n")[0]


def test_the_unit_is_NAMED_and_not_left_as_a_bare_number():
    """🔴 A bare number on this message is the one place a reader could take ounces for lots, and
    this repo has already paid 221x for that confusion once."""
    assert "lots" in live_alerts.format_entry_zone(_snap(), 2, 0.35)


def test_the_size_is_rendered_to_TWO_DECIMALS_like_the_terminal_shows_it():
    """The point of the number is that it matches what he sees in MT5."""
    assert "0.35 lots" in live_alerts.format_entry_zone(_snap(), 2, 0.3456)
    assert "1.00 lots" in live_alerts.format_entry_zone(_snap(), 2, 1.0)


def test_NO_SIZE_is_printed_when_none_was_supplied():
    """The backtest path. It must render exactly as it always did rather than inventing a zero.

    MUTATION: default `lots` to 0.0 and this reddens on the `0.00` that appears.
    """
    head = live_alerts.format_entry_zone(_snap(), 2).split("\n")[0]
    assert "lots" not in head
    assert "BUY LIMIT RESTING" in head


def test_the_direction_and_the_words_that_were_hard_won_are_still_there():
    """The header was reworded after a real send was misread as a fill. Adding a size must not
    cost the two words that fixed it."""
    head = live_alerts.format_entry_zone(_snap(), 2, 0.35).split("\n")[0]
    assert "BUY" in head and "LIMIT" in head and "RESTING" in head
    assert "SELL" in live_alerts.format_entry_zone(_snap(side=-1), 2, 0.35)


# ── the three states, through the real transition layer ──────────────────────────────────────
def test_with_a_broker_the_message_carries_the_size_it_is_holding():
    rec = Recorder()
    a = SetupAlerts(send=rec, log=None, lots_for=lambda side: 0.42)
    a.on_bar(FakeStrategy([[_snap()]]))
    assert "0.42 lots" in _resting_head(rec)


def test_with_NO_broker_the_message_still_goes_out_without_a_size():
    """🔴 *No broker to ask* is NOT *no order*. `alert_rate.py` and every backtest run this path,
    and silencing them would delete the volume measurement this channel is tuned by.

    MUTATION: treat a missing `lots_for` as "nothing resting" and this reddens.
    """
    rec = Recorder()
    a = SetupAlerts(send=rec, log=None)
    a.on_bar(FakeStrategy([[_snap()]]))
    head = _resting_head(rec)
    assert head is not None
    assert "lots" not in head


def test_an_order_the_broker_does_NOT_hold_is_never_announced_as_resting():
    """🔴 The defect this reorder was built to fix. The message used to be composed BEFORE the
    order was placed, so a limit the bridge then refused was still announced as resting — naming
    an order nobody held, on the one message whose whole job is to say an order EXISTS.

    MUTATION: send regardless of the lookup's answer and this reddens.
    """
    rec = Recorder()
    a = SetupAlerts(send=rec, log=None, lots_for=lambda side: None)
    a.on_bar(FakeStrategy([[_snap()]]))
    assert _resting_head(rec) is None


def test_a_refused_bar_does_NOT_burn_the_setups_one_resting_message():
    """🔴 The bookkeeping-before-the-guard mistake, which this layer has already made twice. An
    order refused on one bar can rest on the next; if the first bar marked the message sent, the
    announcement would never arrive and the setup would go silent for good.

    MUTATION: move `sent.add` above the lookup and this reddens.
    """
    rec = Recorder()
    holding = {"lots": None}
    a = SetupAlerts(send=rec, log=None, lots_for=lambda side: holding["lots"])
    strat = FakeStrategy([[_snap()], [_snap()]])
    a.on_bar(strat)  # refused — nothing rests
    assert _resting_head(rec) is None
    holding["lots"] = 0.28  # the next bar it is placed
    a.on_bar(strat)
    assert "0.28 lots" in _resting_head(rec)


def test_the_root_message_is_still_sent_on_a_refused_bar():
    """Suppressing the RESTING reply must not suppress the thread it replies to — the reader still
    needs to know the setup exists."""
    rec = Recorder()
    a = SetupAlerts(send=rec, log=None, lots_for=lambda side: None)
    a.on_bar(FakeStrategy([[_snap()]]))
    assert any("SETUP FORMING" in h for h in rec.heads())


def test_the_size_is_looked_up_PER_SIDE():
    """A long and a short rest in different slots and at different sizes; one lookup for both
    would report one side's size against the other's order."""
    seen = []
    rec = Recorder()
    a = SetupAlerts(
        send=rec, log=None, lots_for=lambda side: seen.append(side) or (0.10 if side > 0 else 0.20)
    )
    a.on_bar(FakeStrategy([[_snap(key="L", side=1), _snap(key="S", side=-1)]]))
    assert sorted(seen) == [-1, 1]
    heads = " ".join(rec.heads())
    assert "0.10 lots · BUY" in heads
    assert "0.20 lots · SELL" in heads


# ── the bridge answers from the PLACED order, never from a computation ────────────────────────
def test_the_bridge_reports_the_lots_it_actually_placed():
    """Through the REAL `OrderBridge`, not a stand-in — a fake that answered would be describing a
    system we do not have.

    MUTATION: derive the figure from the strategy's `qty` instead of reading `_rest` and this
    reddens, because the two are in different units by a factor of the contract size.
    """
    sys.path.insert(0, str(_ROOT / "algos" / "tests"))
    import bridge as live_bridge  # noqa: E402
    from test_live_bridge import _bridge, _FakeExecution  # noqa: E402

    b, _mt5, _ledger, _notes = _bridge(_FakeExecution())
    assert b.resting_lots(1) is None  # nothing placed yet
    b._rest[live_bridge.PRIMARY_LONG] = live_bridge._Rest(ticket=1, price=95.0, lots=0.37, sl=89.5)
    assert b.resting_lots(1) == 0.37
    assert b.resting_lots(-1) is None  # the other side is untouched


# ── the bar ordering that makes the size knowable at all ─────────────────────────────────────
def _runner_with(bridge_sync):
    """A bare `Runner` with only what `_settle_primary` touches. Built by `__new__` rather than
    by running startup, which would need MT5, a feed and a strategy — none of which this property
    is about."""
    import bridge as live_bridge  # noqa: E402
    import runner as live_runner  # noqa: E402

    order = []

    class _Log:
        def error(self, *a, **k):
            pass

    class _Ledger:
        def bar(self, *a, **k):
            order.append("ledger")

    class _Bridge:
        # `state` because production HAS one and `_settle_primary` reads it after the alerts.
        # A fake without it would fail here; a fake that answered something production cannot
        # would be the more dangerous direction, so it holds the real enum.
        state = live_bridge.BridgeState.LIVE

        def sync(self, dec, sig):
            order.append("bridge")
            bridge_sync()

    class _Alerts:
        def on_bar(self, strategy):
            order.append("alerts")

    r = live_runner.LiveRunner.__new__(live_runner.LiveRunner)
    r.ledger = _Ledger()
    r.bridge = _Bridge()
    r.setup_alerts = _Alerts()
    r.strategy = object()
    r.log = _Log()
    r._drain_records = lambda: None
    return r, order


class _Ps:
    dec = sig = seq = None


def test_the_alert_is_written_AFTER_the_broker_has_been_asked():
    """🔴 The whole reason the size can exist. The message says an order EXISTS AT THE BROKER, so
    it has to be composed after the order has been placed — before, it was a prediction, and the
    strategy it read from sizes in ounces and cannot know a lot count.

    MUTATION: put the alert call back above `bridge.sync` and this reddens.
    """
    r, order = _runner_with(lambda: None)
    r._settle_primary(_Ps())
    assert order == ["ledger", "bridge", "alerts"]


def test_a_BROKER_FAILURE_still_lets_the_signals_channel_speak():
    """🔴 The property the old ordering bought, KEPT by `finally` rather than by sequence. A bare
    reorder would let an MT5 wobble silence the channel — trading one defect for a quieter one,
    which is the worse direction every time.

    MUTATION: drop the `try/finally` and this reddens — the exception escapes before the alert.
    """
    import pytest

    def _boom():
        raise RuntimeError("MT5 went away")

    r, order = _runner_with(_boom)
    with pytest.raises(RuntimeError):
        r._settle_primary(_Ps())
    assert order == ["ledger", "bridge", "alerts"]


def test_the_bridge_failure_is_NOT_swallowed():
    """The alert firing must not mask the bridge's exception — the bar stream break that follows
    is how a broken bridge gets noticed at all."""
    import pytest

    r, _order = _runner_with(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        r._settle_primary(_Ps())
