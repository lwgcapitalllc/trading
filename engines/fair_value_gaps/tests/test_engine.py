"""
Hand-traced tests for the fair-value-gap state machine.

These pin the ported Pine behaviour (mpc_assistant.pine FVG block, "FAIR VALUE GAPS — persist until
mitigated"): a 3-candle imbalance (LuxAlgo definition) — the two outer candles don't overlap
(`low > high[2]` bull / `high < low[2]` bear), the middle bar's close cleared the gap
(`close[1] > high[2]` bull / `close[1] < low[2]` bear), and the gap is at least `threshold_pct`% of
price — forms a gap spanning that void; there is NO clean-impulse / progressive-close requirement. A
gap is never mitigated on its own creation bar; it is mitigated only when a candle CLOSES fully past
its far edge (bull `close <= bottom`, bear `close >= top`) — a wick into the gap leaves it alive; the
list is capped at max_count with oldest-first (FIFO) eviction. Full Pine<->Python parity is validated
separately against a TradingView export (fair_value_gaps/tools/compare_fvg.py).

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


# A bullish imbalance: bar 2's low (105.5) sits above bar 0's high (101) — a real gap of 4.5 (~4.5%
# of price) — and the middle bar (bar 1) closed at 103, above bar 0's high. No impulse rule needed.
_BULL = [
    (0, 100.0, 101.0, 99.0, 100.5),
    (1, 102.0, 104.0, 101.5, 103.0),
    (2, 105.0, 107.0, 105.5, 106.5),
]

# A bearish imbalance: bar 2's high (101.5) sits below bar 0's low (105.5), and the middle bar closed
# at 103, below bar 0's low.
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

def test_bull_gap_forms_on_imbalance():
    eng = FairValueGapEngine()
    ev = _run(eng, _BULL)
    assert len(ev.formed) == 1
    g = ev.formed[0]
    assert g.is_bullish is True
    assert g.top == 105.5 and g.bottom == 101.0     # C's low over A's high
    assert g.born_index == 2
    assert len(ev.active) == 1                        # not mitigated on its own creation bar


def test_bear_gap_forms_on_imbalance():
    eng = FairValueGapEngine()
    ev = _run(eng, _BEAR)
    assert len(ev.formed) == 1
    g = ev.formed[0]
    assert g.is_bullish is False
    assert g.top == 105.5 and g.bottom == 101.5     # A's low over C's high
    assert g.born_index == 2
    assert len(ev.active) == 1


def test_no_gap_when_void_does_not_open():
    # Bar 0's high (106) overlaps bar 2's low (105.5) — no void, so no gap regardless of closes.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 106.0, 99.0, 100.5),
        (1, 102.0, 104.0, 101.5, 103.0),
        (2, 105.0, 107.0, 105.5, 106.5),
    ]
    ev = _run(eng, bars)
    assert ev.formed == []
    assert ev.active == []


def test_gap_forms_even_when_displacement_not_clean():
    # A real void with the middle close clearing it, but bar 1 is bearish (close < open). The old
    # engine rejected this ("not a clean impulse"); the LuxAlgo rule accepts it.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 101.0, 99.0, 100.5),
        (1, 104.0, 104.0, 101.5, 102.0),   # bearish bar, but close 102 > bar0 high 101
        (2, 105.0, 107.0, 105.5, 106.5),
    ]
    ev = _run(eng, bars)
    assert len(ev.formed) == 1
    assert ev.formed[0].top == 105.5 and ev.formed[0].bottom == 101.0


def test_gap_forms_even_when_closes_not_progressive():
    # All bullish-ish with a void; closes are NOT progressively higher (c0 106 < c1 107). The old
    # engine rejected this; the LuxAlgo rule only needs the MIDDLE close to clear the gap.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 101.0, 99.0, 100.5),
        (1, 102.0, 108.0, 101.5, 107.0),   # middle close 107 > bar0 high 101
        (2, 105.0, 107.5, 105.5, 106.0),   # close 106 < previous close 107
    ]
    ev = _run(eng, bars)
    assert len(ev.formed) == 1


def test_no_gap_when_middle_close_does_not_clear():
    # Void exists (bar2 low 105.5 > bar0 high 105) but the middle bar closed at 104, BELOW the gap
    # top — the LuxAlgo middle-bar-close condition fails, so no gap.
    eng = FairValueGapEngine()
    bars = [
        (0, 100.0, 105.0, 99.0, 100.0),
        (1, 101.0, 106.0, 100.0, 104.0),   # close 104 <= bar0 high 105 -> middle didn't clear
        (2, 106.0, 108.0, 105.5, 107.0),
    ]
    ev = _run(eng, bars)
    assert ev.formed == []
    assert ev.active == []


def test_no_detection_before_two_bars_of_history():
    # Only two bars fed — the two-bars-back candle does not exist yet, so nothing can form.
    eng = FairValueGapEngine()
    _feed(eng, 0, 100.0, 101.0, 99.0, 100.5)
    ev = _feed(eng, 1, 102.0, 104.0, 101.5, 103.0)
    assert ev.formed == []
    assert ev.active == []


# ── mitigation (close past the FAR edge) ──

def test_bull_gap_mitigated_when_close_past_far_edge():
    eng = FairValueGapEngine()
    _run(eng, _BULL)                                  # gap: top=105.5, bottom=101, born=2
    # bar 3 closes at 100, below the gap's bottom (far edge) -> mitigated. Forms no new gap.
    ev = _feed(eng, 3, 106.0, 106.5, 99.0, 100.0)
    assert len(ev.mitigated) == 1
    assert ev.mitigated[0].born_index == 2
    assert ev.active == []


def test_bear_gap_mitigated_when_close_past_far_edge():
    eng = FairValueGapEngine()
    _run(eng, _BEAR)                                  # gap: top=105.5, bottom=101.5, born=2
    # bar 3 closes at 106, above the gap's top (far edge) -> mitigated.
    ev = _feed(eng, 3, 101.0, 106.5, 100.5, 106.0)
    assert len(ev.mitigated) == 1
    assert ev.active == []


def test_wick_into_gap_does_not_mitigate():
    # bar 3 wicks all the way through the bull gap (low 100.5 < bottom 101) but CLOSES at 104,
    # inside/above the bottom — a wick no longer mitigates; the gap survives.
    eng = FairValueGapEngine()
    _run(eng, _BULL)                                  # gap: top=105.5, bottom=101, born=2
    ev = _feed(eng, 3, 105.0, 106.0, 100.5, 104.0)
    assert ev.mitigated == []
    assert len(ev.active) == 1


def test_gap_not_mitigated_on_its_own_creation_bar():
    # The born guard must stop a gap self-mitigating on the bar it forms.
    eng = FairValueGapEngine()
    ev = _run(eng, _BULL)
    assert ev.mitigated == []
    assert len(ev.active) == 1


# ── FIFO eviction ──

def test_oldest_gap_evicted_past_max_count():
    # Ascending staircase: every bar from index 2 forms a gap, none close past the earlier (lower)
    # gaps' bottoms.
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


# ── size threshold (% of price) ──

def test_threshold_rejects_small_gap():
    # A tiny 0.04-wide gap on ~100 price = 0.04% < the default 0.1% floor -> rejected.
    eng = FairValueGapEngine()
    bars = [
        (0, 99.90, 100.00, 99.80, 99.95),
        (1, 100.05, 100.10, 100.02, 100.08),   # middle close 100.08 > bar0 high 100.00
        (2, 100.06, 100.12, 100.04, 100.10),   # low 100.04 > bar0 high 100.00, gap = 0.04
    ]
    ev = _run(eng, bars)
    assert ev.formed == []
    assert ev.active == []


def test_custom_threshold_rejects_and_allows():
    # The _BULL gap is 4.5 wide on ~101 price = ~4.46%. A 5% threshold rejects it; 4% accepts it.
    assert _run(FairValueGapEngine(threshold_pct=5.0), _BULL).formed == []
    assert len(_run(FairValueGapEngine(threshold_pct=4.0), _BULL).formed) == 1
