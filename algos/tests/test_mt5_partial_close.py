"""`mt5_ops.partial_close` — the one broker call that takes size off a LIVE position.

🔴 **IT HAD NEVER RUN.** Repo-wide there was not one caller before 2026-09-01, so every line of
it was written, reviewed and shipped against nothing. Rule 9: a feature nobody has RUN is not a
feature. These are its first tests.

🔴 **AND IT CLAMPED UP TO THE BROKER MINIMUM.** `max(volume_min, min(lots, held))` meant a slice
below the minimum — or one that rounded to zero against the volume step — silently closed
`volume_min` instead. That is rule 17 exactly: a resized order is not the trade the strategy is
holding. Every refusal test below was watched RED against that body; each one CLOSED SIZE.

⚠ **The fake models `positions_get` FAITHFULLY, which the older harness does not.** The real call
returns `None` when the terminal cannot be asked and an empty tuple when the position is genuinely
gone, and it filters by ticket. `test_mt5_ops_pending.py`'s fake returns every position whatever
you ask for and can never return `None` — a fixture that cannot express the case under test would
have passed the bug (rule 13).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_SHARED = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from broker_result import UNKNOWN  # noqa: E402


class _Pos:
    def __init__(self, ticket, volume, symbol="XAUUSD.p"):
        self.ticket, self.volume, self.symbol = ticket, volume, symbol


class _SymbolInfo:
    def __init__(self, volume_min=0.01, volume_step=0.01):
        self.digits, self.point = 2, 0.01
        self.trade_stops_level = 0
        self.volume_min, self.volume_max, self.volume_step = volume_min, 100.0, volume_step


class _Result:
    def __init__(self, retcode, comment=""):
        self.retcode, self.comment, self.order, self.price = retcode, comment, 0, 0.0


def _fake_mt5():
    m = types.ModuleType("MetaTrader5")
    m.TRADE_ACTION_DEAL = 1
    m.ORDER_TYPE_BUY, m.ORDER_TYPE_SELL = 0, 1
    m.ORDER_TIME_GTC, m.ORDER_FILLING_IOC = 0, 1
    m.TRADE_RETCODE_DONE = 10009
    m.sent = []
    m._symbol = _SymbolInfo()
    m._positions = [_Pos(77, 1.00)]
    m._readable = True  # False = the terminal cannot be asked
    m._closes = 0.0  # how much order_send actually takes off
    m._result = None

    class _Tick:
        bid, ask = 3300.00, 3300.20

    m.symbol_info = lambda sym: m._symbol
    m.symbol_info_tick = lambda sym: _Tick()
    m.last_error = lambda: (0, "ok")

    def positions_get(**kw):
        if not m._readable:
            return None
        rows = m._positions
        if "ticket" in kw:
            rows = [p for p in rows if p.ticket == kw["ticket"]]
        return tuple(rows)

    m.positions_get = positions_get

    def order_send(req):
        m.sent.append(req)
        if m._result is not None:
            return m._result
        take = m._closes if m._closes else req["volume"]
        for p in m._positions:
            if p.ticket == req.get("position"):
                p.volume = round(p.volume - take, 8)
        return _Result(m.TRADE_RETCODE_DONE)

    m.order_send = order_send
    return m


def _bot(fake):
    sys.modules["MetaTrader5"] = fake
    for name in ("mt5_ops",):
        sys.modules.pop(name, None)
    import mt5_ops

    bot = mt5_ops.BotMT5.__new__(mt5_ops.BotMT5)
    bot.magic = 770115
    bot.bot_label = "TEST"
    bot.symbol = "XAUUSD.p"

    class _Log:
        def __init__(self):
            self.lines = []

        def info(self, m):
            self.lines.append(("info", m))

        def error(self, m):
            self.lines.append(("error", m))

        def warning(self, m):
            self.lines.append(("warn", m))

    bot.log = _Log()
    bot.get_tick = lambda sym=None: (3300.00, 3300.20)
    return bot, mt5_ops


# ── it REFUSES rather than resizing (rule 17) ─────────────────────────────────
def test_a_slice_below_the_brokers_minimum_is_REFUSED_not_rounded_up():
    """The defect this rewrite exists for. 0.003 asked, 0.01 minimum: the old body closed 0.01."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.003, "bullish") is False
    assert fake.sent == [], "nothing may reach the wire"
    assert fake._positions[0].volume == 1.00, "the position must be untouched"


def test_a_slice_that_does_not_FIT_the_volume_step_is_REFUSED():
    """0.015 against a 0.01 step. Rounding it closes a size nobody chose."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.015, "bullish") is False
    assert fake.sent == []
    assert fake._positions[0].volume == 1.00


def test_closing_MORE_than_is_open_is_REFUSED_because_that_is_a_full_exit():
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 2.00, "bullish") is False
    assert fake.sent == []


def test_closing_EXACTLY_what_is_open_is_REFUSED_because_that_is_a_full_exit():
    """🔴 **THE BOUNDARY, AND IT WAS THE ONE VALUE NOBODY WROTE DOWN.** For the first few hours of
    this method's life the guard read `want > held`, which refuses only a size LARGER than the
    position — so asking for exactly 1.00 against 1.00 held passed every check, reached the wire,
    emptied the position and returned True while logging "PARTIAL CLOSE".

    ⚠ The test above it (2.00 against 1.00) looked like it covered this and did not, and TWO
    docstrings asserted the refusal that nothing implemented. **A doc and a comment agreeing with
    each other is not evidence.** Closing the last of a position is `close_position` — a different
    call with a different name, so it cannot be reached by an off-by-one in a comparison."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 1.00, "bullish") is False
    assert fake.sent == [], "nothing may reach the wire"
    assert fake._positions[0].volume == 1.00, "the position must be untouched"


def test_a_slice_JUST_UNDER_the_whole_position_still_goes_through():
    """A guard that refuses everything is not a guard. 0.99 of 1.00 leaves a runner, so it is a
    genuine partial and must work."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.99, "bullish") is True
    assert fake._positions[0].volume == 0.01


def test_a_zero_or_negative_slice_is_REFUSED():
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.0, "bullish") is False
    assert bot.partial_close(77, -0.5, "bullish") is False
    assert fake.sent == []


def test_a_slice_the_broker_CAN_express_goes_through_unchanged():
    """A guard that refuses everything is not a guard."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is True
    assert len(fake.sent) == 1
    assert fake.sent[0]["volume"] == 0.50, "the size asked for, not a rounded one"
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_SELL, "a long is banked by SELLING"
    assert fake.sent[0]["position"] == 77
    assert fake._positions[0].volume == 0.50


def test_a_short_is_banked_by_BUYING():
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bearish") is True
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_BUY


# ── "did not happen" and "cannot tell" are different answers (rule 1) ─────────
def test_an_unreadable_position_book_is_UNKNOWN_not_a_failure():
    """The old body's `if not pos: return False` read an unreadable terminal as 'no position' —
    the identical defect `cancel_pending` was fixed for on 2026-08-25."""
    fake = _fake_mt5()
    fake._readable = False
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is UNKNOWN
    assert fake.sent == []


def test_a_position_that_is_genuinely_GONE_is_False_not_UNKNOWN():
    fake = _fake_mt5()
    fake._positions = []
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is False


def test_a_refused_send_that_moved_nothing_is_False():
    fake = _fake_mt5()
    fake._result = _Result(10018, "market closed")
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is False
    assert fake._positions[0].volume == 1.00


def test_a_position_that_cannot_be_RE_READ_after_the_send_is_UNKNOWN():
    """The verdict comes off the position, never off the retcode. If the position cannot be
    re-read, how much is open is not known and a retry could double the bank."""
    fake = _fake_mt5()
    bot, _ = _bot(fake)
    real = fake.order_send

    def send_then_blind(req):
        out = real(req)
        fake._readable = False
        return out

    fake.order_send = send_then_blind
    assert bot.partial_close(77, 0.50, "bullish") is UNKNOWN


def test_a_position_that_moved_by_the_WRONG_amount_is_UNKNOWN():
    """A race with the stop, a partial fill, or another hand on the account. It is neither the
    requested close nor no change, and calling it success would leave the bridge reconciling
    against a size it never verified."""
    fake = _fake_mt5()
    fake._closes = 0.30  # asked for 0.50, only 0.30 came off
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is UNKNOWN


def test_the_verdict_is_read_off_the_POSITION_not_the_retcode():
    """A DONE retcode with nothing actually closed must not report success."""
    fake = _fake_mt5()
    fake._closes = 0.0
    real_send = fake.order_send

    def send_but_change_nothing(req):
        fake.sent.append(req)
        return _Result(fake.TRADE_RETCODE_DONE)

    fake.order_send = send_but_change_nothing
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is False
    assert real_send is not None


def test_missing_symbol_info_is_UNKNOWN_because_nothing_may_be_sized_without_it():
    fake = _fake_mt5()
    fake.symbol_info = lambda sym: None
    bot, _ = _bot(fake)
    assert bot.partial_close(77, 0.50, "bullish") is UNKNOWN
    assert fake.sent == []
