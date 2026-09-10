"""
Hand-traced tests for the fair-value-gap state machine.

These pin the ported Pine behaviour (mpc_jarvis.pine FVG block, "FAIR VALUE GAPS — persist until
mitigated"): a 3-candle imbalance (LuxAlgo definition) — the two outer candles don't overlap
(`low > high[2]` bull / `high < low[2]` bear) and the gap is at least `threshold_pct`% of price —
forms a gap spanning that void; the middle-bar close-cleared check (`close[1] > high[2]` bull /
`close[1] < low[2]` bear) is OPTIONAL, gated by `require_close` (Pine `fvgRequireClose`, default
False below 15m). There is NO clean-impulse / progressive-close requirement. The engine's defaults
are the DEFAULT_* constants in engine.py, held to the indicator by
engines/tests/test_defaults_mirror_the_indicator.py rather than typed here. A
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


_MIDDLE_NO_CLEAR = [
    (0, 100.0, 105.0, 99.0, 100.0),
    (1, 101.0, 106.0, 100.0, 104.0),   # close 104 <= bar0 high 105 -> middle didn't clear the gap
    (2, 106.0, 108.0, 105.5, 107.0),   # void: bar2 low 105.5 > bar0 high 105
]


def test_no_gap_when_middle_close_does_not_clear_with_require_close():
    # With require_close=True the middle-bar-close condition is enforced: it fails here, so no gap.
    ev = _run(FairValueGapEngine(require_close=True), _MIDDLE_NO_CLEAR)
    assert ev.formed == []
    assert ev.active == []


def test_gap_forms_by_default_even_when_middle_close_does_not_clear():
    # Below 15m the indicator runs require_close=False (classic FVG), and that is the engine's
    # default: the same void forms a gap regardless of where the middle bar closed.
    ev = _run(FairValueGapEngine(), _MIDDLE_NO_CLEAR)
    assert len(ev.formed) == 1
    assert ev.formed[0].top == 105.5 and ev.formed[0].bottom == 105.0


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
    # A tiny 0.04-wide gap on ~100 price = 0.04% < a 0.1% floor -> rejected. (Default threshold is now
    # 0.0 = no floor, so this passes an explicit 0.1 like the Pine's 15m+ setting.)
    eng = FairValueGapEngine(threshold_pct=0.1)
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


# ── EQ-exemption coupling (Pine eqExemptFvg) ──

def _staircase(eng, n=5, eq_levels=None, eq_tol=0.0, zone_lo=None, zone_hi=None, zone_dir=0):
    """Ascending staircase (o=100,110,120,…) — bars 2..n-1 each form a bull gap."""
    ev = None
    for k in range(n):
        o = 100.0 + 10 * k
        ev = eng.update(k, o, o + 6.0, o, o + 5.0, eq_levels=eq_levels, eq_tol=eq_tol,
                        zone_lo=zone_lo, zone_hi=zone_hi, zone_dir=zone_dir)
    return ev


def test_eq_exempt_gap_is_held_IN_ADDITION_to_the_cap_not_instead_of_a_gap():
    """The exempt gap rides ON TOP of the cap — `max_count` bounds the ORDINARY gaps only.

    🔴 This is the regression test for the self-cancelling bug (Pine `b1b461b`, ported here
    2026-08-06). The engine used to count EVERY gap against the cap while the drop scan skipped
    the exempt ones, so a protected gap still HELD A SLOT: keeping it evicted the newest ordinary
    gap in its place. That is a SWAP, not an exemption, and it made the whole feature inert —
    measured in Pine over 40,000 M15 bars, the old rule never once held more gaps than OFF.

    cap=2, staircase: bars 2/3/4 each form a bull gap. The bar-2 gap spans [106,120] and an EQ
    level at 110 sits inside it. Non-exempt gaps = bars 3 and 4 = 2 = the cap, so NOTHING is
    dropped and all three survive. Under the old swap rule this returned [2, 4].
    """
    ev = _staircase(FairValueGapEngine(max_count=2), eq_levels=[110.0])
    born = [g.born_index for g in ev.active]
    assert born == [2, 3, 4], f"exempt gap must be held IN ADDITION to the cap; got {born}"
    assert ev.evicted == [], "nothing may be evicted while the ORDINARY gaps are within the cap"


def test_the_cap_still_bites_on_the_ordinary_gaps_while_an_exempt_gap_is_held():
    """The other half, and without it the test above passes for a cap that stopped working.

    Same EQ level, same cap, but one bar longer: bar 5 forms a fourth gap, so the ORDINARY gaps
    (3, 4, 5) now exceed the cap of 2 and the OLDEST ordinary one — bar 3 — is dropped. The
    exempt bar-2 gap is skipped over and survives, which is the exemption doing its job while
    the cap does its own.
    """
    ev = _staircase(FairValueGapEngine(max_count=2), n=6, eq_levels=[110.0])
    assert [g.born_index for g in ev.active] == [2, 4, 5]
    assert len(ev.evicted) == 1 and ev.evicted[0].born_index == 3


def test_no_eq_levels_is_plain_fifo():
    # Same staircase, but no EQ state passed -> plain drop-oldest (bar 2 evicted), unchanged behaviour.
    eng = FairValueGapEngine(max_count=2)
    ev = None
    for k in range(5):
        o = 100.0 + 10 * k
        ev = eng.update(k, o, o + 6.0, o, o + 5.0)
    assert [g.born_index for g in ev.active] == [3, 4]
    assert ev.evicted[0].born_index == 2


# ─────────────────────────────────────────────────────────────────────────────
# The fib ENTRY-BAND exemption (mpc fvgExemptZone) — a gap in the live fib's
# 0.382-0.886 band, ON THE TRADE'S OWN SIDE, is exempt from the cap.
#
# ⚠ These pin BEHAVIOUR, not parity. The band branch has never been compared
#   against Pine on a real export — that is fvg_zone_export.pine's job and it is
#   outstanding. A green here says the rule does what this file says it does.
#
# Geometry of the shared staircase, worked out once so each test can be read:
#   bar 2 gap = [106, 120]   bar 3 gap = [116, 130]
#   bar 4 gap = [126, 140]   bar 5 gap = [136, 150]      (all bullish)
# A band of 110..115 therefore overlaps the bar-2 gap ONLY: bar 3 starts at 116,
# above the band's top, so nothing else is protected by accident.
# ─────────────────────────────────────────────────────────────────────────────

_BAND = dict(zone_lo=110.0, zone_hi=115.0, zone_dir=1)


def test_band_gap_is_held_IN_ADDITION_to_the_cap():
    """Same shape as the EQ test above, and for the same reason.

    A protected gap must NOT hold a slot: `max_count` bounds the ORDINARY gaps only. Counting it
    would make the exemption a SWAP — keeping the band gap would evict an ordinary one in its
    place, which is a loss dressed as a feature. cap=2, ordinary gaps are bars 3 and 4 = the cap,
    so nothing is dropped and all three survive.
    """
    ev = _staircase(FairValueGapEngine(max_count=2), **_BAND)
    assert [g.born_index for g in ev.active] == [2, 3, 4]
    assert ev.evicted == []


def test_the_cap_still_bites_on_ordinary_gaps_while_a_band_gap_is_held():
    """The other half of the pair — without it the test above passes for a cap that stopped working.

    One bar longer: the ordinary gaps (3, 4, 5) now exceed the cap of 2, so the OLDEST ORDINARY
    one is dropped while the band gap is skipped over.
    """
    ev = _staircase(FairValueGapEngine(max_count=2), n=6, **_BAND)
    assert [g.born_index for g in ev.active] == [2, 4, 5]
    assert len(ev.evicted) == 1 and ev.evicted[0].born_index == 3


def test_band_does_not_protect_a_gap_on_the_wrong_side():
    """DIRECTION-MATCHED, deliberately (mpc's own comment).

    On a bearish leg the bullish gaps printing inside the same band belong to the move AGAINST the
    setup, and the entry rule cannot read them either — so protecting them would pin levels nothing
    trades. Same band, direction flipped: the bar-2 gap is bullish, so it is ordinary again and the
    cap evicts it.
    """
    ev = _staircase(FairValueGapEngine(max_count=2), zone_lo=110.0, zone_hi=115.0, zone_dir=-1)
    assert [g.born_index for g in ev.active] == [3, 4]
    assert ev.evicted[0].born_index == 2


def _bear_staircase(eng, n=5, zone_lo=None, zone_hi=None, zone_dir=0):
    """Descending staircase (o=100,90,80,…) — bars 2..n-1 each form a BEAR gap.

    bar 2 gap = [80, 94]   bar 3 gap = [70, 84]   bar 4 gap = [60, 74]
    A band of 85..90 overlaps the bar-2 gap ONLY (bar 3 tops out at 84, below the band).
    """
    ev = None
    for k in range(n):
        o = 100.0 - 10 * k
        ev = eng.update(k, o, o, o - 6.0, o - 5.0,
                        zone_lo=zone_lo, zone_hi=zone_hi, zone_dir=zone_dir)
    return ev


def test_band_protects_a_bearish_gap_on_a_bearish_leg():
    """The mirror of the bullish case, and the setup this exemption was actually written for.

    After a bearish shift price prints gap after gap on the way down; the FIFO drops from the FRONT,
    and the oldest gaps on a retrace setup are the ones UP IN THE ENTRY ZONE — the only gaps the
    trade is ever taken from. cap=2, ordinary gaps are bars 3 and 4, so all three survive.
    """
    ev = _bear_staircase(FairValueGapEngine(max_count=2), zone_lo=85.0, zone_hi=90.0, zone_dir=-1)
    assert [g.born_index for g in ev.active] == [2, 3, 4]


def test_a_finished_leg_stops_pinning_gaps():
    """`zone_dir == 0` means the leg has completed (mpc `fiboResetActive ? 0 : fibo_dir`).

    The CONSUMER owns that zeroing; this engine only has to stop protecting when it arrives. Its
    levels go back into the ordinary FIFO queue, which is the whole point — a setup that is over
    must not keep holding slots away from the next one.

    🔴 THIS TEST USED A BULLISH GAP FOR ONE DRAFT AND COULD NOT SEE THE GUARD IT NAMES. With
    `zone_dir == 0` the direction test alone already rejects a BULLISH gap — `is_bullish != (0 == 1)`
    is True — so deleting the `zone_dir == 0` guard entirely left the whole suite green. The guard is
    reachable only from the BEARISH side, where `False != False` waves the direction test through.
    **Watched RED by deleting the guard**, which is the only reason this docstring is trustworthy.
    """
    ev = _bear_staircase(FairValueGapEngine(max_count=2), zone_lo=85.0, zone_hi=90.0, zone_dir=0)
    assert [g.born_index for g in ev.active] == [3, 4]


def test_no_band_passed_is_plain_fifo():
    """The shipped path for every consumer today: no band, so nothing changes at all."""
    ev = _staircase(FairValueGapEngine(max_count=2))
    assert [g.born_index for g in ev.active] == [3, 4]


def test_band_overlap_not_containment():
    """`gTop >= zoneLo and gBot <= zoneHi` — OVERLAP, mirroring Pine.

    A band sitting entirely INSIDE a large gap still protects it. Requiring containment instead
    would silently drop exactly the big displacement gaps a retrace is entered from, and the
    symptom would be an absence — nothing on screen to say a level was thrown away.
    """
    ev = _staircase(FairValueGapEngine(max_count=2), zone_lo=112.0, zone_hi=114.0, zone_dir=1)
    assert [g.born_index for g in ev.active] == [2, 3, 4]


def test_band_and_eq_exemptions_compose():
    """Two exemptions, either of which alone protects a gap (mpc composes them with `or`).

    The band covers the bar-2 gap; an EQ level at 125 sits inside the bar-3 gap [116,130] and in no
    other. With a cap of 1 the only ORDINARY gap is bar 4, so all three survive — which neither
    exemption could achieve alone.

    🔴 THE LEVEL WAS 120 FOR ONE DRAFT AND THE TEST WAS VACUOUS, in green. 120 is the bar-2 gap's
    top edge, so the EQ rule protected BOTH gaps by itself and the test passed just as happily with
    the band exemption deleted — proven by mutation, not by reading. **A test whose inputs cannot
    distinguish the behaviours it names is describing a system where the thing under test does
    nothing**, which is the same defect this repo already recorded as a scale factor of 1.
    """
    ev = _staircase(FairValueGapEngine(max_count=1), eq_levels=[125.0], **_BAND)
    assert [g.born_index for g in ev.active] == [2, 3, 4]
    assert ev.evicted == []
