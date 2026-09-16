"""Tests for `algos/live/setup_alerts.py` — the pre-trade signals channel.

Weighted toward the ways this layer wrongly says NOTHING, because that is how it fails: a notifier
with nothing to send looks exactly like a market with nothing happening. Same reasoning as
`test_log_review.py` and `test_deadman.py`.

Every test here was watched RED against a deliberate break of the behaviour it names.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import alerts  # noqa: E402
from setup_alerts import (
    BLOCKED_MSG,
    CATEGORIES,
    ENTRY_ZONE_MSG,  # noqa: E402
    RESOLVED_MSG,
    WATCHING_MSG,
    SetupAlerts,
)

from backtest.setups import (
    DEAD,
    FILLED,
    RESTING,  # noqa: E402
    WATCHING,
    Confluence,
    SetupSnapshot,
)


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
    base = dict(
        key="K1",
        strategy="Strat",
        symbol="XAUUSD",
        side=1,
        state=WATCHING,
        confluences=(
            Confluence("Arm", True, "Day Low"),
            Confluence("SOS", True, "confirmed"),
            Confluence("Zone", False, "not tagged yet"),
        ),
        zone=(100.0, 90.0),
        stop=89.5,
    )
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
    assert rec.heads().count("🎯 BUY LIMIT RESTING") == 1


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
    assert rec.heads() == ["👀 SETUP FORMING · LONG", "🎯 BUY LIMIT RESTING"]
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
    assert rec.heads() == ["🎯 BUY LIMIT RESTING"]


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
        icons = {
            "👀": WATCHING_MSG,
            "🎯": ENTRY_ZONE_MSG,
            "🚫": BLOCKED_MSG,
            "✅": RESOLVED_MSG,
            "👋": RESOLVED_MSG,
        }
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
    a.on_bar(Exploding())  # must not raise
    assert warnings and "boom" in warnings[0]


def test_a_send_that_fails_does_not_stop_the_remaining_messages():
    """Telegram returning None (a deleted reply target, a 4xx) must cost that message and no more.

    RED against letting a None message id short-circuit the rest of `_handle`.
    """

    def dead_send(text, kind, reply_to=None):
        return None

    a = SetupAlerts(send=dead_send, log=None)
    a._handle(_snap(state=RESTING, entry=95.0, blocked_by=("Veto",)))  # must not raise
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


# ── surviving a restart — the 2026-09-15 four-identical-alerts defect ────────────────────────
#
# MEASURED on `sos_fade_1`: one long setup produced four identical `SETUP FORMING` roots inside
# 24 hours, and none of the first three could ever be closed. Two independent causes, one symptom,
# and each test below pins one of them.


def test_a_restart_does_NOT_re_announce_a_setup_the_reader_was_already_told_about(tmp_path):
    """The whole point. Before persistence, `_sent` lived in memory only, so every stop, start,
    redeploy or mid-session re-warm announced every open setup again from scratch.

    RED without the state file: the second instance posts a second SETUP FORMING.
    """
    state = tmp_path / "setup_threads.json"
    rec = Recorder()
    first = _alerts(rec, state_path=state)
    first.on_bar(FakeStrategy([[_snap()]]))
    assert [h.split(" · ")[0] for h in rec.heads()] == ["👀 SETUP FORMING"]

    rec2 = Recorder()
    second = _alerts(rec2, state_path=state)
    second.on_bar(FakeStrategy([[_snap()]]))
    assert rec2.sent == [], "the setup was announced a second time across a restart"


def test_the_outcome_after_a_restart_REPLIES_TO_THE_ORIGINAL_message(tmp_path):
    """A resolution that does not reply to the root is a message with no setup attached — the
    reader sees `NO TRADE` in a channel and has to guess which of five setups it closed.

    RED without persisting the message id: `reply_to` comes back None.
    """
    state = tmp_path / "setup_threads.json"
    rec = Recorder()
    _alerts(rec, state_path=state).on_bar(FakeStrategy([[_snap()]]))
    root_id = 1  # Recorder returns ascending ids, and the root was the first message sent

    rec2 = Recorder()
    _alerts(rec2, state_path=state).on_bar(
        FakeStrategy(
            [[_snap(state=DEAD, reason="The setup died before reaching two confluences.")]]
        )
    )
    assert len(rec2.sent) == 1
    assert rec2.sent[0]["reply_to"] == root_id


def test_a_thread_whose_outcome_was_LOST_is_closed_WITHOUT_claiming_an_outcome(tmp_path):
    """The bot was down while the setup resolved, so the strategy's own sentence for it no longer
    exists. The thread must still be closed — but it must NOT say NO TRADE, which is a claim that
    the bot looked at this setup and refused it. It might have traded.

    RED if `reconcile` reuses `format_resolved`: the message reads `👋 NO TRADE`.
    """
    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = _alerts(rec2, state_path=state)
    a.reconcile([], live_keys=[])  # warmed, watching nothing, and it CAN say so
    assert len(rec2.sent) == 1
    text = rec2.sent[0]["text"]
    assert "NO TRADE" not in text
    assert "not recorded" in text
    assert a.open_keys() == []


def test_a_thread_whose_outcome_WAS_replayed_carries_the_strategys_OWN_reason(tmp_path):
    """When the warm-up did replay the death, the reader gets the real reason rather than the
    "outcome not recorded" fallback.

    RED if `reconcile` ignores the replayed snapshots and closes everything as lost.
    """
    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = _alerts(rec2, state_path=state)
    a.reconcile([_snap(state=DEAD, reason="Nothing came to the limit.")], live_keys=[])
    assert len(rec2.sent) == 1
    assert "Nothing came to the limit." in rec2.sent[0]["text"]
    assert a.open_keys() == []


def test_CANNOT_ASK_leaves_every_thread_open_where_WATCHING_NOTHING_closes_them(tmp_path):
    """🔴 Root `CLAUDE.md` rule 1, in the signals channel. `None` means the strategy could not be
    asked which setups are open; `[]` means it was asked and is watching none. Collapsing them
    posts "no longer being watched" onto setups the bot is watching right now.

    RED on `live_keys = live_keys or []`, and on any other collapse of the two.

    ⚠ **Silence is asserted to be DELIBERATE, not incidental.** An early version of this test
    passed against a mutation that fed `None` straight into `set()`: the resulting TypeError was
    swallowed by the never-raises guard, so nothing was sent and the test went green for a reason
    that had nothing to do with the rule it names. The log is checked for exactly that.
    """
    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = SetupAlerts(send=rec2, log=Log(), state_path=state)
    a.reconcile([], live_keys=None)
    assert rec2.sent == []
    assert a.open_keys() == ["K1"]
    assert warnings == [], f"the thread survived by accident, not by rule: {warnings}"


def test_a_still_live_setup_is_NOT_closed_by_the_reconcile(tmp_path):
    """The common case on every restart: the setup is still forming. It keeps its thread and says
    nothing, so the reader is not told about it twice or told it is over.
    """
    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = _alerts(rec2, state_path=state)
    a.reconcile([], live_keys=["K1"])
    assert rec2.sent == []
    assert a.open_keys() == ["K1"]


def test_a_still_live_setup_IN_THE_WARM_UP_DRAIN_is_NOT_answered_NO_TRADE(tmp_path):
    """🔴 The real shape of a restart. The warm-up drain is `live_setups()` in full, so a setup
    still being watched arrives in `resolved` as a WATCHING snapshot AND in `live_keys`.

    MEASURED 2026-09-16: the demo bot restarted at 18:41 UTC with a short open, posted
    `👋 NO TRADE · SHORT` with no reason, then placed that short at 18:45. The test above passes
    `resolved=[]`, which the runner never sends — a fixture kinder than production (rule 13).

    RED against the pre-fix `reconcile`: one `NO TRADE` is sent and the thread is dropped.
    """
    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = _alerts(rec2, state_path=state)
    a.reconcile([_snap()], live_keys=["K1"])
    assert rec2.sent == []
    assert a.open_keys() == ["K1"]


def test_a_NON_TERMINAL_snapshot_is_never_read_as_an_outcome_even_if_not_live(tmp_path):
    """A watching snapshot is not an outcome whatever `live_keys` says. With nothing live the
    thread is closed as LOST — never as a refusal the strategy did not make.

    RED against the pre-fix `reconcile`: the message reads `👋 NO TRADE`.
    """
    state = tmp_path / "setup_threads.json"
    _alerts(Recorder(), state_path=state).on_bar(FakeStrategy([[_snap()]]))

    rec2 = Recorder()
    a = _alerts(rec2, state_path=state)
    a.reconcile([_snap()], live_keys=[])
    assert [m["text"].split(" · ")[0] for m in rec2.sent] == ["🧹 THREAD CLOSED"]


def test_NO_TRADE_always_says_why():
    """A refusal with no sentence is what the reader got on 2026-09-16. RED without the fallback."""
    text = alerts.format_resolved(_snap(state=DEAD, reason=""))
    assert text.startswith("👋 NO TRADE")
    assert len(text.splitlines()) == 2


def test_format_resolved_REFUSES_a_setup_that_has_not_ended():
    """RED if a watching setup can be rendered as NO TRADE."""
    import pytest

    with pytest.raises(ValueError):
        alerts.format_resolved(_snap())


def test_a_corrupt_state_file_costs_the_dedupe_and_NOTHING_ELSE(tmp_path):
    """A process killed mid-write leaves truncated JSON. That must degrade to the old behaviour —
    announce once more — never raise into the bar loop.
    """
    state = tmp_path / "setup_threads.json"
    state.write_text('{"setups": {"K1": {"root": 1, "se')
    rec = Recorder()
    a = _alerts(rec, state_path=state)
    a.on_bar(FakeStrategy([[_snap()]]))
    assert [h.split(" · ")[0] for h in rec.heads()] == ["👀 SETUP FORMING"]


def test_a_caller_with_NO_state_path_behaves_exactly_as_before(tmp_path):
    """`alert_rate.py` and every backtest construct this with nowhere to write. They must not
    acquire a file, and must not fail for the want of one.
    """
    rec = Recorder()
    a = _alerts(rec)
    a.on_bar(FakeStrategy([[_snap()]]))
    a.reconcile([], live_keys=[])
    assert list(tmp_path.iterdir()) == [], "a stateless caller must not acquire a file"
    # The in-memory bookkeeping is still there and still correct, so the reconcile closes the
    # thread exactly as it would with a file. Persistence changes what survives a RESTART; it
    # changes nothing inside one process.
    assert [m["text"].split(" · ")[0] for m in rec.sent] == ["👀 SETUP FORMING", "🧹 THREAD CLOSED"]


def test_threads_are_DROPPED_when_the_bot_moves_to_another_TELEGRAM_CHAT(tmp_path):
    """🔴 A Telegram message id means something only inside ONE chat. A bot moved to another
    account sends its signals to that account's channel — `sos_fade_2` was moved exactly that way
    on 2026-09-15 — so every stored id would then point at a message in a chat this bot no longer
    writes to, and the reader would get a resolution with no setup attached.

    RED without the channel fingerprint: the thread is carried into the new room and the reply
    targets a foreign message id.
    """
    warnings = []

    class Log:
        def warning(self, m):
            warnings.append(m)

    state = tmp_path / "setup_threads.json"
    SetupAlerts(send=Recorder(), log=None, state_path=state, channel="room-A").on_bar(
        FakeStrategy([[_snap()]])
    )

    rec2 = Recorder()
    moved = SetupAlerts(send=rec2, log=Log(), state_path=state, channel="room-B")
    assert moved.open_keys() == []
    assert warnings and "signals channel changed" in warnings[0]
    moved.on_bar(FakeStrategy([[_snap()]]))
    assert [m["text"].split(" · ")[0] for m in rec2.sent] == ["👀 SETUP FORMING"]
    assert rec2.sent[0]["reply_to"] is None


def test_the_SAME_chat_still_carries_its_threads(tmp_path):
    """The control for the test above — the fingerprint must not throw threads away on every
    ordinary restart, which would silently restore the bug it was added to prevent."""
    state = tmp_path / "setup_threads.json"
    SetupAlerts(send=Recorder(), log=None, state_path=state, channel="room-A").on_bar(
        FakeStrategy([[_snap()]])
    )
    rec2 = Recorder()
    again = SetupAlerts(send=rec2, log=None, state_path=state, channel="room-A")
    assert again.open_keys() == ["K1"]
    again.on_bar(FakeStrategy([[_snap()]]))
    assert rec2.sent == []


# ── the thread follows the order the broker ACTUALLY holds (Aaron, 2026-09-16) ────────────────
class Broker:
    """What `bridge.resting_order` answers: the order held per side, or None."""

    def __init__(self):
        self.held = {}

    def __call__(self, side):
        return self.held.get(side)


def _resting(**kw):
    base = dict(state=RESTING, entry=100.0, stop=89.5, side=-1)
    base.update(kw)
    return _snap(**base)


def _texts(rec):
    return [m["text"] for m in rec.sent]


def test_a_RE_PLACED_order_is_reported_with_the_BROKERS_new_price_and_lots():
    """MEASURED 2026-09-16: the demo short was cancelled and re-placed 4,324.14 → 4,316.98 at a
    new size, and the thread still showed the first order. RED before `_follow_order`: no reply.
    """
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.25)
    a._handle(_resting())
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.22)
    a._handle(_resting(entry=4316.98))
    assert [h.split("\n")[0] for h in _texts(rec)][-1] == "🔁 SELL LIMIT MOVED"
    moved = _texts(rec)[-1]
    assert "0.25 → 0.22 lots" in moved
    assert "4,324.14 → 4,316.98" in moved
    assert "4,355.55 → 4,352.44" in moved
    assert all(m["reply_to"] == 1 for m in rec.sent[1:])


def test_an_UNCHANGED_order_posts_nothing_however_many_bars_it_rests():
    """The volume guard. Drift below display precision is not a change. RED on comparing raw
    floats."""
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.25)
    a._handle(_resting())
    for i in range(10):
        broker.held[-1] = alerts.RestingOrder(4324.14 + i * 1e-4, 4355.5477, 0.25)
        a._handle(_resting())
    assert len(rec.sent) == 2  # root + the one resting message


def test_a_PULLED_order_is_SILENT_and_its_replacement_reads_as_a_move():
    """MEASURED 2026-09-16 on the live bot: a re-size cancelled the order, the new one was
    rejected, and nothing rested for 15 minutes. Aaron wants no cancel message — only the new
    price once it is placed, compared against the order the thread last showed.
    RED if a cancel is posted, or if the replacement is compared against nothing.
    """
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.16)
    a._handle(_resting())
    broker.held.pop(-1)
    a._handle(_resting())
    a._handle(_resting(state=WATCHING, entry=None))
    assert len(rec.sent) == 2
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.14)
    a._handle(_resting(entry=4316.98))
    heads = [t.split("\n")[0] for t in _texts(rec)]
    assert heads[1:] == ["🎯 0.16 lots · SELL LIMIT RESTING", "🔁 SELL LIMIT MOVED"]
    assert "0.16 → 0.14 lots" in _texts(rec)[-1]


def test_a_replacement_at_the_SAME_price_and_size_says_nothing():
    """A promote cancels and re-places the identical order. Nothing changed for the reader."""
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.16)
    a._handle(_resting())
    broker.held.pop(-1)
    a._handle(_resting())
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.16)
    a._handle(_resting())
    assert len(rec.sent) == 2


def test_the_last_DESCRIBED_order_survives_a_restart(tmp_path):
    """A promote cancels the order and the new process re-places it. Without persisting what the
    thread last said, the new price is never reported. RED if `order` is not saved."""
    state = tmp_path / "setup_threads.json"
    broker = Broker()
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.25)
    _alerts(Recorder(), order_for=broker, state_path=state)._handle(_resting())

    rec2 = Recorder()
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.22)
    _alerts(rec2, order_for=broker, state_path=state)._handle(_resting(entry=4316.98))
    assert len(rec2.sent) == 1
    assert "0.25 → 0.22 lots" in rec2.sent[0]["text"]


def test_a_fill_after_a_move_closes_the_thread_with_no_stale_numbers():
    """The ENTERED reply names no price or size, so it cannot contradict the order that filled."""
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4324.14, 4355.55, 0.25)
    a._handle(_resting())
    broker.held.pop(-1)
    a._handle(_resting(state=FILLED, reason="Entered."))
    last = _texts(rec)[-1]
    assert last.startswith("✅ ENTERED")
    assert "4,324" not in last and "0.25" not in last
    assert a.open_keys() == []


# ── a promote that changes how setups are NAMED (2026-09-16, sos_fade_demo, 20:17 UTC) ────────
def _legacy_state(state, key="Strat:S:5018", side=-1):
    """What a bot on the OLD naming wrote: a thread keyed by bar POSITION, and no scheme."""
    old = _alerts(Recorder(), state_path=state)
    old.on_bar(FakeStrategy([[_snap(key=key, side=side)]]))
    return old


def test_a_thread_named_under_an_OLDER_key_scheme_is_CARRIED_onto_the_setup_still_being_watched(
    tmp_path,
):
    """🔴 The incident. The running bot keyed the short by bar number (`...:S:5018`); the promote
    renamed setups by time (`...:S:t1789581600000`). The restart warm-up still watched the setup,
    but no stored key matched, so it posted THREAD CLOSED on a live short — and would announce it
    again as a brand-new setup on the next bar.

    RED without the scheme check: a THREAD CLOSED is sent and the thread is gone.
    """
    state = tmp_path / "setup_threads.json"
    _legacy_state(state)

    rec = Recorder()
    a = _alerts(rec, state_path=state, key_scheme="time-v1")
    live = [_snap(key="Strat:S:t1789581600000", side=-1)]
    a.reconcile([], live_keys=[s.key for s in live], live=live)
    assert rec.sent == [], "a setup the strategy still watches was announced as lost"
    assert a.open_keys() == ["Strat:S:t1789581600000"]

    # ...and the thread is the SAME thread: no second root on the next bar, the outcome replies
    # to the original message, and the adoption survives another restart.
    again = _alerts(rec, state_path=state, key_scheme="time-v1")
    again.on_bar(FakeStrategy([live]))
    assert rec.sent == []
    again.on_bar(FakeStrategy([[_snap(key=live[0].key, side=-1, state=DEAD, reason="Aged out.")]]))
    assert len(rec.sent) == 1 and rec.sent[0]["reply_to"] == 1


def test_under_the_SAME_scheme_an_unmatched_thread_is_never_adopted(tmp_path):
    """Adoption is a migration, not a guess made on every start. With the naming unchanged, a
    stored key the strategy no longer reports really is gone. RED if adoption ignores the scheme.
    """
    state = tmp_path / "setup_threads.json"
    old = _alerts(Recorder(), state_path=state, key_scheme="time-v1")
    old.on_bar(FakeStrategy([[_snap(key="Strat:S:t1", side=-1)]]))

    rec = Recorder()
    a = _alerts(rec, state_path=state, key_scheme="time-v1")
    live = [_snap(key="Strat:S:t2", side=-1)]
    a.reconcile([], live_keys=[live[0].key], live=live)
    assert [h.split(" · ")[0] for h in rec.heads()] == ["🧹 THREAD CLOSED"]
    assert a.open_keys() == []


def test_an_AMBIGUOUS_old_thread_is_closed_rather_than_pinned_on_the_wrong_setup(tmp_path):
    """Two old threads on one side and one live setup: which is it? Nobody can say, so neither
    is adopted. RED if the first match wins."""
    state = tmp_path / "setup_threads.json"
    old = _alerts(Recorder(), state_path=state)
    old.on_bar(FakeStrategy([[_snap(key="Strat:S:1", side=-1), _snap(key="Strat:S:2", side=-1)]]))

    rec = Recorder()
    a = _alerts(rec, state_path=state, key_scheme="time-v1")
    live = [_snap(key="Strat:S:t9", side=-1)]
    a.reconcile([], live_keys=[live[0].key], live=live)
    assert len(rec.sent) == 2
    assert a.open_keys() == []


def test_an_old_thread_is_not_adopted_by_a_setup_on_the_OTHER_side(tmp_path):
    state = tmp_path / "setup_threads.json"
    _legacy_state(state, side=-1)
    rec = Recorder()
    a = _alerts(rec, state_path=state, key_scheme="time-v1")
    live = [_snap(key="Strat:L:t9", side=1)]
    a.reconcile([], live_keys=[live[0].key], live=live)
    assert len(rec.sent) == 1 and a.open_keys() == []


# ── an order the STRATEGY withdrew while the setup lives on ─────────────────────────────────
def test_an_order_WITHDRAWN_by_a_rule_says_so_ONCE_with_the_rule():
    """🔴 2026-09-16 20:15 UTC: the final-hour rule pulled the resting sell limit and the setup
    went back to watching. The thread still read "SELL LIMIT RESTING" — an order the account no
    longer held. A pull the strategy gives a reason for is not the silent cancel-and-replace
    churn; it is one message. RED without the pause path: nothing is posted.
    """
    rec, broker = Recorder(), Broker()
    a = _alerts(rec, order_for=broker)
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.14)
    a._handle(_resting())
    broker.held.pop(-1)
    held = ("Final hour (16:00-18:00 New York)",)
    for _ in range(3):
        a._handle(_resting(state=WATCHING, entry=None, paused_by=held))
    heads = [t.split("\n")[0] for t in _texts(rec)]
    assert heads[2:] == ["⏸ SELL LIMIT WITHDRAWN"]
    assert "Final hour" in _texts(rec)[2]
    assert rec.sent[2]["reply_to"] == 1

    # It comes back at the SAME price: the reader was told it is gone, so they are told it is back.
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.14)
    a._handle(_resting(entry=4316.98))
    assert len(rec.sent) == 4
    assert _texts(rec)[3].startswith("🔁 SELL LIMIT MOVED")


def test_a_withdrawal_state_survives_a_restart(tmp_path):
    """RED if the pause is kept in memory only: the restarted bot would say nothing when the
    identical order returns, leaving WITHDRAWN as the thread's last word on a live order."""
    state = tmp_path / "setup_threads.json"
    broker = Broker()
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.14)
    a = _alerts(Recorder(), order_for=broker, state_path=state)
    a._handle(_resting())
    broker.held.pop(-1)
    a._handle(_resting(state=WATCHING, entry=None, paused_by=("Final hour",)))

    rec = Recorder()
    broker.held[-1] = alerts.RestingOrder(4316.98, 4352.44, 0.14)
    _alerts(rec, order_for=broker, state_path=state)._handle(_resting(entry=4316.98))
    assert len(rec.sent) == 1 and rec.sent[0]["text"].startswith("🔁 SELL LIMIT MOVED")


def test_a_withdrawal_before_any_order_was_announced_says_nothing():
    """No resting message was ever sent, so there is nothing to take back."""
    rec = Recorder()
    a = _alerts(rec, order_for=Broker())
    a._handle(_snap(side=-1, paused_by=("Final hour",)))
    assert len(rec.sent) == 1
