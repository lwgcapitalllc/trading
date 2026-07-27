"""B-LEG tests — offline, no network.

Two layers: hand-traced BLegTracker unit tests (band-freeze maths, arm, tap, staleness
death) driven with SimpleNamespace stand-ins for Signals/SeqState, and an end-to-end
driver run on the real engine stack over synthetic multi-day bars (proves the whole chain
wires up, records one decision per post-warmup bar, and books only finite trades).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "strategies" / "python"))
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))

from _synth import synth_bars  # noqa: E402
from mpc_bleg import BLegConfig, BLegTracker, MpcBLegStrategy  # noqa: E402


def _sig(index, close, high, low, *, bull_sos=False, bear_sos=False,
         bbh=None, bbl=None, sbh=None, sbl=None):
    return SimpleNamespace(
        index=index, close=close, high=high, low=low,
        bull_sos=bull_sos, bear_sos=bear_sos,
        bull_bos_high=bbh, bull_bos_low=bbl, bear_bos_high=sbh, bear_bos_low=sbl)


def _seq(bleg_arm_l=False, bleg_arm_s=False):
    return SimpleNamespace(bleg_arm_l=bleg_arm_l, bleg_arm_s=bleg_arm_s)


# ── BLEG_MAX conversion (Pine: days → bars, round-half-away-from-zero) ─────────────
def test_bleg_max_bars_from_days():
    # 1.25 days on 15m (900s) = the original 120 bars
    assert BLegTracker(BLegConfig(bleg_max_days=1.25), tf_seconds=900).bleg_max == 120
    # 1 day on 5m (300s) = 288 bars
    assert BLegTracker(BLegConfig(bleg_max_days=1.0), tf_seconds=300).bleg_max == 288
    # never below 1
    assert BLegTracker(BLegConfig(bleg_max_days=1.0), tf_seconds=10_000_000).bleg_max == 1


# ── band freeze on a bull SOS (Pine 3697-3710) ────────────────────────────────────
def test_band_freeze_long():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    # leg 100 → 110, this bar's high 112. top = 0.5, bot = 0.382, inv = origin.
    st = tr.update(_sig(10, close=108, high=112, low=104, bull_sos=True, bbh=110, bbl=100),
                   _seq())
    assert st.l_top == 105.0                    # 100 + 10*0.5
    assert abs(st.l_bot - 103.82) < 1e-9        # 100 + 10*0.382
    assert st.l_inv == 100.0                    # leg origin (fib 1.0)
    assert st.l_tgt == 112.0                    # expansion extreme = this bar's high
    assert st.l_on is False and st.l_bar is None  # frozen, not armed yet


# ── target extends until armed, then arm freezes it (Pine 3728-3737) ──────────────
def test_arm_and_target_freeze():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    # a later expansion bar (no SOS) pushes the target up while not yet armed
    st = tr.update(_sig(11, 109, 115, 106), _seq())
    assert st.l_tgt == 115.0 and st.l_on is False
    # arm on the continuation-BOS death captured by the sequence
    st = tr.update(_sig(12, 109, 114, 107), _seq(bleg_arm_l=True))
    assert st.l_on is True and st.l_bar == 12
    # once armed the target no longer tracks (frozen at the pre-arm extreme)
    st = tr.update(_sig(13, 109, 120, 108), _seq())
    assert st.l_tgt == 115.0


# ── tap + staleness death (Pine 3749-3753) ────────────────────────────────────────
def test_tap_and_staleness_death():
    cfg = BLegConfig(bleg_max_days=1.25)   # 120 bars on 15m
    tr = BLegTracker(cfg, tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))   # armed @ bar 11
    # price taps the 0.5 band (low <= top=105) → tapped, still on
    st = tr.update(_sig(12, 106, 107, 104.9), _seq())
    assert st.l_tap is True and st.l_on is True
    # 120 bars after the arm bar it goes stale
    st = tr.update(_sig(11 + 121, 106, 107, 106), _seq())
    assert st.l_on is False


# ── invalidation death: a close past the leg origin (Pine 3752) ───────────────────
def test_invalidation_death_long():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))
    st = tr.update(_sig(12, 99.5, 108, 99), _seq())   # close 99.5 < inv 100
    assert st.l_on is False


# ── deepest-band-wins migration keeps the farther band on a fresh untapped SOS ────
def test_deepest_band_migration():
    tr = BLegTracker(BLegConfig(), tf_seconds=900)
    tr.update(_sig(10, 108, 112, 104, bull_sos=True, bbh=110, bbl=100), _seq())
    tr.update(_sig(11, 109, 114, 106), _seq(bleg_arm_l=True))  # live, untapped, top=105
    # a fresh same-side SOS whose 0.5 (106) is NEARER price(109) than the current top(105):
    # |106-109|=3 vs |105-109|=4 → keep the deeper (farther) existing band, don't migrate.
    st = tr.update(_sig(12, 109, 114, 107, bull_sos=True, bbh=112, bbl=100), _seq())
    assert st.l_top == 105.0   # unchanged — the deeper band won


# ── end-to-end on the real engine stack ───────────────────────────────────────────
def test_driver_runs_end_to_end():
    strat = MpcBLegStrategy().run(synth_bars(12), warmup=100)
    assert len(strat.decisions) == 12 * 96 - 100
    assert isinstance(strat.execution.equity, float)
    for t in strat.execution.trades:
        assert t.r == t.r          # not NaN
        assert t.qty > 0


def test_driver_is_deterministic():
    a = MpcBLegStrategy().run(synth_bars(8))
    b = MpcBLegStrategy().run(synth_bars(8))
    assert [d.long_armed for d in a.decisions] == [d.long_armed for d in b.decisions]
    assert len(a.execution.trades) == len(b.execution.trades)


def test_longs_and_shorts_off_means_no_trades():
    strat = MpcBLegStrategy(BLegConfig(exec_longs=False, exec_shorts=False)).run(synth_bars(12))
    assert strat.execution.trades == []


# ── bleg_sl_level — the configurable stop, on the ZONE'S OWN fib ──────────────────
#
# The zone's fib has 0 at the leg ORIGIN and 1.0 at the extreme — the mirror of a standard
# retracement. The entry rests at 0.5 and the band's far edge is 0.382, so the only levels
# BELOW the entry are 0.382 / 0.236 / 0.0. These tests pin that frame so nobody re-derives
# the field as a standard retracement (which would offer 0.618/0.786/0.886 — levels that sit
# on the WRONG SIDE of the entry here).

def _sl(level, origin, entry, is_long):
    from mpc_bleg.execution import BLegExecution
    exe = BLegExecution.__new__(BLegExecution)
    exe._cfg = BLegConfig(bleg_sl_level=level)
    return BLegExecution._sl_price(exe, origin, entry, is_long)


def test_sl_default_is_the_old_hardcoded_origin():
    """"0.0" is the leg origin — the pre-2026-07-27 hardcoded stop. That is what keeps the
    shipped default bar-for-bar Pine-parity safe."""
    assert _sl("0.0", 100.0, 105.0, True) == 100.0
    assert _sl("0.0", 200.0, 195.0, False) == 200.0


def test_sl_382_lands_on_the_band_far_edge():
    """0.382 IS the band's own far edge (`l_bot` = origin + 0.382*range). The entry sits at
    the zone's 0.5, so range = 2*(entry - origin) = 10 here."""
    assert _sl("0.382", 100.0, 105.0, True) == pytest.approx(103.82)
    assert _sl("0.382", 200.0, 195.0, False) == pytest.approx(196.18)   # short mirror


def test_sl_levels_are_read_directly_not_mirrored():
    """Regression guard. The fractions are the ZONE's own, used as-is — 0.236 means 0.236 of
    the leg range up from the origin. A mirrored reading (1 - x) would put it at 0.764, which
    is ABOVE the 0.5 entry on a long: an instantly-stopped trade."""
    origin, entry = 100.0, 105.0      # range 10
    assert _sl("0.236", origin, entry, True) == pytest.approx(102.36)
    assert _sl("0.236", origin, entry, True) < entry, "a long stop must sit BELOW the entry"


def test_every_offered_level_sits_below_the_entry():
    """The whole point of the level set: 0.382/0.236/0.0 are the fib levels BELOW the 0.5
    entry. Nothing offered may sit at or above it, in either direction."""
    for origin, entry, is_long in ((100.0, 105.0, True), (200.0, 195.0, False)):
        for lvl in ("0.382", "0.236", "0.0"):
            sl = _sl(lvl, origin, entry, is_long)
            assert (sl < entry) if is_long else (sl > entry), (lvl, sl, entry)


def test_sl_deeper_level_means_wider_stop_both_directions():
    """Monotonicity: a SMALLER zone fraction is a deeper stop, hence more distance."""
    origin, entry = 100.0, 105.0
    dists = [entry - _sl(l, origin, entry, True) for l in ("0.382", "0.236", "0.0")]
    assert dists == sorted(dists), dists
    origin, entry = 200.0, 195.0
    dists = [_sl(l, origin, entry, False) - entry for l in ("0.382", "0.236", "0.0")]
    assert dists == sorted(dists), dists


def test_tp1_in_r_is_coupled_to_the_stop_level():
    """The finding that governs any stop choice here: TP1 is ALWAYS 0.5*range from the entry,
    while the stop is (0.5 - f)*range — so tightening the stop pushes TP1 FURTHER away in R.
    A TP1 touch is the only thing that stages the stop to breakeven."""
    origin, entry = 100.0, 105.0                 # range 10, TP1 = 2*entry - origin = 110
    tp1 = 2 * entry - origin
    got = {l: (tp1 - entry) / (entry - _sl(l, origin, entry, True))
           for l in ("0.0", "0.236", "0.382")}
    assert got["0.0"] == pytest.approx(1.0)
    assert got["0.236"] == pytest.approx(1.894, abs=0.01)
    assert got["0.382"] == pytest.approx(4.237, abs=0.01)
