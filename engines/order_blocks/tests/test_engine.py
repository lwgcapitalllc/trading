"""
Hand-traced tests for the order-block state machine.

These pin the ported Pine behaviour (mpc_assistant.pine OB blocks, ~lines 38-66 / 863-895 /
1290-1317): a break drops an OB across the first opposite-colour candle scanned back from the
break-leg origin; the OB uses the candle high/low (or body extremes when body_only); OBs are
mitigated when price closes through the far edge; the per-direction list is capped at max_active
with oldest-first (FIFO) eviction; and both the external and internal break paths push into the
SAME two arrays. Full Pine<->Python parity is validated separately against a TradingView export
(order_blocks/tools/compare_ob.py).

Run:  python3 -m pytest order_blocks/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from order_blocks import OrderBlockEngine, StructureSnapshot


# ── snapshot helpers ──

def _flat():
    return StructureSnapshot()  # no break this bar


def _bull_break(l_loc):
    return StructureSnapshot(bull_bos=True, bull_bos_l_loc=l_loc)


def _bear_break(h_loc):
    return StructureSnapshot(bear_bos=True, bear_bos_h_loc=h_loc)


def _int_bull(origin):
    return StructureSnapshot(int_bull_break=True, int_break_origin_loc=origin)


def _int_bear(origin):
    return StructureSnapshot(int_bear_break=True, int_break_origin_loc=origin)


def _feed(eng, idx, o, h, l, c, snap=None):
    return eng.update(idx, o, h, l, c, snap if snap is not None else _flat())


# ── creation: the OB drops across the first opposite-colour candle ──

def test_bull_ob_created_across_last_down_candle():
    eng = OrderBlockEngine()
    # bars 0-4 up, bar 5 DOWN (o=110,h=112,l=105,c=106), bars 6-9 up.
    for i in range(5):
        _feed(eng, i, 100, 103, 99, 102)
    _feed(eng, 5, 110, 112, 105, 106)                 # the down candle
    for i in range(6, 9):
        _feed(eng, i, 106, 109, 105, 108)
    ev = _feed(eng, 9, 108, 111, 107, 110, _bull_break(l_loc=5))  # lookback_idx = 9-5 = 4 -> bar_ago(4)=idx5

    assert len(ev.created) == 1
    ob = ev.created[0]
    assert ob.is_bullish is True
    assert ob.top == 112 and ob.bottom == 105          # full candle high/low (body_only=False)
    assert ob.origin_index == 5                         # the down-candle bar
    assert ob.created_index == 9                         # the break bar
    assert ev.active_bull == [ob] and ev.active_bear == []


def test_bear_ob_created_across_last_up_candle():
    eng = OrderBlockEngine()
    for i in range(5):
        _feed(eng, i, 102, 103, 97, 98)                 # down-ish fillers
    _feed(eng, 5, 100, 112, 99, 110)                    # the up candle
    for i in range(6, 9):
        _feed(eng, i, 108, 109, 104, 105)
    ev = _feed(eng, 9, 106, 107, 100, 101, _bear_break(h_loc=5))

    assert len(ev.created) == 1
    ob = ev.created[0]
    assert ob.is_bullish is False
    assert ob.top == 112 and ob.bottom == 99
    assert ob.origin_index == 5
    assert ev.active_bear == [ob] and ev.active_bull == []


def test_scan_skips_to_first_opposite_colour_candle():
    eng = OrderBlockEngine()
    for i in range(4):
        _feed(eng, i, 100, 103, 99, 102)
    _feed(eng, 4, 120, 122, 114, 115)                   # DOWN candle (older, idx4)
    _feed(eng, 5, 100, 112, 99, 110)                    # UP candle at the origin (idx5) -> skipped
    for i in range(6, 9):
        _feed(eng, i, 110, 113, 109, 112)
    ev = _feed(eng, 9, 112, 115, 111, 114, _bull_break(l_loc=5))  # origin idx5 is UP -> scan back to idx4

    assert len(ev.created) == 1
    ob = ev.created[0]
    assert ob.origin_index == 4                          # skipped the up origin, took the down candle behind it
    assert ob.top == 122 and ob.bottom == 114


def test_no_ob_when_no_opposite_candle_in_scan_window():
    eng = OrderBlockEngine()
    for i in range(9):                                   # every bar an up candle
        _feed(eng, i, 100 + i, 103 + i, 99 + i, 102 + i)
    ev = _feed(eng, 9, 109, 112, 108, 111, _bull_break(l_loc=5))
    assert ev.created == []                              # scan finds no down candle -> nothing dropped


def test_body_only_uses_body_extremes():
    eng = OrderBlockEngine(body_only=True)
    for i in range(5):
        _feed(eng, i, 100, 103, 99, 102)
    _feed(eng, 5, 110, 115, 104, 106)                   # down candle: body 106..110, wick 104..115
    for i in range(6, 9):
        _feed(eng, i, 106, 109, 105, 108)
    ev = _feed(eng, 9, 108, 111, 107, 110, _bull_break(l_loc=5))
    ob = ev.created[0]
    assert ob.top == 110 and ob.bottom == 106            # max/min of open/close, NOT the wicks


# ── lookback guards ──

def test_no_ob_when_origin_in_the_future():
    eng = OrderBlockEngine()
    _feed(eng, 0, 100, 103, 99, 102)
    ev = _feed(eng, 9, 108, 111, 107, 110, _bull_break(l_loc=15))  # lookback_idx = 9-15 = -6
    assert ev.created == []


def test_no_ob_when_origin_beyond_500_bars():
    eng = OrderBlockEngine()
    _feed(eng, 0, 100, 103, 99, 102)
    ev = _feed(eng, 500, 108, 111, 107, 110, _bull_break(l_loc=0))  # lookback_idx = 500 -> not < 500
    assert ev.created == []


# ── mitigation: price closes through the far edge ──

def _make_bull_ob(eng):
    """Drop one bull OB (top=112, bottom=105 across idx5) and return the OB."""
    for i in range(5):
        _feed(eng, i, 100, 103, 99, 102)
    _feed(eng, 5, 110, 112, 105, 106)
    for i in range(6, 9):
        _feed(eng, i, 106, 109, 106, 108)
    ev = _feed(eng, 9, 108, 111, 107, 110, _bull_break(l_loc=5))
    return ev.created[0]


def test_bull_ob_survives_close_at_or_above_bottom():
    eng = OrderBlockEngine()
    ob = _make_bull_ob(eng)                              # bottom = 105
    ev = _feed(eng, 10, 108, 110, 104, 105)             # close == bottom -> NOT mitigated
    assert ev.mitigated == []
    assert ev.active_bull == [ob]


def test_bull_ob_mitigated_on_close_below_bottom():
    eng = OrderBlockEngine()
    ob = _make_bull_ob(eng)                              # bottom = 105
    ev = _feed(eng, 10, 106, 107, 100, 104)             # close 104 < 105 -> mitigated
    assert ev.mitigated == [ob]
    assert ev.active_bull == []


def test_bear_ob_mitigated_on_close_above_top():
    eng = OrderBlockEngine()
    for i in range(5):
        _feed(eng, i, 102, 103, 97, 98)
    _feed(eng, 5, 100, 112, 99, 110)                    # up candle -> bear OB top=112, bottom=99
    for i in range(6, 9):
        _feed(eng, i, 108, 109, 104, 105)
    ob = _feed(eng, 9, 106, 107, 100, 101, _bear_break(h_loc=5)).created[0]
    ev = _feed(eng, 10, 108, 115, 108, 113)             # close 113 > top 112 -> mitigated
    assert ev.mitigated == [ob]
    assert ev.active_bear == []


# ── FIFO eviction at the per-direction cap ──

def test_oldest_ob_evicted_when_cap_exceeded():
    eng = OrderBlockEngine(max_active=2)
    # Three down candles (idx 0, 3, 6), closes kept high so nothing mitigates (all bottoms <= 112).
    _feed(eng, 0, 125, 128, 110, 124)                   # down candle A
    ev_a = _feed(eng, 1, 124, 127, 123, 126, _bull_break(l_loc=0))  # OB-A across idx0
    _feed(eng, 2, 126, 128, 125, 127)
    _feed(eng, 3, 126, 129, 111, 125)                   # down candle B
    ev_b = _feed(eng, 4, 125, 128, 124, 127, _bull_break(l_loc=3))  # OB-B across idx3
    _feed(eng, 5, 127, 129, 126, 128)
    _feed(eng, 6, 127, 130, 112, 126)                   # down candle C
    ev_c = _feed(eng, 7, 126, 129, 125, 128, _bull_break(l_loc=6))  # OB-C -> pushes past cap

    ob_a = ev_a.created[0]
    ob_b = ev_b.created[0]
    ob_c = ev_c.created[0]
    assert ev_c.evicted == [ob_a]                        # oldest aged out (FIFO), not a mitigation
    assert ev_c.mitigated == []
    assert ev_c.active_bull == [ob_b, ob_c]              # cap held at 2, order preserved


# ── internal break path shares the same arrays ──

def test_internal_break_creates_into_bull_array():
    eng = OrderBlockEngine()
    for i in range(5):
        _feed(eng, i, 100, 103, 99, 102)
    _feed(eng, 5, 110, 112, 105, 106)                   # down candle
    for i in range(6, 9):
        _feed(eng, i, 106, 109, 105, 108)
    ev = _feed(eng, 9, 108, 111, 107, 110, _int_bull(origin=5))

    assert len(ev.created) == 1
    assert ev.created[0].is_bullish is True
    assert ev.active_bull and not ev.active_bear
