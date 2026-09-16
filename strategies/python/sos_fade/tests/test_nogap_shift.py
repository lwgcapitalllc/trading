"""The no-gap shift entry (`exec_ngs`) — the 15m context, the fast-bar arm, and the trade it opens.

Aaron, 2026-09-15: a setup that armed, SOS'd and tagged the 0.5 with no fair-value gap to rest on
is taken on the first 1-minute shift in its direction, at market, stop at the 1.0, whole position
off at a multiple of its own risk. Screened as Run 28, replayed as Run 29.

Leg used throughout (bull): 0.0 = 110, 1.0 = 100 — the fixtures of `test_execution.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "strategies" / "python"))

from sos_fade import Execution, SosFadeConfig  # noqa: E402
from sos_fade.dual_clock import FastSig  # noqa: E402
from sos_fade.secondary import NGS_SRC, NoGapCtx, NoGapShiftArm, SecArm  # noqa: E402
from sos_fade.tests.test_execution import _cfg, _seq_long_ready, _sig  # noqa: E402

_CTX = NoGapCtx(dir=1, sos_ms=900_000, stop=100.0, extreme=110.0)


def _ngs_cfg(**kw):
    base = dict(exec_ngs=True, exec_sec_fill_tf_min=1, exec_req_fvg=True)
    base.update(kw)
    return _cfg(**base)


# ── the arm ─────────────────────────────────────────────────────────────────────


def test_a_shift_inside_the_leg_arms_at_the_close_with_the_1_0_stop_and_a_3R_target():
    arm = NoGapShiftArm(3.0).update([_CTX, None], True, False, h=104.5, l=103.5, c=104.0)
    assert arm.l_armed and not arm.s_armed
    assert (arm.l_edge, arm.l_sl, arm.l_src) == (104.0, 100.0, NGS_SRC)
    assert arm.l_tp1 == pytest.approx(116.0)          # 104 + 3 x (104 - 100)
    assert arm.l_tp2 > arm.l_tp1                      # parked beyond, so the ladder never stages off it


def test_a_shift_the_wrong_way_does_not_arm():
    """Watched RED by mutation: reading `shifted_bear` for a long arms here."""
    arm = NoGapShiftArm(3.0).update([_CTX, None], False, True, h=104.5, l=103.5, c=104.0)
    assert not arm.l_armed


def test_a_wick_to_the_stop_retires_the_setup_for_good():
    """Past the 1.0 the setup is lost. A shift on a LATER bar must not revive it.

    Watched RED by mutation: removing the `_dead.add` on a touch arms the second bar."""
    a = NoGapShiftArm(3.0)
    assert not a.update([_CTX, None], False, False, h=101.0, l=99.9, c=100.5).l_armed
    assert not a.update([_CTX, None], True, False, h=104.5, l=103.5, c=104.0).l_armed


def test_a_wick_through_the_extreme_retires_it_too():
    """The move already happened without us."""
    a = NoGapShiftArm(3.0)
    a.update([_CTX, None], False, False, h=110.5, l=108.0, c=109.0)
    assert not a.update([_CTX, None], True, False, h=104.5, l=103.5, c=104.0).l_armed


def test_a_taken_setup_is_never_taken_twice():
    a = NoGapShiftArm(3.0)
    a.retire_key((1, 900_000))
    assert not a.update([_CTX, None], True, False, h=104.5, l=103.5, c=104.0).l_armed


# ── the 15m context ─────────────────────────────────────────────────────────────


def test_the_context_is_built_only_when_there_is_no_gap_to_rest_on():
    """The whole population. With the gap requirement off the engine falls back to a 0.618 limit,
    so there IS an edge and the no-gap entry must stand aside.

    Watched RED by mutation: dropping `edge is None` from the gate builds a context in the
    second half."""
    ex = Execution(_ngs_cfg())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ctx = ex.ngs_ctx[0]
    assert ctx is not None and (ctx.dir, ctx.stop, ctx.extreme) == (1, 100.0, 110.0)
    assert ex.ngs_ctx[1] is None

    ex2 = Execution(_ngs_cfg(exec_req_fvg=False))
    ex2.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex2.ngs_ctx == (None, None)


def test_the_context_is_off_unless_the_entry_is_on():
    ex = Execution(_cfg(exec_req_fvg=True))
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex.ngs_ctx == (None, None)


def test_a_marked_setup_builds_no_context():
    ex = Execution(_ngs_cfg())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.ngs_mark_traded(1, ex.ngs_ctx[0].sos_ms)
    ex.step(_sig(2, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex.ngs_ctx[0] is None


# ── the trade ───────────────────────────────────────────────────────────────────


def _bar(i, o, h, l, c):
    return FastSig(i, 10_000_000 + i * 60_000, o, h, l, c, None, None)


def test_the_trade_enters_at_the_next_open_and_banks_everything_at_3R():
    """Market fill on the bar AFTER the arm, first rung re-priced off the real fill, whole position
    off there, and the closed trade names its trigger.

    Watched RED by mutation: dropping the `NGS_SRC` branch from `_first_rung` prices the rung off
    the re-entry's 1.25R and books +1.25R instead of +3R."""
    ex = Execution(_ngs_cfg())
    arm = NoGapShiftArm(3.0).update([_CTX, None], True, False, h=104.5, l=103.5, c=104.0)
    ex.step_secondary(_bar(0, 103.8, 104.5, 103.5, 104.0), arm)
    assert ex.is_flat
    assert ex.step_secondary(_bar(1, 104.2, 104.6, 104.0, 104.4), SecArm()) == 1
    ex.step_secondary(_bar(2, 104.4, 105.0, 104.3, 104.8), SecArm())
    ex.step_secondary(_bar(3, 104.8, 118.0, 104.7, 117.0), SecArm())
    assert ex.is_flat
    t = ex.trades[-1]
    assert (t.kind, t.src, t.entry_price) == ("secondary", NGS_SRC, 104.2)
    assert t.exit_price == pytest.approx(104.2 + 3 * 4.2)
    assert t.r == pytest.approx(3.0)


def test_the_setting_refuses_a_fast_clock_it_was_not_measured_on():
    with pytest.raises(ValueError, match="1 minute"):
        SosFadeConfig(exec_ngs=True, exec_sec_fill_tf_min=5)
