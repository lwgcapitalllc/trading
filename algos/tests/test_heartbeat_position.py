"""The heartbeat says what the bot holds at the broker, and why it halted (2026-09-12).

Two tags on the Command Center's bot row read these, and before this date neither could exist:
the row said RUNNING through every halt (the hourly review chip was the only sign, up to an hour
late), and nothing said a bot was holding a trade at all. Promised to Aaron as a tag reading
"LONG 0.40 lots · +1.2R".

What is pinned is mostly what the tags must NOT claim: flat and could-not-ask are different
answers (rule 1); an R needs the risk the trade OPENED with, never one off a stop that has moved;
and nothing here may cost the heartbeat stamp the watchdog runs on.
"""

import sys
import time
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _p in (str(_HERE), str(_REPO), str(_REPO / "algos" / "live")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bridge import BridgeState  # noqa: E402
from runner import position_summary  # noqa: E402

# The link tests' runner and state doubles, reused rather than re-written: two hand-built copies of
# one fake are two chances for one of them to describe a runner that does not exist.
from test_mt5_link import _Bridge, _live, _runner, _StateModule  # noqa: E402


def _pos(ticket, *, side=1, lots=0.40, entry=3290.0, sl=3280.0, profit=84.2, swap=-1.2):
    """One position as MT5 reports it. `type` 0 = buy, 1 = sell; `sl` 0.0 = no stop."""
    return SimpleNamespace(
        ticket=ticket,
        type=0 if side > 0 else 1,
        volume=lots,
        price_open=entry,
        sl=sl,
        profit=profit,
        swap=swap,
        magic=770115,
    )


# ── the summary ─────────────────────────────────────────────────────────────


def test_flat_is_None_not_an_empty_summary():
    assert position_summary([]) is None


def test_one_trade_reads_its_side_size_entry_stop_and_R():
    """R = the open profit after swap over the risk the trade OPENED with: (84.20 − 1.20) / 70."""
    got = position_summary([_pos(901)], risk_ticket=901, risk_usd=70.0)
    assert got == {
        "side": "long",
        "lots": 0.4,
        "entry": 3290.0,
        "stop": 3280.0,
        "profit_usd": 83.0,
        "risk_usd": 70.0,
        "r": 1.19,
        "tickets": 1,
    }


def test_a_short_reads_as_short():
    assert position_summary([_pos(901, side=-1)])["side"] == "short"


def test_scale_in_lots_add_up_and_the_trade_keeps_its_own_stop_and_risk():
    """On a hedging account each add is its own ticket. The tag describes the whole position: the
    lots summed, the entry their volume-weighted average, the profit all of them — and the stop and
    the R off the TRADE, which is the bridge's own ticket, not whichever position is listed first.

    MUTATION: take the entry off one ticket → red. MUTATION: take the stop off the first listed
    position → red (the add is listed first here, on purpose).
    """
    base = _pos(901, lots=0.40, entry=3290.0, sl=3280.0, profit=80.0, swap=0.0)
    add = _pos(907, lots=0.20, entry=3296.0, sl=3285.0, profit=28.0, swap=0.0)
    got = position_summary([add, base], risk_ticket=901, risk_usd=70.0)
    assert (got["lots"], got["tickets"], got["entry"]) == (0.6, 2, 3292.0)
    assert (got["profit_usd"], got["r"]) == (108.0, round(108.0 / 70.0, 2))
    assert got["stop"] == 3280.0


def test_R_needs_the_bridges_own_ticket_among_the_positions():
    """The opening risk belongs to ONE trade. A position the bridge has not adopted yet (the bar
    after a fill) is divided by nothing — its profit is still reported.

    MUTATION: accept any ticket → red.
    """
    got = position_summary([_pos(901)], risk_ticket=555, risk_usd=70.0)
    assert (got["r"], got["risk_usd"], got["profit_usd"]) == (None, None, 83.0)


def test_R_is_unknown_when_the_opening_risk_was_not_recorded():
    """`0.0` is the bridge's own "unknown" for that field, and a restore from a record written
    before 2026-09-12 leaves it there. No R — never one off the stop, which has usually moved."""
    for risk in (0.0, None):
        assert position_summary([_pos(901)], risk_ticket=901, risk_usd=risk)["r"] is None


def test_positions_on_both_sides_read_as_mixed_with_no_R():
    """The bridge halts on this. Netting them would describe a hedge as a smaller trade.

    MUTATION: read the side off one position → red.
    """
    got = position_summary([_pos(901), _pos(902, side=-1)], risk_ticket=901, risk_usd=70.0)
    assert (got["side"], got["r"], got["lots"]) == ("mixed", None, 0.8)


def test_a_position_that_reports_no_profit_has_no_profit_and_no_R():
    """0 would be the claim "nothing made or lost"; a position without the field made no claim.

    MUTATION: read a missing profit as 0 → red.
    """
    bare = SimpleNamespace(ticket=901, type=0, volume=0.4, price_open=3290.0, sl=3280.0)
    got = position_summary([bare], risk_ticket=901, risk_usd=70.0)
    assert (got["profit_usd"], got["r"]) == (None, None)


def test_a_position_with_no_stop_says_so_rather_than_a_price_of_zero():
    """MT5 reports 0.0 for a position with no stop, which is not a price.

    MUTATION: pass the 0.0 through → red.
    """
    assert position_summary([_pos(901, sl=0.0)])["stop"] is None


# ── the heartbeat ───────────────────────────────────────────────────────────


def _held_runner(monkeypatch, positions):
    """A runner whose broker answers `positions` (or raises it), holding ticket 901 at $70 risk."""
    r = _runner(monkeypatch, account_info=_live())
    calls = []

    def _read():
        calls.append(1)
        if isinstance(positions, Exception):
            raise positions
        return positions

    r.mt5 = SimpleNamespace(open_positions_strict=_read)
    r.bridge._pos_ticket = 901
    r.bridge._pos_risk_usd = 70.0
    return r, calls


def _beat(r, *, link_up=True):
    st = _StateModule()
    r._heartbeat(st, link_up=link_up, balance=2000.0 if link_up else None)
    return st.written["bot"]


def test_the_heartbeat_carries_the_trade_the_broker_holds(monkeypatch):
    written = _beat(_held_runner(monkeypatch, [_pos(901)])[0])
    assert written["in_trade"] is True
    assert (written["position"]["side"], written["position"]["r"]) == ("long", 1.19)


def test_flat_and_could_not_ask_are_different_answers(monkeypatch):
    """Rule 1. `False` is the broker saying nothing is open; `None` is nobody being able to ask.

    MUTATION: read an unreadable book as flat → red.
    """
    written = _beat(_held_runner(monkeypatch, [])[0])
    assert (written["in_trade"], written["position"]) == (False, None)

    written = _beat(_held_runner(monkeypatch, None)[0])
    assert (written["in_trade"], written["position"]) == (None, None)


def test_a_blind_bot_is_not_asked(monkeypatch):
    """With the link down the answer would describe a terminal nobody can reach.

    MUTATION: drop the link check → red (the read is made).
    """
    r, calls = _held_runner(monkeypatch, [_pos(901)])
    written = _beat(r, link_up=False)
    assert written["in_trade"] is None
    assert calls == []


def test_a_read_that_raises_never_costs_the_heartbeat(monkeypatch):
    """The stamp is what the watchdog runs on; a display field must never be able to cost it."""
    written = _beat(_held_runner(monkeypatch, RuntimeError("IPC recv failed"))[0])
    assert written["in_trade"] is None
    assert abs(written["heartbeat"] - time.time()) < 5


def test_positions_that_cannot_be_summarised_are_still_held(monkeypatch):
    """The broker answered that something is open; only the detail is unknown.

    MUTATION: report a failed summary as could-not-ask → red.
    """
    written = _beat(_held_runner(monkeypatch, [SimpleNamespace(ticket=901)])[0])
    assert (written["in_trade"], written["position"]) == (True, None)


def test_the_heartbeat_names_a_halt_and_only_a_halt(monkeypatch):
    """`status` in the state file carries two vocabularies — the watchdog writes running /
    stalled / stopped / offline into it — so the bridge's state gets a key of its own, and a
    reason rides with it only while halted: beside a live bot it would read as a current fault.

    MUTATION: write the reason whatever the state → red.
    """
    r = _runner(monkeypatch, account_info=_live())
    r.bridge = _Bridge(state=BridgeState.HALTED)
    written = _beat(r)
    assert (written["bridge_state"], written["halt_reason"]) == ("halted", "test halt")

    r.bridge = _Bridge()
    r.bridge.halt_reason = "an old reason nobody cleared"
    written = _beat(r)
    assert (written["bridge_state"], written["halt_reason"]) == ("live", None)
