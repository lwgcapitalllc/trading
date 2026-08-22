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


def _shift_cfg(**kw):
    """A re-entry config PINNED to the 1-minute-shift shape, for the tests that hand-drive it.

    ⚠ PINNED, NOT DEFAULTED, and the distinction is the point. The shift was the default until
    2026-08-20 and is not any more — the gap trigger is. A test below that kept taking the default
    would still RUN, and would arm on a completely different input (a resting price handed in from
    the primary, not a 1m leg), so it would stop exercising the branch its name claims. That is the
    same trap `test_run_dual_primary_is_identical_to_run_when_secondary_off` pins against one level
    up. The tests that assert what the DEFAULTS ARE do not use this helper, by design.
    """
    kw.setdefault("exec_sec_trigger", "1m shift")
    kw.setdefault("exec_sec_stop", "1m leg")
    return SosFadeConfig(exec_secondary=True, **kw)


def test_arm_fires_and_rests_the_right_limit():
    cfg = _shift_cfg()
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
    cfg = _shift_cfg()
    arm_sm = SecondaryArm(cfg)
    # the primary on this 15m leg has NOT reached breakeven (be_sos_l is None): a primary that
    # opened and got stopped at its initial stop leaves no re-entry.
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    assert out.l_armed is False                             # a re-entry is never the first trade


def test_dead_leg_blocks_further_reentries():
    """Once a re-entry on a 15m leg hits its initial stop, `mark_dead` kills the leg — no more
    re-entries on it (even on a fresh 1m shift) until a new break of structure resets it."""
    cfg = _shift_cfg()
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
    arm_sm = _armed_and_traded(_shift_cfg(exec_sec_once_per_setup=True))
    again = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is False, (
        "a fresh 1m leg re-armed on a 15m setup that has already had its one re-entry")
    assert again.l_edge is None, "refused but still published a resting price"


def test_with_the_cap_OFF_a_fresh_1m_leg_re_arms_on_the_same_setup():
    """The rule the cap replaces, pinned so 'off' cannot quietly become 'on'.

    Without this the cap could be made unconditional and every test above would still pass —
    the shipped default is ON, so nothing else exercises the other branch."""
    arm_sm = _armed_and_traded(_shift_cfg(exec_sec_once_per_setup=False))
    again = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is True, "the un-capped rule is one re-entry per 1m LEG, not per setup"


def test_the_cap_is_per_SETUP_not_per_LIFETIME():
    """A new break of structure re-opens the door. The cap bounds a cascade; it does not retire
    the feature, and reading it as a kill switch would make the measured numbers meaningless."""
    arm_sm = _armed_and_traded(_shift_cfg(exec_sec_once_per_setup=True))
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
    cfg = _shift_cfg(exec_sec_once_per_setup=False)
    arm_sm = SecondaryArm(cfg)
    first = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert first.l_armed is True
    arm_sm.mark_dead(1, _SEQ_LONG)
    after = arm_sm.update(_second_1m_leg(), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert after.l_armed is False, (
        "a stopped-out leg re-armed with the cap off — the stop-out rule is not a preference")


def test_the_secondary_ships_OFF_and_its_cap_stays_ON():
    """Aaron's call, 2026-08-21, REVERSING his 2026-08-07 call that shipped it ON.

    ⚠ **This moves every historical figure in this repo that was produced on the defaults**, the
    same way turning it on did. The shipped book is now the PRIMARY book: 181 trades over
    2018-09-14 -> 2026-08-14, where the pair shipped ON gave 235.

    ⚠ **The CAP stays ON and that is not an oversight.** It only has meaning while the secondary
    is enabled, and a reader who turns the secondary on gets the once-per-setup rule with it rather
    than the uncapped book by accident. Flipping the feature off is not a reason to unpin a rule
    that governs it.

    ⚠ **It cannot move `compare_strategy.py`**: the re-entry needs a 1m stream through `run_dual`
    and the gate replays the export's own single frame, so no re-entry has ever fired inside it.
    Verified rather than argued - exit 0 at warmups 100/200/500/1000 on the same export, before and
    after this flip."""
    cfg = SosFadeConfig()
    assert cfg.exec_secondary is False
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
    arm_sm = SecondaryArm(_shift_cfg())
    yes = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None,
                        closed_sos_l=500, lost_sos_l=500)
    assert yes.l_armed is True

    arm_sm = SecondaryArm(_shift_cfg())
    no = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                       ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None,
                       closed_sos_l=500, lost_sos_l=500)
    assert no.l_armed is False


def test_stopped_only_arms_the_leg_the_breakeven_rule_throws_away():
    """The swept-stop case. Same bar, same setup: "Stopped only" arms it, "Breakeven" does not."""
    m1, kw = _m1_bull_sos(103.0, 102.0), dict(
        zone_close=102.5, ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None,
        closed_sos_l=500, lost_sos_l=500)
    loose = SecondaryArm(_shift_cfg(exec_sec_require="Stopped only"))
    assert loose.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is True
    shipped = SecondaryArm(_shift_cfg())
    assert shipped.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is False


def test_stopped_only_refuses_a_leg_whose_primary_WON():
    """"Stopped only" is not "Any close" — a primary that reached TP1 sets `be_sos`, never
    `lost_sos`, so that leg is out of scope for this mode."""
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_require="Stopped only"))
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None,
                        closed_sos_l=500, lost_sos_l=None)
    assert out.l_armed is False


def test_any_close_takes_both_outcomes_and_none_needs_no_primary_at_all():
    kw = dict(zone_close=102.5, ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    m1 = _m1_bull_sos(103.0, 102.0)
    won = SecondaryArm(_shift_cfg(exec_sec_require="Any close"))
    assert won.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=500, lost_sos_l=None, **kw).l_armed
    lost = SecondaryArm(_shift_cfg(exec_sec_require="Any close"))
    assert lost.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=500, lost_sos_l=500, **kw).l_armed
    # ...and "None" arms with no primary record on the leg whatsoever
    bare = SecondaryArm(_shift_cfg(exec_sec_require="None"))
    assert bare.update(m1, _SIG_LONG, _SEQ_LONG, closed_sos_l=None, lost_sos_l=None, **kw).l_armed


def test_an_unknown_require_mode_REFUSES_rather_than_arming_on_everything():
    """A typo must not read as the loosest door. `None` (the string) is a real mode here, so a
    misspelling has a plausible-looking inert reading available — and taking it would put a
    re-entry on every live setup while the page still said "Breakeven"."""
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_require="breakeven"))
    with pytest.raises(ValueError, match="exec_sec_require"):
        arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                      ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)


def test_the_default_zone_edges_are_the_PUBLISHED_fib_levels_not_a_recomputation():
    """Identity, not near-equality. The signal already publishes 0.618 and 0.886, and computing
    them a second time off the leg would differ in the last bits — which is how a control run
    stops reproducing a stored book for no reason anybody can find."""
    arm_sm = SecondaryArm(_shift_cfg())
    lo, hi = arm_sm._zone_edges(_SIG_LONG)
    assert lo is _SIG_LONG.fibo_p3 and hi is _SIG_LONG.fibo_p6


def test_the_deep_edge_at_1_0_arms_where_price_closed_past_the_entry_band():
    """A 15m close of 100.5 is BEYOND 0.886 (101.14) — outside the shipped zone, inside a zone
    whose deep edge is the leg origin (100.0). That close is what a swept stop looks like."""
    m1, kw = _m1_bull_sos(103.0, 102.0), dict(
        zone_close=100.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    shipped = SecondaryArm(_shift_cfg())
    assert shipped.update(m1, _SIG_LONG, _SEQ_LONG, **kw).l_armed is False
    deep = SecondaryArm(_shift_cfg(exec_sec_zone_deep=1.0))
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
    arm_sm = SecondaryArm(_shift_cfg())
    assert _rearm(arm_sm, 1000).l_armed is True
    arm_sm.mark_traded(1)
    assert _rearm(arm_sm, 1001).l_armed is False


def test_a_depth_of_three_allows_exactly_three_reentries_on_one_setup():
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_max_per_setup=3))
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
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_max_per_setup=2))
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
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_max_per_setup=5))
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
    off = SecondaryArm(_shift_cfg())
    assert off.update(down, _SIG_LONG, _SEQ_LONG, **kw).l_armed is True
    on = SecondaryArm(_shift_cfg(exec_sec_req_m1_dir=True))
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


def test_the_secondary_banks_HALF_by_default_and_inherits_at_minus_one():
    """50 since 2026-08-20. It is the half of the pair that turns a favourable excursion into a
    booked one — with nothing banked, 15 of 54 re-entries over 7.9 years finished flat."""
    assert SosFadeConfig().exec_sec_tp1_pct == 50.0
    assert _open_secondary()._tp1_pct() == 50.0
    inherit = _open_secondary(exec_sec_tp1_pct=-1.0)
    assert inherit._tp1_pct() == SosFadeConfig().exec_tp1_pct      # -1.0 = inherit
    own = _open_secondary(exec_sec_tp1_pct=25.0)
    assert own._tp1_pct() == 25.0
    own._entry_kind = "primary"
    assert own._tp1_pct() == SosFadeConfig().exec_tp1_pct          # a primary never reads it


# ── the 15m divergence requirement (exec_sec_req_div) ────────────────────────────
# Watched RED against HEAD before the switch existed: with a no-divergence 15m signal the
# ON case already passed (the hardcoded test refused it) and BOTH OFF cases failed, because
# `sig.bull_div_active` was read directly and no config could reach it.

_SIG_LONG_NODIV = SimpleNamespace(**{**vars(_SIG_LONG), "bull_div_active": False})


def test_the_divergence_requirement_is_OFF_by_default_and_still_refuses_a_sweep_armed_leg_when_ON():
    """Turned ON: no live 15m divergence, no re-entry — whatever else lines up. That was the rule
    until 2026-08-20, and it is what made the feature unreachable on a sweep-armed book
    (`exec_arm_div` off, which is still the default), so it now ships OFF. Both halves are asserted
    here: the new default, and that the old behaviour is still reachable and still refuses."""
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_req_div=True))
    assert SosFadeConfig().exec_sec_req_div is False
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG_NODIV, _SEQ_LONG,
                        zone_close=102.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert out.l_armed is False


def test_with_the_requirement_OFF_the_same_leg_arms_and_prices_identically():
    """OFF removes ONLY the divergence question — the limit, stop and targets are untouched."""
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_req_div=False))
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG_NODIV, _SEQ_LONG,
                        zone_close=102.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert out.l_armed is True
    assert abs(out.l_edge - (103.0 - 1.0 * 0.382)) < 1e-9
    assert out.l_sl == 102.0
    assert out.l_tp1 == 105.0 and out.l_tp2 == 106.18


def test_the_requirement_gates_the_LATCH_too_not_only_the_arm():
    """Both halves, because the Pine tested it twice. Gating only the arm would leave a leg
    latched from a divergence-less shift and let it fire on a LATER bar — a re-entry the ON
    path never had, appearing on a config that claims to be the shipped one.

    ⚠ This one CANNOT go red against HEAD — HEAD hardcodes the requirement, so the latch was
    gated by construction. Proved by MUTATION instead: replacing the latch's divergence test
    with `True` (arm-only gating) reddens exactly this test and none of the other 40."""
    arm_sm = SecondaryArm(_shift_cfg(exec_sec_req_div=True))   # PINNED — ships OFF since 2026-08-20
    # the 1m shift happens with no divergence → nothing may be latched…
    arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG_NODIV, _SEQ_LONG,
                  zone_close=102.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    # …so a later bar that DOES have a divergence, but no fresh shift, still has no leg to arm.
    quiet = M1State(bull_sos_bar=1000, bear_sos_bar=None, bull_leg_hi=103.0, bull_leg_lo=102.0,
                    bear_leg_hi=None, bear_leg_lo=None, direction=1,
                    new_bull_sos=False, new_bear_sos=False)
    assert arm_sm.update(quiet, _SIG_LONG, _SEQ_LONG, zone_close=102.5, ny_hour=10,
                         flat=True, be_sos_l=500, be_sos_s=None).l_armed is False


def test_the_requirement_is_NOT_exec_arm_div_and_neither_reads_the_other():
    """The trap this switch exists for. `exec_arm_div` says what may arm the PRIMARY; this says
    whether the RE-ENTRY needs a divergence. Turning the primary's divergence arming ON must not
    silently satisfy the re-entry, and turning this OFF must not let the primary arm on one."""
    cfg = _shift_cfg(exec_arm_div=True, exec_sec_req_div=True)
    out = SecondaryArm(cfg).update(_m1_bull_sos(103.0, 102.0), _SIG_LONG_NODIV, _SEQ_LONG,
                                   zone_close=102.5, ny_hour=10, flat=True,
                                   be_sos_l=500, be_sos_s=None)
    assert out.l_armed is False
    assert _shift_cfg(exec_sec_req_div=False).exec_arm_div is False


# ── the FVG-in-zone trigger + the stop anchor (exec_sec_trigger / exec_sec_stop) ─────
# Watched RED against HEAD: every one fails on the missing config field or on the arm refusing,
# because before this the ONLY way to arm was a 1m break of structure and the ONLY stop was the
# 1m leg origin.

def _m1_quiet(conf_low=None, conf_high=None):
    """A 1m bar with NO structure event at all — the gap trigger must not need one."""
    return M1State(bull_sos_bar=None, bear_sos_bar=None, bull_leg_hi=None, bull_leg_lo=None,
                   bear_leg_hi=None, bear_leg_lo=None, direction=0,
                   new_bull_sos=False, new_bear_sos=False,
                   conf_high=conf_high, conf_low=conf_low)


_GAP_KW = dict(zone_close=102.5, ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)


def test_the_gap_trigger_arms_with_no_1m_shift_at_all():
    """The whole point: the 2025-10-29 long never got a usable 1m shift, so the trigger must not
    require one. Entry is the PRIMARY's own point-of-interest price, passed in — not recomputed."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="swing low")
    out = SecondaryArm(cfg).update(_m1_quiet(conf_low=101.5), _SIG_LONG, _SEQ_LONG,
                                   poi_edge_l=102.8, **_GAP_KW)
    assert out.l_armed is True
    assert out.l_edge == 102.8          # the primary's edge, untouched by any retrace
    assert out.l_sl == 101.5            # the 1m engine's last confirmed swing low
    assert out.l_tp1 == 105.0 and out.l_tp2 == 106.18   # same 15m targets as always


def test_the_gap_trigger_refuses_when_the_setup_has_no_gap_to_enter_on():
    """No point-of-interest price means no gap qualified — which must be a REFUSAL, never a
    fallback onto some other level. `None` here is 'nothing to enter on', not 'enter anywhere'."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="swing low")
    out = SecondaryArm(cfg).update(_m1_quiet(conf_low=101.5), _SIG_LONG, _SEQ_LONG,
                                   poi_edge_l=None, **_GAP_KW)
    assert out.l_armed is False and out.l_edge is None


def test_the_gap_trigger_refuses_when_the_1m_swing_has_not_confirmed_yet():
    """No stop anchor is the same class of answer as no entry — refuse. Sizing is risk divided by
    stop distance, so an unnoticed fallback here is the 54-lot defect wearing a different hat."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="swing low")
    out = SecondaryArm(cfg).update(_m1_quiet(conf_low=None), _SIG_LONG, _SEQ_LONG,
                                   poi_edge_l=102.8, **_GAP_KW)
    assert out.l_armed is False


def test_each_stop_anchor_prices_the_same_entry_differently():
    """Stop placement flipped the sign on the first case measured, so each anchor is pinned."""
    for mode, expected in (("swing low", 101.5), ("0.886", 101.14), ("1.0", 100.0)):
        cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                            exec_sec_stop=mode)
        out = SecondaryArm(cfg).update(_m1_quiet(conf_low=101.5), _SIG_LONG, _SEQ_LONG,
                                       poi_edge_l=102.8, **_GAP_KW)
        assert out.l_armed is True, mode
        assert out.l_sl == expected, mode


def test_an_entry_the_wrong_side_of_its_stop_refuses_rather_than_sizing_off_it():
    """A long whose gap edge sits BELOW its stop is not a tight trade, it is a negative one, and
    `qty = risk / distance` would happily divide by it."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="swing low")
    out = SecondaryArm(cfg).update(_m1_quiet(conf_low=103.5), _SIG_LONG, _SEQ_LONG,
                                   poi_edge_l=102.8, **_GAP_KW)
    assert out.l_armed is False


def test_the_gap_trigger_and_the_0_886_stop_are_the_DEFAULTS_since_2026_08_20():
    """What ships. Both moved together on 2026-08-20 and they have to: the gap trigger has no 1m
    leg to stop behind, and pairing it with the old anchor is refused at construction."""
    assert SosFadeConfig().exec_sec_trigger == "FVG in zone"
    assert SosFadeConfig().exec_sec_stop == "0.886"
    assert SosFadeConfig().exec_sec_req_div is False    # the gate that kept it from ever firing


def test_the_1m_shift_path_still_ignores_the_gap_edge_when_it_is_pinned_back_on():
    """The pre-2026-08-20 rule, reachable and unchanged — a 1m shift, a 1m-leg stop, and no
    interest in the primary's edge even when one is passed."""
    out = SecondaryArm(_shift_cfg()).update(
        _m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, poi_edge_l=999.0, **_GAP_KW)
    assert out.l_armed is True
    assert abs(out.l_edge - (103.0 - 1.0 * 0.382)) < 1e-9   # NOT 999.0
    assert out.l_sl == 102.0


def test_the_gap_trigger_with_a_1m_leg_stop_REFUSES_at_construction():
    """That pair has no stop at all — the gap trigger latches no 1m leg. A silent no-trade would
    read on the page as 'the gap trigger found nothing', which is a different finding entirely."""
    with pytest.raises(ValueError, match="1m leg"):
        SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                      exec_sec_stop="1m leg")


def test_an_unknown_trigger_or_stop_REFUSES_rather_than_running_the_shipped_rule():
    with pytest.raises(ValueError, match="exec_sec_trigger"):
        SosFadeConfig(exec_secondary=True, exec_sec_trigger="fvg")
    with pytest.raises(ValueError, match="exec_sec_stop"):
        SosFadeConfig(exec_secondary=True, exec_sec_stop="swing")


# ── the re-entry's own first target, in R (exec_sec_tp_r) ────────────────────────────
# Watched RED against HEAD: the field did not exist, so every one fails at construction.

def _fill_secondary(entry, sl, tp1, tp2, direction=1, **cfg_kw):
    """Fill a secondary at `entry` through the real entry path, and hand back its ladder."""
    from strategies.python.mpc_sos_fade.execution import Decision, _Pending
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg)
    pend = _Pending(direction, entry, 1.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind="secondary")
    return ex


def test_the_R_target_DEFAULTS_to_1_25R_and_at_minus_one_the_ladder_is_the_15m_fib():
    """1.25R since 2026-08-20 — measured, and it is half of a pair (the other half is how much
    banks there). -1 restores the 15m fib rung the primary uses, and that path must still work."""
    assert SosFadeConfig().exec_sec_tp_r == 1.25
    shipped = _fill_secondary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0)
    assert shipped._tp1 == 102.5 and shipped._tp2 == 106.0   # 1.25 x its own 2.00 risk
    inherit = _fill_secondary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_sec_tp_r=-1.0)
    assert inherit._tp1 == 105.0 and inherit._tp2 == 106.0


def test_a_1R_target_replaces_the_first_rung_and_leaves_the_second_alone():
    """1R for a long risking 2.00 from 100.00 is 102.00 — its OWN risk, not the 15m fib."""
    ex = _fill_secondary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_sec_tp_r=1.0)
    assert ex._tp1 == 102.0
    assert ex._tp2 == 106.0          # untouched — this lever moves one rung


def test_the_R_target_mirrors_for_a_short():
    ex = _fill_secondary(entry=100.0, sl=102.0, tp1=95.0, tp2=94.0, direction=-1,
                         exec_sec_tp_r=1.5)
    assert ex._tp1 == 97.0           # 100 - 1.5 * 2.00


def test_the_R_target_prices_off_the_INITIAL_stop_so_the_trail_cannot_drag_it_in():
    """The target must mean the risk the trade was SIZED against. If it were re-derived from the
    live stop, every ratchet would pull the target closer and 1R would stop meaning 1R."""
    ex = _fill_secondary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_sec_tp_r=2.0)
    assert ex._tp1 == 104.0
    ex._sl = 99.5                    # the trail ratchets…
    assert ex._tp1 == 104.0          # …and the target does not move


def test_the_R_target_never_touches_a_PRIMARY():
    """A primary keeps the 15m ladder whatever this says — it is a re-entry lever only, and the
    shipped 164-trade book must be reproducible with it set."""
    from strategies.python.mpc_sos_fade.execution import Decision, _Pending
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_tp_r=1.0)
    ex = Execution(cfg)
    pend = _Pending(1, 100.0, 1.0, 98.0, 105.0, 106.0, None)
    bar = SimpleNamespace(index=1, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, 100.0, bar, Decision(index=1), kind="primary")
    assert ex._tp1 == 105.0


def test_a_zero_or_negative_R_target_REFUSES_rather_than_sitting_on_the_entry():
    with pytest.raises(ValueError, match="exec_sec_tp_r"):
        SosFadeConfig(exec_secondary=True, exec_sec_tp_r=0.0)
    with pytest.raises(ValueError, match="exec_sec_tp_r"):
        SosFadeConfig(exec_secondary=True, exec_sec_tp_r=-0.5)


# ── the re-entry's own risk size (`exec_sec_risk_pct`) ────────────────────────────────
#
# Watched RED against HEAD on 2026-08-20 — every one of the six failed before
# `exec_sec_risk_pct` existed (AttributeError on the default test, wrong lot on the rest).
#
# The lever exists because the re-entries deepen the PRIMARY's own drawdown rather than
# diversifying it: 51.8% -> 68.1% for +27.8R over 7.9 years, both versions troughing in the
# same 2023-04 -> 2024-10 stretch. Sizing is the only honest way to buy that back, because
# nothing here changes WHICH bars a re-entry takes.


def _sec_qty(**cfg_kw):
    """Lot the real sizing path rests for the shared long arm, under `cfg_kw`."""
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg, initial_capital=100_000.0)
    arm = SecArm(l_armed=True, l_edge=102.618, l_sl=102.0, l_tp1=105.0, l_tp2=106.18, l_leg=1000)
    pend = ex._secondary_pending(arm)
    assert pend is not None, "the shared arm must rest an order — the fixture is the control"
    return pend.qty


def test_the_reentry_risk_knob_DEFAULTS_to_half_the_primarys_risk():
    """50 since 2026-08-20, and the shipped lot must actually BE half — a default that reads 50
    while still sizing full weight is exactly the failure this section exists to catch."""
    assert SosFadeConfig().exec_sec_risk_pct == 50.0
    assert _sec_qty() == pytest.approx(_sec_qty(exec_sec_risk_pct=100.0) / 2.0)


def test_100_means_the_same_risk_as_the_primary():
    """The identity the number is defined against, and what reproduces any figure measured before
    2026-08-20: the whole account risk over the stop distance, with no re-entry discount at all."""
    assert _sec_qty(exec_sec_risk_pct=100.0) == pytest.approx(
        (100_000.0 * SosFadeConfig().exec_risk_pct / 100.0) / (102.618 - 102.0))


def test_the_knob_is_a_PERCENTAGE_of_the_primary_risk_not_a_percentage_of_equity():
    """The bug this pins: reading it as an absolute %-of-equity would make 50 mean *five times*
    the shipped size when the primary risks 10%. It must compose with the primary's own number."""
    base = _sec_qty(exec_risk_pct=10.0, exec_sec_risk_pct=100.0)
    assert _sec_qty(exec_risk_pct=10.0, exec_sec_risk_pct=50.0) == pytest.approx(base / 2.0)
    assert _sec_qty(exec_risk_pct=20.0, exec_sec_risk_pct=50.0) == pytest.approx(base)


def test_a_bigger_reentry_is_allowed_because_the_knob_only_sizes():
    assert _sec_qty(exec_sec_risk_pct=200.0) == pytest.approx(
        _sec_qty(exec_sec_risk_pct=100.0) * 2.0)


def _primary_qty(monkeypatch, **cfg_kw):
    """Lot the real PRIMARY placer rests for one armed long, under `cfg_kw`.

    `_place_entries` is driven directly with the arming, the block recorder, the stop anchor and
    the fib freeze stubbed out. What is left running is the sizing expression itself, which is
    the whole point — a test that stubbed the sizing too would pass against any wiring.
    """
    from strategies.python.mpc_sos_fade import execution as _ex_mod
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg, initial_capital=100_000.0)
    monkeypatch.setattr(ex, "_armed", lambda *a, **k: (True, False))
    monkeypatch.setattr(ex, "_record_blocks", lambda *a, **k: None)
    monkeypatch.setattr(ex, "_sl_anchor", lambda *a, **k: 102.0)
    monkeypatch.setattr(_ex_mod, "_freeze_fib", lambda sig: None)
    sig = SimpleNamespace(index=1, time_ms=0, fibo_p1=105.0, fibo_p2=104.0,
                          fibo_p3=103.0, fibo_p7=106.0)
    seq = SimpleNamespace(l_sos_bar=1000, s_sos_bar=None)
    ex._place_entries(sig, seq, SimpleNamespace(long_veto=False, short_veto=False), 102.618, None)
    assert ex._pend_long is not None, "the primary never rested an order — the fixture is broken"
    return ex._pend_long.qty


def test_the_knob_never_touches_a_PRIMARY(monkeypatch):
    """Secondaries only — this is what keeps every stored primary figure valid, exactly as the
    other re-entry-only levers do."""
    full = _primary_qty(monkeypatch)
    assert _primary_qty(monkeypatch, exec_sec_risk_pct=25.0) == pytest.approx(full)
    assert _primary_qty(monkeypatch, exec_sec_risk_pct=400.0) == pytest.approx(full)


def test_zero_or_negative_reentry_risk_is_REFUSED_not_clamped():
    """A zero lot fills, closes and lands in the trade list at 0R — a trade that looks taken and
    moved nothing. The honest way to stop taking re-entries is to switch them off."""
    for bad in (0.0, -1.0, -50.0):
        with pytest.raises(ValueError, match="exec_sec_risk_pct"):
            SosFadeConfig(exec_secondary=True, exec_sec_risk_pct=bad)
    # ...and it is not asked at all when re-entries are off, same as every other re-entry input.
    assert SosFadeConfig(exec_secondary=False, exec_sec_risk_pct=0.0).exec_sec_risk_pct == 0.0


# ── RECLAIM ENTRY — the swept-stop re-entry ──────────────────────────────
# The only trigger of the three built for a primary that LOST: stopped at the deep edge, price
# reclaims that level instead of breaking the leg, and a limit rests back AT it for the retest.
# Every test below drives `SecondaryArm.update` one 1m bar at a time, because the whole feature is
# a state machine over bars — a single-call test could not tell "reclaimed" from "was never below".

def _rec_cfg(**kw):
    """A re-entry config PINNED to the reclaim shape.

    ⚠ PINNED for the same reason `_shift_cfg` is: the shipped trigger is the gap one, so a test
    that took the default would still run and would arm on a completely different input.
    ⚠ `exec_sec_require="Stopped only"` is part of the SHAPE, not a variation. Under the default
    breakeven gate this trigger cannot fire at all — a primary that reached breakeven is not one
    that was stopped at the deep edge — and `test_reclaim_cannot_fire_under_the_breakeven_gate`
    is the test that says so out loud.
    """
    kw.setdefault("exec_sec_trigger", "Reclaim Entry")
    # The reclaim half reads its OWN fields (`exec_rec_*`) rather than the shared `exec_sec_*`
    # ones, so that the gap half can be live alongside it wanting the opposite precondition and a
    # different stop. These setdefaults are the shipped defaults restated, so a test that overrides
    # nothing is testing the shipped configuration.
    kw.setdefault("exec_rec_stop", "1.0")
    kw.setdefault("exec_rec_require", "Stopped only")
    return SosFadeConfig(exec_secondary=True, **kw)


def _m1_no_event():
    """A 1m bar with NO structure event — what the reclaim trigger runs on. It reads price, not
    structure, so every one of its bars looks like this."""
    return M1State(bull_sos_bar=None, bear_sos_bar=None, bull_leg_hi=None, bull_leg_lo=None,
                   bear_leg_hi=None, bear_leg_lo=None, direction=0,
                   new_bull_sos=False, new_bear_sos=False)


def _feed(arm_sm, bars, sig=_SIG_LONG, seq=_SEQ_LONG, lost_l=500, lost_s=None, zone_close=99.0):
    """Run (high, low) 1m bars through the arm. `zone_close` defaults to 99.0 — BELOW the whole
    retrace zone, which is where a stopped-out primary actually leaves the last 15m close. If the
    reclaim ever starts depending on the zone gate, every one of these tests goes red."""
    out = []
    for hi, lo in bars:
        out.append(arm_sm.update(_m1_no_event(), sig, seq, zone_close=zone_close, ny_hour=10,
                                 flat=True, be_sos_l=None, be_sos_s=None,
                                 closed_sos_l=None, closed_sos_s=None,
                                 lost_sos_l=lost_l, lost_sos_s=lost_s,
                                 bar_high=hi, bar_low=lo))
    return out


def test_reclaim_arms_at_the_deep_edge_with_the_leg_origin_stop():
    """The whole design in one pass: stopped at the 0.886 (101.14), price stays under it, then
    trades back through — and a limit rests AT 101.14 with the stop at the 1.0 (100.0)."""
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(101.0, 100.6),     # gate opens; still under the deep edge
                         (101.1, 100.8),     # still under
                         (101.5, 100.9)])    # RECLAIM — high pushes back through 101.14
    assert out[0].l_armed is False
    assert out[1].l_armed is False
    assert out[2].l_armed is True
    assert out[2].l_edge == pytest.approx(101.14)   # the limit rests AT the deep edge
    assert out[2].l_sl == pytest.approx(100.0)      # stop = the 1.0, the level that kills the leg
    assert out[2].l_leg == 500                      # the "leg" is the SETUP, so the caps still work


def test_reclaim_does_not_fire_on_the_bar_the_gate_opens():
    """On the stop-out bar price is AT the deep edge by definition, and that bar's own wick back
    through it is the stop being hit — not a reclaim. Firing here would enter every stopped trade
    immediately, which is the opposite of the rule."""
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(105.0, 100.5)])    # first bar, high far above the deep edge
    assert out[0].l_armed is False


def test_reclaim_never_arms_while_price_stays_below_the_level():
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(101.0, 100.9)] * 30)
    assert all(o.l_armed is False for o in out)


def test_reclaim_is_voided_by_the_stop_level_and_stays_voided():
    """Price reaching the 1.0 before the retest ends the setup's re-entry. A resting limit whose
    stop is already breached is not a trade anyone would take, and a later reclaim is a different
    leg's move."""
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(101.0, 100.6),
                         (101.0, 99.9),      # touches the 1.0 → voided
                         (101.5, 100.9),     # a reclaim AFTER the void must not resurrect it
                         (102.0, 101.5)])
    assert [o.l_armed for o in out] == [False, False, False, False]


def test_reclaim_ignores_the_zone_gate():
    """The zone reads the last-closed 15m CLOSE, and a primary is stopped at the deep edge BY a
    15m bar closing through it — so the zone is usually false at the only moment this can fire.
    Pinned at a close of 99.0, below the entire zone."""
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(101.0, 100.6), (101.5, 100.9)], zone_close=99.0)
    assert out[1].l_armed is True


def test_reclaim_cannot_fire_under_the_breakeven_gate():
    """A primary that reached breakeven is not one that was stopped at the deep edge, so the pair
    is inert — and it must be inert SILENTLY rather than arming off some other gate.

    ⚠ It moves `exec_rec_require`, NOT `exec_sec_require`. The shared field is the GAP half's and
    the reclaim stopped reading it when the two became combinable; a test still pointed at the
    shared one would pass whatever this half did."""
    arm_sm = SecondaryArm(_rec_cfg(exec_rec_require="Breakeven"))
    out = _feed(arm_sm, [(101.0, 100.6), (101.5, 100.9), (102.0, 101.2)])
    assert all(o.l_armed is False for o in out)


def test_reclaim_without_the_bar_extremes_takes_no_trades():
    """A caller that does not pass the 1m bar's high/low gets NO re-entries — never a different
    rule. The other two triggers do not need them, so this is the one way the feature can be
    half-wired, and a silent fallback would report it as 'the reclaim found nothing'."""
    arm_sm = SecondaryArm(_rec_cfg())
    out = [arm_sm.update(_m1_no_event(), _SIG_LONG, _SEQ_LONG, zone_close=99.0, ny_hour=10,
                         flat=True, be_sos_l=None, be_sos_s=None,
                         closed_sos_l=None, closed_sos_s=None,
                         lost_sos_l=500, lost_sos_s=None) for _ in range(5)]
    assert all(o.l_armed is False for o in out)


def test_reclaim_short_side_mirrors_the_long():
    """A down-leg: 0.0 = 100 (the low, the target), 1.0 = 110 (the origin). The 0.886 sits at
    108.86, and a reclaim is price trading back DOWN through it."""
    sig = SimpleNamespace(
        fibo_dir=-1, fibo_p7=100.0, fibo_p10=110.0, fibo_p3=106.18, fibo_p6=108.86,
        fibo_p2=105.0, fibo_p1=103.82, bull_div_active=False, bear_div_active=True,
        veto_on=False, veto_rsi_ob=False, veto_rsi_os=False)
    seq = SimpleNamespace(l_sos_bar=None, s_sos_bar=700)
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(109.4, 109.0), (109.3, 108.5)], sig=sig, seq=seq,
                lost_l=None, lost_s=700, zone_close=111.0)
    assert out[0].s_armed is False
    assert out[1].s_armed is True
    assert out[1].s_edge == pytest.approx(108.86)
    assert out[1].s_sl == pytest.approx(110.0)


def test_reclaim_setup_death_clears_the_latch():
    """A new break of structure must start the state machine over. Carrying a reclaim across
    setups would arm the next one off the last one's move."""
    arm_sm = SecondaryArm(_rec_cfg())
    _feed(arm_sm, [(101.0, 100.6), (101.5, 100.9)])          # reclaimed
    dead = SimpleNamespace(l_sos_bar=None, s_sos_bar=None)
    _feed(arm_sm, [(101.5, 100.9)], seq=dead, lost_l=None)   # setup dies
    fresh = SimpleNamespace(l_sos_bar=600, s_sos_bar=None)
    out = _feed(arm_sm, [(101.5, 100.9)], seq=fresh, lost_l=600)
    assert out[0].l_armed is False                            # needs its own reclaim, on a later bar


def test_reclaim_arms_once_per_setup():
    arm_sm = SecondaryArm(_rec_cfg())
    out = _feed(arm_sm, [(101.0, 100.6), (101.5, 100.9)])
    assert out[1].l_armed is True
    arm_sm.mark_traded(1)
    after = _feed(arm_sm, [(101.6, 100.9)])
    assert after[0].l_armed is False


# ── the COMBINED trigger — both halves live at once ─────────────────────────────────────────────
#
# The whole design rests on one structural fact: a primary either reaches TP1 (stamping the
# breakeven latch) or closes at stage 0 (stamping the loss latch), never both. So the two halves
# fire on disjoint setups and can share one position slot, one latch and one `_traded` stamp.
# These tests drive that fact directly — each feeds a setup that is stopped or is at breakeven,
# never one that is somehow both, because the execution layer cannot produce one.


def _both_cfg(**kw):
    """The combined trigger at its shipped-adjacent defaults: the gap half on `Breakeven`, the
    reclaim half on `Stopped only`. Config validation refuses any other pairing, so these two are
    not a choice this helper is making."""
    kw.setdefault("exec_sec_trigger", "FVG in zone + Reclaim Entry")
    kw.setdefault("exec_sec_require", "Breakeven")
    kw.setdefault("exec_rec_require", "Stopped only")
    return SosFadeConfig(exec_secondary=True, **kw)


def _feed_both(arm_sm, bars, be_l=None, lost_l=None, zone_close=99.0, poi=103.0):
    """Feed 1m (high, low) bars with BOTH halves' inputs supplied on every bar.

    `be_l` / `lost_l` are the two mutually exclusive primary outcomes; passing one leaves the
    other half's gate shut, which is what the real execution layer does. `poi` is the primary's
    own resting price, the only thing the gap half enters on.
    """
    out = []
    for hi, lo in bars:
        out.append(arm_sm.update(_m1_no_event(), _SIG_LONG, _SEQ_LONG, zone_close=zone_close,
                                 ny_hour=10, flat=True, be_sos_l=be_l, be_sos_s=None,
                                 closed_sos_l=None, closed_sos_s=None,
                                 lost_sos_l=lost_l, lost_sos_s=None,
                                 poi_edge_l=poi, poi_edge_s=None,
                                 bar_high=hi, bar_low=lo))
    return out


def test_combined_arms_the_reclaim_on_a_stopped_setup_with_the_reclaims_own_stop():
    """A STOPPED primary is the reclaim's case. It must rest at the deep edge with the reclaim's
    own leg-origin stop — not at the primary's resting price with the gap half's 0.886."""
    out = _feed_both(SecondaryArm(_both_cfg()),
                     [(101.0, 100.6), (101.5, 100.9)], lost_l=500)
    assert out[1].l_armed is True
    assert out[1].l_src == "reclaim"
    assert out[1].l_edge == pytest.approx(101.14)   # the deep edge, not the 103.0 POI
    assert out[1].l_sl == pytest.approx(100.0)      # the 1.0, not the gap half's 0.886


def test_combined_arms_the_gap_on_a_breakeven_setup_with_the_gaps_own_stop():
    """A BREAKEVEN primary is the gap half's case, and it is unchanged by the reclaim being live
    beside it: the limit rests at the primary's own price with the shared 0.886 stop."""
    out = _feed_both(SecondaryArm(_both_cfg()),
                     [(103.5, 102.0)], be_l=500, zone_close=102.5)
    assert out[0].l_armed is True
    assert out[0].l_src == "gap"
    assert out[0].l_edge == pytest.approx(103.0)    # the primary's resting price
    assert out[0].l_sl == pytest.approx(101.14)     # the 0.886


def test_combined_never_lets_the_gap_half_latch_a_setup_the_primary_LOST():
    """🔴 The one that would be silent. Every other gap condition is satisfied here — the setup is
    live, the last 15m close sits INSIDE the zone, a resting price exists — and only the
    precondition separates the halves. Without the gate on the gap latch this arms at 103.0 with a
    101.14 stop: a plausible-looking order at the wrong price, on a setup that belongs to the
    reclaim. Nothing raises, and the R column simply reads differently."""
    out = _feed_both(SecondaryArm(_both_cfg()),
                     [(101.0, 100.6), (101.5, 100.9)], lost_l=500, zone_close=102.5)
    assert all(o.l_src != "gap" for o in out)
    # 🔴 THE FIRST BAR IS THE ASSERTION THAT MATTERS AND IT WAS MISSING. Price has not reclaimed
    # yet, so nothing may be armed — but the gap block latches the same 15m SOS bar the reclaim
    # would, and the reclaim expresses "price has come back" THROUGH that latch. Without the gate
    # on the gap latch the side is latched here, the reclaim is judged to own it, and the order
    # rests at the deep edge one bar before price ever returned to it. The mutation harness found
    # this: removing the guard reddened nothing at all until this line existed.
    assert out[0].l_armed is False
    assert out[1].l_src == "reclaim"
    assert out[1].l_edge == pytest.approx(101.14)


def test_combined_leaves_a_setup_that_did_neither_alone():
    """No breakeven latch and no loss latch = a primary still open, or one that never traded.
    Neither half may arm off it."""
    out = _feed_both(SecondaryArm(_both_cfg()),
                     [(101.0, 100.6), (101.5, 100.9), (103.5, 102.0)], zone_close=102.5)
    assert all(o.l_armed is False for o in out)
    assert all(o.l_src is None for o in out)


def test_the_reclaim_alone_reads_its_own_fields_not_the_shared_ones():
    """The reclaim half reads `exec_rec_*` under the plain value exactly as under the combined
    one, so the trigger means the same thing in both. Moving the SHARED stop must not move it."""
    out = _feed(SecondaryArm(_rec_cfg(exec_sec_stop="0.886")),
                [(101.0, 100.6), (101.5, 100.9)])
    assert out[1].l_armed is True
    assert out[1].l_sl == pytest.approx(100.0)      # the reclaim's own 1.0, not the shared 0.886


def test_the_combined_trigger_refuses_a_precondition_pairing_that_can_overlap():
    """Breakeven/Stopped-only is the ONLY pairing that cannot both be true of one setup, and it is
    what lets the halves share a latch. Anything else is refused at construction rather than
    racing at run time."""
    for sec, rec in (("Any close", "Stopped only"), ("Breakeven", "None"),
                     ("None", "None"), ("Stopped only", "Stopped only")):
        with pytest.raises(ValueError, match="cannot both be true"):
            _both_cfg(exec_sec_require=sec, exec_rec_require=rec)


def test_the_reclaim_refuses_a_stop_anchor_it_cannot_price():
    """Its entry is a FIXED price, so a 1m swing can land on either side of it. Refused for the
    plain value and the combined one alike."""
    for trigger in ("Reclaim Entry", "FVG in zone + Reclaim Entry"):
        for anchor in ("1m leg", "swing low"):
            with pytest.raises(ValueError, match="exec_rec_stop"):
                SosFadeConfig(exec_secondary=True, exec_sec_trigger=trigger,
                              exec_sec_require="Breakeven", exec_rec_require="Stopped only",
                              exec_rec_stop=anchor)


def test_the_combined_trigger_still_refuses_the_gap_halfs_impossible_stop():
    """`1m leg` has nothing to read under the gap half whichever value selected it — the guard
    reads "is the gap half live", not the literal string."""
    with pytest.raises(ValueError, match="1m leg"):
        _both_cfg(exec_sec_stop="1m leg")


def test_the_gap_trigger_prices_off_the_gap_even_when_a_1m_SHIFT_latched_the_side():
    """🔴 The regression the control replay caught, and no unit test saw it.

    The 1-minute latch (section 3) runs under EVERY single-value trigger, including the two that
    have no 1m leg to price off. So on a bar carrying a 1m structure event the side is latched
    "1m shift" while the operator has selected the gap. Which rule prices the order is the
    CONFIGURED trigger's, always — key it off whichever block latched last and this bar arms at a
    38.2% retrace of a 1-minute leg, a rule nobody switched on.

    Nothing raises when it is wrong. On the shipped book it silently added 4 re-entries and 4.9R,
    and the only way it surfaced was re-running the unchanged configuration and finding it moved.

    ⚠ THIS TEST CANNOT FAIL FOR THAT REASON AND THE SIBLING BELOW IS THE ONE THAT PINS IT — said
    out loud rather than left for the next reader to assume. On a bar carrying BOTH a 1m event and
    a gap price the gap block runs second and overwrites the shift latch, so the two rules agree
    here and only the sibling's no-gap-price case can tell them apart. What this one pins is the
    positive: a gap arm reports itself as the gap and rests at the gap price.
    """
    # The SHIPPED 0.886 stop, not `swing low`: the shared 1m-SOS helper carries no confirmed swing,
    # so that anchor would refuse for a reason unrelated to what this test is about.
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="0.886")
    arm_sm = SecondaryArm(cfg)
    # A real 1m shift of structure, 101.0 → 103.0, on a bar that also carries a gap price.
    out = arm_sm.update(_m1_bull_sos(103.0, 101.0), _SIG_LONG, _SEQ_LONG,
                        poi_edge_l=102.8, **_GAP_KW)
    assert out.l_armed is True
    assert out.l_src == "gap"
    assert out.l_edge == 102.8          # the gap price — NOT 103.0 - (2.0 * 0.382) = 102.236
    assert out.l_sl == pytest.approx(101.14)


def test_the_gap_trigger_refuses_a_1m_SHIFT_latch_when_no_gap_price_exists():
    """The other half of the same rule, and the half that actually moved the book. With no gap
    price the gap trigger has nothing to enter on and must refuse — even though a 1-minute leg is
    sitting right there, fully valid, and the previous line of code was happy to use it."""
    cfg = SosFadeConfig(exec_secondary=True, exec_sec_trigger="FVG in zone",
                        exec_sec_stop="0.886")
    out = SecondaryArm(cfg).update(_m1_bull_sos(103.0, 101.0), _SIG_LONG, _SEQ_LONG,
                                   poi_edge_l=None, **_GAP_KW)
    assert out.l_armed is False and out.l_edge is None


def test_the_combined_value_prices_by_the_precondition_even_when_a_1m_shift_latched():
    """A 1m structure event may move the shared latch — it always has, under every trigger — but it
    must not change WHICH half prices the side. Ownership is the open precondition, so a stopped
    setup stays the reclaim's however many 1-minute events land on it.

    ⚠ This test was originally called "…turns the 1m shift latch OFF", which is what the code did
    for one iteration. Suppressing that latch made the combined book's halves behave differently
    from the same halves run alone, so the rule changed and the name had to change with it — a
    test whose name outlives its rule is the next reader's wrong answer."""
    arm_sm = SecondaryArm(_both_cfg())
    # ⚠ `zone_close` sits INSIDE the retrace band here, unlike every other reclaim test. That is
    # deliberate and it is what makes the test able to fail: the 1m latch requires the zone, so at
    # the reclaim's realistic below-the-band close it would not fire whatever this rule said, and
    # the test would pass against a broken guard. Measured — it did, until this line changed.
    # The reclaim itself ignores the zone, so moving it changes nothing about what is being tested.
    kw = dict(zone_close=102.5, ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None,
              closed_sos_l=None, closed_sos_s=None, lost_sos_l=500, lost_sos_s=None,
              poi_edge_l=103.0, poi_edge_s=None)
    # bar 1 opens the reclaim's gate; bar 2 reclaims AND carries a 1m shift of structure.
    arm_sm.update(_m1_no_event(), _SIG_LONG, _SEQ_LONG, bar_high=101.0, bar_low=100.6, **kw)
    out = arm_sm.update(_m1_bull_sos(103.0, 101.0), _SIG_LONG, _SEQ_LONG,
                        bar_high=101.5, bar_low=100.9, **kw)
    assert out.l_armed is True
    assert out.l_src == "reclaim"
    assert out.l_edge == pytest.approx(101.14)   # the deep edge, not a 1-minute retrace
