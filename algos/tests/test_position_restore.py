"""A restart with a trade open picks the trade back up — or halts, exactly as it used to.

**The failure these pin.** Before this, `adopt_broker_state` halted on ANY position MT5 already
held and the runner exited (code 4). A bot that restarted overnight with a trade open therefore
left it with whatever stop it had at the moment the process died: the broker-side stop stood, so
it was never naked, but nothing ratcheted it again and the time stop never fired. Aaron's words:
*"this is crucial because this can happen when I go to bed."*

**What is being guarded is the NARROWNESS, not the restore.** The restore is one path; the halt
is still every other path, and most of these tests are about a halt. A bug that made the bridge
adopt a position it could not prove was its own would double a book, which is strictly worse than
the problem being fixed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LIVE = _HERE.parent / "live"
_SHARED = _HERE.parent / "shared"
# `_HERE` so the fakes in `test_live_bridge` can be reused rather than re-written. Two hand-built
# copies of one broker fake is two chances for one of them to describe a shape MT5 never sends.
for _p in (str(_HERE), str(_LIVE), str(_SHARED)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridge as live_bridge  # noqa: E402
import position_state  # noqa: E402
from test_live_bridge import (  # noqa: E402
    _bridge,
    _FakeExecution,
    _FakeMt5Ops,
    _Pos,
)

# The emulator state a real record carries. Opaque to `position_state` and to the bridge by
# design — only `Execution.restore_position` reads it — so a fake one is honest here.
_SNAP = {"_pos_dir": 1, "_stage": 1, "_max_fav": 3301.5}


def _record(
    tmp_path,
    *,
    ticket=901,
    direction=1,
    lots=0.42,
    entry=3290.0,
    stop=3280.0,
    magic=770115,
    symbol="XAUUSD",
    strategy=None,
):
    position_state.write(
        tmp_path,
        bot="BOT_TEST",
        symbol=symbol,
        magic=magic,
        ticket=ticket,
        broker=position_state.BrokerFacts(dir=direction, lots=lots, entry=entry, stop=stop),
        strategy=_SNAP if strategy is None else strategy,
    )


def _held(ticket=901, direction=1, lots=0.42, entry=3290.0, stop=3280.0):
    """One position, as MT5 reports it. `type` 0 = buy, 1 = sell."""
    return _Pos(ticket, 0 if direction > 0 else 1, entry, lots, stop)


def _startup(tmp_path, *, positions, execution=None):
    ops = _FakeMt5Ops()
    ops.positions = list(positions)
    b, ops, ledger, notes = _bridge(
        execution or _FakeExecution(), mt5ops=ops, instance_dir=tmp_path
    )
    b.adopt_broker_state()
    return b, ops, ledger, notes


# ── the file itself ──────────────────────────────────────────────────────────


def test_a_record_round_trips(tmp_path):
    _record(tmp_path)
    got = position_state.read(tmp_path)
    assert got is not None
    assert got.ticket == 901
    assert got.broker.dir == 1 and got.broker.lots == 0.42
    assert got.broker.entry == 3290.0 and got.broker.stop == 3280.0
    assert got.strategy == _SNAP


def test_a_torn_record_reads_as_NO_record_not_as_a_best_effort(tmp_path):
    """Corrupt and absent must be the SAME answer, because the caller's response to both is to
    halt. A partial parse here would hand the emulator a position with fields it invented."""
    _record(tmp_path)
    position_state.path_for(tmp_path).write_text(
        '{"version": 1, "broker": {"dir": 1', encoding="utf-8"
    )
    assert position_state.read(tmp_path) is None


def test_a_record_from_an_unknown_version_reads_as_NO_record(tmp_path):
    """A bot that has just been upgraded must halt on the old position and let a human look, not
    carry on against fields whose meaning it is guessing."""
    _record(tmp_path)
    raw = json.loads(position_state.path_for(tmp_path).read_text())
    raw["version"] = position_state.VERSION + 1
    position_state.path_for(tmp_path).write_text(json.dumps(raw), encoding="utf-8")
    assert position_state.read(tmp_path) is None


def test_a_record_missing_a_broker_field_reads_as_NO_record(tmp_path):
    _record(tmp_path)
    raw = json.loads(position_state.path_for(tmp_path).read_text())
    del raw["broker"]["stop"]
    position_state.path_for(tmp_path).write_text(json.dumps(raw), encoding="utf-8")
    assert position_state.read(tmp_path) is None


def test_no_file_at_all_reads_as_None(tmp_path):
    assert position_state.read(tmp_path) is None


def test_clear_removes_it_and_is_safe_to_call_twice(tmp_path):
    _record(tmp_path)
    position_state.clear(tmp_path)
    position_state.clear(tmp_path)
    assert position_state.read(tmp_path) is None


def test_writing_leaves_no_temp_file_behind(tmp_path):
    """The write is temp-file-then-replace so a process dying mid-write cannot leave a half
    record. A stray `.tmp` would be read by nothing, but it is the visible symptom of the
    atomicity being broken, so it is asserted."""
    _record(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [position_state.FILENAME]


# ── the comparison ───────────────────────────────────────────────────────────


def test_a_price_difference_below_one_point_is_not_a_disagreement(tmp_path):
    """MT5 rounds to the symbol's digits and a float round-trip through JSON is not bit-exact, so
    an equality test would halt on every ordinary restart and the feature would be switched off
    inside a week. One point is below the smallest move the broker can quote."""
    _record(tmp_path, stop=3280.0)
    rec = position_state.read(tmp_path)
    assert position_state.disagreements(rec, _held(stop=3280.000004), point=0.01) == []


def test_a_moved_stop_IS_a_disagreement_and_says_both_numbers(tmp_path):
    _record(tmp_path, stop=3280.0)
    rec = position_state.read(tmp_path)
    diffs = position_state.disagreements(rec, _held(stop=3285.0), point=0.01)
    assert len(diffs) == 1
    assert "3280.0" in diffs[0] and "3285.0" in diffs[0]


def test_a_flipped_direction_IS_a_disagreement(tmp_path):
    _record(tmp_path, direction=1)
    rec = position_state.read(tmp_path)
    assert any(
        "direction" in d for d in position_state.disagreements(rec, _held(direction=-1), point=0.01)
    )


def test_a_different_size_IS_a_disagreement(tmp_path):
    _record(tmp_path, lots=0.42)
    rec = position_state.read(tmp_path)
    assert any("size" in d for d in position_state.disagreements(rec, _held(lots=0.84), point=0.01))


# ── the bridge, at startup ───────────────────────────────────────────────────


def test_a_matching_record_is_staged_rather_than_halted(tmp_path):
    _record(tmp_path)
    b, _, _, _ = _startup(tmp_path, positions=[_held()])
    assert b.state is not live_bridge.BridgeState.HALTED
    assert b._pending_restore == _SNAP
    assert b._pos_ticket == 901


def test_it_is_NOT_applied_until_after_the_warmup(tmp_path):
    """⚠ The ordering is the whole reason `apply_restore` is a second method. `warm()` replays
    ~5,000 bars through this same emulator and opens imaginary trades of its own, so anything
    written before it is overwritten by a fiction."""
    _record(tmp_path)
    ex = _FakeExecution()
    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=ex)
    assert getattr(ex, "restored", None) is None, (
        "adopt_broker_state must not touch the emulator — the warm-up has not run yet"
    )


def test_apply_restore_hands_it_to_the_strategy_and_goes_LIVE(tmp_path):
    _record(tmp_path)
    ex = _FakeExecution()
    b, _, ledger, _ = _startup(tmp_path, positions=[_held()], execution=ex)
    assert b.apply_restore() is True
    assert ex.restored == _SNAP
    b.begin_live()
    assert b.state is live_bridge.BridgeState.LIVE, (
        "a restored position is a real fill this bot made, not a warm-up artefact — WARMING here "
        "would reproduce the very failure the restore exists to end"
    )
    assert any(r[0] == "event:position_restored" for r in ledger.rows)


def test_a_restored_bot_announces_it_once(tmp_path):
    _record(tmp_path)
    b, _, _, notes = _startup(tmp_path, positions=[_held()], execution=_FakeExecution())
    b.apply_restore()
    assert any("TRADE RESUMED" in n for n in notes)


# ── a restart must not move the trade onto the other clock (2026-09-02) ───────
#
# 🔴 **THE FIELD THAT DID NOT COME BACK.** Which leg opened a trade is stamped at the FILL, and
# construction defaults it to the primary — so a restart holding a RE-ENTRY picked it back up as
# a primary. Everything else about the trade restored perfectly. It was unreachable until the
# blanket re-entry refusal was lifted on the same day, which is why it had never bitten.
#
# ⚠ **The emulator was never the problem** — the real `Execution` carries `_entry_kind` in its
# `_POSITION_FIELDS` and restores it. The bridge simply did not ask.


def _reentry_snap():
    """A record of a trade the RE-ENTRY opened. Same shape as `_SNAP`, one field different."""
    return {**_SNAP, "_entry_kind": "secondary"}


def test_a_restored_RE_ENTRY_comes_back_on_the_FILL_clock_not_the_15_minute_one(tmp_path):
    """MUTATION: delete the `_pos_intent` line in `apply_restore` and this goes red — the trade
    comes back as a primary and the 15-minute clock books its close."""
    _record(tmp_path, strategy=_reentry_snap())
    ex = _FakeExecution()
    b, _, ledger, _ = _startup(tmp_path, positions=[_held()], execution=ex)

    assert b._pos_intent == "primary", "the default before anything is restored"
    assert b.apply_restore() is True
    assert b._pos_intent == "secondary"

    row = next(kw for kind, kw in ledger.rows if kind == "event:position_restored")
    assert row["intent"] == "secondary", "a person reading the record must see which clock has it"


def test_the_15_minute_clock_does_not_BOOK_a_restored_re_entrys_close(tmp_path):
    """The consequence, not the field — a hold length is an index into ONE clock's bar numbering
    and these two frames differ by 3x, so the wrong clock books the trade in the wrong frame and
    every alert and ledger row goes with it.

    MUTATION: same one line. Without it this books a closed trade on the 15-minute path.
    """
    _record(tmp_path, strategy=_reentry_snap())
    b, _, ledger, _ = _startup(tmp_path, positions=[_held()], execution=_FakeExecution())
    b.apply_restore()
    b.begin_live()

    # The broker no longer holds it. On the 15-MINUTE path, which does not own this trade.
    b._observe_close([], _Dec(), _Sig(), owner="primary")
    assert not any(kind == "closed" for kind, _ in ledger.rows), (
        "the fill clock opened this trade and books it; the 15-minute clock must sit out"
    )


def test_a_restored_PRIMARY_still_comes_back_on_the_15_minute_clock(tmp_path):
    """⚠ The other half, and it is not decoration: a fix that hands EVERY restored trade to the
    fill clock would pass the two tests above and break every bot in this repo."""
    _record(tmp_path)  # `_SNAP` carries no leg field at all — an older record
    ex = _FakeExecution(entry_kind="primary")
    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=ex)
    assert b.apply_restore() is True
    assert b._pos_intent == "primary"


# ── every other shape still halts ────────────────────────────────────────────


def test_no_record_halts(tmp_path):
    b, _, _, _ = _startup(tmp_path, positions=[_held()])
    assert b.state is live_bridge.BridgeState.HALTED
    assert "no usable record" in b.halt_reason


def test_a_ticket_that_does_not_match_halts_and_names_both(tmp_path):
    """The identity check. Anything else open under this magic is not the trade we wrote down,
    whatever else agrees about it."""
    _record(tmp_path, ticket=901)
    b, _, _, _ = _startup(tmp_path, positions=[_held(ticket=902)])
    assert b.state is live_bridge.BridgeState.HALTED
    assert "T902" in b.halt_reason and "T901" in b.halt_reason


def test_a_stop_moved_by_hand_halts_rather_than_being_adopted(tmp_path):
    """The judgement this encodes: a stop that differs means something moved it that this system
    does not know about, and the bot cannot tell a hand edit from a bug. Adopting the broker's
    number would compute every later ratchet off a level the strategy never chose."""
    _record(tmp_path, stop=3280.0)
    b, _, _, _ = _startup(tmp_path, positions=[_held(stop=3285.0)])
    assert b.state is live_bridge.BridgeState.HALTED
    assert "3280.0" in b.halt_reason and "3285.0" in b.halt_reason
    assert "NOT be adopted" in b.halt_reason


def test_a_record_for_a_different_bot_halts(tmp_path):
    """A record naming another magic describes another bot's trade. Reading it would be this
    repo's own doubled-book failure arriving through a stray file."""
    _record(tmp_path, magic=770999)
    b, _, _, _ = _startup(tmp_path, positions=[_held()])
    assert b.state is live_bridge.BridgeState.HALTED
    assert "770999" in b.halt_reason


def test_two_positions_halt_whatever_the_record_says(tmp_path):
    """One position slot, so no single record can describe two. It is also the shape a duplicate
    process leaves behind, and that must never be quietly absorbed."""
    _record(tmp_path)
    b, _, _, _ = _startup(tmp_path, positions=[_held(901), _held(902)])
    assert b.state is live_bridge.BridgeState.HALTED
    assert "one at a time" in b.halt_reason


def test_a_bridge_with_no_instance_directory_halts(tmp_path):
    """It cannot look, so it cannot prove anything — and *cannot ask* is never *it is fine*."""
    ops = _FakeMt5Ops()
    ops.positions = [_held()]
    b, _, _, _ = _bridge(_FakeExecution(), mt5ops=ops, instance_dir=None)
    b.adopt_broker_state()
    assert b.state is live_bridge.BridgeState.HALTED


def test_a_strategy_that_refuses_the_record_halts_rather_than_running_on(tmp_path):
    """It got past every broker check and the emulator still would not take it — which means the
    record was written by a different build of the strategy. Same answer as an unreadable record,
    for the same reason."""
    _record(tmp_path)
    ex = _FakeExecution()

    def _boom(snap):
        raise ValueError("missing: _stage")

    ex.restore_position = _boom

    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=ex)
    assert b.apply_restore() is False
    assert b.state is live_bridge.BridgeState.HALTED
    assert "_stage" in b.halt_reason


# ── writing it, over the trade's life ────────────────────────────────────────


def test_the_record_is_cleared_when_the_trade_closes(tmp_path):
    """A record naming a dead ticket cannot restore anything, but it would sit in the instance
    directory describing a trade that is over."""
    _record(tmp_path)
    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=_FakeExecution())
    b.apply_restore()
    assert position_state.read(tmp_path) is not None

    b._observe_close([], _Dec(), _Sig())
    assert position_state.read(tmp_path) is None
    assert b._restored is False


class _Dec:
    l_stage = s_stage = 0
    long_edge = short_edge = long_veto = short_veto = None
    tp1 = tp2 = 0.0
    stop = 0.0
    fills: list = []


class _Sig:
    time_ms = 1_754_000_900_000
    index = 12
    high = low = close = 3290.0
    bull_div_active = bear_div_active = False
    recent_ssl = recent_bsl = None
    ny_hour = 9


# ── carrying it across a re-warm ─────────────────────────────────────────────


def test_a_rewarm_carries_the_open_position_across_the_rebuild(tmp_path):
    """🔴 The more likely door onto the same failure than a process restart. `_recover_link` and
    the `gap > 4` branch both rebuild the strategy and replay through a FRESH emulator — so a
    link outage while a trade was open (MetaTrader auto-updated under the bot for 50 minutes on
    2026-08-04) left the broker holding a position the emulator knew nothing about, and the
    bridge halted on the next bar. The bot survived the outage and was stopped by its recovery."""
    _record(tmp_path)
    old = _FakeExecution()
    old.snapshot = dict(_SNAP)
    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=old)
    b.apply_restore()

    b.stage_rewarm()
    fresh = _FakeExecution()  # what `_build_strategy` hands back
    b._ex = fresh
    assert b.apply_restore(announce=False) is True
    assert fresh.restored == _SNAP


def test_a_rewarm_while_FLAT_carries_nothing(tmp_path):
    b, _, _, _ = _startup(tmp_path, positions=[])
    b.stage_rewarm()
    assert b._pending_restore is None
    assert b.apply_restore() is False


def test_a_rewarm_does_not_send_a_second_alert(tmp_path):
    """`_recover_link` and the gap branch each already send their own message for the same event,
    and two alerts for one event is how a channel gets muted. The LEDGER still carries it."""
    _record(tmp_path)
    ex = _FakeExecution()
    ex.snapshot = dict(_SNAP)
    b, _, ledger, notes = _startup(tmp_path, positions=[_held()], execution=ex)
    b.apply_restore()
    notes.clear()

    b.stage_rewarm()
    b._ex = _FakeExecution()
    b.apply_restore(announce=False)

    assert not any("TRADE RESUMED" in n for n in notes)
    assert sum(1 for r in ledger.rows if r[0] == "event:position_restored") == 2


def test_a_snapshot_that_raises_during_a_rewarm_does_not_halt(tmp_path):
    """Halting here would stop a bot that is still perfectly coherent — the re-warm has not
    happened yet. `_agrees` halts on the next bar if the position really is lost, which is the
    existing and already-tested path."""
    _record(tmp_path)
    ex = _FakeExecution()

    def _boom():
        raise RuntimeError("nope")

    ex.snapshot_position = _boom

    b, _, _, _ = _startup(tmp_path, positions=[_held()], execution=ex)
    b._pending_restore = None
    b.stage_rewarm()
    assert b._pending_restore is None
    assert b.state is not live_bridge.BridgeState.HALTED
