"""Tests for the secondary (1m sniper) re-entry — starting with the 1m structure feed.

`Structure1m` is a thin latch over the canonical `market_structure` engine (Pine `f_struct1m`):
it must report a 1m SOS the bar it fires, capture that break's leg endpoints, hold them until the
next same-side SOS, and never invent a leg on a bar with no SOS. We reuse the structure engine's
OWN hand-traced scenario (major_length=2) — bar 8 there is a confirmed external bear SOS (CHoCH),
so it is the ground truth for the bear side; the scenario has no bull SOS, which pins the bull side
to "never latched".
"""

import dataclasses
import sys

import pytest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]        # repo root (…/trading)
sys.path.insert(0, str(_ROOT))
# reuse the structure engine's hand-traced bar scenario as ground truth
sys.path.insert(0, str(_ROOT / "engines" / "market_structure" / "tests"))

from strategies.python.mpc_sos_fade.secondary import Structure1m
from test_engine import _SCENARIO_BARS  # noqa: E402


def _run():
    """Feed the scenario through Structure1m, returning the per-bar M1State list."""
    s1 = Structure1m(major_length=2)
    return [s1.update(b.index, b.open, b.high, b.low, b.close) for b in _SCENARIO_BARS]


def test_bear_sos_latches_on_bar_8_with_its_leg():
    states = _run()
    st8 = states[8]
    assert st8.new_bear_sos is True                      # the SOS fires on bar 8
    assert st8.bear_sos_bar == 8
    assert st8.bear_leg_hi is not None and st8.bear_leg_lo is not None
    assert st8.bear_leg_hi > st8.bear_leg_lo             # a valid leg (0.0 above 1.0)


def test_new_bear_sos_edge_fires_exactly_once():
    states = _run()
    fired = [i for i, s in enumerate(states) if s.new_bear_sos]
    assert fired == [8]                                  # the edge is a one-bar pulse


def test_no_bull_sos_in_this_scenario():
    states = _run()
    assert all(not s.new_bull_sos for s in states)       # scenario has no bull SOS
    assert states[-1].bull_sos_bar is None               # so the bull side never latched
    assert states[-1].bull_leg_hi is None


def test_leg_persists_after_the_sos_bar():
    """The leg endpoints hold on every bar after the SOS until a new same-side SOS
    overwrites them (a consumer reads the current leg on any bar, not just the SOS bar)."""
    states = _run()
    hi8, lo8 = states[8].bear_leg_hi, states[8].bear_leg_lo
    for s in states[9:]:            # no further bear SOS after bar 8 in this scenario
        assert s.bear_leg_hi == hi8 and s.bear_leg_lo == lo8
        assert s.new_bear_sos is False


# ── The parity guard: run_dual's PRIMARY path == run(), with exec_secondary OFF ──────────
# The secondary must be purely additive. With it off, `run_dual(df15, df1m)` steps the 15m bars
# in the same order with the same OHLC and never calls step_secondary, so its decision stream and
# trade list must be byte-identical to `run(df15)`. This is the offline stand-in for the truth that
# compare_strategy.py stays exit 0 — it directly exercises the driver + the execution guards on
# real-shaped (deterministic synthetic) data, no cache/network needed.
import math

import pandas as pd

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.strategy import MpcSosFadeStrategy


def _synth_df15(n: int) -> pd.DataFrame:
    """A deterministic 15m OHLC frame — a drifting sine so structure/fib/etc. actually move."""
    idx = pd.date_range("2025-01-01", periods=n, freq="15min")
    rows = []
    px = 2000.0
    for i in range(n):
        px += 3.0 * math.sin(i / 7.0) + 0.4 * math.sin(i / 2.3)
        o = px
        c = px + 1.5 * math.sin(i / 3.0)
        hi = max(o, c) + 1.2
        lo = min(o, c) - 1.2
        rows.append((o, hi, lo, c))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def _synth_df1m(df15: pd.DataFrame) -> pd.DataFrame:
    """A 1m frame spanning the same window. Content is irrelevant with the secondary OFF (its
    stream is never consumed) — it exists only to exercise the merge interleaving."""
    start, end = df15.index[0], df15.index[-1] + pd.Timedelta("15min")
    idx = pd.date_range(start, end, freq="1min", inclusive="left")
    rows = []
    for i in range(len(idx)):
        px = 2000.0 + math.sin(i / 30.0)
        rows.append((px, px + 0.3, px - 0.3, px))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def test_run_dual_primary_is_identical_to_run_when_secondary_off():
    df15 = _synth_df15(400)
    df1m = _synth_df1m(df15)
    # PINNED False, not defaulted. `exec_secondary` ships True since 2026-08-07, so relying on
    # the default here would silently turn this into a test of the secondary path — and it would
    # still pass, because this synthetic 1m stream never arms one. A parity test that stops
    # exercising the branch it names is worse than no test.
    cfg = SosFadeConfig(exec_secondary=False)
    a = MpcSosFadeStrategy(cfg).run(df15)
    b = MpcSosFadeStrategy(cfg).run_dual(df15, df1m)
    assert a.decisions == b.decisions           # Decision/Fill are dataclasses → structural ==
    assert a.execution.trades == b.execution.trades


# ── Hand-traced arm + execution (proves the machinery FIRES when conditions align) ──────
# The real 4-day 1m window never lined up all the preconditions on one bar, so these craft the
# aligned state directly: a live 15m LONG leg the primary already traded, price in the 0.618-0.886
# zone, a fresh 1m bull SOS with a valid leg — and check the arm rests the right limit, and that
# execution fills + closes it as a `secondary` trade.
from types import SimpleNamespace

from strategies.python.mpc_sos_fade.execution import Execution
from strategies.python.mpc_sos_fade.secondary import M1State, SecArm, SecondaryArm

# A 15m LONG fib: up-leg low(1.0)=100 → high(0.0)=110. Retrace zone 0.618-0.886 = [101.14, 103.82].
_SIG_LONG = SimpleNamespace(
    fibo_dir=1, fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p6=101.14,
    fibo_p7=110.0, fibo_p10=100.0, bull_div_active=True, bear_div_active=False,
    veto_on=False, veto_rsi_ob=False, veto_rsi_os=False)
_SEQ_LONG = SimpleNamespace(l_sos_bar=500, s_sos_bar=None)


def _m1_bull_sos(hi, lo):
    return M1State(bull_sos_bar=1000, bear_sos_bar=None, bull_leg_hi=hi, bull_leg_lo=lo,
                   bear_leg_hi=None, bear_leg_lo=None, direction=1,
                   new_bull_sos=True, new_bear_sos=False)


def test_arm_fires_and_rests_the_right_limit():
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # a 1m leg 102.0→103.0 inside the zone; primary on this 15m leg reached BE (be_sos_l == l_sos_bar)
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert out.l_armed is True
    assert abs(out.l_edge - (103.0 - 1.0 * 0.382)) < 1e-9   # 38.2% retrace of the 1m leg
    assert out.l_sl == 102.0                                # stop = 1m leg origin (1.0)
    assert out.l_tp1 == 105.0 and out.l_tp2 == 106.18       # 15m 0.5 / 0.382
    assert out.l_leg == 1000

    # once that leg has re-entered, it must not re-arm (each 1m leg fires once)
    arm_sm.mark_traded(1)
    again = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is False


def test_arm_blocked_until_primary_reached_breakeven():
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # the primary on this 15m leg has NOT reached breakeven (be_sos_l is None): a primary that
    # opened and got stopped at its initial stop leaves no re-entry.
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    assert out.l_armed is False                             # a re-entry is never the first trade


def test_dead_leg_blocks_further_reentries():
    """Once a re-entry on a 15m leg hits its initial stop, `mark_dead` kills the leg — no more
    re-entries on it (even on a fresh 1m shift) until a new break of structure resets it."""
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # arms normally on the first fresh 1m leg
    a = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                      ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert a.l_armed is True

    # that re-entry stops out → driver kills the leg
    arm_sm.mark_dead(1, _SEQ_LONG)
    # a brand-new 1m leg (bar 1001) forms in the same setup — must NOT arm (leg is dead)
    dead = arm_sm.update(M1State(bull_sos_bar=1001, bear_sos_bar=None, bull_leg_hi=104.0,
                                 bull_leg_lo=103.0, bear_leg_hi=None, bear_leg_lo=None,
                                 direction=1, new_bull_sos=True, new_bear_sos=False),
                         _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                         ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert dead.l_armed is False

    # a new break of structure (l_sos_bar goes None) resets the dead flag
    seq_dead = SimpleNamespace(l_sos_bar=None, s_sos_bar=None)
    arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, seq_dead, zone_close=102.5,
                  ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    # the next setup on a new leg (600) can arm again
    seq_new = SimpleNamespace(l_sos_bar=600, s_sos_bar=None)
    revived = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, seq_new, zone_close=102.5,
                            ny_hour=10, flat=True, be_sos_l=600, be_sos_s=None)
    assert revived.l_armed is True


def _bar1m(i, o, h, l, c):
    # last_conf_* feed the STRUCTURE runner trail; None here = no confirmed swing on this
    # synthetic 1m stream, so the trail stays off and the stage-2 floor alone holds the stop.
    return SimpleNamespace(index=i, time_ms=1_700_000_000_000 + i * 60_000,
                           open=o, high=h, low=l, close=c,
                           last_conf_high=None, last_conf_low=None)


def test_execution_fills_and_closes_a_secondary_trade():
    execu = Execution(SosFadeConfig(exec_secondary=True), initial_capital=100_000.0)
    arm = SecArm(l_armed=True, l_edge=102.618, l_sl=102.0, l_tp1=105.0, l_tp2=106.18, l_leg=1000)

    # bar A: place the resting limit (one-bar delay — no fill this bar)
    assert execu.step_secondary(_bar1m(0, 102.7, 102.8, 102.65, 102.7), arm) is None
    assert execu.is_flat
    # bar B: price dips to the limit → fills LONG as a secondary; no exit on the fill bar
    assert execu.step_secondary(_bar1m(1, 102.7, 102.8, 102.5, 102.6), arm) == 1
    assert not execu.is_flat and execu.entry_kind == "secondary"
    # bar C: price collapses through the 1m-leg stop → full stop-out, trade closes
    execu.step_secondary(_bar1m(2, 102.4, 102.5, 101.5, 101.6), arm)
    assert execu.is_flat
    assert len(execu.trades) == 1
    t = execu.trades[0]
    assert t.kind == "secondary" and t.dir == 1
    assert abs(t.entry_price - 102.618) < 1e-9
    assert t.pnl_usd < 0                                    # stopped for a loss


# ── the 1m signal object PRODUCTION builds, not the one this file hand-rolls ──────────

def test_run_dual_builds_a_1m_sig_carrying_every_field_advance_stage_reads():
    """The bug this pins: `_bar1m` above is a TEST fixture, and it carries `last_conf_*` because
    the person who wrote it knew the trail needs them. `run_dual` builds its OWN `_Bar1mSig`, and
    until 2026-08-06 that one did NOT — so `_advance_stage` raised `AttributeError` on the first
    1m bar after any secondary fill, and the re-entry had never opened a position on real data.

    Every secondary test passed throughout, because they all fed the fixture rather than the
    production object. So this test refuses to name the fields: it reads whatever `_advance_stage`
    dereferences off `sig` straight out of its source, and demands the real object carry all of
    them. Add a `sig.something` to `_advance_stage` and this fails until `run_dual` supplies it.
    """
    import inspect
    import re

    import pandas as pd

    from strategies.python.mpc_sos_fade.execution import Execution
    from strategies.python.mpc_sos_fade.strategy import MpcSosFadeStrategy

    needed = set(re.findall(r"\bsig\.(\w+)", inspect.getsource(Execution._advance_stage)))
    assert needed, "read no fields off _advance_stage — the regex or the method moved"

    seen = []
    orig = Execution.step_secondary

    def capture(self, sig1m, arm):
        seen.append(sig1m)
        return orig(self, sig1m, arm)

    def frame(minutes, n):
        idx = pd.date_range("2024-01-01", periods=n, freq=f"{minutes}min", tz="UTC")
        return pd.DataFrame({"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}, index=idx)

    Execution.step_secondary = capture
    try:
        MpcSosFadeStrategy(config=SosFadeConfig(exec_secondary=True, symbol="XAUUSD"),
                           initial_capital=10_000.0).run_dual(frame(15, 40), frame(1, 600))
    finally:
        Execution.step_secondary = orig

    assert seen, "run_dual never reached step_secondary — this test proved nothing"
    missing = sorted(f for f in needed if not hasattr(seen[0], f))
    assert not missing, (
        f"run_dual's 1m sig is missing {missing}, which _advance_stage reads on every managed "
        f"bar — any secondary trade surviving to its next 1m bar raises AttributeError")


# ─────────────────────────────────────────────────────────────────────────────
# `exec_sec_once_per_setup` — one re-entry per PRIMARY, not per 1-minute leg.
#
# Aaron read two SEC chips on one screen (2024-12-02) and asked why the feature could fire twice
# off one structure break. It can: the original latch retires the 1m LEG, and a live 15m setup
# keeps producing fresh legs. These pin the cap, the un-capped rule it replaces, and — the one
# that matters most — that the two 15m-keyed latches did not get merged into one.
# ─────────────────────────────────────────────────────────────────────────────

def _second_1m_leg():
    """A different 1m leg (bar 1001) on the SAME 15m setup — what the cap has to refuse."""
    return M1State(bull_sos_bar=1001, bear_sos_bar=None, bull_leg_hi=104.0, bull_leg_lo=103.0,
                   bear_leg_hi=None, bear_leg_lo=None, direction=1,
                   new_bull_sos=True, new_bear_sos=False)


def _armed_and_traded(cfg):
    """Arm once on the first 1m leg and fill it, the state both paths start from."""
    arm_sm = SecondaryArm(cfg)
    first = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert first.l_armed is True, "the fixture never armed — nothing below proves anything"
    arm_sm.mark_traded(1)
    return arm_sm


def test_the_cap_refuses_a_second_reentry_on_the_same_15m_setup():
    arm_sm = _armed_and_traded(SosFadeConfig(exec_secondary=True, exec_sec_once_per_setup=True))
    again = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is False, (
        "a fresh 1m leg re-armed on a 15m setup that has already had its one re-entry")
    assert again.l_edge is None, "refused but still published a resting price"


def test_with_the_cap_OFF_a_fresh_1m_leg_re_arms_on_the_same_setup():
    """The rule the cap replaces, pinned so 'off' cannot quietly become 'on'.

    Without this the cap could be made unconditional and every test above would still pass —
    the shipped default is ON, so nothing else exercises the other branch."""
    arm_sm = _armed_and_traded(SosFadeConfig(exec_secondary=True, exec_sec_once_per_setup=False))
    again = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is True, "the un-capped rule is one re-entry per 1m LEG, not per setup"


def test_the_cap_is_per_SETUP_not_per_LIFETIME():
    """A new break of structure re-opens the door. The cap bounds a cascade; it does not retire
    the feature, and reading it as a kill switch would make the measured numbers meaningless."""
    arm_sm = _armed_and_traded(SosFadeConfig(exec_secondary=True, exec_sec_once_per_setup=True))
    seq_new = SimpleNamespace(l_sos_bar=600, s_sos_bar=None)
    revived = arm_sm.update(_second_1m_leg(), _SIG_LONG, seq_new, zone_close=102.5,
                            ny_hour=10, flat=True, be_sos_l=600, be_sos_s=None)
    assert revived.l_armed is True, "a NEW 15m setup was refused its first re-entry"


def test_the_stop_out_latch_is_not_the_cap_latch():
    """`mark_dead` must still kill a leg with the cap OFF.

    Both gate on the 15m SOS bar, so the cheap implementation serves them from one latch — and
    then a risk rule (a re-entry stopped out, so this setup is finished) silently depends on a
    preference switch.

    It cannot be watched red against HEAD (the stop-out latch predates the cap and already
    worked), so its non-vacuity was proven by MUTATION: gating `_dead` on
    `exec_sec_once_per_setup` turns it red. ⚠ Note the neighbouring mutation — stamping `_dead`
    from `mark_traded` — is caught by `test_with_the_cap_OFF_...` instead, not by this. The pair
    covers the shortcut; neither test does alone."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_once_per_setup=False)
    arm_sm = SecondaryArm(cfg)
    first = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert first.l_armed is True
    arm_sm.mark_dead(1, _SEQ_LONG)
    after = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert after.l_armed is False, (
        "a stopped-out leg re-armed with the cap off — the stop-out rule is not a preference")


def test_the_secondary_and_its_cap_ship_ON():
    """Aaron's call, 2026-08-07, and it MOVES every historical figure in this repo.

    Both are asserted here rather than in a general defaults test because the pair is what
    describes the shipped book: the secondary alone is the uncapped 190-trade run."""
    cfg = SosFadeConfig()
    assert cfg.exec_secondary is True
    assert cfg.exec_sec_once_per_setup is True


# ── the minimum-stop floor on the 1m path ────────────────────────────────────────

# A 1m long: buy limit 102.618, stop at the leg origin 102.0 → a 0.618 stop distance.
_TIGHT_LONG = SecArm(l_armed=True, l_edge=102.618, l_sl=102.0, l_tp1=105.0, l_tp2=106.18,
                     l_leg=1000)
# The same leg read short: sell limit 102.0, stop above at 102.618. Same 0.618 distance.
_TIGHT_SHORT = SecArm(s_armed=True, s_edge=102.0, s_sl=102.618, s_tp1=99.0, s_tp2=98.0,
                      s_leg=1000)


def _pending(**cfg_kw):
    execu = Execution(SosFadeConfig(exec_secondary=True, **cfg_kw), initial_capital=100_000.0)
    return execu


def test_the_min_stop_floor_refuses_a_secondary_whose_stop_is_too_tight():
    """The defect this pins: `_secondary_pending` asked only `dist > 0` while `_place_entries`
    had enforced the floor since 2026-07-30, so the 1m re-entry could rest a limit the 15m path
    would have refused — and `qty = risk / dist`, so the tighter the stop the BIGGER the position.

    0.618 against a floor of ~1.03 (0.618 is 60% of it). Measured on real history, 90 of 1,956
    secondary limits rested under the shipped 0.08% floor."""
    execu = _pending(exec_min_stop_mode="% of price", exec_min_stop_val=1.0)
    assert execu._min_stop_floor(102.618) > 0.618           # the floor really does bite here
    assert execu._secondary_pending(_TIGHT_LONG) is None
    assert execu._secondary_pending(_TIGHT_SHORT) is None


def test_the_floor_lets_a_secondary_through_when_the_stop_clears_it():
    """The other half, and the one that stops the fix from being 'refuse everything'.

    ⚠ This one PASSES against HEAD and is kept deliberately: it pins the direction the old
    `dist > 0` rule already got right, which is exactly the direction a later 'simplification'
    would restore. A rule stated in only one direction is the one that gets undone."""
    execu = _pending(exec_min_stop_mode="% of price", exec_min_stop_val=0.1)
    assert execu._min_stop_floor(102.618) < 0.618
    long_pend = execu._secondary_pending(_TIGHT_LONG)
    short_pend = execu._secondary_pending(_TIGHT_SHORT)
    assert long_pend is not None and long_pend.dir == 1
    assert short_pend is not None and short_pend.dir == -1


def test_the_floor_is_LIVE_on_the_secondary_at_the_shipped_defaults():
    """`exec_min_stop_mode` has shipped "% of price" 0.08 since 2026-08-04 — it is NOT Off — so
    this guard bites in a default run rather than waiting to be switched on. That is the whole
    reason it had to be added: the 1m path was the one place the shipped floor did not reach.

    Both directions, because guarding one side and not the other is the shape of bug that would
    show up as a mysterious short-side-only sizing outlier years later."""
    execu = _pending()
    assert execu._cfg.exec_min_stop_mode == "% of price"
    assert execu._cfg.exec_min_stop_val == 0.08
    # 0.08% of 102.618 is ~$0.082, which a 0.618 stop clears comfortably
    assert execu._secondary_pending(_TIGHT_LONG) is not None
    assert execu._secondary_pending(_TIGHT_SHORT) is not None
    # …and a stop UNDER that floor is refused, on the shipped settings, on both sides
    tight_long = dataclasses.replace(_TIGHT_LONG, l_sl=102.618 - 0.05)
    tight_short = dataclasses.replace(_TIGHT_SHORT, s_sl=102.0 + 0.05)
    assert execu._secondary_pending(tight_long) is None
    assert execu._secondary_pending(tight_short) is None


def test_the_floor_is_inert_when_the_mode_is_switched_Off():
    """"Off" is a real floor of 0.0 that every positive distance clears — not a skipped check —
    so pinning the mode reproduces the pre-guard behaviour exactly."""
    execu = _pending(exec_min_stop_mode="Off")
    assert execu._min_stop_floor(102.618) == 0.0
    assert execu._secondary_pending(_TIGHT_LONG) is not None
    assert execu._secondary_pending(_TIGHT_SHORT) is not None


def test_an_unknowable_floor_refuses_the_secondary_exactly_as_it_refuses_the_primary():
    """"x ATR(14)" before the ATR has 14 bars has no floor to compare against. The 15m path
    refuses there (Pine's NA comparison reads as false), and the 1m path must not quietly
    diverge into permitting — an unknown floor is the one case where the two rules disagreeing
    would be invisible, because it only happens during warm-up."""
    execu = _pending(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=0.3)
    assert execu._atr is None                               # no 15m bar has been stepped
    assert execu._min_stop_floor(102.618) is None
    assert execu._secondary_pending(_TIGHT_LONG) is None
    assert execu._secondary_pending(_TIGHT_SHORT) is None


# ─────────────────────────────────────────────────────────────────────────────────────────────
# The LOOSENED gates — `exec_sec_require` / `exec_sec_zone_deep` / `exec_sec_zone_shallow`
# (2026-08-19). Aaron's case: in at 0.618, the stop at 0.886 gets swept, price reclaims and runs
# the setup without you. The shipped rule refuses that leg forever, because the primary never
# reached TP1. These pin the four doors and, first, that the DEFAULTS did not move.
# ─────────────────────────────────────────────────────────────────────────────────────────────

def test_the_default_gate_is_the_breakeven_rule_and_ignores_the_new_latches():
    """Watched RED by mutating `_primary_gate`'s "Breakeven" branch to `return True` — the
    second half then arms. The new latches must not leak into the shipped path: a leg whose
    primary closed (or was stopped) but never reached TP1 still arms NOTHING at the default."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True))
    yes = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None,
                        closed_sos_l=500, lost_sos_l=500)
    assert yes.l_armed is True

    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True))
    no = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                       ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None,
                       closed_sos_l=500, lost_sos_l=500)
    assert no.l_armed is False


def test_stopped_only_arms_the_leg_the_breakeven_rule_throws_away():
    """The swept-stop case. Same bar, same setup: "Stopped only" arms it, "Breakeven" does not."""
    m1, kw = _m1_bull_sos(103.0, 102.0), dict(
        zone_close=102.5, ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None,
        closed_sos_l=500, lost_sos_l=500)
    loose = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="Stopped only"))
    assert loose.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is True
    shipped = SecondaryArm(SosFadeConfig(exec_secondary=True))
    assert shipped.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is False


def test_stopped_only_refuses_a_leg_whose_primary_WON():
    """"Stopped only" is not "Any close" — a primary that reached TP1 sets `be_sos`, never
    `lost_sos`, so that leg is out of scope for this mode."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="Stopped only"))
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None,
                        closed_sos_l=500, lost_sos_l=None)
    assert out.l_armed is False


def test_any_close_takes_both_outcomes_and_none_needs_no_primary_at_all():
    kw = dict(zone_close=102.5, ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    m1 = _m1_bull_sos(103.0, 102.0)
    won = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="Any close"))
    assert won.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=500, lost_sos_l=None, **kw).l_armed
    lost = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="Any close"))
    assert lost.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=500, lost_sos_l=500, **kw).l_armed
    # ...and "None" arms with no primary record on the leg whatsoever
    bare = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="None"))
    assert bare.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=None, lost_sos_l=None, **kw).l_armed


def test_an_unknown_require_mode_REFUSES_rather_than_arming_on_everything():
    """A typo must not read as the loosest door. `None` (the string) is a real mode here, so a
    misspelling has a plausible-looking inert reading available — and taking it would put a
    re-entry on every live setup while the page still said "Breakeven"."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_require="breakeven"))
    with pytest.raises(ValueError, match="exec_sec_require"):
        arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                      ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)


def test_the_default_zone_edges_are_the_PUBLISHED_fib_levels_not_a_recomputation():
    """Identity, not near-equality. The signal already publishes 0.618 and 0.886, and computing
    them a second time off the leg would differ in the last bits — which is how a control run
    stops reproducing a stored book for no reason anybody can find."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True))
    lo, hi = arm_sm._zone_edges(_SIG_LONG)
    assert lo is _SIG_LONG.fibo_p3 and hi is _SIG_LONG.fibo_p6


def test_the_deep_edge_at_1_0_arms_where_price_closed_past_the_entry_band():
    """A 15m close of 100.5 is BEYOND 0.886 (101.14) — outside the shipped zone, inside a zone
    whose deep edge is the leg origin (100.0). That close is what a swept stop looks like."""
    m1, kw = _m1_bull_sos(103.0, 102.0), dict(
        zone_close=100.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    shipped = SecondaryArm(SosFadeConfig(exec_secondary=True))
    assert shipped.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is False
    deep = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_zone_deep=1.0))
    assert deep.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is True


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Cascade DEPTH (`exec_sec_max_per_setup`) and the secondary-only EXIT overrides
# (`exec_sec_be_at`, `exec_sec_tp1_pct`, `exec_sec_req_m1_dir`), 2026-08-19. Aaron: "what if this
# secondary re-entry also gets scratched — up to what number should we allow before settling into
# losses, and what tells us to stop taking them?"
# ─────────────────────────────────────────────────────────────────────────────────────────────

def _rearm(arm_sm, leg_bar, seq=None):
    """Fire a fresh 1m leg on the same 15m setup and return whether it armed."""
    m1 = M1State(bull_sos_bar=leg_bar, bear_sos_bar=None, bull_leg_hi=103.0, bull_leg_lo=102.0,
                 bear_leg_hi=None, bear_leg_lo=None, direction=1,
                 new_bull_sos=True, new_bear_sos=False)
    seq = seq or _SEQ_LONG
    return arm_sm.update(m1, _SIG_LONG, seq, zone_close=102.5, ny_hour=10,
                         flat=True, be_sos_l=seq.l_sos_bar, be_sos_s=None)


def test_the_depth_default_is_one_and_is_the_shipped_cap():
    """Watched RED with `depth` forced to 2 — the second leg then arms."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True))
    assert _rearm(arm_sm, 1000).l_armed is True
    arm_sm.mark_traded(1)
    assert _rearm(arm_sm, 1001).l_armed is False


def test_a_depth_of_three_allows_exactly_three_reentries_on_one_setup():
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_max_per_setup=3))
    for i, leg in enumerate((1000, 1001, 1002), start=1):
        assert _rearm(arm_sm, leg).l_armed is True, f"re-entry {i} should arm"
        arm_sm.mark_traded(1)
    assert _rearm(arm_sm, 1003).l_armed is False       # the fourth is capped


def test_the_depth_counter_is_per_SETUP_and_resets_on_a_new_break_of_structure():
    """A deeper cap must not become a lifetime budget — a new 15m SOS bar starts a fresh count.

    ⚠ The SECOND setup has to spend its FULL allowance for this to be worth anything. Checking
    only that the new setup's first re-entry arms passes against a counter that never resets,
    because the SOS-bar comparison alone already re-opens the door — that version of this test
    survived the mutation that removed the reset entirely.
    """
    seq_new = SimpleNamespace(l_sos_bar=600, s_sos_bar=None)
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_max_per_setup=2))
    for leg in (1000, 1001):                       # setup 500 spends both of its re-entries
        assert _rearm(arm_sm, leg).l_armed is True
        arm_sm.mark_traded(1)
    assert _rearm(arm_sm, 1002).l_armed is False

    for leg in (1003, 1004):                       # setup 600 must get TWO of its own
        assert _rearm(arm_sm, leg, seq_new).l_armed is True, f"leg {leg} on the new setup"
        arm_sm.mark_traded(1)
    assert _rearm(arm_sm, 1005, seq_new).l_armed is False


def test_a_stopped_reentry_still_kills_the_leg_however_deep_the_cap_is():
    """The depth counts SCRATCHES, never losses — the dead-leg rule sits underneath it."""
    arm_sm = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_max_per_setup=5))
    assert _rearm(arm_sm, 1000).l_armed is True
    arm_sm.mark_traded(1)
    arm_sm.mark_dead(1, _SEQ_LONG)          # that re-entry hit its own initial stop
    assert _rearm(arm_sm, 1001).l_armed is False


def test_a_depth_below_one_refuses_rather_than_reading_as_unlimited():
    with pytest.raises(ValueError, match="exec_sec_max_per_setup"):
        SosFadeConfig(exec_secondary=True, exec_sec_max_per_setup=0)


def test_the_1m_direction_filter_is_OFF_by_default_and_blocks_when_ON():
    down = M1State(bull_sos_bar=1000, bear_sos_bar=None, bull_leg_hi=103.0, bull_leg_lo=102.0,
                   bear_leg_hi=None, bear_leg_lo=None, direction=-1,
                   new_bull_sos=True, new_bear_sos=False)
    kw = dict(zone_close=102.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    off = SecondaryArm(SosFadeConfig(exec_secondary=True))
    assert off.update(down, _SIG_LONG, _SEQ_LONG, **kw).l_armed is True
    on = SecondaryArm(SosFadeConfig(exec_secondary=True, exec_sec_req_m1_dir=True))
    assert on.update(down, _SIG_LONG, _SEQ_LONG, **kw).l_armed is False


def _open_secondary(**cfg_kw):
    """A filled LONG secondary that has just touched TP1 (stage 1), so the stop question is live."""
    cfg = SosFadeConfig(exec_secondary=True, exec_be_buf_tk=30, **cfg_kw)
    ex = Execution(cfg)
    ex._entry_kind = "secondary"
    ex._pos_dir = 1
    ex._entry = 100.0
    ex._sl = 99.0
    ex._stage = 1
    return ex


def test_a_secondary_ratchets_to_breakeven_at_TP1_by_default():
    assert _open_secondary()._current_stop() == 100.0 + 30 * SosFadeConfig().mintick


def test_be_at_TP2_holds_the_secondarys_INITIAL_stop_through_TP1():
    """The scratch mechanism, pinned: at TP1 the shipped ladder puts the stop $0.30 above entry
    and price takes it back. "TP2" leaves the initial stop where it was."""
    assert _open_secondary(exec_sec_be_at="TP2")._current_stop() == 99.0


def test_be_at_TP2_does_NOT_touch_a_PRIMARY():
    """Secondaries only — the primary's ladder is what the Pine parity gate checks."""
    ex = _open_secondary(exec_sec_be_at="TP2")
    ex._entry_kind = "primary"
    assert ex._current_stop() == 100.0 + 30 * SosFadeConfig().mintick


def test_the_secondary_banks_its_own_TP1_percentage_and_inherits_at_minus_one():
    ex = _open_secondary()
    assert ex._tp1_pct() == SosFadeConfig().exec_tp1_pct      # -1.0 = inherit
    own = _open_secondary(exec_sec_tp1_pct=50.0)
    assert own._tp1_pct() == 50.0
    own._entry_kind = "primary"
    assert own._tp1_pct() == SosFadeConfig().exec_tp1_pct     # a primary never reads it
