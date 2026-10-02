"""The re-entry WATCH — a re-entry the bot can still take, reported before it can fire.

🔴 **Why (2026-10-01, `sos_fade_demo`, live):** the first trade closed at breakeven at 08:15 UTC
and the re-entry filled at 08:17 with no warning. The setup's thread had closed at the first fill,
so nothing said a second chance was open.

The safety property is `test_whenever_the_arm_arms_the_watch_already_calls_it_possible`: a warning
that can be absent on a bar the arm fires is the original defect. Everything else pins the words and
the life of one thread.

**Proven by mutation, 2026-10-02 — all new code, so nothing could go red at HEAD except by import
error.** Every mutation below reddened the test named, restored after, fresh bytecode per run:
gap half dropped from `outlook` → the gap announce test (and 10 others); reclaim priced off the
gap half's stop → the reclaim test; flat test dropped → still-open test; source match dropped →
RESTING test; fill branch disabled → fill test; "possible" made to require the reclaim first → the
guarantee test; `_watch_on` dropped → warm-up test; the `try` narrowed → failing-watch test; every
end reported as "expired" → 4 of 5 ending cases; void ignored → retired test; watch opened before
the memory is restored → restore test; unwarned fill left silent → that test; terminal snapshots
never drained → drained-once test; any close opening the door → no-door test; the switch ignored →
switched-off test; an unlatched gap priced anyway → the unlatched test.
"""

from __future__ import annotations

import copy
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))

from backtest.setups import DEAD, FILLED, RESTING, WATCHING  # noqa: E402
from strategies.python.sos_fade.config import SosFadeConfig  # noqa: E402
from strategies.python.sos_fade.execution import _Pending  # noqa: E402
from strategies.python.sos_fade.reentry_watch import KEY_SUFFIX  # noqa: E402
from strategies.python.sos_fade.secondary import M1State, SecondaryArm  # noqa: E402
from strategies.python.sos_fade.strategy import SosFadeStrategy  # noqa: E402

# A 15m LONG leg 100 (origin, 1.0) -> 110 (extreme, 0.0). 0.618 = 103.82, 0.886 = 101.14.
SOS = 500
SOS_MS = 1_790_820_000_000


def _sig(**kw):
    base = dict(
        fibo_dir=1, fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p6=101.14,
        fibo_p7=110.0, fibo_p10=100.0, bull_div_active=True, bear_div_active=False,
        veto_on=False, veto_rsi_ob=False, veto_rsi_os=False,
        bull_sos=False, bear_sos=False, bull_bos=False, bear_bos=False, fibo7_touched=False,
        close=104.0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _seq(l_sos=SOS, s_sos=None):
    return SimpleNamespace(l_sos_bar=l_sos, s_sos_bar=s_sos)


def _m1(**kw):
    base = dict(bull_sos_bar=None, bear_sos_bar=None, bull_leg_hi=None, bull_leg_lo=None,
                bear_leg_hi=None, bear_leg_lo=None, direction=0,
                new_bull_sos=False, new_bear_sos=False)
    base.update(kw)
    return M1State(**base)


def _cfg(**kw):
    """The live bot's re-entry shape (`sos_fade_demo`, 2026-10-02), pinned rather than defaulted."""
    base = dict(
        exec_secondary=True, exec_sec_trigger="FVG in zone + Reclaim Entry",
        exec_sec_require="Breakeven", exec_rec_require="Stopped only",
        exec_sec_stop="0.886", exec_rec_stop="1.0", exec_rec_entry_mode="Retest",
        exec_sec_once_per_setup=True, exec_sec_max_per_setup=1, exec_sec_req_div=False,
        exec_sl_buf_tk=5.0, exec_min_atr_pct=0.0, symbol="XAUUSD.p",
    )
    base.update(kw)
    return SosFadeConfig(**base)


def _rig(**cfg_kw):
    """A real order layer and a real arm, with the first trade's latches set by hand."""
    st = SosFadeStrategy(_cfg(**cfg_kw))
    ex = st.execution
    ex._bar_ms[SOS] = SOS_MS
    arm = SecondaryArm(st.config)
    return ex, arm


def _gap_ready(ex, arm):
    """First trade reached its first target and closed; the setup latched in the zone with a gap."""
    ex._be_sos_l = SOS
    ex._prim_closed_sos_l = SOS
    ex._poi_edge_l = 102.8
    arm._l_leg = SOS


def _stopped(ex):
    ex._prim_closed_sos_l = SOS
    ex._prim_lost_sos_l = SOS


def _snaps(ex):
    return [s for s in ex.live_setups() if s.reentry_of is not None]


# ── when it is announced ─────────────────────────────────────────────────────────────────────
def test_a_gap_reentry_is_announced_when_the_first_trade_closes_after_its_first_target():
    """MUTATION: drop the gap half from `outlook` and nothing is reported."""
    ex, arm = _rig()
    _gap_ready(ex, arm)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    [s] = _snaps(ex)
    assert s.state == WATCHING and s.side == 1
    assert s.reentry_of == ex._setup_key(True, SOS, SOS_MS)
    assert s.key == s.reentry_of + KEY_SUFFIX
    assert s.origin_ms == SOS_MS
    # The gap half rests at the LIVE gap edge once latched — the price `_edge` would use.
    assert s.planned_entry == 102.8
    assert s.stop == pytest.approx(101.14 - 5 * 0.01)  # the 0.886 less the buffer
    assert [c.met for c in s.confluences] == [True, True, True]


def test_a_reclaim_reentry_names_the_level_and_the_origin_stop():
    """The plan's terms for the reclaim: the price is the 0.886, the stop the leg's 1.0 plus the
    buffer. MUTATION: price it off the gap half's anchor and the stop reads 101.09."""
    ex, arm = _rig()
    _stopped(ex)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    [s] = _snaps(ex)
    assert s.planned_entry == 101.14
    assert s.stop == pytest.approx(100.0 - 5 * 0.01)
    assert s.zone is None
    assert s.confluences[0].detail == "First trade was stopped at its original stop"
    assert [c.met for c in s.confluences] == [True, False, False]


def test_an_unlatched_gap_reentry_shows_the_zone_and_no_price():
    ex, arm = _rig()
    _gap_ready(ex, arm)
    arm._l_leg = None
    ex.reentry_watch.observe(arm, _sig(), _seq())
    [s] = _snaps(ex)
    assert s.planned_entry is None
    assert s.zone == (103.82, 101.14)


def test_nothing_is_announced_while_the_first_trade_is_still_open():
    """Breakeven is stamped at the first TARGET, while the trade is still running. MUTATION: drop
    the `is_flat` test and a warning goes out an hour before the first trade has closed."""
    ex, arm = _rig()
    _gap_ready(ex, arm)
    ex._pos_dir = 1
    ex.reentry_watch.observe(arm, _sig(), _seq())
    assert _snaps(ex) == []


def test_nothing_is_announced_when_the_first_trade_opened_no_door():
    """Closed before its first target and not at its original stop: neither half applies."""
    ex, arm = _rig()
    ex._prim_closed_sos_l = SOS
    ex.reentry_watch.observe(arm, _sig(), _seq())
    assert _snaps(ex) == []


def test_nothing_is_announced_with_the_reentry_switched_off():
    ex, arm = _rig(exec_secondary=False, exec_scale_mode="Trail")
    _gap_ready(ex, arm)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    assert _snaps(ex) == []


# ── the life of the thread ───────────────────────────────────────────────────────────────────
def test_it_reports_RESTING_only_while_ITS_OWN_order_is_on_the_book():
    """MUTATION: drop the `pend.src == look.half` test and a level-memory order reads as this."""
    ex, arm = _rig()
    _gap_ready(ex, arm)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    ex._pend_sec = _Pending(1, 102.8, 1.0, 101.09, 105.0, 106.18, SOS, src="lvl")
    assert _snaps(ex)[0].state == WATCHING
    ex._pend_sec = _Pending(1, 102.8, 1.0, 101.09, 105.0, 106.18, SOS, src="gap")
    [s] = _snaps(ex)
    assert s.state == RESTING and s.entry == 102.8 and s.stop == 101.09


def test_a_fill_closes_the_thread_as_RE_ENTERED_and_it_never_reopens():
    """MUTATION: keep the watch open on a fill and the same setup is announced again."""
    ex, arm = _rig()
    _gap_ready(ex, arm)
    w = ex.reentry_watch
    w.observe(arm, _sig(), _seq())
    arm._l_sos = SOS
    arm.mark_traded(1)
    ex._pos_dir = 1
    w.observe(arm, _sig(), _seq(), filled=1)
    done = ex.drain_setups()
    [s] = [x for x in done if x.reentry_of]
    assert s.state == FILLED and s.reason == "Re-entered."
    ex._pos_dir = 0  # the re-entry closed
    w.observe(arm, _sig(), _seq())
    assert _snaps(ex) == []


@pytest.mark.parametrize("sig_kw, words", [
    (dict(bear_sos=True), "Structure broke the other way"),
    (dict(bull_bos=True), "A new break of structure ended the setup"),
    (dict(fibo7_touched=True), "final target"),
    (dict(close=99.0), "past where the move started"),
    (dict(), "The setup expired"),
])
def test_the_setup_ending_closes_the_thread_with_the_reason_on_that_bar(sig_kw, words):
    ex, arm = _rig()
    _gap_ready(ex, arm)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    ex.reentry_watch.observe(arm, _sig(**sig_kw), _seq(l_sos=None))
    [s] = _snaps(ex)
    assert s.state == DEAD and words in s.reason


@pytest.mark.parametrize("retire, words", [
    ("used", "one re-entry was already used"),
    ("void", "Price reached the stop level before it came back"),
])
def test_a_retired_reentry_closes_the_thread_with_why(retire, words):
    """`used` arrives across a restart (the saved memory); `void` is the reclaim's stop reached."""
    ex, arm = _rig()
    _stopped(ex)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    if retire == "used":
        arm._l_used, arm._l_used_n = SOS, 1
    else:
        arm._l_void = True
    ex.reentry_watch.observe(arm, _sig(), _seq())
    [s] = _snaps(ex)
    assert s.state == DEAD and words in s.reason


def test_a_fill_with_no_warning_open_still_gets_a_thread():
    """Should never happen — the tool counts it — but a silent re-entry is the original defect."""
    ex, arm = _rig()
    _gap_ready(ex, arm)
    arm._l_sos = SOS
    arm.mark_traded(1)
    ex._pos_dir = 1
    ex.reentry_watch.observe(arm, _sig(), _seq(), filled=1)
    [s] = _snaps(ex)
    assert s.state == FILLED


def test_the_terminal_snapshot_is_drained_once():
    ex, arm = _rig()
    _gap_ready(ex, arm)
    ex.reentry_watch.observe(arm, _sig(), _seq())
    ex.reentry_watch.observe(arm, _sig(bear_sos=True), _seq(l_sos=None))
    assert len([s for s in ex.drain_setups() if s.reentry_of]) == 1
    assert [s for s in ex.drain_setups() if s.reentry_of] == []


# ── the guarantee ────────────────────────────────────────────────────────────────────────────
def test_whenever_the_arm_arms_the_watch_already_calls_it_possible():
    """🔴 THE property: on every combination of the first trade's outcome, the cap, the dead leg,
    the void, the latch, a gap and the zone, if `update` arms a side then `outlook` — read BEFORE
    the update, from the same state — calls that side possible and not retired. So a warning can
    never be missing on a bar a re-entry rests.

    MUTATION: make `outlook` require `_l_rec` for the reclaim half (a stricter "possible") and
    this reddens on the bar the reclaim arms.
    """
    armed_seen = 0
    for (be, lost, used, dead, void, rec, seen, leg, poi, close) in itertools.product(
        (None, SOS), (None, SOS), (False, True), (False, True), (False, True), (False, True),
        (False, True), (False, True), (None, 102.8), (102.5, 108.0),
    ):
        ex, arm = _rig()
        closed = SOS if (be or lost) else None
        arm._l_used, arm._l_used_n = (SOS, 1) if used else (None, 0)
        arm._l_dead = SOS if dead else None
        arm._l_void, arm._l_rec, arm._l_seen = void, rec, seen
        arm._l_leg = SOS if leg else None
        sig, seq = _sig(), _seq()
        look, _ = arm.outlook(sig, seq, be, None, closed, None, lost, None, poi, None)
        out = copy.deepcopy(arm).update(
            _m1(), sig, seq, zone_close=close, ny_hour=10, flat=True, be_sos_l=be,
            be_sos_s=None, closed_sos_l=closed, lost_sos_l=lost, poi_edge_l=poi,
            bar_high=101.5, bar_low=101.0,
        )
        if out.l_armed:
            armed_seen += 1
            assert look is not None and not look.retired, (be, lost, used, dead, void, rec)
    assert armed_seen > 0  # the grid really reaches the arm, or this proves nothing


# ── the clock that feeds it ──────────────────────────────────────────────────────────────────
def _clock():
    st = SosFadeStrategy(_cfg())
    from strategies.python.sos_fade.dual_clock import DualClock

    clock = DualClock(st, stack=None, tf_primary_ms=900_000)
    ex = st.execution
    ex._bar_ms[SOS] = SOS_MS
    clock.last_sig, clock.last_seq = _sig(), _seq()
    _gap_ready(ex, clock.arm_sm)
    return clock, ex


def test_the_watch_is_silent_through_a_warm_up():
    """A live warm-up replays the primary alone; a watch opened there describes history.
    MUTATION: drop `_watch_on` and the warm-up's own replayed trade is announced."""
    clock, ex = _clock()
    clock._watch_reentry()
    assert _snaps(ex) == []


def test_restoring_the_memory_starts_the_watch_with_the_memory_already_back():
    """A used setup is never opened after a restart; an unused one is reported at once, so the
    start-up reconcile keeps its thread instead of closing and re-announcing it."""
    clock, ex = _clock()
    clock.restore_reentry_memory(None)
    assert len(_snaps(ex)) == 1

    clock, ex = _clock()
    clock.restore_reentry_memory({"arm": {"l": {"used_ms": SOS_MS, "used_n": 1}, "s": {}}})
    assert _snaps(ex) == []


def test_a_failing_watch_never_takes_the_step_down_and_says_why():
    """REPORTING ONLY inside the live bar loop. MUTATION: drop the `try` and this raises."""
    clock, ex = _clock()
    clock._watch_on = True

    def boom(*a, **k):
        raise RuntimeError("bad snapshot")

    clock.arm_sm.outlook = boom
    clock._watch_reentry()
    assert ex.reentry_watch.failed == "RuntimeError: bad snapshot"
    assert _snaps(ex) == []
