"""Offline tests for the pending-order layer and the broker-clock fix in `shared/mt5_ops.py`.

`MetaTrader5` is Windows-only and needs a running terminal, so it is FAKED here — the point is
to pin the decisions `mt5_ops` makes before it calls `order_send`, which is where every bug in
this layer lives. What reaches the wire (action, type, rounded price, stepped volume) is
asserted against the recorded request; whether the broker then accepts it is not our logic.

Run: command-center/backend/.venv/bin/python -m pytest algos/tests/ -q
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"


# ── the fake terminal ─────────────────────────────────────────────────────────
class _SymbolInfo:
    def __init__(self, digits=2, point=0.01, stops_level=0,
                 volume_min=0.01, volume_max=100.0, volume_step=0.01):
        self.digits = digits
        self.point = point
        self.trade_stops_level = stops_level
        self.volume_min = volume_min
        self.volume_max = volume_max
        self.volume_step = volume_step


class _Tick:
    def __init__(self, bid, ask):
        self.bid, self.ask = bid, ask


class _Result:
    def __init__(self, retcode, order=0, price=0.0):
        self.retcode, self.order, self.price = retcode, order, price


class _Order:
    def __init__(self, ticket, magic):
        self.ticket, self.magic = ticket, magic


def _fake_mt5():
    m = types.ModuleType("MetaTrader5")
    m.TRADE_ACTION_DEAL = 1
    m.TRADE_ACTION_PENDING = 5
    m.TRADE_ACTION_SLTP = 6
    m.TRADE_ACTION_MODIFY = 7
    m.TRADE_ACTION_REMOVE = 8
    m.ORDER_TYPE_BUY = 0
    m.ORDER_TYPE_SELL = 1
    m.ORDER_TYPE_BUY_LIMIT = 2
    m.ORDER_TYPE_SELL_LIMIT = 3
    m.ORDER_TIME_GTC = 0
    m.ORDER_FILLING_IOC = 1
    m.ORDER_FILLING_RETURN = 2
    m.TRADE_RETCODE_DONE = 10009

    m.sent = []
    m._symbol = _SymbolInfo()
    m._tick = _Tick(3300.00, 3300.20)
    m._orders = []
    m._positions = []
    m._rates = None
    m._next_ticket = 5000

    m.symbol_info = lambda sym: m._symbol
    m.symbol_info_tick = lambda sym: m._tick
    m.last_error = lambda: (0, "ok")
    m.copy_rates_from_pos = lambda sym, tf, start, count: m._rates

    def orders_get(**kw):
        if "ticket" in kw:
            return tuple(o for o in m._orders if o.ticket == kw["ticket"])
        return tuple(m._orders)
    m.orders_get = orders_get
    m.positions_get = lambda **kw: tuple(m._positions)

    def order_send(req):
        m.sent.append(req)
        m._next_ticket += 1
        return _Result(m.TRADE_RETCODE_DONE, order=m._next_ticket, price=req.get("price", 0.0))
    m.order_send = order_send
    return m


class _Log:
    def __init__(self):
        self.lines = []

    def _rec(self, msg):
        self.lines.append(str(msg))

    info = warning = error = _rec

    def saw(self, fragment):
        return any(fragment.lower() in ln.lower() for ln in self.lines)


@pytest.fixture
def mt5ops(monkeypatch):
    """Import `mt5_ops` against a fake terminal, freshly each test so `sent` is isolated."""
    fake = _fake_mt5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.syspath_prepend(str(_SHARED))
    for mod in ("mt5_ops", "bot_state", "broker_clock"):
        sys.modules.pop(mod, None)
    import mt5_ops
    return mt5_ops, fake


def _bot(mt5_ops, log=None):
    return mt5_ops.BotMT5("XAUUSD", 770115, "BOT_TEST", {}, {"login": 1}, log or _Log())


# ── the broker clock ──────────────────────────────────────────────────────────
def test_get_candles_converts_broker_time_to_true_utc(mt5ops):
    """The bug this replaced labelled BROKER-LOCAL seconds as UTC, putting every bar 2-3h out
    and every session boundary with it. In January the broker runs UTC+2, so a bar the terminal
    reports as 12:00 is really 10:00 UTC."""
    mt5_ops, fake = mt5ops
    broker_noon = pd.Timestamp("2026-01-15 12:00:00").value // 10**9
    fake._rates = [{"time": broker_noon, "open": 1, "high": 2, "low": 0, "close": 1}]

    df = _bot(mt5_ops).get_candles(15, 1)
    assert df["time"].iloc[0] == pd.Timestamp("2026-01-15 10:00:00", tz="UTC")


def test_get_candles_follows_the_dst_switch(mt5ops):
    """July is UTC+3, January UTC+2. A single constant offset would be wrong for half the year
    — and wrong in the direction that smears session boundaries rather than failing loudly."""
    mt5_ops, fake = mt5ops
    fake._rates = [{"time": pd.Timestamp("2026-07-15 12:00:00").value // 10**9,
                    "open": 1, "high": 2, "low": 0, "close": 1}]
    df = _bot(mt5_ops).get_candles(15, 1)
    assert df["time"].iloc[0] == pd.Timestamp("2026-07-15 09:00:00", tz="UTC")


def test_get_candles_returns_an_empty_frame_not_none(mt5ops):
    mt5_ops, fake = mt5ops
    fake._rates = None
    assert _bot(mt5_ops).get_candles(15, 10).empty


# ── volume normalisation ──────────────────────────────────────────────────────
def test_volume_rounds_down_to_the_step(mt5ops):
    """DOWN, never to nearest: rounding up crosses the risk the strategy sized for, on every
    single entry."""
    mt5_ops, _ = mt5ops
    assert _bot(mt5_ops).normalize_volume(0.4279) == 0.42


def test_sub_minimum_volume_is_refused_not_rounded_up(mt5ops):
    """0.004 lots means the account is too small for this stop distance. Substituting the
    0.01 minimum would place a bet 2.5x bigger than the one that was risk-checked."""
    mt5_ops, _ = mt5ops
    assert _bot(mt5_ops).normalize_volume(0.004) == 0.0


def test_volume_is_clamped_to_the_broker_maximum(mt5ops):
    mt5_ops, fake = mt5ops
    fake._symbol.volume_max = 50.0
    assert _bot(mt5_ops).normalize_volume(999.0) == 50.0


# ── placing a resting limit ───────────────────────────────────────────────────
def test_buy_limit_is_placed_below_market(mt5ops):
    mt5_ops, fake = mt5ops
    ticket, price = _bot(mt5_ops).place_pending_limit("bullish", 0.42, 3290.00, 3280.00)
    assert ticket is not None
    req = fake.sent[-1]
    assert req["action"] == fake.TRADE_ACTION_PENDING
    assert req["type"] == fake.ORDER_TYPE_BUY_LIMIT
    assert req["price"] == 3290.00 and req["sl"] == 3280.00
    assert req["volume"] == 0.42
    assert req["magic"] == 770115


def test_sell_limit_is_placed_above_market(mt5ops):
    mt5_ops, fake = mt5ops
    _bot(mt5_ops).place_pending_limit("bearish", 0.5, 3320.00, 3330.00)
    assert fake.sent[-1]["type"] == fake.ORDER_TYPE_SELL_LIMIT


def test_a_limit_on_the_wrong_side_of_market_is_refused(mt5ops):
    """Price already traded through the level, so this is not a limit any more — it would fill
    instantly at the market, which is a different trade from the one the strategy chose."""
    mt5_ops, fake = mt5ops
    log = _Log()
    ticket, _ = _bot(mt5_ops, log).place_pending_limit("bullish", 0.42, 3310.00, 3280.00)
    assert ticket is None and fake.sent == []
    assert log.saw("wrong side of the market")


def test_a_limit_inside_the_brokers_stops_level_is_refused(mt5ops):
    mt5_ops, fake = mt5ops
    fake._symbol.trade_stops_level = 500          # 500 points × 0.01 = $5.00
    log = _Log()
    ticket, _ = _bot(mt5_ops, log).place_pending_limit("bullish", 0.42, 3298.00, 3280.00)
    assert ticket is None and fake.sent == []
    assert log.saw("stops_level")


def test_a_stop_inside_the_brokers_stops_level_is_refused(mt5ops):
    """The floor applies twice — market-to-limit AND limit-to-stop. This is the second one, and
    it is the one a strategy with a tight fib stop actually hits."""
    mt5_ops, fake = mt5ops
    fake._symbol.trade_stops_level = 500
    log = _Log()
    ticket, _ = _bot(mt5_ops, log).place_pending_limit("bullish", 0.42, 3290.00, 3289.00)
    assert ticket is None and fake.sent == []
    assert log.saw("stops_level")


def test_a_position_too_small_to_place_is_refused_with_a_reason(mt5ops):
    mt5_ops, fake = mt5ops
    log = _Log()
    ticket, _ = _bot(mt5_ops, log).place_pending_limit("bullish", 0.004, 3290.00, 3280.00)
    assert ticket is None and fake.sent == []
    assert log.saw("not rounding up")


# ── modify / cancel ───────────────────────────────────────────────────────────
def test_modify_sends_price_and_stop_only(mt5ops):
    """MT5 silently ignores volume on a MODIFY. Keeping it out of the request is what stops a
    caller believing a re-size happened — the bridge must cancel and re-place instead."""
    mt5_ops, fake = mt5ops
    assert _bot(mt5_ops).modify_pending(5001, 3291.00, 3281.00) is True
    req = fake.sent[-1]
    assert req["action"] == fake.TRADE_ACTION_MODIFY
    assert "volume" not in req


def test_cancelling_an_already_gone_ticket_counts_as_success(mt5ops):
    """It filled, or someone cancelled it. The caller's intent — "there should be no order
    here" — is satisfied either way, and returning False would make the bridge retry forever."""
    mt5_ops, fake = mt5ops
    fake.order_send = lambda req: _Result(99999)      # a refusal
    fake._orders = []                                  # ...and the ticket is gone
    assert _bot(mt5_ops).cancel_pending(5001) is True


# ── magic isolation ───────────────────────────────────────────────────────────
def test_pending_orders_and_positions_are_filtered_by_magic(mt5ops):
    """One terminal can host several bots and a human clicking Buy. A bot that cancelled
    another's orders would be the worst possible bug in this file."""
    mt5_ops, fake = mt5ops
    fake._orders = [_Order(1, 770115), _Order(2, 999999), _Order(3, 770115)]
    fake._positions = [_Order(10, 999999)]
    bot = _bot(mt5_ops)
    assert [o.ticket for o in bot.get_pending_orders()] == [1, 3]
    assert bot.get_open_positions() == []


def test_cancel_all_pending_only_touches_this_bots_orders(mt5ops):
    mt5_ops, fake = mt5ops
    fake._orders = [_Order(1, 770115), _Order(2, 999999)]
    assert _bot(mt5_ops).cancel_all_pending() == 1
    assert [r["order"] for r in fake.sent] == [1]
