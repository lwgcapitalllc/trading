"""
Tests for market_structure.StructureEngine — hand-traced against the ported Pine logic.

The main scenario (test_full_scenario) uses major_length=2 (pivot window = 2+1+2 = 5 bars)
instead of the production default of 15, purely so the bar count stays small enough to hand-trace
and comment. The state machine itself is identical regardless of major_length — only the pivot
window width and the ~majorLength-bar new-swing-candidate lag change.

Every asserted event below was derived by manually replaying the ported rules in engine.py
(mirroring structure_engine.pine) bar by bar before running the code — see the inline comments.
Reasoning was cross-checked by actually running the engine and confirming it matched the
hand-derived prediction before being locked into these assertions.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_structure import Bar, StructureEngine


def B(i, o, h, l, c):
    return Bar(index=i, open=o, high=h, low=l, close=c)


# ── The full 15-bar scenario ────────────────────────────────────────────────
#
# major_length=2 → pivot window is 5 bars (2 left + center + 2 right); a pivot is only known
# 2 bars after the fact.
#
# Bars 0-4: a down-then-up V. Bar 2 (low=9.0) is the unique local min across bars 0-4, so at
#   bar 4 ta.pivotlow confirms it as pl_val=9.0 located at bar 2. This seeds ASL=9.0@2, dir=1.
#   The same bar's bootstrap scan (opposite-side seed) finds bar 4's own high (10.3) as the
#   highest value scanned so far and, since 10.3 > 9.0, seeds ASH=10.3@4 too. seeded=True.
#
# Bars 5-6: price grinds up. At bar 6, close=10.35 > ash(10.3) → body-close break → bull_bos.
#   dir was already 1 (not -1), so is_choch=False: plain BOS, not SOS. ash is consumed (→None),
#   dir stays 1, and a new pullback-tracking cycle starts (pb_mode=1) seeded with pb_extreme=
#   high@6=10.5. Also since there was no active bearish pullback to promote, asl is re-scanned
#   over history since last_conf_high_loc and lands on 9.6 (bar4's low — the lowest low scanned
#   in the bounded window), i.e. the "else" (bounded rescan) branch, not "was_in_bear_pb".
#
# Bar 7: continues up (close=10.5), no break (ash is None so ash_broken is False; asl=9.6 not
#   touched). Pullback-mode-1 tracking updates: high=10.6 > current pb_extreme(10.5) → resets
#   extreme to 10.6@7, count back to 0.
#
# Bar 8: big bearish bar, close=8.2. asl at this point is 9.6 → close < asl → asl_broken →
#   bear_bos. dir was 1 and choch_lock was False → is_choch=True → bear_sos (CHoCH) fires too,
#   and choch_lock is set. Because pb_mode was 1 with an active pb_extreme (10.6@7), this takes
#   the "was_in_bull_pb" path: that pullback extreme (10.6@7) gets promoted straight to the new
#   locked ASH (skipping the bounded-rescan branch), and a new pb_mode=-1 (tracking down) cycle
#   starts seeded with pb_extreme=low@8=8.0.
#
# Bars 9-11: three qualifying "up" pullback closes against the pb_mode=-1 down-tracking cycle
#   (a pullback against a down move must close *above* a rising threshold, mirroring the mode=1
#   case). Chosen so each bar avoids being both "inside" the previous bar and a fresh lower low
#   (which would reset the extreme/count):
#     bar 9  (h=8.6, l=8.1, c=8.5): not inside prior (bar8 range 8.55h(open? n/a)/8.0l — high 8.6
#             establishes a genuinely wider range); no new low (8.1 not < 8.0); close 8.5 >
#             threshold 8.0 → qualifies, count=1, last-qualify-high(lqh)=8.6.
#     bar 10 (h=8.9, l=8.05, c=8.8): high 8.9 > prev bar's high 8.6 → not inside; no new low
#             (8.05 not < 8.0); close 8.8 > threshold(lqh)=8.6 → qualifies, count=2, lqh=8.9.
#     bar 11 (h=9.2, l=8.0, c=9.1): high 9.2 > prev high 8.9 → not inside; low 8.0 == pb_extreme
#             (strict "<" test fails so no reset); close 9.1 > threshold(lqh)=8.9 → qualifies,
#             count reaches 3 → CONFIRM new ASL at pb_extreme=8.0, loc=8, LOCKED.
#             This fires external new_swing_low=True, which seeds the internal engine into
#             mode=1 (tracking up toward the next internal swing high). Internal pullback
#             tracking starts in this same bar (i_pb_started was False) at pb_extreme=high@11=9.2.
#
# Bars 12-14: three qualifying internal down-pullback closes (mirrors the external mechanism,
#   scoped to the internal engine) against the internal mode=1 (tracking up) cycle:
#     bar 12 (h=9.15, l=8.9, c=8.95): inside bar 11's range (9.15<9.2 and 8.9>8.0) but this is
#             the internal engine's "candle 1" (i_pb_lqc is na and extreme unchanged) so the
#             is_inside gate is bypassed; close 8.95 < threshold(pb_extreme)=9.2 → qualifies,
#             count=1, lqh=8.9.
#     bar 13 (h=9.0, l=8.7, c=8.8): not inside bar 12 (low 8.7 not > 8.9); close 8.8 <
#             threshold(lqh)=8.9 → qualifies, count=2, lqh=8.7.
#     bar 14 (h=8.85, l=8.5, c=8.6): not inside bar 13 (low 8.5 not > 8.7); close 8.6 <
#             threshold(lqh)=8.7 → qualifies, count reaches 3 → CONFIRM internal swing high at
#             pb_extreme=9.2, loc=11. Since this is the first internal swing since seeding
#             (i_had_bos is still False), the label is "iSH" (not "iHH" — see NOTE in engine.py:
#             the Pine source's label only ever distinguishes "first swing" vs "not first swing",
#             it never actually compares against a previous internal price despite the code
#             comment implying otherwise).
#
# Bars 15-16: exercise the internal iBOS / demoted-iHL path, which nothing in bars 0-14 reaches.
#   After bar 14 confirms the internal swing high (iSH @ 9.2), internal mode drops to 0
#   ("watching") in that same bar, with last_mode still 1 (set back at bar 11's seed) — so the
#   "track extreme while watching" block immediately starts tracking the LOW as tracked_ext,
#   starting with bar 14's own low (8.5), same-bar.
#     bar 15 (h=8.9, l=8.55, c=8.7): low 8.55 doesn't beat tracked_ext=8.5, so tracked_ext stays
#             8.5@14. No external or internal event fires.
#     bar 16 (h=9.4, l=8.6, c=9.3): close 9.3 > i_sw_price(9.2) with last_mode==1 → internal iBOS
#             fires (bullish), at price=9.2 (the internal swing just broken). Since tracked_ext
#             (8.5@14) is set, it gets demoted and labeled "iHL" — the label the port had
#             previously dropped entirely (see CLAUDE.md). Neither bar touches the external
#             engine: close stays well inside [asl=8.0, ash=10.6].
# All values below were confirmed by running the engine and printing every non-default event
# field per bar, cross-checked against the reasoning above before being locked into assertions.
_SCENARIO_BARS = [
    B(0, 10.0, 10.2, 9.8, 10.0),
    B(1, 10.0, 10.1, 9.5, 9.6),
    B(2, 9.6, 9.7, 9.0, 9.2),
    B(3, 9.2, 9.8, 9.1, 9.7),
    B(4, 9.7, 10.3, 9.6, 10.2),
    B(5, 10.2, 10.4, 10.0, 10.1),
    B(6, 10.1, 10.5, 10.0, 10.35),
    B(7, 10.35, 10.6, 10.2, 10.5),
    B(8, 10.5, 10.55, 8.0, 8.2),
    B(9, 8.2, 8.6, 8.1, 8.5),
    B(10, 8.5, 8.9, 8.05, 8.8),
    B(11, 8.8, 9.2, 8.0, 9.1),
    B(12, 9.1, 9.15, 8.9, 8.95),
    B(13, 8.95, 9.0, 8.7, 8.8),
    B(14, 8.8, 8.85, 8.5, 8.6),
    B(15, 8.6, 8.9, 8.55, 8.7),
    B(16, 8.7, 9.4, 8.6, 9.3),
]


@pytest.fixture
def scenario_events():
    eng = StructureEngine(major_length=2)
    return eng.replay(_SCENARIO_BARS)


def test_bootstrap_seeds_ash_and_asl():
    """Bars 0-4: bar 2's low (9.0) is the unique pivot low over the 5-bar window ending at bar 4.
    It seeds ASL, and the same-bar bootstrap scan seeds ASH from bar 4's own high (10.3)."""
    eng = StructureEngine(major_length=2)
    eng.replay(_SCENARIO_BARS[:5])  # bars 0-4

    assert eng.active_swing_low is not None
    assert eng.active_swing_low.price == 9.0
    assert eng.active_swing_low.index == 2

    assert eng.active_swing_high is not None
    assert eng.active_swing_high.price == 10.3
    assert eng.active_swing_high.index == 4

    assert eng.dir == 1  # pivot low found first → dir seeded bullish


def test_no_events_fire_during_bootstrap(scenario_events):
    for ev in scenario_events[:6]:  # bars 0-5, before the bull BOS at bar 6
        assert not ev.external.bull_bos
        assert not ev.external.bear_bos
        assert not ev.external.bull_sos
        assert not ev.external.bear_sos


def test_bar4_seeds_unconfirmed_high_and_low(scenario_events):
    """Bar 4's bootstrap creates two *unconfirmed* ("ASH"/"ASL", non-locked) candidates in the
    same bar: ASL from the pivot-low seed, ASH from the same-bar opposite-side scan."""
    ev = scenario_events[4].external
    assert ev.unconfirmed_low_set is True
    assert ev.unconfirmed_low_price == 9.0
    assert ev.unconfirmed_low_index == 2
    assert ev.unconfirmed_high_set is True
    assert ev.unconfirmed_high_price == 10.3
    assert ev.unconfirmed_high_index == 4


def test_bull_bos_fires_on_bar_6(scenario_events):
    """close=10.35 body-closes above ash=10.3. dir was already bullish (1), so this is a
    continuation BOS, not a CHoCH/SOS. The broken ash is the first-ever confirmed high, so it's
    classified "HH"; the pre-existing (bootstrap) asl is demoted and classified "HL"; and a
    fresh unconfirmed asl is set from the bounded rescan."""
    ev = scenario_events[6].external
    assert ev.bull_bos is True
    assert ev.bull_sos is False
    assert ev.bull_bos_price == 10.3

    assert ev.broken_high_label == "HH"
    assert ev.broken_high_price == 10.3
    assert ev.broken_high_index == 4

    assert ev.broken_low_label == "HL"
    assert ev.broken_low_price == 9.0
    assert ev.broken_low_index == 2

    assert ev.unconfirmed_low_set is True
    assert ev.unconfirmed_low_price == 9.6
    assert ev.unconfirmed_low_index == 4


def test_bear_sos_choch_fires_on_bar_8(scenario_events):
    """close=8.2 body-closes below asl=9.6. dir was bullish (1) and choch_lock was False, so
    this break is classified as a CHoCH: both bear_bos and bear_sos fire, and dir flips to -1.
    A bullish pullback was in progress (pb_extreme=10.6@7), so it gets immediately promoted to
    a LOCKED ASH and classified "HH"; the broken asl is classified "HL".

    The promotion does NOT raise new_swing_high — that flag fires only on a clean 3-candle
    pullback confirmation, matching the Pine source (which sets st.new_swing_high only in the
    pb_mode==1 confirm block, never in the break branch). This is the parity fix validated on
    the XAUUSD-15m export."""
    eng = StructureEngine(major_length=2)
    events = eng.replay(_SCENARIO_BARS)

    ev = events[8].external
    assert ev.bear_bos is True
    assert ev.bear_bos_price == 9.6
    assert ev.bear_sos is True  # CHoCH
    assert eng.dir == -1  # confirmed via replay of full scenario, dir stays -1 after bar 8

    # Break-promotion locks the ASH but must NOT fire new_swing_high (Pine parity).
    assert ev.new_swing_high is False
    assert ev.new_swing_high_price is None
    assert ev.new_swing_high_index is None
    # The level is still locked and active, just not signalled as a new_swing event.
    assert eng.active_swing_high is not None
    assert eng.active_swing_high.price == 10.6
    assert eng.active_swing_high.index == 7
    assert eng.active_swing_high.locked is True

    assert ev.broken_high_label == "HH"
    assert ev.broken_high_price == 10.6
    assert ev.broken_high_index == 7

    assert ev.broken_low_label == "HL"
    assert ev.broken_low_price == 9.6
    assert ev.broken_low_index == 4

    # Re-derive dir at exactly bar 8 (not the end of the full replay) via a fresh engine.
    eng2 = StructureEngine(major_length=2)
    eng2.replay(_SCENARIO_BARS[:9])  # bars 0-8
    assert eng2.dir == -1


def test_external_new_swing_low_confirms_on_bar_11(scenario_events):
    """3-candle pullback confirmation locks a new ASL at pb_extreme=8.0 (set at bar 8), fires
    new_swing_low, and this in turn seeds the internal engine."""
    ev = scenario_events[11].external
    assert ev.new_swing_low is True

    eng = StructureEngine(major_length=2)
    eng.replay(_SCENARIO_BARS[:12])  # bars 0-11
    asl = eng.active_swing_low
    assert asl is not None
    assert asl.price == 8.0
    assert asl.index == 8
    assert asl.locked is True

    # Internal engine was seeded into mode=1 (tracking up) by this new_swing_low.
    assert eng.internal_mode == 1


def test_internal_swing_high_confirms_on_bar_14(scenario_events):
    """3 qualifying internal pullback closes confirm an internal swing high (iSH — first
    internal swing since seeding) at price=9.2 (the high set back at bar 11)."""
    ev = scenario_events[14].internal
    assert ev.new_swing_high is True
    assert ev.swing_high_label == "iSH"

    eng = StructureEngine(major_length=2)
    eng.replay(_SCENARIO_BARS[:15])  # bars 0-14 only — bars 15-16 move past this point
    swing = eng.internal_swing
    assert swing is not None
    assert swing.price == 9.2
    assert swing.index == 11
    assert swing.locked is True
    # Confirming the swing hands control back to mode=0 (watching), per the Pine source.
    assert eng.internal_mode == 0


def test_internal_ibos_and_demoted_low_label_on_bar16(scenario_events):
    """Bar 16 closes above the just-confirmed internal swing high (9.2) with last_mode still 1
    (tracking-up context) → internal iBOS fires. The low tracked while watching (8.5, set at
    bar 14 the moment mode dropped to 0) gets demoted and labeled "iHL" — the label the port
    had previously dropped entirely. Neither event touches the external engine."""
    ev = scenario_events[16]
    assert ev.internal.bull_bos is True
    assert ev.internal.bull_bos_price == 9.2
    assert ev.internal.demoted_low_label == "iHL"
    assert ev.internal.demoted_low_price == 8.5
    assert ev.internal.demoted_low_index == 14

    assert ev.external == type(ev.external)()  # no external event fired on this bar


def test_replay_accepts_dict_bars():
    """replay() must accept an iterable of plain dicts, not just Bar instances (per the
    documented convenience API), and produce identical events to the Bar-object path."""
    dict_bars = [
        {"index": b.index, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
        for b in _SCENARIO_BARS
    ]
    eng_dicts = StructureEngine(major_length=2)
    events_from_dicts = eng_dicts.replay(dict_bars)

    eng_bars = StructureEngine(major_length=2)
    events_from_bars = eng_bars.replay(_SCENARIO_BARS)

    assert len(events_from_dicts) == len(events_from_bars)
    for a, b in zip(events_from_dicts, events_from_bars):
        assert a == b


def test_update_called_bar_by_bar_matches_replay():
    """update() fed one bar at a time must produce identical results to replay() — replay is
    documented as a pure convenience wrapper, not a different code path."""
    eng = StructureEngine(major_length=2)
    manual_events = [eng.update(b) for b in _SCENARIO_BARS]

    eng2 = StructureEngine(major_length=2)
    replay_events = eng2.replay(_SCENARIO_BARS)

    assert manual_events == replay_events
