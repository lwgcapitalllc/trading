"""Tests for backtest/tools/sweep_edge.py — the sweep trigger and its confluence set.

⚠ WHY THESE EXIST AND THE OTHER STUDY TOOLS HAVE NONE. `sweep_edge.py` answers ONE question —
structure levels or session levels or both — and that answer is decided entirely by two small
pieces of bookkeeping: which bar counts as a sweep, and which families were holding a level at
that price. A slip in either reports a clean, plausible ranking exactly as cleanly as the truth
does, and the tool prints ninety rows of it. That is the same argument `overlap_audit.py` and
`jitter_audit.py` carry for their own arithmetic.

🔴 EVERY TEST HERE WAS WATCHED RED, and the first two were watched red against a REAL BUG rather
than a synthetic mutation: `sweep_pass` scored confluence off the live dict it was popping from,
so the four levels swept at 1192.89 on the real cache reported four DIFFERENT confluence sets,
descending as they were removed. Restoring `for lid, lv in snap.items()` -> reading `live` in
`_build` reddens `test_confluence_*` and nothing else.

⚠ Nothing here touches `backtest/cache/` — those files are git-ignored broker data, so a
cache-backed test passes on this machine and errors on a fresh clone. Levels are built by hand.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "tools"))

import sweep_edge as se  # noqa: E402

ATR = 1.0
CONF = 0.5


def bar(i, o, h, low, c, ts=0):
    return se.Row(i=i, ts=ts, o=o, h=h, l=low, c=c, v=0.0)


def lvl(family, side, price, name="X", created=0, sibling=None, session=None):
    return se.Live(
        family=family,
        side=side,
        name=name,
        price=price,
        created_i=created,
        sibling=sibling,
        session_name=session,
    )


def run(live, r, arm=None, mode="reclaim"):
    return se.sweep_pass(live, arm, r, ATR, mode, "London", CONF, 0, 0, 0)


# --------------------------------------------------------------------------- the trigger


def test_wick_through_and_close_back_is_a_sweep():
    live = {1: lvl("session", "low", 100.0)}
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    assert [s.family for s in fired] == ["session"]
    assert fired[0].direction == 1
    assert fired[0].stop == 99.5  # the sweep wick, not the level
    assert live == {}  # a level fires once


def test_close_through_is_a_BREAK_and_the_level_is_dead():
    """The distinction the whole trigger rests on: a close beyond the level means the market
    went past it, so it is not a pool of stops any more and may never be swept later."""
    live = {1: lvl("session", "low", 100.0)}
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 99.6))
    assert fired == []
    assert live == {}

    # and it stays dead — a later wick-and-reclaim at the same price fires nothing
    fired, _ = run(live, bar(6, 99.6, 101.0, 99.0, 100.9))
    assert fired == []


def test_a_bar_that_never_reaches_the_level_does_nothing():
    live = {1: lvl("session", "low", 100.0)}
    fired, _ = run(live, bar(5, 101.0, 102.0, 100.5, 101.5))
    assert fired == []
    assert set(live) == {1}


def test_high_side_level_is_the_mirror_and_trades_short():
    live = {1: lvl("day", "high", 100.0)}
    fired, _ = run(live, bar(5, 99.5, 100.8, 99.4, 99.7))
    assert fired[0].direction == -1
    assert fired[0].stop == 100.8


def test_wick_mode_ignores_the_close_entirely():
    """`--trigger wick` is the control that showed the reclaim is doing the work. It must fire
    on the bar the reclaim rule calls a BREAK, or that comparison is measuring nothing."""
    live = {1: lvl("session", "low", 100.0)}
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 99.6), mode="wick")
    assert len(fired) == 1
    assert fired[0].direction == 1


# --------------------------------------------------------------------------- confluence


def test_confluence_is_the_same_for_every_level_swept_at_one_price():
    """🔴 The regression test for the order-dependence bug. Four families holding one price is
    the normal case, not a corner: a session low that is also PDL, PWL and the last H4 low is a
    single line on the chart. All four must report all four."""
    live = {
        1: lvl("session", "low", 100.0),
        2: lvl("day", "low", 100.0),
        3: lvl("week", "low", 100.0),
        4: lvl("h4", "low", 100.05),
    }
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))

    assert len(fired) == 4
    expected = {"session", "day", "week", "h4"}
    for s in fired:
        assert set(s.conf) == expected, f"{s.family} saw {sorted(s.conf)}"


def test_confluence_survives_reversing_the_insertion_order():
    """The bug was invisible under any single ordering — it produced a self-consistent set every
    time. Only comparing two orderings exposes it."""

    def sets_for(items):
        live = dict(items)
        fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
        return {s.family: set(s.conf) for s in fired}

    items = [
        (1, lvl("session", "low", 100.0)),
        (2, lvl("day", "low", 100.0)),
        (3, lvl("h4", "low", 100.0)),
    ]
    assert sets_for(items) == sets_for(list(reversed(items)))


def test_the_structure_arm_counts_toward_confluence_and_is_counted_by_it():
    """The armed structure level lives outside `live`, so it is the one that gets forgotten."""
    live = {1: lvl("session", "low", 100.0)}
    arm = lvl("structure", "low", 100.1)
    fired, new_arm = run(live, bar(5, 100.5, 101.0, 99.5, 100.6), arm=arm)

    assert new_arm is None  # the arm was swept too
    by_family = {s.family: set(s.conf) for s in fired}
    assert by_family["session"] == {"session", "structure"}
    assert by_family["structure"] == {"session", "structure"}


def test_a_level_beyond_the_tolerance_is_not_confluence():
    live = {
        1: lvl("session", "low", 100.0),
        2: lvl("day", "low", 100.0 - 2 * CONF * ATR),  # comfortably outside
    }
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    swept = [s for s in fired if s.family == "session"][0]
    assert set(swept.conf) == {"session"}


def test_a_level_on_the_OTHER_side_is_not_confluence():
    """A high and a low at the same price are opposite trades, not agreement."""
    live = {
        1: lvl("session", "low", 100.0),
        2: lvl("day", "high", 100.0),
    }
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    swept = [s for s in fired if s.family == "session"][0]
    assert set(swept.conf) == {"session"}


# --------------------------------------------------------------------------- targets


def test_rotation_targets_only_count_when_they_are_AHEAD_of_the_entry():
    """A previous-day high BELOW a long's entry is history, not a target. Counting it would put
    a free hit in the rotation column on every trade — and the rotation column is the whole
    answer to "does it come back to the other end".

    ⚠ Both target paths are exercised deliberately. The sibling goes through `_ahead` and the
    day/week targets through their own comprehension, so a fixture whose sibling happens to be
    ahead tests only half of it — which is exactly what the first version of this test did, and
    a mutation that deleted the `_ahead` guard outright survived it.
    """
    live = {
        1: lvl("session", "low", 100.0, sibling=103.0),
        2: lvl("day", "high", 99.0),  # behind a long — must not become a target
        3: lvl("week", "high", 110.0),
    }
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    s = [x for x in fired if x.family == "session"][0]
    assert s.tgt_sibling == 103.0
    assert s.tgt_day is None
    assert s.tgt_week == 110.0


def test_a_sibling_BEHIND_the_entry_is_not_a_target_either():
    """The `_ahead` guard on its own. A session low swept so hard that the session's HIGH is now
    below the entry has no rotation left to make."""
    live = {1: lvl("session", "low", 100.0, sibling=99.2)}
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    assert fired[0].tgt_sibling is None


def test_the_nearest_target_ahead_is_the_one_chosen():
    """Two day highs above a long: the rotation column asks whether it got there, so it must be
    the first one, not whichever the dict happened to yield."""
    live = {
        1: lvl("session", "low", 100.0),
        2: lvl("day", "high", 120.0),
        3: lvl("day", "high", 104.0),
    }
    fired, _ = run(live, bar(5, 100.5, 101.0, 99.5, 100.6))
    s = [x for x in fired if x.family == "session"][0]
    assert s.tgt_day == 104.0


def test_scoring_stops_at_the_stop_and_the_stop_wins_a_tied_bar():
    """The convention every number in the study inherits: when one bar holds both the stop and
    the target, the STOP wins. It makes the tool pessimistic, which is the safe direction."""
    rows = [bar(i, 100.0, 100.0, 100.0, 100.0) for i in range(4)]
    rows[1] = bar(1, 100.0, 104.0, 98.0, 100.0)  # holds +2R target AND the -1R stop
    sig = se.Signal(
        family="t",
        name="t",
        i=0,
        ts=0,
        direction=1,
        level=100.0,
        entry=100.0,
        stop=99.0,
        risk_atr=1.0,
        depth_atr=0.0,
        age=0,
        ext_dir=0,
        ext_run=0,
        int_run=0,
        with_trend=False,
        swept_in="-",
        origin="-",
    )
    se.resolve(rows, sig, target_r=2.0, horizon=10)
    assert sig.outcome == "loss"
    assert sig.mfe_r == 0.0  # the ambiguous bar's excursion is discarded, not banked


def test_a_zero_risk_signal_is_refused_rather_than_scored():
    sig = se.Signal(
        family="t",
        name="t",
        i=0,
        ts=0,
        direction=1,
        level=100.0,
        entry=100.0,
        stop=100.0,
        risk_atr=0.0,
        depth_atr=0.0,
        age=0,
        ext_dir=0,
        ext_run=0,
        int_run=0,
        with_trend=False,
        swept_in="-",
        origin="-",
    )
    se.resolve([bar(i, 100.0, 101.0, 99.0, 100.0) for i in range(4)], sig, 2.0, 10)
    assert sig.outcome == "bad"


# --------------------------------------------------------------------------- dedupe


def test_dedupe_collapses_one_trade_wearing_several_hats():
    """The per-family rows are meant to double-count — that is what makes them comparable. Any
    row claiming to be a BOOK must not, or it reports the same trade up to five times."""
    common = dict(
        name="X",
        ts=0,
        direction=1,
        level=100.0,
        entry=100.6,
        stop=99.5,
        risk_atr=1.0,
        depth_atr=0.0,
        age=0,
        ext_dir=0,
        ext_run=0,
        int_run=0,
        with_trend=False,
        swept_in="-",
        origin="-",
    )
    same = [se.Signal(family=f, i=5, **common) for f in ("session", "day", "week")]
    other = se.Signal(family="session", i=6, **common)
    assert len(se._dedupe(same)) == 1
    assert len(se._dedupe(same + [other])) == 2


def test_dedupe_keeps_opposite_directions_on_one_bar_apart():
    """A bar can sweep a high and a low. Those are two trades, not one."""
    common = dict(
        name="X",
        ts=0,
        level=100.0,
        entry=100.0,
        risk_atr=1.0,
        depth_atr=0.0,
        age=0,
        ext_dir=0,
        ext_run=0,
        int_run=0,
        with_trend=False,
        swept_in="-",
        origin="-",
    )
    a = se.Signal(family="session", i=5, direction=1, stop=99.0, **common)
    b = se.Signal(family="session", i=5, direction=-1, stop=101.0, **common)
    assert len(se._dedupe([a, b])) == 2


# --------------------------------------------------------------------------- guards


def test_the_feed_version_guard_is_a_FLOOR_not_an_equality():
    """`!= 2` bricked three sibling study tools the day FEED_VERSION went to 3 for a reason that
    had nothing to do with time. v3 must be acceptable input here."""
    assert se.MIN_FEED_VERSION == 2
    assert 3 >= se.MIN_FEED_VERSION


@pytest.mark.parametrize(
    "risk_atr,expected", [(0.24, 1), (0.25, 1), (0.4, 2), (0.51, 2), (999.0, 40)]
)
def test_control_stop_buckets_are_clamped_at_both_ends(risk_atr, expected):
    """A stop distance outside the grid must land in the nearest cell, never index off the end —
    an unclamped bucket silently drops those signals from every control."""
    assert se.Control.bucket(risk_atr) == expected
