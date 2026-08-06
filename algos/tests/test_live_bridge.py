"""The order bridge — strategy intent mirrored onto MT5.

These tests pin the DECISIONS, not the wire format: what the bridge chooses to place, move,
cancel or refuse given a strategy state and a broker state. That is where every bug in this
layer lives, and none of it needs a terminal.

The two behaviours worth reading first:
  * a real emulator-vs-broker disagreement HALTS the bot rather than continuing on a fiction;
  * a size change is a CANCEL + RE-PLACE, because MT5's MODIFY silently ignores volume.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

_LIVE = Path(__file__).resolve().parent.parent / "live"
sys.path.insert(0, str(_LIVE))
import bridge as live_bridge  # noqa: E402


# ── fakes ─────────────────────────────────────────────────────────────────────
@dataclass
class _Pend:
    dir: int
    edge: float
    qty: float
    sl: float
    tp1: float = 0.0
    tp2: float = 0.0
    sos_bar: int = 7


class _Pos:
    def __init__(self, ticket, type_, price_open, volume, sl):
        self.ticket, self.type = ticket, type_
        self.price_open, self.volume, self.sl = price_open, volume, sl


class _Order:
    def __init__(self, ticket):
        self.ticket = ticket


class _FakeMt5Ops:
    symbol = "XAUUSD"
    magic = 770115
    bot_label = "BOT_TEST"

    def __init__(self):
        self.positions: list = []
        self.orders: list = []
        self.actions: list = []
        self._ticket = 900
        self.deal = (0.0, 0.0)

    def get_open_positions(self, symbol=None):
        return list(self.positions)

    def get_pending_orders(self, symbol=None):
        return list(self.orders)

    def normalize_volume(self, lots, symbol=None):
        v = int(lots / 0.01 + 1e-9) * 0.01
        return round(v, 2) if v >= 0.01 else 0.0

    def place_pending_limit(self, direction, lots, price, sl, tp=0.0, comment="", symbol=None):
        self._ticket += 1
        self.actions.append(("place", direction, lots, price, sl))
        return self._ticket, price

    def modify_pending(self, ticket, price, sl, tp=0.0, symbol=None):
        self.actions.append(("modify", ticket, price, sl))
        return True

    def cancel_pending(self, ticket):
        self.actions.append(("cancel", ticket))
        return True

    def move_sl(self, ticket, new_sl, tp=None):
        self.actions.append(("move_sl", ticket, new_sl))
        return True

    def get_deal_result(self, ticket):
        return self.deal

    def disconnect(self):
        pass


class _FakeExecution:
    def __init__(self, pos_dir=0, pend_long=None, pend_short=None):
        self._pos_dir = pos_dir
        self._pend_long = pend_long
        self._pend_short = pend_short
        self._entry = 0.0
        self.blocks: list = []
        self.misses: list = []


class _Dec:
    def __init__(self, stop=None, **kw):
        self.stop = stop
        self.l_stage = kw.get("l_stage", 0)
        self.s_stage = kw.get("s_stage", 0)
        self.long_edge = kw.get("long_edge")
        self.short_edge = kw.get("short_edge")
        self.long_veto = kw.get("long_veto", False)
        self.short_veto = kw.get("short_veto", False)
        self.tp1 = kw.get("tp1", 0.0)
        self.tp2 = kw.get("tp2", 0.0)


class _Sig:
    index = 42
    time_ms = 1_780_000_000_000
    close = 3300.0
    ny_hour = 9
    bull_div_active = False
    bear_div_active = False
    recent_ssl = ""
    recent_bsl = ""


class _FakeLedger:
    def __init__(self):
        self.rows: list = []

    def _rec(self, kind, **kw):
        self.rows.append((kind, kw))

    def event(self, name, **kw):
        self._rec("event:" + name, **kw)

    def trade_opened(self, **kw):
        self._rec("opened", **kw)

    def trade_closed(self, **kw):
        self._rec("closed", **kw)

    def bar(self, *a, **k):
        pass

    def kinds(self):
        return [k for k, _ in self.rows]


class _Log:
    def __init__(self):
        self.lines = []

    def _rec(self, m):
        self.lines.append(str(m))

    info = warning = error = _rec


@pytest.fixture(autouse=True)
def _stub_mt5(monkeypatch):
    """`_moved` and `_contract_size` reach for MetaTrader5. Stub it so the tick size and
    contract size are the real gold ones rather than the fallbacks."""
    m = types.ModuleType("MetaTrader5")

    class _SI:
        point = 0.01
        trade_contract_size = 100.0

    m.symbol_info = lambda s: _SI()
    monkeypatch.setitem(sys.modules, "MetaTrader5", m)


def _bridge(execution, *, dry_run=False, mt5ops=None, ledger=None, notes=None, kinds=None):
    mt5ops = mt5ops or _FakeMt5Ops()
    ledger = ledger or _FakeLedger()
    notes = notes if notes is not None else []
    kinds = kinds if kinds is not None else []

    def _notify(text, kind, reply_to=None):
        """Mirrors the real signature: a routing KIND, an optional reply target, and back comes a
        message id. The id is what a trade's EXIT replies to, so a fake that returned None would
        quietly test the no-thread path and never the one that runs.

        `kind` is positional and required here on purpose — a fake that defaulted it would go on
        passing after a call site stopped stating one, which is the whole thing the routing exists
        to make impossible. `kinds` records them so a test can assert WHERE a message went."""
        notes.append(text)
        kinds.append(kind)
        return len(notes)

    b = live_bridge.OrderBridge(mt5ops, execution, ledger, _Log(),
                                notify=_notify, dry_run=dry_run)
    b.state = live_bridge.BridgeState.LIVE
    return b, mt5ops, ledger, notes


# ── configuration guards ──────────────────────────────────────────────────────
def test_partial_take_profits_are_refused_not_ignored():
    """The bridge places one entry and one stop. A configured scale-out that silently never
    happens would make the live curve diverge from every backtest with nothing to point at."""
    cfg = types.SimpleNamespace(exec_tp1_pct=30.0, exec_tp2_pct=40.0,
                                exec_secondary=False, fill_model="bar")
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="partial take-profits"):
        live_bridge.assert_supported(cfg)


def test_tick_fill_model_is_refused():
    cfg = types.SimpleNamespace(exec_tp1_pct=0, exec_tp2_pct=0,
                                exec_secondary=False, fill_model="tick")
    with pytest.raises(live_bridge.UnsupportedStrategyConfig, match="BACKTEST cost model"):
        live_bridge.assert_supported(cfg)


def test_the_shipped_config_is_supported():
    cfg = types.SimpleNamespace(exec_tp1_pct=0.0, exec_tp2_pct=0.0,
                                exec_secondary=False, fill_model="bar")
    live_bridge.assert_supported(cfg)          # no raise


# ── placing and maintaining a resting limit ───────────────────────────────────
def test_a_strategy_limit_becomes_a_broker_limit():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]
    assert "event:order_placed" in ledger.kinds()


def test_an_unchanged_limit_is_left_alone():
    """Re-writing an identical order every bar is churn the broker sees as flapping — and it
    resets the order's queue position for nothing."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == []


def test_a_moved_limit_is_modified_in_place():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3292.5, 0.42, 3282.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("modify", 901, 3292.5, 3282.0)]


def test_a_resized_limit_is_cancelled_and_replaced():
    """MT5's MODIFY ignores volume. Sizing moves with equity every bar, so getting this wrong
    means the position size silently freezes at whatever it was when the order was first
    placed."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3290.0, 0.55, 3280.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["cancel", "place"]
    assert ops.actions[-1][2] == 0.55


def test_a_withdrawn_setup_cancels_the_order():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = None
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("cancel", 901)]


def test_a_sub_minimum_size_is_recorded_rather_than_rounded_up():
    """The account is too small for this stop distance. Placing the broker minimum instead
    would be a bigger bet than the strategy risk-checked — and it would look like a normal
    trade afterwards. Recorded so the missing trade is countable."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.004, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:order_too_small" in ledger.kinds()


# ── an open position ──────────────────────────────────────────────────────────
def test_the_stop_is_ratcheted_to_the_strategys_current_stop():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, 0.42, 3280.0)]
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, _ = _bridge(ex, mt5ops=ops)
    b.sync(_Dec(stop=3285.0), _Sig())
    assert ("move_sl", 555, 3285.0) in ops.actions
    assert "event:stop_moved" in ledger.kinds()


def test_an_unchanged_stop_is_not_rewritten():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(555, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(pos_dir=1), mt5ops=ops)
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(a[0] == "move_sl" for a in ops.actions)


def test_opening_a_position_reports_the_brokers_real_fill():
    """The strategy's intended limit and the broker's fill are BOTH recorded — the gap between
    them is the only honest measure of live execution quality, and it is invisible if only one
    is kept."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())                                    # places the limit
    ops.positions = [_Pos(901, 0, 3289.7, 0.42, 3280.0)]      # ...it fills, 30c better
    ex._pos_dir, ex._pend_long = 1, None
    b.sync(_Dec(stop=3280.0), _Sig())

    opened = [kw for k, kw in ledger.rows if k == "opened"][0]
    assert opened["price"] == 3289.7          # what the broker gave
    assert opened["intended_price"] == 3290.0  # where the strategy rested its limit
    assert notes and "ENTRY" in notes[0]


# ── which room each alert goes to ────────────────────────────────────────────────────────────
# The bridge is the only thing in this repo that sends a TRADE message, and it also sends the
# single most serious HEALTH one. Both are pinned, because the split is only worth anything if
# it holds at the one place that produces both kinds.

def test_the_entry_and_exit_alerts_are_TRADES():
    import notify
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    kinds: list = []
    b, ops, ledger, notes = _bridge(ex, kinds=kinds)
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(901, 0, 3290.0, 0.42, 3280.0)]
    ex._pos_dir, ex._pend_long = 1, None
    b.sync(_Dec(stop=3280.0), _Sig())                 # entry alert
    ops.positions = []
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())                            # exit alert
    assert kinds, "the bridge sent nothing at all"
    assert set(kinds) == {notify.TRADE}


def test_a_HALT_is_health_not_a_trade():
    """A halt is the bot refusing to place orders — a fact about the machinery, and the one
    message that must not be sitting in a room only checked when a fill arrives."""
    import notify
    kinds: list = []
    b, ops, ledger, notes = _bridge(_FakeExecution(), kinds=kinds)
    b._halt("emulator and broker disagree")
    assert kinds == [notify.HEALTH]
    assert notes and "HALTED" in notes[0]


def test_closing_a_position_reports_pnl_and_r():
    """Risk is measured off the BROKER's fill and the stop actually attached — R has to
    describe the trade that happened, not the one that was intended."""
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(901, 0, 3290.0, 0.42, 3280.0)]
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b.sync(_Dec(stop=3280.0), _Sig())          # adopt the open position
    ops.positions = []                          # ...it closes
    ops.deal = (3320.0, 1260.0)                 # 30 points × 0.42 × 100
    ex._pos_dir = 0
    b.sync(_Dec(), _Sig())

    closed = [kw for k, kw in ledger.rows if k == "closed"][0]
    assert closed["pnl_usd"] == 1260.0
    # risk = |3290 - 3280| × 0.42 lots × 100 contract size = $420 → 3R
    assert closed["r_multiple"] == pytest.approx(3.0)
    # The exit alert leads with the OUTCOME, not the word "exit" — see algos/live/alerts.py.
    assert any("WIN" in n and "Made $1,260.00" in n for n in notes)


def test_a_position_cancels_any_leftover_resting_order():
    """One position slot. A limit still resting on the other side would open a second trade the
    strategy has no model of."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(950, 1, 3320.0, 0.4, 3330.0)]   # a SHORT filled
    ex._pos_dir = -1
    ops.actions.clear()
    b.sync(_Dec(stop=3330.0), _Sig())
    assert ("cancel", 901) in ops.actions


# ── divergence ────────────────────────────────────────────────────────────────
def test_a_strategy_position_the_broker_does_not_have_halts_the_bot():
    """Every later decision would be computed against a trade that does not exist."""
    b, ops, ledger, notes = _bridge(_FakeExecution(pos_dir=1))
    b.sync(_Dec(stop=3280.0), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED
    assert "MT5 has none" in b.halt_reason
    assert any("HALTED" in n for n in notes)


def test_a_broker_position_the_strategy_does_not_know_about_halts_the_bot():
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(777, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(pos_dir=0), mt5ops=ops)
    # the position is observed (so it is logged), then the disagreement is caught
    b.sync(_Dec(), _Sig())
    ops.positions = [_Pos(777, 0, 3290.0, 0.42, 3280.0)]
    b._pos_ticket = None
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED


def test_a_halted_bridge_places_nothing_further():
    ex = _FakeExecution(pos_dir=1)
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(stop=3280.0), _Sig())          # halts
    ops.actions.clear()
    ex._pos_dir, ex._pend_long = 0, _Pend(1, 3290.0, 0.42, 3280.0)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []


def test_startup_refuses_to_adopt_an_unknown_position():
    """Silently taking over an unknown position is how a restart doubles a book — the strategy
    would size a fresh entry with no idea it is already exposed."""
    ops = _FakeMt5Ops()
    ops.positions = [_Pos(1, 0, 3290.0, 0.42, 3280.0)]
    b, ops, _, _ = _bridge(_FakeExecution(), mt5ops=ops)
    b.adopt_broker_state()
    assert b.state is live_bridge.BridgeState.HALTED
    assert "no local record" in b.halt_reason


def test_startup_clears_stale_resting_orders():
    """A limit from a previous run was priced off state this process no longer has."""
    ops = _FakeMt5Ops()
    ops.orders = [_Order(11), _Order(12)]
    b, ops, _, _ = _bridge(_FakeExecution(), mt5ops=ops)
    b.adopt_broker_state()
    assert [a for a in ops.actions if a[0] == "cancel"] == [("cancel", 11), ("cancel", 12)]


# ── warmup ────────────────────────────────────────────────────────────────────
def test_a_position_opened_during_warmup_is_never_placed_live():
    """Its entry is in the past at a price that is gone. Opening it now at market would be a
    different trade, so the bridge waits for the emulator to flatten."""
    ex = _FakeExecution(pos_dir=1, pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.begin_live()
    assert b.state is live_bridge.BridgeState.WARMING
    b.sync(_Dec(stop=3280.0), _Sig())
    assert ops.actions == []                 # no order, and no halt either
    assert b.state is live_bridge.BridgeState.WARMING


def test_the_bridge_goes_live_once_the_warmup_position_closes():
    ex = _FakeExecution(pos_dir=1)
    b, ops, ledger, _ = _bridge(ex)
    b.begin_live()
    ex._pos_dir = 0
    ex._pend_long = _Pend(1, 3290.0, 0.42, 3280.0)
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE
    assert "event:went_live" in ledger.kinds()
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]


# ── dry run ───────────────────────────────────────────────────────────────────
def test_dry_run_sends_nothing_but_records_what_it_would_have_done():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.42, 3280.0))
    b, ops, ledger, _ = _bridge(ex, dry_run=True)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:dry_run_action" in ledger.kinds()
