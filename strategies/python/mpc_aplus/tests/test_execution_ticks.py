"""Tick-mode execution (A2): real bid/ask fills + commission + swap.

The load-bearing test here is `test_bar_mode_is_untouched_by_a2`: bar mode is what
`compare_strategy.py` diffs against the Pine, so A2 is only allowed to ADD a branch, never to
alter the default path. The rest prove the two things a bar cannot show — which side of the book
transacted, and what a stop actually cost — plus that costs land inside the trade's own P&L.
"""

import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.fills import AccountProfile, SwapModel, TickPathResolver
from backtest.data.ticks import Tick
from strategies.python.mpc_aplus.config import AplusConfig
from strategies.python.mpc_aplus.execution import Execution, _Pending


class FakeTicks:
    """A tick source serving one canned stream for any window."""

    def __init__(self, ticks):
        self._ticks = ticks

    def window(self, symbol, start_ms, end_ms):
        return [t for t in self._ticks if start_ms <= t.ms < end_ms]


class Sig:
    """The handful of Signals fields Execution reads on a fill path."""

    def __init__(self, index=0, time_ms=0, o=100.0, h=101.0, l=99.0, c=100.0):
        self.index, self.time_ms = index, time_ms
        self.open, self.high, self.low, self.close = o, h, l, c
        self.bull_sos = self.bear_sos = False
        self.ny_hour = 10


def _profile(commission=0.0, swap=None):
    return AccountProfile("test", commission, contract_size=100.0, latency_ms=0, swap=swap)


def _resolver(ticks):
    return TickPathResolver(FakeTicks(ticks), "XAUUSD.s", latency_ms=0)


def _pend(direction, edge, sl, tp1, tp2, qty=100.0):
    return _Pending(dir=direction, edge=edge, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)


class Dec:
    def __init__(self):
        self.fills = []
        self.closed_r = None


# ── the parity guard ─────────────────────────────────────────────────────────────

def test_bar_mode_is_untouched_by_a2():
    """No resolver + no profile ⇒ the pre-A2 behaviour, exactly. compare_strategy.py rests on it."""
    ex = Execution(AplusConfig(), initial_capital=10_000.0)
    assert ex._resolver is None and ex._profile is None
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    sig, dec = Sig(o=100.0, h=101.0, l=99.2), Dec()
    assert ex._try_entry_fill(sig, dec) is True
    assert ex._entry == 99.5          # fills AT the limit, no spread
    assert ex._costs_usd == 0.0       # and charges nothing


def test_bar_mode_charges_no_costs_even_overnight():
    """Bar mode has no profile, so the swap hook is a no-op — an honest zero."""
    ex = Execution(AplusConfig(), initial_capital=10_000.0)
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec())
    ex._charge_swap(Sig(time_ms=_ms("2026-03-11 23:00")))
    assert ex._costs_usd == 0.0


# ── the side of the book ─────────────────────────────────────────────────────────

def test_long_entry_buys_the_ask_so_the_spread_is_paid():
    """A long entering lifts the ask. The limit is on the BID's journey down, but the fill price
    is the ask — that difference IS the spread, paid by construction rather than modelled."""
    ticks = [Tick(0, bid=100.0, ask=100.33), Tick(100, bid=99.4, ask=99.50)]
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile())
    ex.bar_ms = 300_000
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True
    assert ex._entry == 99.50         # the ASK reached the limit, not the bid


def test_short_entry_sells_the_bid():
    ticks = [Tick(0, bid=100.0, ask=100.33), Tick(100, bid=100.6, ask=100.93)]
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile())
    ex.bar_ms = 300_000
    ex._pend_short = _pend(-1, 100.6, 101.0, 100.0, 99.5)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True
    assert ex._entry == 100.6         # the BID reached the limit


def test_long_exit_sells_the_bid_not_the_ask():
    """The conflation this guards: a long's ENTRY buys, but its EXIT sells. Testing the exit
    against the ask would refund part of the spread on every one of the ladder's legs."""
    ex = Execution(AplusConfig(), 10_000.0, profile=_profile())
    ex._resolver = _resolver([Tick(0, bid=100.5, ask=100.83)])
    ex.bar_ms = 300_000
    ex._pos_dir, ex._qty, ex._entry = 1, 100.0, 99.5
    ex._sl, ex._tp1, ex._tp2 = 99.0, 100.5, 101.0
    ex._entry_ms, ex._entry_equity, ex._risk_usd = 0, 10_000.0, 50.0
    dec = Dec()
    ex._manage_open(Sig(index=1, time_ms=0, o=100.0, h=101.0, l=99.6), dec)
    # TP1 = 100.5 and the BID printed exactly 100.5 ⇒ filled. The ask (100.83) is irrelevant here.
    assert any(f.order_id.endswith("TP1") for f in dec.fills)


# ── slippage is measured, not assumed ────────────────────────────────────────────

def test_stop_fills_at_the_next_real_price_so_slippage_is_measured():
    """A stop is a market order: it fills at the next price that EXISTS. Reporting the level as
    the fill would erase exactly the cost the tick model was built to measure."""
    # bid jumps 99.10 -> 98.60, straight through a stop at 99.00
    ticks = [Tick(0, bid=99.10, ask=99.43), Tick(50, bid=98.60, ask=98.93)]
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile())
    ex.bar_ms = 300_000
    ex._pos_dir, ex._qty, ex._entry = 1, 100.0, 99.5
    ex._sl, ex._tp1, ex._tp2 = 99.0, 100.5, 101.0
    ex._entry_ms, ex._entry_equity, ex._risk_usd = 0, 10_000.0, 50.0
    dec = Dec()
    ex._manage_open(Sig(index=1, time_ms=0, o=99.2, h=99.3, l=98.6), dec)
    stop_fill = [f for f in dec.fills if f.kind == "exit"][0]
    assert stop_fill.price == 98.60   # NOT 99.00 — it slipped $0.40, and we can see it


def test_limit_exit_does_not_slip_against_you():
    ticks = [Tick(0, bid=100.7, ask=101.03)]      # gapped past TP1 in our favour
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile())
    ex.bar_ms = 300_000
    ex._pos_dir, ex._qty, ex._entry = 1, 100.0, 99.5
    ex._sl, ex._tp1, ex._tp2 = 99.0, 100.5, 101.0
    ex._entry_ms, ex._entry_equity, ex._risk_usd = 0, 10_000.0, 50.0
    dec = Dec()
    ex._manage_open(Sig(index=1, time_ms=0, o=100.7, h=101.0, l=100.6), dec)
    assert [f for f in dec.fills if f.kind == "exit"][0].price == 100.7   # better, not worse


# ── costs ────────────────────────────────────────────────────────────────────────

def test_commission_is_charged_per_side_and_scaled_to_lots():
    """qty is in OUNCES; commission is quoted per LOT. Skipping the conversion is a 100x error."""
    ticks = [Tick(0, bid=99.4, ask=99.50)]
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile(3.50))
    ex.bar_ms = 300_000
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0, qty=100.0)   # 100 oz = 1.0 lot
    ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec())
    assert ex._costs_usd == pytest.approx(-3.50)                    # one side, one lot
    assert ex.equity == pytest.approx(10_000.0 - 3.50)


def test_costs_land_inside_the_trades_own_pnl():
    """Costs are charged AFTER the R baseline snapshot, so the trade's P&L (and its R) carry
    them. Charging before would quietly exclude them from the number being judged."""
    ticks = [Tick(0, bid=99.4, ask=99.50)]
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver(ticks), profile=_profile(3.50))
    ex.bar_ms = 300_000
    ex._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec())
    assert ex._entry_equity == 10_000.0          # baseline taken before the charge
    assert ex._equity_at_entry_delta() == pytest.approx(-3.50)   # so the cost is inside the trade


def _ms(text):
    """'YYYY-MM-DD HH:MM' as NY wall-clock -> epoch ms."""
    from zoneinfo import ZoneInfo
    naive = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    return int(naive.replace(tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)


_SWAP = SwapModel(swap_long_points=-78.29, swap_short_points=29.49,
                  contract_size=100.0, digits=2, triple_weekday=2)


def _open_at(direction, entry_text, commission=0.0):
    ex = Execution(AplusConfig(), 10_000.0, resolver=_resolver([]),
                   profile=_profile(commission, swap=_SWAP))
    ex._pos_dir, ex._qty, ex._filled_qty = direction, 100.0, 0.0   # 1.0 lot
    ex._entry_ms = _ms(entry_text)
    ex._costs_usd, ex._last_roll_ms = 0.0, None
    return ex


def test_swap_charges_a_long_and_credits_a_short():
    """The asymmetry is the point: omitting swap flatters every long AND understates every short."""
    long_ = _open_at(1, "2026-03-10 10:00")
    long_._charge_swap(Sig(time_ms=_ms("2026-03-10 18:00")))
    assert long_._costs_usd == pytest.approx(-78.29)

    short = _open_at(-1, "2026-03-10 10:00")
    short._charge_swap(Sig(time_ms=_ms("2026-03-10 18:00")))
    assert short._costs_usd == pytest.approx(+29.49)   # a real credit


def test_wednesday_books_three_nights():
    ex = _open_at(1, "2026-03-11 10:00")               # 2026-03-11 is a Wednesday
    ex._charge_swap(Sig(time_ms=_ms("2026-03-11 18:00")))
    assert ex._costs_usd == pytest.approx(-78.29 * 3)


def test_a_rollover_is_charged_once_not_once_per_bar():
    """Every bar after 17:00 sees the same rollover. Latching it is the same edge-vs-level
    distinction that caused the sweep double-count bug in signals.py."""
    ex = _open_at(1, "2026-03-10 10:00")
    for hh in ("18:00", "18:05", "18:10", "23:55"):
        ex._charge_swap(Sig(time_ms=_ms(f"2026-03-10 {hh}")))
    assert ex._costs_usd == pytest.approx(-78.29)      # one night, not four


def test_two_nights_held_charges_twice():
    ex = _open_at(1, "2026-03-09 10:00")
    ex._charge_swap(Sig(time_ms=_ms("2026-03-09 18:00")))
    ex._charge_swap(Sig(time_ms=_ms("2026-03-10 18:00")))
    assert ex._costs_usd == pytest.approx(-78.29 * 2)


def test_a_rollover_before_the_entry_is_not_charged():
    """Opening at 18:00 means the 17:00 roll already happened — that night wasn't held."""
    ex = _open_at(1, "2026-03-10 18:30")
    ex._charge_swap(Sig(time_ms=_ms("2026-03-10 18:35")))
    assert ex._costs_usd == 0.0


def test_intraday_trade_pays_no_swap():
    ex = _open_at(1, "2026-03-10 10:00")
    ex._charge_swap(Sig(time_ms=_ms("2026-03-10 15:00")))
    assert ex._costs_usd == 0.0


def test_saturday_books_nothing():
    """The market is shut; the weekend is carried by the triple-swap weekday instead."""
    ex = _open_at(1, "2026-03-13 10:00")               # Friday
    roll = ex._last_rollover_before(_ms("2026-03-14 12:00"))   # Saturday noon
    assert roll is not None and roll[1].weekday() != 5


# ── config wiring ────────────────────────────────────────────────────────────────

def test_tick_mode_refuses_an_unknown_account():
    """Tick mode prices real costs, so it must name a real account rather than default to free."""
    from strategies.python.mpc_aplus.strategy import MpcAplusStrategy
    cfg = dataclasses.replace(AplusConfig(), fill_model="tick",
                              account_profile="nope", symbol="XAUUSD.s")
    with pytest.raises(ValueError, match="unknown"):
        MpcAplusStrategy(cfg)


def test_tick_mode_requires_a_symbol():
    from strategies.python.mpc_aplus.strategy import MpcAplusStrategy
    cfg = dataclasses.replace(AplusConfig(), fill_model="tick",
                              account_profile="puprime_standard", symbol="")
    with pytest.raises(ValueError, match="symbol"):
        MpcAplusStrategy(cfg)


def test_bad_fill_model_is_rejected():
    from strategies.python.mpc_aplus.strategy import MpcAplusStrategy
    with pytest.raises(ValueError, match="fill_model"):
        MpcAplusStrategy(dataclasses.replace(AplusConfig(), fill_model="ticks"))


def test_default_config_is_bar_mode():
    """The default must stay the Pine-faithful one — parity is the default obligation."""
    from strategies.python.mpc_aplus.strategy import MpcAplusStrategy
    s = MpcAplusStrategy(AplusConfig())
    assert AplusConfig().fill_model == "bar"
    assert s.execution._resolver is None and s.execution._profile is None
