"""
Hand-traced tests for the Sniper fib zone state machine.

These pin the ported Pine behaviour (mpc_assistant.pine GRP_SNIPER): a BOS drops a fresh
0.382-0.5 zone across the impulse leg and arms it; price entering that zone confirms once; a new
BOS replaces the zone and re-arms; the break bar itself never counts as its own confirm. Full
Pine<->Python parity is validated separately against a TradingView export (compare_fib.py).

Run:  python3 -m pytest fibonacci/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fibonacci import SniperFib, StructureSnapshot, fib_from_origin


# ── geometry: the zone measures its ratios FROM the impulse-leg origin ──

def test_fib_from_origin_bull_and_bear():
    # Bull leg 100->110: 0.382 sits 3.82 above the low, 0.5 at the midpoint.
    assert fib_from_origin(110.0, 100.0, 1, 0.382) == 100.0 + 10.0 * 0.382
    assert fib_from_origin(110.0, 100.0, 1, 0.500) == 105.0
    # Bear leg: mirror — measured DOWN from the high.
    assert fib_from_origin(110.0, 100.0, -1, 0.382) == 110.0 - 10.0 * 0.382
    assert fib_from_origin(110.0, 100.0, -1, 0.500) == 105.0


# ── snapshots ──

def _bull_bos(high=110.0, low=100.0):
    return StructureSnapshot(bull_bos=True, bull_bos_high=high, bull_bos_low=low, bull_bos_l_loc=0)


def _bear_bos(high=110.0, low=100.0):
    return StructureSnapshot(bear_bos=True, bear_bos_high=high, bear_bos_low=low, bear_bos_h_loc=0)


def _flat():
    return StructureSnapshot()  # no BOS this bar


# ── Sniper fib state machine ──

def test_no_zone_before_any_bos():
    fib = SniperFib()
    ev = fib.update(high=105.0, low=104.0, snap=_flat())
    assert not ev.active
    assert not ev.created and not ev.confirmed
    assert ev.zone_top is None and ev.zone_bot is None


def test_bull_bos_creates_zone_geometry():
    fib = SniperFib()
    # BOS bar prints above the zone (high 111, low 109) so it does not confirm itself.
    ev = fib.update(high=111.0, low=109.0, snap=_bull_bos(110.0, 100.0))
    assert ev.active and ev.created and ev.direction == 1
    assert ev.zone_bot == 100.0 + 10.0 * 0.382   # 103.82 (the 0.382 level)
    assert ev.zone_top == 105.0                  # 0.5 level
    assert not ev.confirmed and not ev.zone_active


def test_bear_bos_creates_zone_geometry():
    fib = SniperFib()
    ev = fib.update(high=101.0, low=99.0, snap=_bear_bos(110.0, 100.0))
    assert ev.active and ev.created and ev.direction == -1
    assert ev.zone_bot == 105.0                  # 0.5 level
    assert ev.zone_top == 110.0 - 10.0 * 0.382   # 106.18 (the 0.382 level)


def test_confirm_fires_when_price_enters_zone():
    fib = SniperFib()
    fib.update(111.0, 109.0, _bull_bos(110.0, 100.0))   # zone [103.82, 105], not entered
    # Next bar trades into the zone.
    ev = fib.update(high=104.5, low=104.0, snap=_flat())
    assert ev.confirmed
    assert ev.zone_active
    assert not ev.created


def test_confirm_is_edge_triggered_once():
    fib = SniperFib()
    fib.update(111.0, 109.0, _bull_bos(110.0, 100.0))
    fib.update(104.5, 104.0, _flat())                   # confirms here
    ev = fib.update(high=104.5, low=104.0, snap=_flat())  # still inside the zone
    assert not ev.confirmed          # fires once, not every bar it sits in the zone
    assert ev.zone_active            # ...but the latch stays set


def test_price_outside_zone_does_not_confirm():
    fib = SniperFib()
    fib.update(111.0, 109.0, _bull_bos(110.0, 100.0))   # zone [103.82, 105]
    ev = fib.update(high=108.0, low=106.0, snap=_flat())  # stays above the zone
    assert not ev.confirmed and not ev.zone_active


def test_new_bos_replaces_zone_and_rearms():
    fib = SniperFib()
    fib.update(111.0, 109.0, _bull_bos(110.0, 100.0))
    fib.update(104.5, 104.0, _flat())                   # confirmed -> zone_active True
    # A fresh BOS: new geometry, re-armed, and the break bar never counts as its own confirm.
    ev = fib.update(high=121.0, low=119.0, snap=_bull_bos(120.0, 110.0))
    assert ev.created
    assert not ev.zone_active and not ev.confirmed
    assert ev.zone_bot == 110.0 + 10.0 * 0.382
    assert ev.zone_top == 115.0


def test_bos_bar_straddling_its_own_zone_confirms_silently():
    """If the break bar's own range already covers the new zone, Pine latches sniperZoneActive
    but clears the Confirmed status on the same bar (the reset at the end). So the confirm is
    consumed silently: no event now, and no later bar can re-confirm this zone."""
    fib = SniperFib()
    # Zone is [103.82, 105]; the BOS bar's own low reaches into it (low 104).
    ev = fib.update(high=111.0, low=104.0, snap=_bull_bos(110.0, 100.0))
    assert ev.created
    assert ev.zone_active          # latched on the break bar
    assert not ev.confirmed        # ...but the break bar never shows a confirm event
    # A later bar sitting inside the zone must NOT re-confirm.
    ev2 = fib.update(high=104.5, low=104.0, snap=_flat())
    assert not ev2.confirmed
