"""The breakeven buffer as a FRACTION of the trade's own stop, and the cost floor under it.

Until 2026-08-24 the staged ("breakeven") stop was one fixed tick distance on every trade. That
is wrong in two directions at once, and both were MEASURED on run 5a5e2174d095 (243 trades,
XAUUSD.p M15 2020-01-01..2026-08-23, PU Prime ECN costs charged):

* **too small** — 10 of that run's 46 scratches were net LOSSES, because 30 ticks does not cover
  what a multi-day hold costs in financing (median round trip $0.020/oz, but $1.704 at 3-7 days
  and $5.592 at worst, correlation 0.727 with hold time).
* **too large** — a fixed buffer big enough for those lands at or PAST the rung that staged it on
  the tight-stop trades, so the next bar closes the trade at the target instead of protecting a
  runner. 24 of 243 trades at 300 ticks; 70 of 243 at 600.

What these tests pin is the SHAPE of the replacement, not one run's arithmetic:

* the shipped tick mode is untouched, so no stored result can move without a config change;
* the fraction mode scales with the trade's own frozen risk;
* the cap keeps the staged stop short of the rung that staged it, always;
* the cost floor counts the exit side that has NOT been charged yet, or it covers half a round
  trip while claiming to cover one;
* the one case where the floor cannot fit under the cap is a REFUSAL to stage, not a silent clamp
  to a price that guarantees a loss.

Every test here was watched RED — see `docs/SOS_FADE_BUILD_NOTES.md` for the mutation table.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.fills import AccountProfile
from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution, _Pending

from .test_execution_ticks import Dec, Sig


def _profile(commission=0.0):
    return AccountProfile("lab", commission, slippage_ticks=0, swap=None)


def _long_in(ex, entry=99.5, sl=99.0, tp1=100.5, tp2=101.0, qty=100.0):
    """A long at 99.5 risking 0.50, first rung 1.00 away. Every number below is off these."""
    ex._pend_long = _Pending(dir=1, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True


# ── the shipped path does not move ───────────────────────────────────────────────

def test_tick_mode_is_the_default_and_ignores_every_new_field():
    """The live bot runs this branch. A default that read the new fields would move a deployed
    strategy the moment this landed, with no promote and no restart."""
    cfg = SosFadeConfig()
    assert cfg.exec_be_buf_mode == "Ticks"
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex)
    assert ex._be_buffer() == pytest.approx(cfg.exec_be_buf_tk * cfg.mintick)


# ── the buffer scales with the trade's own risk ──────────────────────────────────

def test_fraction_mode_scales_with_the_frozen_entry_risk():
    """Same setting, two stop widths, two buffers — that is the entire point of the mode."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop", exec_be_buf_r=0.20)
    tight = Execution(cfg, initial_capital=10_000.0)
    _long_in(tight, sl=99.0)                       # risk 0.50
    assert tight._be_buffer() == pytest.approx(0.10)

    wide = Execution(cfg, initial_capital=10_000.0)
    _long_in(wide, sl=98.0, tp1=103.0, tp2=104.0)  # risk 1.50, rung 3.50 away
    assert wide._be_buffer() == pytest.approx(0.30)


def test_buffer_does_not_drift_as_the_trade_runs():
    """Risk is the FROZEN entry risk, so the cushion is the same size on the bar it stages and on
    every bar after. Pricing it off the excursion instead would widen the buffer as the trade won
    — the cushion would grow exactly when there is least left to protect.

    ⚠ Written this way ON PURPOSE after the first version was found VACUOUS. That one asserted the
    buffer is read off `_sl` rather than "the live stop", and `Execution` has no live-stop
    attribute to read — no mutation could make it fail, because the code cannot express the bug it
    described. This version pins a source (`_max_fav`) the code CAN reach, and dies when it does.
    """
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop", exec_be_buf_r=0.20)
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex)
    at_stage = ex._be_buffer()
    ex._stage = 2
    ex._max_fav = 100.4                             # most of the way to the rung
    assert ex._be_buffer() == pytest.approx(at_stage)
    assert ex._be_buffer() == pytest.approx(0.10)


# ── the cap ──────────────────────────────────────────────────────────────────────

def test_cap_keeps_the_staged_stop_short_of_the_rung_that_staged_it():
    """A buffer that reaches the rung closes the trade at the target instead of protecting it.
    Measured: that happened on 70 of 243 trades at a 600-tick fixed buffer."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop",
                        exec_be_buf_r=0.90, exec_be_cap_pct=75.0)
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex, sl=98.0)                           # risk 1.50 -> uncapped buffer 1.35
    rung = ex._tp1                                  # 100.5, i.e. 1.00 from entry
    assert ex._be_buffer() == pytest.approx(0.75)   # capped at 75% of 1.00
    ex._stage = 1
    assert ex._current_stop() < rung


def test_cap_is_measured_off_the_nearer_rung_on_a_flipped_ladder():
    """`_stage_rungs` exists because a re-entry's two rungs can arrive out of order. Capping off
    `_tp1` directly would, on a flipped one, cap against a price the trade has not reached."""
    cfg = SosFadeConfig(exec_secondary=True, exec_be_buf_mode="Fraction of stop",
                        exec_be_buf_r=0.90, exec_be_cap_pct=75.0)
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex, sl=98.0, tp1=104.0, tp2=100.5)     # FLIPPED: tp2 is the nearer rung
    ex._entry_kind = "secondary"
    assert ex._stage_rungs()[0] == pytest.approx(100.5)
    assert ex._be_buffer() == pytest.approx(0.75)   # off 100.5, not off 104.0


# ── the cost floor ───────────────────────────────────────────────────────────────

def test_accrued_cost_counts_the_exit_side_that_has_not_been_charged_yet():
    """At entry only ONE side of the commission is on the ledger. A floor built off that covers
    half a round trip and calls it a round trip."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=_profile(3.0))
    _long_in(ex, qty=100.0)                         # 100 oz = 1 lot
    assert ex._costs_usd == pytest.approx(-3.0)     # entry side only
    assert ex._accrued_cost_price() == pytest.approx(0.06)   # $6 round trip over 100 oz


def test_cost_floor_lifts_the_buffer_when_the_fraction_would_not_cover_costs():
    """The whole point: a staged exit that does not clear its own costs is a small LOSS."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop + cost",
                        exec_be_buf_r=0.20, exec_be_cost_margin_r=0.05)
    ex = Execution(cfg, initial_capital=10_000.0, profile=_profile(30.0))
    _long_in(ex)                                    # risk 0.50; cost 0.60/oz round trip
    # fraction alone would be 0.10, which does not cover 0.60.
    assert ex._be_buffer() == pytest.approx(0.60 + 0.05 * 0.50)


def test_cost_margin_is_what_turns_a_breakeven_into_a_small_win():
    """Margin 0 exits flat after costs; positive banks something. Aaron's ask, made a dial."""
    base = dict(exec_be_buf_mode="Fraction of stop + cost", exec_be_buf_r=0.20)
    flat = Execution(SosFadeConfig(**base, exec_be_cost_margin_r=0.0),
                     initial_capital=10_000.0, profile=_profile(30.0))
    _long_in(flat)
    assert flat._be_buffer() == pytest.approx(0.60)          # exactly covers costs

    paid = Execution(SosFadeConfig(**base, exec_be_cost_margin_r=0.10),
                     initial_capital=10_000.0, profile=_profile(30.0))
    _long_in(paid)
    assert paid._be_buffer() == pytest.approx(0.60 + 0.05)   # 0.10 of a 0.50 stop on top


def test_cost_floor_ignores_the_spread_when_fills_are_modelled_on_the_book():
    """`_charge_spread` returns early under `bid_ask_fills` because the cost is already in the
    fill prices. Counting it here would bill it a second time in a different currency."""
    modelled = AccountProfile("lab", 0.0, slippage_ticks=0, swap=None,
                              spread=0.10, bid_ask_fills=True)
    flat = AccountProfile("lab", 0.0, slippage_ticks=0, swap=None, spread=0.10)
    a = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=modelled)
    _long_in(a)
    b = Execution(SosFadeConfig(), initial_capital=10_000.0, profile=flat)
    _long_in(b)
    assert a._accrued_cost_price() == pytest.approx(0.0)
    assert b._accrued_cost_price() > 0.0


# ── the conflict: cost floor above the cap ───────────────────────────────────────

def test_hold_stop_refuses_to_stage_when_no_price_both_covers_cost_and_clears_the_rung():
    """A trade whose financing alone is past the cap cannot be protected profitably. Moving the
    stop anyway would be a stop labelled breakeven that guarantees a loss."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop + cost",
                        exec_be_cost_conflict="Hold stop", exec_be_cap_pct=75.0)
    ex = Execution(cfg, initial_capital=10_000.0, profile=_profile(100.0))
    _long_in(ex)                                    # cost 2.00/oz vs a 0.75 cap
    assert ex._be_buffer() is None
    ex._stage = 1
    assert ex._current_stop() == pytest.approx(ex._sl)    # frozen entry stop, not staged


def test_clamp_to_cap_stages_anyway_and_stays_under_the_rung():
    """The configurable alternative — a known small loss instead of a full stop. Still capped."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop + cost",
                        exec_be_cost_conflict="Clamp to cap", exec_be_cap_pct=75.0)
    ex = Execution(cfg, initial_capital=10_000.0, profile=_profile(100.0))
    _long_in(ex)
    assert ex._be_buffer() == pytest.approx(0.75)
    ex._stage = 1
    assert ex._current_stop() < ex._tp1


def test_stage_two_floor_never_refuses_even_under_the_conflict():
    """Stage 2 has no previous stop worth holding — the trade is past BOTH rungs, so refusing
    would loosen the stop back toward entry on a trade that is winning."""
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop + cost",
                        exec_be_cost_conflict="Hold stop", exec_tp2_stop_mode="Breakeven")
    ex = Execution(cfg, initial_capital=10_000.0, profile=_profile(100.0))
    _long_in(ex)
    assert ex._be_buffer() is None                  # stage 1 would refuse...
    assert ex._be_buffer(hold_ok=False) == pytest.approx(0.75)
    ex._stage = 2
    assert ex._current_stop() == pytest.approx(ex._entry + 0.75)


# ── a short is not a long with the sign flipped by accident ──────────────────────

def test_short_stages_below_its_entry():
    cfg = SosFadeConfig(exec_be_buf_mode="Fraction of stop", exec_be_buf_r=0.20)
    ex = Execution(cfg, initial_capital=10_000.0)
    ex._pend_short = _Pending(dir=-1, edge=100.5, qty=100.0, sl=101.0, tp1=99.5, tp2=99.0,
                              sos_bar=1)
    assert ex._try_entry_fill(Sig(o=100.0, h=100.8, l=99.0), Dec()) is True
    ex._stage = 1
    assert ex._be_buffer() == pytest.approx(0.10)
    assert ex._current_stop() == pytest.approx(100.5 - 0.10)


# ── the config refuses the settings that would silently do nothing ───────────────

@pytest.mark.parametrize("kwargs, needle", [
    ({"exec_be_buf_mode": "Percent"}, "exec_be_buf_mode"),
    ({"exec_be_buf_mode": "Fraction of stop", "exec_be_buf_r": 0.0}, "exec_be_buf_r"),
    ({"exec_be_buf_mode": "Fraction of stop", "exec_be_buf_r": 1.0}, "exec_be_buf_r"),
    ({"exec_be_buf_mode": "Fraction of stop", "exec_be_cap_pct": 100.0}, "exec_be_cap_pct"),
    ({"exec_be_buf_mode": "Fraction of stop", "exec_be_cap_pct": 0.0}, "exec_be_cap_pct"),
    ({"exec_be_buf_mode": "Fraction of stop + cost",
      "exec_be_cost_margin_r": -0.1}, "exec_be_cost_margin_r"),
    ({"exec_be_buf_mode": "Fraction of stop + cost",
      "exec_be_cost_conflict": "Ignore"}, "exec_be_cost_conflict"),
])
def test_config_refuses_rather_than_silently_doing_nothing(kwargs, needle):
    with pytest.raises(ValueError, match=needle):
        SosFadeConfig(**kwargs)


def test_new_fields_are_not_validated_in_tick_mode():
    """Tick mode reads none of them, so a stale value left in a saved config must not refuse a
    run it has no effect on."""
    SosFadeConfig(exec_be_buf_mode="Ticks", exec_be_buf_r=5.0, exec_be_cap_pct=250.0)
