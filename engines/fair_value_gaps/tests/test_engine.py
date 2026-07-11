"""
Hand-traced tests for the fair-value-gap state machine.

These pin the ported Pine behaviour (mpc_assistant.pine FVG block, "FAIR VALUE GAPS — persist until
mitigated"): a clean 3-candle displacement (all same-direction closes, progressively higher/lower)
that leaves a real void (`low > high[2]` bull / `high < low[2]` bear) forms a gap spanning that
void; a gap is never tapped on its own creation bar; it is mitigated the moment price taps its near
edge (bull `low <= top`, bear `high >= bottom`); the list is capped at max_count with oldest-first
(FIFO) eviction; and a min-ticks size filter can reject small gaps. Full Pine<->Python parity is
validated separately against a TradingView export (fair_value_gaps/tools/compare_fvg.py).

Run:  python3 -m pytest fair_value_gaps/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fair_value_gaps import FairValueGapEngine


def _feed(eng, idx, o, h, l, c):
    return eng.update(idx, o, h, l, c)


# A clean bullish displacement: bars 0,1,2 all bullish, progressively higher closes, and bar 2's
# low (105.5) sits above bar 0's high (101) — a real gap of 4.5.
_BULL = [
    (0, 100.0, 101.0, 99.0, 100.5),
    (1, 102.0, 104.0, 101.5, 103.0),
    (2, 105.0, 107.0, 105.5, 106.5),
]

# A clean bearish displacement: bars 0,1,2 all bearish, progressively lower closes, and bar 2's
# high (101.5) sits below bar 0's low (105.5) — a real gap.
_BEAR = [
    (0, 106.0, 107.0, 105.5, 105.5),
    (1, 104.0, 104.5, 102.0, 103.0),
    (2, 101.0, 101.5, 99.0, 100.0),
]


def _run(eng, bars):
    ev = None
    for (i, o, h, l, c) in bars:
        ev = _feed(eng, i, o, h, l, c)
    return ev


# ── formation ──

def test_bull_gap_forms_on_clean_displacement():
    eng = FairValueGapEngine()
    ev = _run(eng, _BULL)
    assert len(ev.formed) == 1
    g = ev.formed[0]
    assert g.is_bullish is True
    assert g.top == 105.5 and g.bottom == 101.0     # C's low over A's high
    assert g.born_index == 2
    assert len(ev.active) == 1                        # not tapped on its own creation bar


def test_bear_gap_forms_on_clean_displacement():
    eng = FairValueGapEngine()
    ev = _run(eng, _BEAR)
    assert len(ev.formed) == 1
    g = ev.formed[0]
    assert g.is_bullish is False
    assert g.top == 105.5 and g.bottom == 101.5     # A's low over C's high
    assert g.born_index == 2
    assert len(ev.active) == 1


def test_no_gap_when_void_does_not_open():
    # Same bullish, progressive closes, but bar 0's high (106) overlaps bar 2's low (105.5) — no void.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 106.0, 99.0, 100.5),
        (1, 102.0, 104.0, 101.5, 103.0),
        (2, 105.0, 107.0, 105.5, 106.5),
    ]
    ev = _run(eng, bars)
    assert ev.formed == []
    assert ev.active == []


def test_no_gap_when_displacement_not_clean():
    # A real void, but bar 1 is bearish (close < open) — not a one-way impulse, so no gap.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 101.0, 99.0, 100.5),
        (1, 104.0, 104.0, 101.5, 102.0),   # close 102 < open 104 -> not bullish
        (2, 105.0, 107.0, 105.5, 106.5),
    ]
    ev = _run(eng, bars)
    assert ev.formed == []


def test_no_gap_when_closes_not_progressive():
    # All three bullish and a void exists, but closes are not progressively higher (c0 < c1).
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 101.0, 99.0, 100.5),
        (1, 102.0, 108.0, 101.5, 107.0),   # close 107
        (2, 105.0, 107.5, 105.5, 106.0),   # close 106 < previous close 107 -> not progressive
    ]
    ev = _run(eng, bars)
    assert ev.formed == []


def test_no_detection_before_two_bars_of_history():
    # Only two bars fed — the two-bars-back candle does not exist yet, so nothing can form.
    eng = FairValueGapEngine()
    _feed(eng, 0, 100.0, 101.0, 99.0, 100.5)
    ev = _feed(eng, 1, 102.0, 104.0, 101.5, 103.0)
    assert ev.formed == []
    assert ev.active == []


# ── mitigation ──

def test_bull_gap_mitigated_when_near_edge_tapped():
    eng = FairValueGapEngine()
    _run(eng, _BULL)                                  # gap: top=105.5, bottom=101, born=2
    # bar 3 dips to tap the top edge (low 105 <= 105.5); not itself an impulse, so no new gap.
    ev = _feed(eng, 3, 106.0, 106.5, 105.0, 105.5)
    assert len(ev.mitigated) == 1
    assert ev.mitigated[0].born_index == 2
    assert ev.active == []


def test_bear_gap_mitigated_when_near_edge_tapped():
    eng = FairValueGapEngine()
    _run(eng, _BEAR)                                  # gap: top=105.5, bottom=101.5, born=2
    # bar 3 pops up to tap the bottom edge (high 102 >= 101.5).
    ev = _feed(eng, 3, 100.5, 102.0, 100.0, 101.0)
    assert len(ev.mitigated) == 1
    assert ev.active == []


def test_gap_not_tapped_on_its_own_creation_bar():
    # bar 2's own low IS the bull gap's top edge; the born guard must stop it self-mitigating.
    eng = FairValueGapEngine()
    ev = _run(eng, _BULL)
    assert ev.mitigated == []
    assert len(ev.active) == 1


# ── FIFO eviction ──

def test_oldest_gap_evicted_past_max_count():
    # Ascending staircase: every bar from index 2 forms a gap, none tap the earlier (lower) gaps.
    eng = FairValueGapEngine(max_count=2)
    ev = None
    for k in range(5):
        o = 100.0 + 10 * k
        ev = _feed(eng, k, o, o + 6.0, o, o + 5.0)   # bullish, low=o, high=o+6, close=o+5
    # Gaps formed at bars 2,3,4. With cap 2, bar 4's formation evicts the bar-2 gap.
    assert len(ev.active) == 2
    assert [g.born_index for g in ev.active] == [3, 4]
    assert len(ev.evicted) == 1 and ev.evicted[0].born_index == 2
    assert ev.mitigated == []


# ── size filter ──

def test_min_ticks_filter_rejects_small_gap():
    # The bull gap is 4.5 wide; with min_size = 5 ticks * 1.0 mintick it is filtered out.
    eng = FairValueGapEngine(min_ticks=5, mintick=1.0)
    ev = _run(eng, _BULL)
    assert ev.formed == []
    assert ev.active == []


def test_min_ticks_filter_allows_gap_at_threshold():
    # Same gap (4.5) clears a 4-tick * 1.0 threshold.
    eng = FairValueGapEngine(min_ticks=4, mintick=1.0)
    ev = _run(eng, _BULL)
    assert len(ev.formed) == 1
