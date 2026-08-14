"""Bar-mode costs — the lab's `commission_per_side` / `slippage_ticks`, charged at last.

Until 2026-08-01 the lab collected both numbers, stored them on the run row and displayed them,
and NOTHING read them: every Python run was frictionless while reporting a cost profile it had
not applied. The tell in the data was 52 losing trades each losing exactly 10.00% of prior
equity, which no cost model can produce.

What these tests pin is the shape of the fix, not the arithmetic of one run:

* **A run that states no costs is byte-identical to before** — with no profile no charge path is
  entered. (That the LAB builds no profile at 0/0 is pinned next door, in the backend's
  `tests/test_python_runner.py`, because `_cost_profile` lives on that side of the seam.)
* **Commission is per LOT per side.** Reading the lab's dollars as per-UNIT would overcharge gold
  by 100x, and nothing downstream would look wrong.
* **Slippage is charged on MARKET exits only, and only in bar mode.** A resting limit fills at
  its price or better or not at all; tick mode measures the real thing off the tape, so an
  estimate there would book it twice.
"""

import dataclasses
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.fills import AccountProfile, TickPathResolver
from backtest.data.ticks import Tick
from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Execution, _Pending

from .test_execution_ticks import Dec, FakeTicks, Sig


def _lab_profile(commission=0.0, slippage_ticks=0):
    """What `python_runner._cost_profile` builds from a run's stated costs."""
    return AccountProfile("lab", commission, slippage_ticks=slippage_ticks, swap=None)


def _pend(direction, edge, sl, tp1, tp2, qty=100.0):
    return _Pending(dir=direction, edge=edge, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)


def _long_in(ex, entry=99.5, sl=99.0, tp1=100.5, tp2=101.0, qty=100.0):
    ex._pend_long = _pend(1, entry, sl, tp1, tp2, qty)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True


# ── commission ───────────────────────────────────────────────────────────────────

def test_commission_is_per_lot_per_side_not_per_unit():
    """$3/side/lot on 100 oz (= 1 lot) is $3 in and $3 out, NOT $300. Getting the unit wrong
    would look entirely plausible on the page and be off by the contract size."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=_lab_profile(3.0))
    _long_in(ex, qty=100.0)
    assert ex._costs_usd == -3.0                       # entry side
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 100.0, "x", Dec())
    assert ex._costs_usd == -6.0                       # exit side too


def test_commission_scales_with_size():
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=_lab_profile(3.0))
    _long_in(ex, qty=250.0)                            # 2.5 lots
    assert ex._costs_usd == -7.5


# ── slippage ─────────────────────────────────────────────────────────────────────

def test_slippage_is_charged_on_a_market_exit():
    """A stop is a market order. 2 ticks × $0.01 × 100 oz × pv 1.0 = $2.00."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_lab_profile(slippage_ticks=2))
    _long_in(ex, qty=100.0)
    assert ex._costs_usd == 0.0, "the entry is a resting limit — it does not slip"
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 99.0, "stop", Dec())
    assert ex._costs_usd == -2.0


def test_a_take_profit_rung_does_not_slip():
    """TP rungs are resting limits: they fill at their price or better or not at all. Charging
    them would price a cost that does not exist, in the pessimistic direction."""
    cfg = dataclasses.replace(SosFadeConfig(), exec_tp1_pct=30.0, exec_tp2_pct=40.0)
    ex = Execution(cfg, initial_capital=10_000.0, profile=_lab_profile(slippage_ticks=2))
    _long_in(ex, qty=100.0)
    ex._exit_portion("L-TP1", 100.5, 30.0, Sig(), Dec(), market=False)
    assert ex._costs_usd == 0.0


def test_tick_mode_ignores_the_slippage_estimate():
    """Tick mode fills at the next price that actually existed, so the slippage is already in the
    fill price. Charging the estimate on top would book it twice."""
    resolver = TickPathResolver(FakeTicks([Tick(0, bid=99.0, ask=99.33)]), "XAUUSD", latency_ms=0)
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_lab_profile(slippage_ticks=50), resolver=resolver)
    ex._pos_dir, ex._qty, ex._entry, ex._entry_ms = 1, 100.0, 100.0, 0
    ex._filled_qty, ex._entry_equity, ex._exit_notional, ex._exit_qty = 0.0, 10_000.0, 0.0, 0.0
    ex._costs_usd = 0.0
    ex._charge_slippage(100.0)
    assert ex._costs_usd == 0.0


def test_no_profile_means_no_slippage_and_no_commission():
    """The bar-mode default. `compare_strategy.py` runs here."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0)
    _long_in(ex, qty=100.0)
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 99.0, "stop", Dec())
    assert ex._costs_usd == 0.0


# ── the whole trade ──────────────────────────────────────────────────────────────

def test_costs_land_inside_the_trades_own_pnl_and_r():
    """Costs are charged AFTER the R baseline is snapshotted, so they reduce the trade's own
    result rather than being quietly excluded from it. A $1 stop loss on 100 oz is -$100 gross;
    with $3/side commission and 2 ticks of slippage it is -$108 net."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_lab_profile(3.0, slippage_ticks=2))
    _long_in(ex, entry=100.0, sl=99.0, qty=100.0)
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 99.0, "stop", Dec())
    trade = ex.trades[-1]
    assert trade.costs_usd == -8.0                     # 3 + 3 commission, 2.00 slippage
    assert round(trade.pnl_usd, 6) == -108.0
    assert round(ex.equity, 6) == 10_000.0 - 108.0


# ── spread, as a COST (bid_ask_fills off) ────────────────────────────────────────
#
# Added 2026-08-02. Spread was the largest KNOWN cost bar mode still charged nothing for — unlike
# slippage it is measured, stable, and different per broker (Vantage gold 0.22, PU Prime 0.33).
# These pin the two things that would look plausible if wrong: that one round turn costs exactly
# ONE spread however many rungs the ladder fills, and that turning on `bid_ask_fills` stops the
# cost path rather than adding to it.

def _spread_profile(spread=0.22, bid_ask_fills=False):
    return AccountProfile("lab", 0.0, spread=spread, bid_ask_fills=bid_ask_fills, swap=None)


def test_spread_costs_half_on_entry_and_half_on_exit():
    """The quoted mid sits between bid and ask, so each side of a round turn gives up half the
    spread. 0.22 on 100 oz = $22 round turn, $11 a side."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=_spread_profile(0.22))
    _long_in(ex, qty=100.0)
    assert round(ex._costs_usd, 6) == -11.0
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 99.0, "stop", Dec())
    assert round(ex._costs_usd, 6) == -22.0


def test_a_three_rung_exit_still_pays_exactly_one_spread():
    """The reason it is charged as HALVES rather than per fill. A ladder that banks TP1, TP2 and
    the runner exits three times; billing a whole spread each would treble a measured cost."""
    cfg = dataclasses.replace(SosFadeConfig(), exec_tp1_pct=30.0, exec_tp2_pct=40.0)
    ex = Execution(cfg, initial_capital=10_000.0, profile=_spread_profile(0.22))
    _long_in(ex, entry=99.5, sl=99.0, tp1=100.5, tp2=101.0, qty=100.0)
    ex._exit_portion("L-TP1", 100.5, 30.0, Sig(), Dec(), market=False)
    ex._exit_portion("L-TP2", 101.0, 40.0, Sig(), Dec(), market=False)
    ex._exit_portion("L-RUN", 101.5, 30.0, Sig(), Dec(), market=False)
    assert round(ex._costs_usd, 6) == -22.0            # 11 in + 11 spread across all three rungs


def test_spread_is_not_charged_when_the_fills_already_pay_it():
    """`bid_ask_fills` books the entry on the ask and the exit on the bid, so the spread is paid
    BY CONSTRUCTION. Charging it as well would bill the same spread twice — the two are
    alternatives, not layers that stack."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_spread_profile(0.22, bid_ask_fills=True))
    _long_in(ex, qty=100.0)
    ex._close_at(Sig(o=100.0, h=101.0, l=99.0), 99.0, "stop", Dec())
    assert ex._costs_usd == 0.0


def test_tick_mode_ignores_the_stated_spread():
    """Same rule as slippage: the resolver transacts on the real side of the book, so the spread
    is already in the fill price."""
    resolver = TickPathResolver(FakeTicks([Tick(0, bid=99.0, ask=99.22)]), "XAUUSD", latency_ms=0)
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_spread_profile(0.22), resolver=resolver)
    assert ex._spread() == 0.0


def test_no_profile_means_no_spread():
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0)
    _long_in(ex, qty=100.0)
    assert ex._costs_usd == 0.0


# ── spread, as a FILL rule (bid_ask_fills on) — the half that moves trades ───────

def test_a_longs_entry_limit_needs_the_bid_to_reach_one_spread_below_it():
    """Broker bars are the BID and a long BUYS the ask. A limit at 99.50 is reached when the ask
    touches it, i.e. when the bid is at 99.28 — so a bar whose low is exactly 99.50 fills the
    order in bid-only bar mode and does not fill it in reality."""
    off = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=_spread_profile(0.22))
    off._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    assert off._try_entry_fill(Sig(o=100.0, h=101.0, l=99.50), Dec()) is True

    on = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_spread_profile(0.22, bid_ask_fills=True))
    on._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    assert on._try_entry_fill(Sig(o=100.0, h=101.0, l=99.50), Dec()) is False, \
        "the ask never got to the limit — this long did not happen"

    on2 = Execution(SosFadeConfig(), initial_capital=10_000.0,
                    profile=_spread_profile(0.22, bid_ask_fills=True))
    on2._pend_long = _pend(1, 99.5, 99.0, 100.5, 101.0)
    assert on2._try_entry_fill(Sig(o=100.0, h=101.0, l=99.28), Dec()) is True
    assert on2._entry == 99.5, "it fills AT the limit — the limit price is the ask price"


def test_a_shorts_entry_is_unchanged_because_it_sells_the_bid():
    """The asymmetry is the point: only two of the four order sides are buys."""
    on = Execution(SosFadeConfig(), initial_capital=10_000.0,
                   profile=_spread_profile(0.22, bid_ask_fills=True))
    on._pend_short = _pend(-1, 100.5, 101.0, 99.5, 99.0)
    assert on._try_entry_fill(Sig(o=100.0, h=100.50, l=99.0), Dec()) is True
    assert on._entry == 100.5


def test_a_shorts_stop_triggers_one_spread_earlier_than_the_bid_bar_shows():
    """A short's stop is a BUY. Bar mode waits for the bid to reach it, so it MISSES stops a real
    account would have been taken out on — the optimistic direction, which is the dangerous one."""
    cfg = dataclasses.replace(SosFadeConfig(), exec_be_buf_tk=0.0)
    off = Execution(cfg, initial_capital=10_000.0, profile=_spread_profile(0.22))
    off._pend_short = _pend(-1, 100.0, 101.0, 99.0, 98.5)
    assert off._try_entry_fill(Sig(o=99.0, h=100.2, l=98.0), Dec()) is True
    off._manage_open(Sig(o=100.0, h=100.90, l=100.0), Dec())
    assert off._pos_dir == -1, "bid high 100.90 never reached the 101.00 stop"

    on = Execution(cfg, initial_capital=10_000.0,
                   profile=_spread_profile(0.22, bid_ask_fills=True))
    on._pend_short = _pend(-1, 100.0, 101.0, 99.0, 98.5)
    assert on._try_entry_fill(Sig(o=99.0, h=100.2, l=98.0), Dec()) is True
    on._manage_open(Sig(o=100.0, h=100.90, l=100.0), Dec())
    assert on._pos_dir == 0, "ask high 101.12 took the stop out"
    assert on.trades[-1].exit_price == 101.0


def test_bid_ask_fills_leaves_a_longs_exits_alone():
    """A long exits by SELLING — the bar already IS the bid, so nothing shifts."""
    cfg = dataclasses.replace(SosFadeConfig(), exec_be_buf_tk=0.0)
    ex = Execution(cfg, initial_capital=10_000.0,
                   profile=_spread_profile(0.22, bid_ask_fills=True))
    ex._pend_long = _pend(1, 100.0, 99.0, 101.0, 101.5)
    assert ex._try_entry_fill(Sig(o=101.0, h=101.5, l=99.5), Dec()) is True
    ex._manage_open(Sig(o=100.0, h=100.5, l=99.10), Dec())
    assert ex._pos_dir == 1, "bid low 99.10 never reached the 99.00 stop, spread or no spread"
    ex._manage_open(Sig(o=100.0, h=100.5, l=99.00), Dec())
    assert ex._pos_dir == 0 and ex.trades[-1].exit_price == 99.0
