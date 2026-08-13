"""Tests for `algos/live/setup_alerts.py` — the pre-trade signals channel.

Weighted toward the ways this layer wrongly says NOTHING, because that is how it fails: a notifier
with nothing to send looks exactly like a market with nothing happening. Same reasoning as
`test_log_review.py` and `test_deadman.py`.

Every test here was watched RED against a deliberate break of the behaviour it names.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from backtest.setups import (Confluence, DEAD, FILLED, RESTING,  # noqa: E402
                             SetupSnapshot, WATCHING)
from setup_alerts import (BLOCKED_MSG, CATEGORIES, ENTRY_ZONE_MSG,  # noqa: E402
                          RESOLVED_MSG, SetupAlerts, WATCHING_MSG)


class Recorder:
    """Stands in for `runner._notify`, returning ascending message ids like Telegram does."""

    def __init__(self):
        self.sent = []

    def __call__(self, text, kind, reply_to=None):
        self.sent.append({"text": text, "kind": kind, "reply_to": reply_to})
        return len(self.sent)

    def heads(self):
        return [m["text"].split("\n")[0] for m in self.sent]


class FakeStrategy:
    """A strategy that implements the contract. `queue` is one list of snapshots per bar."""

    def __init__(self, queue):
        self._queue = list(queue)
        self.execution = self

    def live_setups(self):
        return self._queue[0] if self._queue else []

    def drain_setups(self):
        return self._queue.pop(0) if self._queue else []


def _snap(**kw):
    base = dict(key="K1", strategy="Strat", symbol="XAUUSD", side=1, state=WATCHING,
                confluences=(Confluence("Arm", True, "Day Low"),
                             Confluence("SOS", True, "confirmed"),
                             Confluence("Zone", False, "not tagged yet")),
                zone=(100.0, 90.0), stop=89.5)
    base.update(kw)
    return SetupSnapshot(**base)


def _alerts(rec, **kw):
    return SetupAlerts(send=rec, log=None, **kw)


# ── the dedupe, which is the measured failure this layer exists to prevent ───────────────────
def test_a_setup_is_announced_ONCE_however_many_bars_it_lives_for():
    """MEASURED: a resting limit is rebuilt every bar, and one setup produced 665 raw transitions
    across 332 setups over 6.5 years. A level-triggered alert fires every 15 minutes for the life
    of the setup.

    RED against dropping the `_sent` bookkeeping and sending on state alone.
    """
    rec = Recorder()
    a = _alerts(rec)
    for _ in range(20):
        a._handle(_snap())
    assert rec.heads().count("👀 SETUP FORMING · LONG") == 1


def test_the_resting_message_is_sent_once_even_if_the_order_flickers():
    """The exact measured shape: an order rests, is cancelled when the edge disappears, and rests
    again. That is ONE setup and must be ONE message.

    RED against edge-triggering on the raw `None -> _Pending` transition.
    """
    rec = Recorder()
    a = _alerts(rec)
    for state in (RESTING, WATCHING, RESTING, WATCHING, RESTING):
        a._handle(_snap(state=state, entry=95.0, targets=(92.0, 88.0)))
    assert rec.heads().count("🎯 ENTRY ZONE LIVE · LONG") == 1


# ── threading, so an outcome is never read apart from the setup it came from ─────────────────
def test_every_later_message_replies_to_the_setups_own_root():
    """RED against passing `reply_to=None` on the replies — the outcome would float loose in the
    group naming no setup."""
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap())
    a._handle(_snap(state=RESTING, entry=95.0))
    a._handle(_snap(state=DEAD, reason="Never filled."))
    root_id = 1
    assert rec.sent[0]["reply_to"] is None
    assert [m["reply_to"] for m in rec.sent[1:]] == [root_id, root_id]


def test_the_root_is_sent_first_even_when_a_setup_arrives_already_RESTING():
    """A fast leg can arm and reach its entry zone on ONE bar. Without this the reply would be
    sent with nothing to reply to and the thread would read backwards.

    RED against only sending the root when `state == WATCHING`.
    """
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap(state=RESTING, entry=95.0))
    assert rec.heads() == ["👀 SETUP FORMING · LONG", "🎯 ENTRY ZONE LIVE · LONG"]
    assert rec.sent[1]["reply_to"] == 1


def test_two_sides_of_one_bar_are_two_independent_threads():
    """RED against keying the bookkeeping on anything but the snapshot's own `key`."""
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap(key="L:7", side=1))
    a._handle(_snap(key="S:7", side=-1))
    assert rec.heads() == ["👀 SETUP FORMING · LONG", "👀 SETUP FORMING · SHORT"]
    assert [m["reply_to"] for m in rec.sent] == [None, None]


# ── cleanup, whose failure has no symptom for months ─────────────────────────────────────────
def test_a_resolved_setup_drops_its_bookkeeping():
    """A process meant to run for months cannot keep a dict entry per setup it has ever seen.

    RED against not popping `_threads` / `_sent` on a terminal state.
    """
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap())
    a._handle(_snap(state=FILLED, reason="Entered."))
    assert a._threads == {} and a._sent == {}


def test_a_resting_setup_does_NOT_drop_its_thread():
    """The mirror of the test above, and the reason `TERMINAL` is only FILLED and DEAD: dropping a
    resting setup's thread would leave its own fill message with nothing to reply to."""
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap(state=RESTING, entry=95.0))
    assert "K1" in a._threads


# ── blocked ──────────────────────────────────────────────────────────────────────────────────
def test_a_blocked_setup_is_reported_once_and_names_every_refusing_rule():
    """The Pine reports only the FIRST blocker because a chart tag has room for one line. A reader
    asking "is this rule earning its keep" needs the whole set.

    RED against sending only `blocked_by[0]`.
    """
    rec = Recorder()
    a = _alerts(rec)
    for _ in range(3):
        a._handle(_snap(blocked_by=("Veto", "Final hour")))
    blocked = [m for m in rec.sent if m["text"].startswith("🚫")]
    assert len(blocked) == 1
    assert "Veto" in blocked[0]["text"] and "Final hour" in blocked[0]["text"]


def test_a_setup_with_no_blocking_rule_sends_no_blocked_message():
    rec = Recorder()
    _alerts(rec)._handle(_snap())
    assert not [m for m in rec.sent if m["text"].startswith("🚫")]


# ── categories ───────────────────────────────────────────────────────────────────────────────
def test_a_switched_off_category_is_suppressed_while_the_others_still_send():
    """Turning one category off must not disturb the rest — in particular the root being off must
    not stop the replies, which then post standalone.

    ⚠ **This test does NOT prove the ordering of `sent.add` against the category check**, and an
    earlier version of this docstring claimed it did. Mutating the two lines to swap that order
    left every test green, because a suppressed category produces no observable difference either
    way: `_on` is False on every bar, so re-checking it costs nothing. The claim was removed
    rather than a test written to defend a mechanism that does not exist.

    RED against ignoring `categories` and always sending.
    """
    rec = Recorder()
    a = _alerts(rec, categories=(ENTRY_ZONE_MSG,))
    for _ in range(5):
        a._handle(_snap(state=RESTING, entry=95.0))
    assert rec.heads() == ["🎯 ENTRY ZONE LIVE · LONG"]


def test_an_unknown_category_name_is_dropped_rather_than_silently_enabling_everything():
    """Category names are a WIRE FORMAT — they live in instance configs. A typo must turn that one
    off, never turn all of them on."""
    rec = Recorder()
    a = _alerts(rec, categories=("watchign",))
    a._handle(_snap())
    assert rec.sent == []


def test_every_declared_category_is_reachable():
    """Guards against a category constant that no code path can ever send — the dead-label shape
    (root CLAUDE.md rule 7). Fails by NAME on whichever one is unreachable."""
    seen = set()
    for state, blocked in ((WATCHING, ()), (RESTING, ()), (WATCHING, ("Veto",)), (FILLED, ())):
        rec = Recorder()
        a = _alerts(rec)
        a._handle(_snap(state=state, blocked_by=blocked, entry=95.0))
        icons = {"👀": WATCHING_MSG, "🎯": ENTRY_ZONE_MSG, "🚫": BLOCKED_MSG, "✅": RESOLVED_MSG,
                 "👋": RESOLVED_MSG}
        seen |= {icons[m["text"][0]] for m in rec.sent}
    assert seen == set(CATEGORIES), f"unreachable categories: {sorted(set(CATEGORIES) - seen)}"


# ── tradeable: only signal what the bot could actually take ──────────────────────────────────
def test_a_setup_the_bot_cannot_take_is_never_announced():
    """Aaron, 2026-08-13: *"I should only be getting signals for the trades originating from my
    default settings."* A signal for a trade the bot has already refused is a label with no code
    behind it, pointed at a human who might act on it.

    RED against dropping the `tradeable` guard.
    """
    rec = Recorder()
    a = _alerts(rec)
    for state in (WATCHING, RESTING, DEAD):
        a._handle(_snap(state=state, tradeable=False, entry=95.0, reason="x"))
    assert rec.sent == []


def test_an_untradeable_setup_leaves_NO_bookkeeping_behind():
    """The guard runs before `_sent.setdefault`, so a suppressed setup must not occupy a slot in
    either dict — otherwise a strategy that reports a setup as untradeable and then tradeable
    would find its root already marked sent and go silent for good.

    RED against checking `tradeable` after the bookkeeping is created.
    """
    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap(tradeable=False))
    assert a._sent == {} and a._threads == {}
    a._handle(_snap(tradeable=True))
    assert rec.heads() == ["👀 SETUP FORMING · LONG"]


def test_tradeable_defaults_TRUE_so_a_strategy_that_says_nothing_is_still_heard():
    """Defaulting to False would silently mute every strategy that has not been taught the field.
    An opt-out must be explicit."""
    rec = Recorder()
    _alerts(rec)._handle(_snap())
    assert len(rec.sent) == 1


# ── the absence rule: cannot-ask must never look like nothing-to-say ─────────────────────────
def test_a_strategy_without_the_contract_is_REPORTED_by_name_not_silently_skipped():
    """🔴 Three separate jobs in this repo ran for weeks against an empty registry and reported
    success. `_drain` must return None — not `[]` — and say so once.

    RED against returning `[]` for an unsupported strategy.
    """

    class NoContract:
        def __init__(self):
            self.execution = self

    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    a = SetupAlerts(send=Recorder(), log=Log())
    assert a._drain(NoContract()) is None
    assert len(warnings) == 1 and "NoContract" in warnings[0]
    assert "cannot report" in warnings[0]


def test_the_unsupported_warning_is_sent_ONCE_not_on_every_bar():
    """A bar-rate warning is a log nobody reads. RED against dropping `_unsupported_reported`."""

    class NoContract:
        def __init__(self):
            self.execution = self

    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    a = SetupAlerts(send=Recorder(), log=Log())
    for _ in range(50):
        a.on_bar(NoContract())
    assert len(warnings) == 1


def test_a_strategy_watching_NOTHING_is_not_the_same_as_one_that_cannot_be_ASKED():
    """`[]` and `None` must stay distinguishable all the way up. This is root CLAUDE.md rule 1 one
    layer above the terminal probe that made it a rule."""
    a = SetupAlerts(send=Recorder(), log=None)
    assert a._drain(FakeStrategy([[]])) == []


def test_supported_reads_through_to_the_execution_object():
    a = SetupAlerts(send=Recorder(), log=None)
    assert a.supported(FakeStrategy([[]])) is True


# ── never raise: this runs inside the live bar loop ──────────────────────────────────────────
def test_a_formatter_that_explodes_cannot_take_down_the_bar_loop():
    """🔴 `on_bar` runs between the strategy stepping and the broker being reconciled. A notifier
    that can stop a trading loop is worse than a missed message.

    RED against removing the `except` in `on_bar`.
    """
    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    class Exploding:
        def __init__(self):
            self.execution = self

        def live_setups(self):
            raise RuntimeError("boom")

        def drain_setups(self):
            raise RuntimeError("boom")

    a = SetupAlerts(send=Recorder(), log=Log())
    a.on_bar(Exploding())            # must not raise
    assert warnings and "boom" in warnings[0]


def test_a_send_that_fails_does_not_stop_the_remaining_messages():
    """Telegram returning None (a deleted reply target, a 4xx) must cost that message and no more.

    RED against letting a None message id short-circuit the rest of `_handle`.
    """
    def dead_send(text, kind, reply_to=None):
        return None

    a = SetupAlerts(send=dead_send, log=None)
    a._handle(_snap(state=RESTING, entry=95.0, blocked_by=("Veto",)))   # must not raise
    assert a._threads["K1"] is None


def test_a_strategy_with_live_setups_but_no_drain_is_WARNED_about():
    """Without `drain_setups` the resolved snapshots repeat for the life of the process. It still
    works, so this must not refuse — but it must not be silent either."""

    class NoDrain:
        def __init__(self):
            self.execution = self

        def live_setups(self):
            return []

    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    a = SetupAlerts(send=Recorder(), log=Log())
    assert a._drain(NoDrain()) == []
    assert warnings and "drain_setups" in warnings[0]


# ── routing ──────────────────────────────────────────────────────────────────────────────────
def test_every_message_goes_out_as_SIGNAL_kind():
    """A pre-trade setup must never land in the room that carries fills — `algos/CLAUDE.md` →
    *Two rooms*. RED against passing TRADE or HEALTH here."""
    from notify import SIGNAL

    rec = Recorder()
    a = _alerts(rec)
    a._handle(_snap(state=RESTING, entry=95.0, blocked_by=("Veto",)))
    a._handle(_snap(state=DEAD, reason="died"))
    assert {m["kind"] for m in rec.sent} == {SIGNAL}
    assert SIGNAL not in ("trade", "health")
