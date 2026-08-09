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
_SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(_SHARED))
sys.path.insert(0, str(_LIVE))
import bridge as live_bridge  # noqa: E402
from order_sizing import SymbolSpec  # noqa: E402

# The live bot's real symbol, with the numbers measured off the PU Prime terminal on
# 2026-07-31 (`instances/mpc_sos_fade_demo/config.json` → `_measured`).
#
# ⚠ The fake below returns THIS dataclass — the same type `mt5_ops.symbol_spec` returns. That is
# deliberate and it is a rule, not a convenience: this repo has already lost three weeks to a
# test fixture that was MORE COMPLETE than production (`test_secondary.py`, 2026-08-06 — the fake
# 1m bar carried two fields the real one did not, so every test exercised a shape the code never
# produced). Sharing the type makes that impossible: a field the fake supplies is one the real
# method must supply too.
GOLD_SPEC = SymbolSpec(symbol="XAUUSD", contract_size=100.0, tick_size=0.01, tick_value=1.0,
                       volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=2)


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
    def __init__(self, ticket, price=0.0, sl=0.0, volume=0.0, buy=True):
        self.ticket = ticket
        # Carried so `account_exposure` below can be DERIVED from this book rather than
        # hand-listed beside it. A fake whose exposure disagrees with its own order book is the
        # 2026-08-07 trap one level up: it would test a shape production never produces.
        self.price, self.sl, self.volume, self.buy = price, sl, volume, buy


class _FakeMt5Ops:
    symbol = "XAUUSD"
    magic = 770115
    bot_label = "BOT_TEST"

    def __init__(self, *, spec=GOLD_SPEC, free=1_000_000.0, leverage=500.0):
        self.positions: list = []
        self.orders: list = []
        self.actions: list = []
        self._ticket = 900
        self.deal = (0.0, 0.0)
        self.spec = spec
        self.free = free
        self.leverage = leverage
        # What OTHER magics hold on this account — another bot, or a hand trade. `None` stands
        # for "the terminal could not be asked", which is a different answer from an empty
        # account and the bridge has to treat it as one.
        self.external: list = []
        self.exposure_readable = True

    def get_open_positions(self, symbol=None):
        return list(self.positions)

    def get_pending_orders(self, symbol=None):
        return list(self.orders)

    def account_exposure(self, symbol=None):
        """Everything on the account across EVERY magic — this bot's own book plus `external`.

        DERIVED from `self.positions` / `self.orders`, never hand-listed: production reads one
        terminal, so a fake whose exposure and whose order book can disagree tests a state that
        cannot occur. It also means the bridge's own-magic exclusion is genuinely exercised —
        with a hand-listed exposure it would be exercising nothing.
        """
        from account_risk import Exposure
        if not self.exposure_readable:
            return None
        out = []
        for p in self.positions:
            out.append(Exposure(ticket=p.ticket, symbol=self.symbol, magic=self.magic,
                                direction=1 if p.type == 0 else -1, volume=p.volume,
                                entry=p.price_open, stop=p.sl, resting=False))
        for o in self.orders:
            out.append(Exposure(ticket=o.ticket, symbol=self.symbol, magic=self.magic,
                                direction=1 if o.buy else -1, volume=o.volume,
                                entry=o.price, stop=o.sl, resting=True))
        return out + list(self.external)

    def normalize_volume(self, lots, symbol=None):
        v = int(lots / 0.01 + 1e-9) * 0.01
        return round(v, 2) if v >= 0.01 else 0.0

    def symbol_spec(self, symbol=None):
        return self.spec

    def free_margin(self):
        return self.free

    def margin_for(self, direction, lots, price, symbol=None):
        if self.spec is None:
            return None
        return lots * self.spec.contract_size * price / self.leverage

    # ⚠ `place` / `cancel` maintain `self.orders`, because a real broker does. Until 2026-08-07
    # this fake recorded the CALL and left the order book empty, so `get_pending_orders()`
    # always answered "nothing resting" — which is indistinguishable from the broker having
    # deleted the order, the exact condition `_observe_vanished` now watches for. A fake whose
    # book never agrees with its own actions cannot test anything that reads that book.
    def place_pending_limit(self, direction, lots, price, sl, tp=0.0, comment="", symbol=None):
        self._ticket += 1
        self.actions.append(("place", direction, lots, price, sl))
        self.orders.append(_Order(self._ticket, price=price, sl=sl, volume=lots,
                                  buy=direction == "bullish"))
        return self._ticket, price

    def modify_pending(self, ticket, price, sl, tp=0.0, symbol=None):
        self.actions.append(("modify", ticket, price, sl))
        return True

    def cancel_pending(self, ticket):
        self.actions.append(("cancel", ticket))
        self.orders = [o for o in self.orders if o.ticket != ticket]
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

    class _AI:
        # The account-level risk cap is a fraction of the LIVE balance, so the stub has to serve
        # one. Without it `_account_balance` returns None and the cap REFUSES every order —
        # correctly ("cannot ask" is never "affordable"), but it would make every cap test pass
        # for the wrong reason.
        balance = 2000.0

    m.symbol_info = lambda s: _SI()
    m.account_info = lambda: _AI()
    monkeypatch.setitem(sys.modules, "MetaTrader5", m)


def _bridge(execution, *, dry_run=False, mt5ops=None, ledger=None, notes=None, kinds=None,
            account_risk_cap_pct=None):
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
                                notify=_notify, dry_run=dry_run,
                                account_risk_cap_pct=account_risk_cap_pct)
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
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]
    assert "event:order_placed" in ledger.kinds()


def test_an_unchanged_limit_is_left_alone():
    """Re-writing an identical order every bar is churn the broker sees as flapping — and it
    resets the order's queue position for nothing."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == []


def test_a_moved_limit_is_modified_in_place():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3292.5, 42.0, 3282.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("modify", 901, 3292.5, 3282.0)]


def test_a_resized_limit_is_cancelled_and_replaced():
    """MT5's MODIFY ignores volume. Sizing moves with equity every bar, so getting this wrong
    means the position size silently freezes at whatever it was when the order was first
    placed."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = _Pend(1, 3290.0, 55.0, 3280.0)
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["cancel", "place"]
    assert ops.actions[-1][2] == 0.55


def test_a_withdrawn_setup_cancels_the_order():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, _, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ex._pend_long = None
    ops.actions.clear()
    b.sync(_Dec(), _Sig())
    assert ops.actions == [("cancel", 901)]


def test_a_sub_minimum_size_is_recorded_rather_than_rounded_up():
    """The account is too small for this stop distance. Placing the broker minimum instead
    would be a bigger bet than the strategy risk-checked — and it would look like a normal
    trade afterwards. Recorded so the missing trade is countable.

    ⚠ The event is `order_refused` carrying `code`, not the old dedicated `order_too_small`.
    That was one of eight ways an order can fail to reach the broker, and giving one of them its
    own name left the other seven — including the margin refusal that would have caught the
    2026-08-07 order — with nowhere to be recorded.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 0.4, 3280.0))   # 0.4 oz = 0.004 lots
    b, ops, ledger, _ = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:order_refused" in ledger.kinds()
    refusal = next(kw for k, kw in ledger.rows if k == "event:order_refused")
    assert refusal["code"] == "below_broker_minimum"


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
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
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
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
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
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
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
    ex._pos_dir, ex._pend_long = 0, _Pend(1, 3290.0, 42.0, 3280.0)
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
    ex = _FakeExecution(pos_dir=1, pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
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
    ex._pend_long = _Pend(1, 3290.0, 42.0, 3280.0)
    b.sync(_Dec(), _Sig())
    assert b.state is live_bridge.BridgeState.LIVE
    assert "event:went_live" in ledger.kinds()
    assert ops.actions == [("place", "bullish", 0.42, 3290.0, 3280.0)]


# ── dry run ───────────────────────────────────────────────────────────────────
def test_dry_run_sends_nothing_but_records_what_it_would_have_done():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, _ = _bridge(ex, dry_run=True)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:dry_run_action" in ledger.kinds()


# ── sizing: the 2026-08-07 oversizing incident ────────────────────────────────
#
# The arithmetic itself is pinned instrument-by-instrument in `test_order_sizing.py`. These are
# the BRIDGE's half: that it converts at all, that it converts through the one seam, and that
# every way an order can fail to reach the broker leaves a record and a message.

class _Cfg:
    """A stand-in for `SosFadeConfig` carrying only what the bridge reads off it."""
    def __init__(self, risk_pct=10.0, point_value=1.0):
        self.exec_risk_pct = risk_pct
        self.point_value = point_value
        self.exec_tp1_pct = 0.0
        self.exec_tp2_pct = 0.0


def _sizing_bridge(pend, *, balance=2000.0, free=2000.0, spec=GOLD_SPEC, risk_pct=10.0,
                   point_value=1.0, monkeypatch=None):
    ex = _FakeExecution(pend_long=pend)
    ex.cfg = _Cfg(risk_pct, point_value)
    ops = _FakeMt5Ops(spec=spec, free=free)
    b, ops, ledger, notes = _bridge(ex, mt5ops=ops)
    b._account_balance = lambda: balance
    return b, ops, ledger, notes


def test_the_bridge_sends_LOTS_where_the_strategy_computed_UNITS():
    """🔴 THE REGRESSION TEST FOR THE INCIDENT. Watched red against HEAD.

    `Execution` computes `qty = equity·risk%/stop_distance` in the INSTRUMENT's units — ounces
    for gold. MT5's `volume` is LOTS. Before 2026-08-07 the bridge handed one straight to the
    other and every order was 100x, because gold's contract is 100 oz.

    24.79 ounces is a $200 risk over an $8.07 stop. It must reach the broker as **0.24 lots**,
    not 24.79.
    """
    b, ops, _, _ = _sizing_bridge(_Pend(1, 4286.75448, 24.79, 4294.82248))
    b.sync(_Dec(), _Sig())
    assert len(ops.actions) == 1
    verb, side, lots, price, sl = ops.actions[0]
    assert (verb, side) == ("place", "bullish")
    assert lots == 0.24, f"sent {lots} lots — units were not converted to lots"


def test_the_exact_incident_order_never_reaches_the_broker():
    """🔴 The real numbers off ticket 320620565, driven through the real bridge.

    54.82 units at 10% of a compounded $4,423 emulator balance, on an account holding $2,000.
    Before the fix this went out as 54.82 LOTS, rested for eight hours, and was deleted by the
    broker at the fill with `[no money]`.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(-1, 4286.75448, 54.82, 4294.82248))
    b._ex._pend_long, b._ex._pend_short = None, _Pend(-1, 4286.75448, 54.82, 4294.82248)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert "event:order_refused" in ledger.kinds()
    assert any("REFUSED" in n for n in notes)


def test_an_order_the_account_cannot_afford_is_refused_and_not_shrunk():
    """Aaron's question, at the bridge. The answer is NO TRADE — never a smaller one.

    A shrunk order leaves the emulator holding one size and the broker another, and the two
    drift apart with nothing reporting it. That is the same divergence that halts the bot,
    arriving quietly instead of loudly.
    """
    # 500 oz = 5 lots = $43,000 of margin at 1:500, against $2,000 free. The balance is set so
    # the risk is genuinely AUTHORISED ($5,000 is 10% of $50,000) — otherwise the equity check
    # fires first and this test would pass without ever reaching the margin one.
    b, ops, ledger, _ = _sizing_bridge(_Pend(1, 4300.0, 500.0, 4290.0),
                                       balance=50_000.0, free=2000.0)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    code = next(kw for k, kw in ledger.rows if k == "event:order_refused")["code"]
    assert code == "insufficient_margin"


def test_a_refusal_alerts_once_and_then_stays_quiet():
    """A setup can rest for hours and is re-offered every bar. One message, not sixty — a
    channel that repeats itself is one nobody reads on the day it matters."""
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 3290.0, 0.4, 3280.0))
    for _ in range(5):
        b.sync(_Dec(), _Sig())
    assert ops.actions == []
    assert len([n for n in notes if "REFUSED" in n]) == 1
    # ...but every occurrence is still RECORDED, so the count is not lost with the noise.
    assert len([k for k in ledger.kinds() if k == "event:order_refused"]) == 5


def test_a_refusal_that_clears_can_alert_again():
    """The counterpart. Keying the silence on the refusal CODE rather than on 'have we ever
    alerted' is what stops this becoming the de-duplicating-alerter bug — a NEW problem after a
    good order must still speak up."""
    pend_ok = _Pend(1, 4300.0, 200.0 / 10.0, 4290.0)      # 20 oz, $200 risk, 0.20 lots
    b, ops, _, notes = _sizing_bridge(_Pend(1, 3290.0, 0.4, 3280.0))
    b.sync(_Dec(), _Sig())
    assert len([n for n in notes if "REFUSED" in n]) == 1
    b._ex._pend_long = pend_ok
    b.sync(_Dec(), _Sig())                                 # places fine, refusal cleared
    b._ex._pend_long = _Pend(1, 3290.0, 0.4, 3280.0)
    b.sync(_Dec(), _Sig())
    assert len([n for n in notes if "REFUSED" in n]) == 2


def test_a_symbol_the_terminal_cannot_describe_refuses_rather_than_guessing():
    """No symbol info means no contract size and no tick value. Every available fallback is a
    number that would size a real position off a guess."""
    b, ops, ledger, _ = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0), spec=None)
    b.sync(_Dec(), _Sig())
    assert ops.actions == []
    code = next(kw for k, kw in ledger.rows if k == "event:order_refused")["code"]
    assert code == "symbol_unreadable"


def test_a_placed_order_records_what_it_actually_risks():
    """🔴 The record that did not exist. Nothing anywhere on 2026-08-07 stated what an order
    put at risk in dollars — so a 221x position left an artefact indistinguishable from a
    correct one. `order_placed` now carries the money, not just the lots."""
    b, ops, ledger, _ = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    rec = next(kw for k, kw in ledger.rows if k == "event:order_placed")
    assert rec["lots"] == 0.2
    assert rec["units"] == 20.0
    assert rec["risk_ccy"] == pytest.approx(200.0, abs=0.5)
    assert rec["margin_ccy"] is not None


# ── an order the broker deleted underneath us ─────────────────────────────────
def test_a_resting_order_the_broker_deleted_is_noticed_and_reported():
    """🔴 Watched red against HEAD. This is what actually happened, and nothing could see it.

    The broker removed the resting sell limit with `deleted [no money]`. The bridge went on
    believing it was there, the emulator filled itself on the next bar, and the only symptom
    anywhere was a generic halt six hours later saying the two disagreed.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    assert b._rest[1] is not None
    ops.orders.clear()                     # the broker deleted it; no position appeared
    b.sync(_Dec(), _Sig())
    assert "event:order_vanished" in ledger.kinds()
    assert any("ORDER GONE" in n for n in notes)


def test_a_filled_order_is_not_reported_as_vanished():
    """The other half, and the one that makes the check usable: an order leaving the book
    because it FILLED is the normal case and must stay silent.

    ⚠ KEPT AND LABELLED: this one PASSES against HEAD, and could not have failed there — before
    the vanish check existed there was nothing to fire wrongly. It pins the ordering that makes
    the new check usable (`_observe_vanished` runs AFTER `_observe_open`, which consumes the
    resting order on a fill), and without it a later 'tidy-up' that reorders the two would turn
    every ordinary fill into an alert with the whole suite still green.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 4300.0, 20.0, 4290.0))
    b.sync(_Dec(), _Sig())
    ops.orders.clear()
    ops.positions = [_Pos(950, 0, 4300.0, 0.2, 4290.0)]
    b._ex._pos_dir = 1
    b.sync(_Dec(stop=4290.0), _Sig())
    assert "event:order_vanished" not in ledger.kinds()
    assert not any("ORDER GONE" in n for n in notes)


def test_the_halt_names_the_refusal_that_caused_it():
    """🔴 The message Aaron actually got, improved.

    'Its resting limit filled in the emulator and not at the broker' is true of every cause at
    once, so it sent the reader at the fill logic when the answer was the order size. If the
    order was REFUSED, the halt says so and quotes the reason.
    """
    b, ops, ledger, notes = _sizing_bridge(_Pend(1, 4300.0, 500.0, 4290.0),
                                           balance=50_000.0, free=2000.0)
    b.sync(_Dec(), _Sig())                      # refused: insufficient margin
    b._ex._pos_dir = 1                          # the emulator fills it anyway
    b._ex._pend_long = None
    b.sync(_Dec(stop=4290.0), _Sig())
    assert b.state is live_bridge.BridgeState.HALTED
    assert "REFUSED" in b.halt_reason
    assert "insufficient_margin" in b.halt_reason


# ── the ACCOUNT-level risk cap (G10) ──────────────────────────────────────────
#
# `exec_risk_pct` is per-TRADE and has never had anything above it, so two bots at 10% put 20%
# on from a state neither can see. These drive the whole seam — the unfiltered broker read, the
# arithmetic, and the refusal — rather than the arithmetic alone, because the arithmetic was
# already right in `test_account_risk.py` and the wiring is where a cap goes quietly missing.
def _cap_pend(edge=3300.0, sl=3290.0, qty=20.0):
    """A long wanting $200 of risk on the stub's $2,000 balance: 20 oz = 0.2 lots, $10 stop,
    $1.00 per 0.01 per lot = $200 = exactly 10%."""
    return _Pend(dir=1, edge=edge, qty=qty, sl=sl)


def _other_bot(risk_dollars, magic=880220):
    """A SECOND bot's open position holding `risk_dollars` of the account's budget."""
    from account_risk import Exposure
    lots = risk_dollars / (10.0 / 0.01 * 1.00)     # $10 of stop distance on gold
    return Exposure(ticket=555, symbol="XAUUSD", magic=magic, direction=1, volume=lots,
                    entry=3300.0, stop=3290.0, resting=False)


def test_with_no_cap_configured_the_bridge_behaves_exactly_as_before(_stub_mt5):
    """The default has to be inert. Every live result this repo has measured was taken with no
    account cap, and a default appearing from nowhere would move a live bot with no measurement
    behind it."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()))
    ops.external = [_other_bot(100_000.0)]         # the account is enormously over any cap
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place"]


def test_the_second_bot_is_REFUSED_when_the_first_holds_the_whole_budget(_stub_mt5):
    """Aaron's requirement, end to end: one bot has the account's risk on, this one wants in,
    and the system blocks it. Nothing reaches the broker."""
    b, ops, ledger, notes = _bridge(_FakeExecution(pend_long=_cap_pend()),
                                    account_risk_cap_pct=10.0)
    ops.external = [_other_bot(200.0)]             # the whole 10% of $2,000
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    refusals = [e for e in ledger.rows if e[0] == "event:order_refused"]
    assert refusals and refusals[0][1]["code"] == "account_risk_cap"
    assert "880220" in refusals[0][1]["detail"]


def test_room_freed_by_the_other_bot_moving_ITS_stop_to_breakeven_lets_this_one_in(_stub_mt5):
    """The property that makes a reservation model worth having, and the reason the cap reads the
    CURRENT stop rather than the entry one: the other bot is still in the market, still holding a
    full position, and holding NO risk — so it is not blocking anything."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    from account_risk import Exposure
    ops.external = [Exposure(ticket=555, symbol="XAUUSD", magic=880220, direction=1,
                             volume=0.20, entry=3300.0, stop=3300.0, resting=False)]
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place"]


def test_a_partly_used_budget_REFUSES_rather_than_placing_a_smaller_order(_stub_mt5):
    """Refuse, never shrink. A resized order is not the trade the strategy's emulator is holding;
    the two would grade different R and `_agrees` would halt the bot on a divergence the safety
    feature created. The BACKTEST allocator shrinks instead, which is coherent there because the
    account hands the granted size back — nothing hands a size back across a process boundary."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    ops.external = [_other_bot(150.0)]             # $50 of room against a $200 order
    b.sync(_Dec(), _Sig())

    assert ops.actions == []                       # NOT a 0.05-lot order
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == \
        ["account_risk_cap"]


def test_this_bots_OWN_resting_order_does_not_block_its_own_re_size(_stub_mt5):
    """The own-magic exclusion, and it is not a shortcut. The strategy has ONE position slot, so
    anything of ours already resting is what this order REPLACES — counting it would make the bot
    refuse its own re-sizes near the cap, which reads exactly like a broken strategy."""
    b, ops, _, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    b.sync(_Dec(), _Sig())                          # places, and the fake's book now holds it
    assert [a[0] for a in ops.actions] == ["place"]

    b._ex._pend_long = _cap_pend(edge=3301.0, sl=3291.0)   # same risk, moved a dollar
    b.sync(_Dec(), _Sig())
    assert [a[0] for a in ops.actions] == ["place", "modify"]


def test_a_hand_trade_with_NO_STOP_refuses_rather_than_scoring_as_zero_risk(_stub_mt5):
    """The dangerous shape. A stopless position's risk is UNBOUNDED, and the falsy value it
    arrives as is the same shape as 'no risk' — so scoring it zero would let the one thing the
    cap exists to bound sit invisibly underneath it."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    from account_risk import Exposure
    ops.external = [Exposure(ticket=42, symbol="XAUUSD", magic=0, direction=1, volume=0.5,
                             entry=3300.0, stop=0.0, resting=False)]
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    refusals = [e for e in ledger.rows if e[0] == "event:order_refused"]
    assert refusals[0][1]["code"] == "account_risk_unmeasurable"
    assert "NO broker-side stop" in refusals[0][1]["detail"]


def test_an_unreadable_account_REFUSES_and_never_reads_as_an_empty_one(_stub_mt5):
    """A cap that opens itself when the terminal wobbles is a cap that is absent exactly when the
    account is least healthy — the `mt5_link` three-state rule applied to money."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0)
    ops.exposure_readable = False
    b.sync(_Dec(), _Sig())

    assert ops.actions == []
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == \
        ["account_risk_unreadable"]


def test_a_per_order_refusal_is_reported_BEFORE_the_account_cap(_stub_mt5):
    """Precedence. A refusal should name the first thing wrong with the ORDER itself before it
    starts talking about what other bots are holding — otherwise a collapsed stop gets blamed on
    a busy account and the reader goes looking in the wrong place."""
    b, ops, ledger, _ = _bridge(_FakeExecution(pend_long=_Pend(dir=1, edge=3300.0, qty=20.0,
                                                               sl=3300.0)),
                                account_risk_cap_pct=10.0)
    ops.external = [_other_bot(200.0)]              # the account is also full
    b.sync(_Dec(), _Sig())
    assert [e[1]["code"] for e in ledger.rows if e[0] == "event:order_refused"] == \
        ["zero_stop_distance"]
