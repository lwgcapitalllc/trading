"""Tests for backtest/tools/overlap_audit.py.

The tool's output is a set of confident-looking counts that nobody can eyeball against a
6.5-year replay, which is exactly the shape this repo keeps getting wrong — an arithmetic
slip here would report "the legs never overlap" just as cleanly as the truth does. So the
bar arithmetic is pinned on hand-traced cases where the answer is countable by hand.

The replay itself is not tested here (that is the strategies' own suites); what is tested
is everything between a trade list and a printed number.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "overlap_audit.py"
_spec = importlib.util.spec_from_file_location("overlap_audit", _TOOL)
oa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oa)


class _T:
    """The three Trade fields the tool reads."""

    def __init__(self, direction, entry, exit_, r=0.0):
        self.dir = direction
        self.entry_index = entry
        self.exit_index = exit_
        self.r = r


def _overlap(holds_a, holds_b, n):
    """The tool's own bar-overlap arithmetic, mirrored so a change to it fails here."""
    oa_, ob_ = oa._occupancy(holds_a, n), oa._occupancy(holds_b, n)
    both = same = opp = 0
    for x, y in zip(oa_, ob_):
        if x and y:
            both += 1
            same += x == y
            opp += x != y
    return both, same, opp


# ── the bar range a trade occupies ───────────────────────────────────────────────

def test_a_hold_is_half_open_so_a_trade_occupies_its_entry_bar_not_its_exit_bar():
    # Entering on bar 10 and exiting on bar 13 = exposed on 10, 11, 12.
    holds = oa._holds([_T(1, 10, 13)])
    assert oa._occupancy(holds, 20).count(1) == 3


def test_a_same_bar_entry_and_exit_still_occupies_one_bar():
    # A trade that opens and closes inside one bar is real exposure, and a naive
    # half-open range would score it zero and quietly drop it from every count.
    holds = oa._holds([_T(-1, 5, 5)])
    occ = oa._occupancy(holds, 10)
    assert occ.count(-1) == 1
    assert occ[5] == -1


def test_direction_is_carried_onto_every_bar_of_the_hold():
    occ = oa._occupancy(oa._holds([_T(-1, 2, 5)]), 8)
    assert occ == [0, 0, -1, -1, -1, 0, 0, 0]


# ── overlap between the two bots ─────────────────────────────────────────────────

def test_back_to_back_trades_do_not_overlap():
    # A ends ON the bar B starts. With half-open ranges that is zero shared bars, and
    # it must stay that way — counting the handover bar would manufacture an overlap
    # out of two bots that were never in the market together.
    a = oa._holds([_T(1, 10, 20)])
    b = oa._holds([_T(1, 20, 30)])
    assert _overlap(a, b, 40) == (0, 0, 0)


def test_one_bar_of_genuine_overlap_is_counted():
    a = oa._holds([_T(1, 10, 21)])
    b = oa._holds([_T(1, 20, 30)])
    assert _overlap(a, b, 40) == (1, 1, 0)


def test_same_and_opposite_direction_overlap_are_split():
    # A is long 10-20 and short 30-40; B is long 15-35. Shared: 15-20 (5 bars, same
    # side) and 30-35 (5 bars, opposite).
    a = oa._holds([_T(1, 10, 20), _T(-1, 30, 40)])
    b = oa._holds([_T(1, 15, 35)])
    assert _overlap(a, b, 50) == (10, 5, 5)


def test_overlap_beyond_the_frame_is_clipped_not_counted():
    # An exit index past the last bar (an open position at the end of the run) must not
    # index off the end, and must not be credited with bars that do not exist.
    a = oa._holds([_T(1, 8, 100)])
    b = oa._holds([_T(1, 8, 100)])
    assert _overlap(a, b, 10) == (2, 2, 0)


def test_two_positions_at_once_within_ONE_strategy_raises():
    # Every bot here runs a single position slot. If that ever changes, collapsing the
    # two into one direction cell would understate the bot's own exposure and silently
    # halve the overlap — refuse rather than mis-measure.
    with pytest.raises(SystemExit):
        oa._occupancy(oa._holds([_T(1, 5, 15), _T(-1, 10, 20)]), 30)


# ── correlation ──────────────────────────────────────────────────────────────────

def test_correlation_of_a_flat_series_is_None_not_zero():
    # "Cannot be computed" and "uncorrelated" are different facts. Returning 0.0 for the
    # first is the same absence-as-value trap that let a dead MT5 link read as a quiet
    # market — a flat month stream would print as reassuring independence.
    assert oa._pearson([1.0, 2.0, 3.0], [4.0, 4.0, 4.0]) is None
    assert oa._pearson([1.0, 2.0], [1.0, 2.0]) is None


def test_correlation_of_identical_series_is_one():
    assert oa._pearson([1.0, -2.0, 3.0, 0.5], [1.0, -2.0, 3.0, 0.5]) == pytest.approx(1.0)


def test_correlation_of_mirrored_series_is_minus_one():
    assert oa._pearson([1.0, -2.0, 3.0, 0.5], [-1.0, 2.0, -3.0, -0.5]) == pytest.approx(-1.0)
