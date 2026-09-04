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
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"


# ── the fake terminal ─────────────────────────────────────────────────────────
class _SymbolInfo:
    def __init__(
        self,
        digits=2,
        point=0.01,
        stops_level=0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    ):
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
    # `comment` carries the BROKER's own sentence ("AutoTrading disabled by client"). It is the
    # field a human acts on and no refusal path in `mt5_ops` logged it until 2026-08-10.
    def __init__(self, retcode, order=0, price=0.0, comment=""):
        self.retcode, self.order, self.price = retcode, order, price
        self.comment = comment


class _Deal:
    """One MT5 deal. `time` is EPOCH SECONDS IN THE BROKER SERVER'S CLOCK — which is the whole
    subject of the deal-history tests below."""

    def __init__(
        self,
        position_id,
        entry,
        price=0.0,
        profit=0.0,
        swap=0.0,
        commission=0.0,
        volume=0.01,
        when=None,
    ):
        self.position_id = position_id
        self.entry = entry  # 0 = entry deal, 1 = exit deal
        self.price = price
        self.profit = profit
        self.swap = swap
        self.commission = commission
        self.volume = volume
        self.time = when


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
        if m._refuse_with is not None:
            return m._refuse_with
        m._next_ticket += 1
        return _Result(m.TRADE_RETCODE_DONE, order=m._next_ticket, price=req.get("price", 0.0))

    m.order_send = order_send
    m._refuse_with = None  # set to a _Result (or leave None) to refuse

    m._deals = []

    def history_deals_get(from_, to, **kw):
        """The REAL filter MT5 applies, and the reason the fix was needed: it compares the deal's
        SERVER-clock time against the caller's bounds. A fake that ignored the window would have
        made the broken code pass."""
        out = []
        for d in m._deals:
            when = datetime.utcfromtimestamp(d.time)
            if not (from_ <= when <= to):
                continue
            # `position=` narrows but is not trusted to be exact — production re-filters too.
            if "position" in kw and d.position_id != kw["position"]:
                continue
            out.append(d)
        return tuple(out)

    m.history_deals_get = history_deals_get
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
    fake._rates = [
        {
            "time": pd.Timestamp("2026-07-15 12:00:00").value // 10**9,
            "open": 1,
            "high": 2,
            "low": 0,
            "close": 1,
        }
    ]
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
    fake._symbol.trade_stops_level = 500  # 500 points × 0.01 = $5.00
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
    fake.order_send = lambda req: _Result(99999)  # a refusal
    fake._orders = []  # ...and the ticket is gone
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


# ── why an order was refused ──────────────────────────────────────────────────
#
# Measured 2026-08-10 on a PU Prime demo with the terminal's AlgoTrading button off: the order
# was rejected (retcode 10027, "AutoTrading disabled by client") and `place_order` logged
# `Order failed: (1, 'Success')`, because it reported `last_error()` — the health of the API
# CALL — instead of the result's retcode. Every test below is red against that code.
_REFUSED = 10027
_REFUSED_TEXT = "AutoTrading disabled by client"


def test_refusal_names_the_retcode_and_the_brokers_own_words(mt5ops):
    """The two facts a reader needs, and the old message carried neither."""
    mt5_ops, fake = mt5ops
    msg = mt5_ops.refusal_detail(_Result(_REFUSED, comment=_REFUSED_TEXT), mt5_mod=fake)
    assert "10027" in msg
    assert _REFUSED_TEXT in msg


def test_refusal_distinguishes_no_reply_from_a_rejection(mt5ops):
    """`order_send` returning None is a TRANSPORT failure — there is no retcode to report, and
    saying "retcode=None" as though the broker had answered would be the same category error the
    whole fix is about."""
    mt5_ops, fake = mt5ops
    msg = mt5_ops.refusal_detail(None, mt5_mod=fake)
    assert "no reply" in msg.lower()
    assert "retcode" not in msg.lower().split("last_error")[0]


def test_a_refused_market_order_does_not_log_the_word_success(mt5ops):
    """The incident, reproduced. `last_error()` is (0, 'ok') in this fake and (1, 'Success') on
    the real terminal — either way it must not be the ONLY thing in the line."""
    mt5_ops, fake = mt5ops
    fake._refuse_with = _Result(_REFUSED, comment=_REFUSED_TEXT)
    log = _Log()
    ticket, price = _bot(mt5_ops, log).place_order("bullish", 0.01, sl=0.0, tp=0.0)
    assert (ticket, price) == (None, None)
    assert log.saw("10027") and log.saw(_REFUSED_TEXT)


def test_a_refused_pending_limit_reports_the_brokers_words(mt5ops):
    """This is the path the SOS Fade bot actually enters on — every entry is a resting limit."""
    mt5_ops, fake = mt5ops
    fake._refuse_with = _Result(_REFUSED, comment=_REFUSED_TEXT)
    log = _Log()
    assert _bot(mt5_ops, log).place_pending_limit("bullish", 0.01, 3200.0, 3190.0) == (None, None)
    assert log.saw("10027") and log.saw(_REFUSED_TEXT)


def test_a_refused_stop_move_is_reported_at_all(mt5ops):
    """`move_sl` logged NOTHING on failure. It is how the stop is staged to breakeven — which
    this strategy does on essentially every trade, at a median of one bar — so a silent refusal
    leaves the strategy believing it is protected while the broker holds the original stop."""
    mt5_ops, fake = mt5ops
    fake._positions = [_Order(77, 770115)]
    fake._positions[0].symbol = "XAUUSD"
    fake._positions[0].tp = 0.0
    fake._refuse_with = _Result(_REFUSED, comment=_REFUSED_TEXT)
    log = _Log()
    assert _bot(mt5_ops, log).move_sl(77, 3210.0) is False
    assert log.saw("10027") and log.saw(_REFUSED_TEXT)


def test_a_refused_close_is_reported_at_all(mt5ops):
    """`close_position` also returned a bare False. A close the broker refuses leaves the bot's
    book and the broker's disagreeing, which is the one thing `bridge._agrees` halts on."""
    mt5_ops, fake = mt5ops
    pos = _Order(88, 770115)
    pos.symbol, pos.volume, pos.profit, pos.tp = "XAUUSD", 0.01, 0.0, 0.0
    fake._positions = [pos]
    fake._refuse_with = _Result(_REFUSED, comment=_REFUSED_TEXT)
    log = _Log()
    ok, _, _ = _bot(mt5_ops, log).close_position(88, "bullish", reason="TEST")
    assert ok is False
    assert log.saw("10027") and log.saw(_REFUSED_TEXT)


# ── deal history vs the broker clock ──────────────────────────────────────────
#
# MT5 stamps a deal's `time` in the SERVER's clock. PU Prime's server runs +3h ahead of UTC
# (measured 2026-08-10), and both readers bounded their window with `datetime.utcnow()` — so a
# deal that had just happened was stamped PAST THE END of its own window and neither function
# could see it. Both tests are red against that code, and the fake's `history_deals_get` applies
# the real time filter so they can be.
_SERVER_AHEAD_HOURS = 3


def _server_stamp(ahead_hours: int = _SERVER_AHEAD_HOURS) -> float:
    """Epoch seconds for a deal that happened NOW, stamped in a server clock running ahead."""
    return (datetime.utcnow() + timedelta(hours=ahead_hours)).timestamp()


def test_breakdown_finds_a_deal_stamped_in_a_server_clock_ahead_of_utc(mt5ops):
    mt5_ops, fake = mt5ops
    when = _server_stamp()
    fake._deals = [
        _Deal(101, entry=0, price=4335.14, commission=-0.10, when=when),
        _Deal(101, entry=1, price=4335.13, profit=-0.10, commission=-0.10, when=when),
    ]
    bd = _bot(mt5_ops).get_deal_breakdown(101)
    assert bd["deals"] == 2
    assert bd["commission_usd"] == pytest.approx(-0.20)
    assert bd["close_price"] == pytest.approx(4335.13)


def test_deal_result_finds_a_deal_stamped_in_a_server_clock_ahead_of_utc(mt5ops):
    mt5_ops, fake = mt5ops
    when = _server_stamp()
    fake._deals = [_Deal(202, entry=1, price=4400.5, profit=12.5, when=when)]
    assert _bot(mt5_ops).get_deal_result(202) == (4400.5, 12.5)


def test_a_server_clock_BEHIND_utc_is_covered_too(mt5ops):
    """The margin has to work in both directions. A broker on UTC-5 stamps a deal in the past,
    which the 7-day lookback already covers — this pins that the forward margin did not break
    it, because a window fixed only at the top would be the same bug mirrored."""
    mt5_ops, fake = mt5ops
    fake._deals = [_Deal(303, entry=1, price=1.0, profit=2.0, when=_server_stamp(-5))]
    assert _bot(mt5_ops).get_deal_result(303) == (1.0, 2.0)


def test_the_wider_window_still_refuses_another_positions_deals(mt5ops):
    """Widening the window is only safe because correctness comes from the position filter, not
    from the bounds. If that filter ever weakens, this fix turns into cross-contamination
    between trades — so it is pinned here rather than assumed."""
    mt5_ops, fake = mt5ops
    when = _server_stamp()
    fake._deals = [
        _Deal(404, entry=0, commission=-0.10, when=when),
        _Deal(404, entry=1, profit=5.0, commission=-0.10, when=when),
        _Deal(999, entry=1, profit=1000.0, commission=-99.0, when=when),  # somebody else's
    ]
    bd = _bot(mt5_ops).get_deal_breakdown(404)
    assert bd["deals"] == 2
    assert bd["gross_usd"] == pytest.approx(5.0)
    assert bd["commission_usd"] == pytest.approx(-0.20)


def test_no_deals_still_reads_as_not_found_rather_than_free(mt5ops):
    """The half of the rule that was always right, and the one a "simplification" would drop:
    a dict of zeros with `deals: 0` means NOT FOUND. `algos/live/bridge.py` keys its fallback on
    exactly that, so a zero commission and an unanswerable question must stay distinguishable."""
    mt5_ops, fake = mt5ops
    fake._deals = []
    bd = _bot(mt5_ops).get_deal_breakdown(505)
    assert bd["deals"] == 0
    assert bd["commission_usd"] == 0.0


# ── the timeout that is not a failure (2026-08-25) ───────────────────────────
#
# 🔴 On 2026-08-25 four order requests timed out, all four reached the broker, and the bot
# re-sent on every bar because `place_pending_limit` returned `(None, None)` for a timeout
# exactly as it does for a rejection. Five copies of one limit filled at 4661.50 within 69
# milliseconds. These pin the broker layer's half of the fix; the bridge's half is in
# `test_order_reconciliation.py`.
#
# Retcode 10012 is TRADE_RETCODE_TIMEOUT: the reply never arrived. Nothing about it says the
# broker did not act.


class _RestingOrder:
    """Shaped like an MT5 order — `price_open` and `volume_current`, not `price`/`volume`.

    ⚠ `volume_current` is what is LEFT on a partially-filled order, and it is the field
    production reads. A fake using `volume` would let a reconciliation that reads the wrong
    name pass.
    """

    def __init__(self, ticket, price, volume, magic=770115, sl=0.0):
        self.ticket = ticket
        self.price_open = price
        self.volume_current = volume
        self.magic = magic
        self.sl = sl


def _timeout():
    return _Result(10012, comment="Request timeout")


def test_a_timed_out_send_whose_order_LANDED_returns_that_ticket(mt5ops):
    """The incident, at the layer it happened. The terminal says the request failed; the order
    book says otherwise; the order book wins.

    WATCHED RED: make `_reconcile_pending` return `None` unconditionally and this fails with
    `(None, None)` - i.e. the caller re-sends, which is the incident.
    """
    mt5_ops, fake = mt5ops
    log = _Log()
    bot = _bot(mt5_ops, log)

    def order_send(req):
        fake.sent.append(req)
        fake._orders.append(_RestingOrder(7777, req["price"], req["volume"]))  # it DID land
        return _timeout()

    fake.order_send = order_send

    ticket, price = bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0)

    assert ticket == 7777, "an order that is demonstrably at the broker was reported as absent"
    assert price == 3310.0
    assert log.saw("IS at the broker")


def test_a_timed_out_send_that_really_failed_still_reports_failure(mt5ops):
    """The fix must not turn every refusal into an imagined order. Nothing new on the book means
    nothing was placed, and the caller is right to try again."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._refuse_with = _timeout()

    assert bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0) == (None, None)


def test_an_order_that_was_ALREADY_resting_is_not_mistaken_for_a_new_one(mt5ops):
    """The baseline is what makes the diff mean anything. An identical order resting before the
    send must not be adopted as the result of it - that would invent an order the bot then
    believes it owns, which is the same disease pointed the other way."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._orders.append(_RestingOrder(6666, 3310.0, 0.40))
    fake._refuse_with = _timeout()

    assert bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0) == (None, None)


def test_an_unreadable_book_after_the_send_is_UNKNOWN_not_failure(mt5ops):
    """ "Cannot ask" is never "it did not happen". Reporting failure here is what gets the order
    re-sent, and the whole incident is one re-send repeated.

    WATCHED RED: return `None` instead of `UNKNOWN` from the `after is None` arm - this fails
    because the caller is handed a clean failure it will act on.
    """
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._refuse_with = _timeout()

    calls = {"n": 0}

    def orders_get(**kw):
        calls["n"] += 1
        return None if calls["n"] > 1 else tuple()  # baseline reads, the follow-up does not

    fake.orders_get = orders_get

    ticket, price = bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0)
    assert ticket is mt5_ops.UNKNOWN


def test_an_unreadable_book_BEFORE_the_send_is_UNKNOWN(mt5ops):
    """Without a baseline the diff is meaningless: an order already resting cannot be told from
    one that just landed. Refusing to answer beats answering with a coin flip."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._refuse_with = _timeout()
    fake.orders_get = lambda **kw: None

    ticket, _ = bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0)
    assert ticket is mt5_ops.UNKNOWN


def test_a_confirmed_send_never_consults_the_book(mt5ops):
    """The reconciliation is the exceptional path. A clean DONE must stay one order_send and two
    cheap reads, or the common case pays for the rare one on every bar."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    reads = {"n": 0}
    real = fake.orders_get

    def counting(**kw):
        reads["n"] += 1
        return real(**kw)

    fake.orders_get = counting
    ticket, _ = bot.place_pending_limit("bearish", 0.40, 3310.0, 3320.0)
    assert ticket and reads["n"] == 1  # the baseline only


def test_an_unreadable_book_makes_a_failed_CANCEL_unknown_not_successful(mt5ops):
    """🔴 The quietest of the three faults. `cancel_pending` re-asked the broker - the right
    shape - but asked with a call that returns `None` both when the order is gone and when the
    terminal cannot be reached, and `not None` is True. **An unreadable book was reported as a
    successful cancel**, after which the bridge cleared its record and placed a replacement.

    WATCHED RED: restore `if not mt5.orders_get(ticket=ticket): return True` and this returns
    True for a cancel that never happened.
    """
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._refuse_with = _timeout()
    fake.orders_get = lambda **kw: None

    assert bot.cancel_pending(4242) is mt5_ops.UNKNOWN


def test_a_cancel_for_an_order_that_is_genuinely_gone_still_succeeds(mt5ops):
    """A race with a fill must not read as a failure, or the bridge retries forever."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)
    fake._refuse_with = _Result(10013, comment="Invalid request")

    assert bot.cancel_pending(4242) is True


def test_the_strict_read_separates_empty_from_unreadable(mt5ops):
    """The distinction the whole fix rests on, asserted directly rather than through a caller."""
    mt5_ops, fake = mt5ops
    bot = _bot(mt5_ops)

    assert bot.pending_orders_strict() == []
    fake.orders_get = lambda **kw: None
    assert bot.pending_orders_strict() is None
    # ...while the lenient reader still flattens both, which is why callers that ACT use the
    # strict one. Pinned so the two cannot quietly converge.
    assert bot.get_pending_orders() == []


# ── the MARKET order's volume guard (added 2026-09-03) ────────────────────────
#
# 🔴 `place_pending_limit` normalised its volume and `place_order` did not — an ASYMMETRY rather
# than a decision. It never bit because nothing in the live path called the market form until the
# market-entry route landed, which is exactly the shape of a gap that surfaces on first use.


def test_a_sub_minimum_market_order_is_refused_and_never_rounded_UP(mt5ops):
    """🔴 Rule 17. Rounding 0.004 up to a 0.01 minimum is 2.5x the risk the strategy authorised —
    a bigger position than anything asked for, arriving silently.

    MUTATION: drop the `vol <= 0` guard in `place_order` and this goes red.
    """
    mt5_ops, fake = mt5ops
    log = _Log()
    ticket, price = _bot(mt5_ops, log).place_order("bullish", 0.004, sl=3190.0, tp=0.0)
    assert (ticket, price) == (None, None)
    assert log.saw("minimum") or log.saw("NOT rounding up")


def test_a_market_order_SENDS_the_normalised_volume_not_the_requested_one(mt5ops):
    """Rule 3: a record — and a wire — says what was SENT, not what was asked for.

    0.037 lots on a 0.01 step is 0.03. Sending 0.037 gets a bare retcode from the venue.
    MUTATION: send `lots` instead of `vol` and this goes red.
    """
    mt5_ops, fake = mt5ops
    _bot(mt5_ops, _Log()).place_order("bullish", 0.037, sl=3190.0, tp=0.0)
    assert fake.sent[-1]["volume"] == 0.03, fake.sent[-1]


def test_the_market_order_refusal_names_the_number_it_refused(mt5ops):
    """A refusal that does not say what was too small sends the reader to guess.

    MUTATION: drop the lots and the minimum from the message and this goes red.
    """
    mt5_ops, fake = mt5ops
    log = _Log()
    _bot(mt5_ops, log).place_order("bullish", 0.004, sl=3190.0, tp=0.0)
    assert log.saw("0.004") and log.saw("0.01")
