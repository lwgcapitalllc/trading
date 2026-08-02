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
