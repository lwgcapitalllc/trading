"""The fib each B-LEG trade is priced off — recorded so the lab's chart can draw it.

This fork prices its whole trade off a fib on the frozen SOS leg (entry 0.5, stop 1.0, TP1 0.0),
but it overrides `_place_entries` and so recorded NOTHING until 2026-08-11 — the Fibs layer was
absent on every B-LEG run while the bot was the more fib-native of the two.

The load-bearing test here is the CONVENTION one. This bot's own vocabulary calls its entry band
"the 0.382-0.5 pocket", measuring up from the leg ORIGIN; a drawn fib measures down from the leg
EXTREME. Both name the same two prices. Recording the wrong one puts a real-looking ladder on the
chart whose rungs sit at the wrong retracements — the exact failure the A+ ladder cannot have,
because there the strategy reads its levels off an engine that already chose a convention.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))

from mpc_sos_fade.execution import _FIB_RATIOS as _APLUS_RATIOS  # noqa: E402

from mpc_bleg.execution import _FIB_RATIOS, _band_fib  # noqa: E402


def test_a_long_ladder_puts_the_entry_stop_and_tp1_on_their_own_rungs():
    """A bull leg 1000 -> 1100. The bot rests at 1050 (band 0.5), stops at 1000 (leg origin) and
    takes TP1 at 1100 (the broken swing extreme). Those three must BE rungs, not near them."""
    fib = _band_fib(ext=1100.0, inv=1000.0, direction=1, leg_ms=1_700_000_000_000)
    lv = dict(fib.levels)
    assert lv[0.0] == 1100.0  # TP1 — the leg extreme
    assert lv[0.5] == 1050.0  # entry — the band's near edge
    assert lv[1.0] == 1000.0  # stop — the leg origin
    assert fib.start_ms == 1_700_000_000_000


def test_a_short_ladder_is_the_mirror():
    """A bear leg 1100 -> 1000: stop ABOVE at the origin, TP1 below at the extreme."""
    fib = _band_fib(ext=1000.0, inv=1100.0, direction=-1, leg_ms=1_700_000_000_000)
    lv = dict(fib.levels)
    assert lv[0.0] == 1000.0
    assert lv[0.5] == 1050.0
    assert lv[1.0] == 1100.0


def test_the_band_far_edge_is_recorded_as_0_618_not_0_382():
    """⚠ THE CONVENTION TEST — the one that makes the drawn ladder mean what the labels say.

    `bleg.py` computes the band's far edge as `origin + range*0.382` and calls it 0.382, because it
    measures from the ORIGIN. A drawn fib measures from the EXTREME, where that same price is
    0.618. Recording it under 0.382 would shift every rung on the chart onto the wrong retracement
    while still looking like a perfectly ordinary fib.
    """
    fib = _band_fib(ext=1100.0, inv=1000.0, direction=1, leg_ms=1)
    lv = dict(fib.levels)
    band_far_edge = 1000.0 + (1100.0 - 1000.0) * 0.382  # exactly what bleg.py stores as `l_bot`
    assert lv[0.618] == band_far_edge
    assert lv[0.382] != band_far_edge


def test_the_ladder_matches_the_a_plus_bot_rung_for_rung():
    """Both bots' fibs are drawn on ONE chart, so a ratio has to mean one thing. If the A+ ladder
    ever gains or loses a rung this fails, rather than the two silently drifting apart."""
    assert _FIB_RATIOS == tuple(r for r, _ in _APLUS_RATIOS)


def test_an_undatable_leg_records_nothing_rather_than_a_fib_with_no_start():
    """All-or-nothing, like the A+ bot. A leg whose swing predates the replay window has no honest
    start time here, and a ladder drawn from the entry bar would misreport where the leg began."""
    assert _band_fib(ext=1100.0, inv=1000.0, direction=1, leg_ms=None) is None
    assert _band_fib(ext=None, inv=1000.0, direction=1, leg_ms=1) is None
    assert _band_fib(ext=1000.0, inv=1000.0, direction=1, leg_ms=1) is None  # zero-height leg


def test_the_tracker_freezes_the_leg_with_the_band_and_re_freezes_on_migration():
    """`*_ext`/`*_leg_ms` must be taken in the same breath as the band. If a migration replaced the
    band and kept the old leg, the chart would draw one leg's fib around another leg's entry."""
    from mpc_bleg import BLegConfig, BLegTracker

    tr = BLegTracker(BLegConfig(), tf_seconds=900)

    def sig(index, close, high, low, **kw):
        base = dict(
            index=index,
            close=close,
            high=high,
            low=low,
            bull_sos=False,
            bear_sos=False,
            bull_bos_high=None,
            bull_bos_low=None,
            bear_bos_high=None,
            bear_bos_low=None,
            bull_bos_high_ms=None,
            bull_bos_low_ms=None,
            bear_bos_high_ms=None,
            bear_bos_low_ms=None,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    seq = SimpleNamespace(bleg_arm_l=False, bleg_arm_s=False)

    st = tr.update(
        sig(
            0,
            1050,
            1100,
            1000,
            bull_sos=True,
            bull_bos_high=1100.0,
            bull_bos_low=1000.0,
            bull_bos_high_ms=2000,
            bull_bos_low_ms=1000,
        ),
        seq,
    )
    assert st.l_ext == 1100.0
    assert st.l_leg_ms == 1000  # the EARLIER anchor — where the leg began

    # A second SOS on a different leg re-freezes the band, so the recorded leg must move with it.
    st = tr.update(
        sig(
            1,
            2050,
            2100,
            2000,
            bull_sos=True,
            bull_bos_high=2100.0,
            bull_bos_low=2000.0,
            bull_bos_high_ms=9000,
            bull_bos_low_ms=8000,
        ),
        seq,
    )
    assert st.l_ext == 2100.0
    assert st.l_leg_ms == 8000
    assert st.l_inv == 2000.0  # the band moved too — one leg, not two


def test_the_recorded_leg_is_not_the_tracking_target():
    """`*_tgt` keeps climbing after the freeze; `*_ext` must not. They are different numbers and
    reusing `tgt` would stretch the fib to wherever price ran, which is not the leg."""
    from mpc_bleg import BLegConfig, BLegTracker

    tr = BLegTracker(BLegConfig(), tf_seconds=900)

    def sig(index, close, high, low, **kw):
        base = dict(
            index=index,
            close=close,
            high=high,
            low=low,
            bull_sos=False,
            bear_sos=False,
            bull_bos_high=None,
            bull_bos_low=None,
            bear_bos_high=None,
            bear_bos_low=None,
            bull_bos_high_ms=None,
            bull_bos_low_ms=None,
            bear_bos_high_ms=None,
            bear_bos_low_ms=None,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    seq = SimpleNamespace(bleg_arm_l=False, bleg_arm_s=False)
    tr.update(
        sig(
            0,
            1050,
            1100,
            1000,
            bull_sos=True,
            bull_bos_high=1100.0,
            bull_bos_low=1000.0,
            bull_bos_high_ms=2000,
            bull_bos_low_ms=1000,
        ),
        seq,
    )
    st = tr.update(sig(1, 1200, 1250, 1180), seq)  # price runs well past the leg extreme
    assert st.l_tgt == 1250.0
    assert st.l_ext == 1100.0
