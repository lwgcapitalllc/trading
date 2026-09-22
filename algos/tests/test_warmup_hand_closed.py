"""A replayed copy of a trade the owner already closed is dropped, never waited out (2026-09-17).

**The failure these pin.** A warm-up rebuilds the strategy's position from bars, and bars know
nothing about a hand close. So a restart — or any re-warm after a feed gap, a link outage or a
settings edit — ended holding a copy of a trade that no longer existed, and the bot sat in
WARMING placing nothing until that copy's own exit, up to 36 hours. Live on 2026-09-17:
`sos_fade_demo` and `sos_fade_1` after the 04:01 UTC promote.

The ledger here is the REAL `Ledger` writing real files, so nothing answers that production
cannot. The two restart rows are copied byte-for-byte from the box's own ledger for that day.

RED before the fix: both "drops" tests fail (the bridge sat in WARMING with no close requested).
MUTATION: `_warmup_trade_already_closed` returns None -> the same two go red; ignoring the
direction, the price or the open time each turns one mismatch case red.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_LIVE = _HERE.parent / "live"
_SHARED = _HERE.parent / "shared"
for _p in (str(_HERE), str(_LIVE), str(_SHARED)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bridge as live_bridge  # noqa: E402
from ledger import Ledger  # noqa: E402
from test_live_bridge import (  # noqa: E402
    _bridge,
    _closed_by_hand,
    _Dec,
    _FakeExecution,
    _Pend,
    _Sig,
)

# The two rows on the box for sos_fade_demo, 2026-09-17, as written (read-only copy).
_BOX_OPENED = {
    "ts": "2026-09-17T01:40:07+00:00",
    "bot": "sos_fade_demo",
    "kind": "trade",
    "event": "opened",
    "ticket": 364105022,
    "dir": "SHORT",
    "symbol": "XAUUSD.p",
    "intent": "primary",
    "lots": 0.14,
    "price": 4316.98,
    "intended_price": 4316.981400000001,
    "slippage": -0.0014000000010128133,
    "stop": 4352.44,
    "tp1": 0.0,
    "tp2": 0.0,
    "risk_pct": 5.0,
}  # noqa: E501
_BOX_CLOSED = {
    "ts": "2026-09-17T04:17:22+00:00",
    "bot": "sos_fade_demo",
    "kind": "trade",
    "event": "closed",
    "ticket": 364105022,
    "dir": "SHORT",
    "symbol": "XAUUSD.p",
    "intent": "primary",
    "lots": 0.14,
    "price": 4286.84,
    "pnl_usd": 421.68,
    "entry_price": 4316.98,
    "intended_price": 4316.98,
    "r": 0.8494,
    "reason": "closed_by_you",
    "held_bars": None,
    "booked_after_the_fact": True,
    "closed_at": "2026-09-17T03:19:43+00:00",
}  # noqa: E501

# The 15-minute bar the replay says the short filled on (01:30 UTC; the broker fill was 01:40).
_ENTRY_BAR_MS = int(datetime(2026, 9, 17, 1, 30, tzinfo=timezone.utc).timestamp() * 1000)


def _box_ledger(tmp_path, rows):
    d = tmp_path / "ledger"
    d.mkdir()
    with (d / "decisions-2026-09-17.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return Ledger(d, "sos_fade_demo")


def _replay_holding(direction=-1, entry=4316.9814, entry_ms=_ENTRY_BAR_MS):
    ex = _FakeExecution(pos_dir=direction)
    ex._entry, ex._entry_ms = entry, entry_ms
    return ex


def _restart(tmp_path, rows, **replay):
    ex = _replay_holding(**replay)
    b, ops, ledger, _n = _bridge(ex, ledger=_box_ledger(tmp_path, rows))
    b.state = live_bridge.BridgeState.LIVE
    b.begin_live()
    return b, ops, ex


def _dropped(tmp_path) -> bool:
    text = "".join(p.read_text() for p in (tmp_path / "ledger").glob("decisions-*.jsonl"))
    return "warmup_position_dropped" in text


def test_restart_after_a_hand_close_drops_the_copy_and_trades(tmp_path):
    b, ops, ex = _restart(tmp_path, [_BOX_OPENED, _BOX_CLOSED])
    assert ex.close_requested == live_bridge.MANUAL_CLOSE_REASON
    assert _dropped(tmp_path)
    assert ops.actions == [], "nothing is opened"

    ex._pos_dir = 0  # the strategy's own close fills on its next bar
    ex._pend_long = _Pend(1, 4200.0, 14.0, 4180.0)
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE
    assert any(a[0] == "place" for a in ops.actions), "it trades again"


def test_restart_with_no_closed_row_still_waits(tmp_path):
    b, ops, ex = _restart(tmp_path, [_BOX_OPENED])
    assert b.state is live_bridge.BridgeState.WARMING
    assert ex.close_requested is None and not _dropped(tmp_path)


@pytest.mark.parametrize(
    "replay",
    [
        {"entry": 4316.50},  # a different trade's price
        {"direction": 1},  # a long, and the closed trade was a short
        {"entry_ms": _ENTRY_BAR_MS + 3_600_000},  # replay entered AFTER the real trade opened
        {"entry_ms": 0},  # the strategy cannot say when it entered: unknown is no match
    ],
)
def test_a_mismatched_replay_still_waits(tmp_path, replay):
    b, _ops, ex = _restart(tmp_path, [_BOX_OPENED, _BOX_CLOSED], **replay)
    assert b.state is live_bridge.BridgeState.WARMING
    assert ex.close_requested is None


def test_an_unreadable_ledger_still_waits(tmp_path):
    b, _ops, ex = _restart(tmp_path, [_BOX_OPENED, _BOX_CLOSED])
    ex2 = _replay_holding()
    b._ex = ex2
    b._ledger.trade_rows_since = lambda since_ms: None
    b.begin_live()
    assert b.state is live_bridge.BridgeState.WARMING and ex2.close_requested is None


def test_a_hand_close_in_session_then_a_rewarm_stays_flat(tmp_path):
    """The in-session path books the close, the strategy drops its copy a bar later — and a
    re-warm after a feed gap, which replays the same trade back into a FRESH strategy, drops it
    again from the row the in-session close wrote."""
    d = tmp_path / "ledger"
    ledger = Ledger(d, "bot")
    ex = _FakeExecution(pend_short=_Pend(-1, 4316.98, 14.0, 4352.44))
    b, ops, _l, _n = _bridge(ex, ledger=ledger, instance_dir=tmp_path)
    entry_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - 3_600_000
    # Reuse the shared setup's shape: rest, fill, hold.
    b.sync(_Dec(), _Sig())
    from test_live_bridge import _Pos

    ticket = ops.orders[0].ticket
    ops.positions = [_Pos(ticket, 1, 4316.98, 0.14, 4352.44)]
    ex._pos_dir, ex._pend_short, ex._entry, ex._entry_ms = -1, None, 4316.98, entry_ms
    ex.snapshot = {"_stage": 0}
    b.sync(_Dec(stop=4352.44), _Sig())
    _closed_by_hand(ops)
    b.sync(_Dec(stop=4352.44), _Sig())
    assert ex.close_requested == live_bridge.MANUAL_CLOSE_REASON
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE and b.is_flat

    # a feed gap: the runner stages, rebuilds the strategy (the replay holds the trade again)
    b.stage_rewarm()
    fresh = _replay_holding(entry=4316.98, entry_ms=entry_ms)
    b._ex = fresh
    b.apply_restore()
    b.begin_live()
    assert fresh.close_requested == live_bridge.MANUAL_CLOSE_REASON
    fresh._pos_dir = 0
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE
    assert b.state is not live_bridge.BridgeState.HALTED


# ── no closed row, but the BROKER says the trade is over (2026-09-22) ─────────
#
# The live case: the fill clock halted on a hand close before the 15-minute clock could book it,
# so the ledger holds the `opened` row and no `closed` row. Every restart then rebuilt the short
# and waited up to 36 hours for a copy of a trade the broker had already closed.
#
# RED before: the first test sat in WARMING with no close requested.
# MUTATION: skip the broker fallback in `_warmup_trade_already_closed` -> the first goes red;
# drop the size check -> the partial case goes red; drop the open-position check -> the
# still-open case goes red.


def _restart_asking_broker(tmp_path, origin, positions=()):
    ex = _replay_holding()
    b, ops, _ledger, _n = _bridge(ex, ledger=_box_ledger(tmp_path, [_BOX_OPENED]))
    ops.origin = origin
    ops.positions = list(positions)
    b.state = live_bridge.BridgeState.LIVE
    b.begin_live()
    return b, ops, ex


def test_no_closed_row_but_the_broker_shows_it_fully_closed_drops_the_copy(tmp_path):
    b, ops, ex = _restart_asking_broker(tmp_path, {"opened": 0.14, "closed": {0: 0.14}})
    assert ex.close_requested == live_bridge.MANUAL_CLOSE_REASON
    assert _dropped(tmp_path)
    assert ops.actions == [], "nothing is opened"
    assert b.state is live_bridge.BridgeState.WARMING  # goes LIVE when the strategy is flat


@pytest.mark.parametrize(
    "origin",
    [
        None,  # history could not be read
        {"opened": 0.14, "closed": {}},  # read, and no closing deal
        {"opened": 0.14, "closed": {0: 0.07}},  # only part of it closed
        {"opened": 0.0, "closed": {0: 0.14}},  # no opening deal found: deals do not add up
    ],
)
def test_no_closed_row_and_the_broker_cannot_prove_it_closed_still_waits(tmp_path, origin):
    b, _ops, ex = _restart_asking_broker(tmp_path, origin)
    assert b.state is live_bridge.BridgeState.WARMING
    assert ex.close_requested is None and not _dropped(tmp_path)


def test_no_closed_row_and_the_ticket_is_still_open_at_the_broker_still_waits(tmp_path):
    from test_live_bridge import _Pos

    b, _ops, ex = _restart_asking_broker(
        tmp_path,
        {"opened": 0.14, "closed": {0: 0.14}},
        positions=[_Pos(364105022, 1, 4316.98, 0.14, 4352.44)],
    )
    assert ex.close_requested is None and not _dropped(tmp_path)
