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


def _frame(minutes, n, start="2024-01-01 00:00:00"):
    """A synthetic bar frame on a regular `minutes` grid.

    Real feeds have weekend holes; these do not, on purpose. The arithmetic under test is
    "which grid unit does this bar open on", and a gapless frame is the only one where the
    right answer is countable by hand.
    """
    import pandas as pd

    idx = pd.date_range(start=start, periods=n, freq=f"{minutes}min")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


_DF15 = _frame(15, 200)
_GRID15 = oa.Grid(_DF15)


def _holds(trades, df=None, grid=None):
    """`_holds` on ONE 15-minute frame, where the grid is that frame and the map is identity.

    Every case below this line was written before the tool could take two frames, and they
    are left reading in bar indices deliberately — if the same-frame path ever stops being
    the identity, these go red rather than quietly measuring something else.
    """
    df = _DF15 if df is None else df
    return oa._holds(trades, df, _GRID15 if grid is None else grid)


def _overlap(holds_a, holds_b, n):
    """The tool's OWN arithmetic, called — not mirrored (2026-09-02).

    ⚠ This used to be a hand-written copy, described here as "mirrored so a change to it fails
    here". It did fail here, which was the good half; the bad half is that a mirror has to be
    re-derived by hand by whoever changes the rule, and this repo has already recorded that exact
    shape drifting in silence between a Python evaluator and its JavaScript twin. Calling the
    tool's `overlap_counts` means these cases pin the thing that actually runs.
    """
    return oa.overlap_counts(oa._occupancy(holds_a, n), oa._occupancy(holds_b, n))


# ── the bar range a trade occupies ───────────────────────────────────────────────


# ⚠ These three moved their PREMISE on 2026-09-02, never their subject. `_occupancy` returns
# `(longs, shorts)` per bar instead of a single direction, because a bot with re-entries genuinely
# holds two positions at once. Half-open ranges, the same-bar round trip and direction being
# carried across the hold are all still exactly what is being pinned — only the cell's shape moved.


def test_a_hold_is_half_open_so_a_trade_occupies_its_entry_bar_not_its_exit_bar():
    # Entering on bar 10 and exiting on bar 13 = exposed on 10, 11, 12.
    holds = _holds([_T(1, 10, 13)])
    assert sum(1 for longs, _ in oa._occupancy(holds, 20) if longs) == 3


def test_a_same_bar_entry_and_exit_still_occupies_one_bar():
    # A trade that opens and closes inside one bar is real exposure, and a naive
    # half-open range would score it zero and quietly drop it from every count.
    holds = _holds([_T(-1, 5, 5)])
    occ = oa._occupancy(holds, 10)
    assert sum(1 for _, shorts in occ if shorts) == 1
    assert occ[5] == (0, 1)


def test_direction_is_carried_onto_every_bar_of_the_hold():
    occ = oa._occupancy(_holds([_T(-1, 2, 5)]), 8)
    flat, short = (0, 0), (0, 1)
    assert occ == [flat, flat, short, short, short, flat, flat, flat]


# ── overlap between the two bots ─────────────────────────────────────────────────


def test_back_to_back_trades_do_not_overlap():
    # A ends ON the bar B starts. With half-open ranges that is zero shared bars, and
    # it must stay that way — counting the handover bar would manufacture an overlap
    # out of two bots that were never in the market together.
    a = _holds([_T(1, 10, 20)])
    b = _holds([_T(1, 20, 30)])
    assert _overlap(a, b, 40) == (0, 0, 0)


def test_one_bar_of_genuine_overlap_is_counted():
    a = _holds([_T(1, 10, 21)])
    b = _holds([_T(1, 20, 30)])
    assert _overlap(a, b, 40) == (1, 1, 0)


def test_same_and_opposite_direction_overlap_are_split():
    # A is long 10-20 and short 30-40; B is long 15-35. Shared: 15-20 (5 bars, same
    # side) and 30-35 (5 bars, opposite).
    a = _holds([_T(1, 10, 20), _T(-1, 30, 40)])
    b = _holds([_T(1, 15, 35)])
    assert _overlap(a, b, 50) == (10, 5, 5)


def test_overlap_beyond_the_frame_is_clipped_not_counted():
    # An exit index past the last bar (an open position at the end of the run) must not
    # index off the end, and must not be credited with bars that do not exist.
    a = _holds([_T(1, 8, 100)])
    b = _holds([_T(1, 8, 100)])
    assert _overlap(a, b, 10) == (2, 2, 0)


def test_two_positions_at_once_within_ONE_strategy_are_COUNTED_not_collapsed():
    """🔴 This test REPLACES one that asserted `_occupancy` RAISES here, and the swap is the
    point rather than a detail.

    That refusal was right for as long as every bot ran one position slot, and it earned its keep:
    when the re-entries were finally replayed on 2026-09-02 it fired immediately instead of
    letting the tool understate A+'s exposure. But A+ arms its re-entry when the primary reaches
    BREAKEVEN — the primary is still open then — so two concurrent positions are now the bot's
    real behaviour, and refusing to measure the truth is not a fix.

    **The RISK the old test guarded is unchanged and is what this one pins: two positions must
    never collapse into one cell**, because that is the reading that silently halves a bot's own
    exposure. Overlapping bars 10-14 carry one long and one short at the same time.
    """
    occ = oa._occupancy(_holds([_T(1, 5, 15), _T(-1, 10, 20)]), 30)
    assert occ[7] == (1, 0)  # the long alone
    assert occ[12] == (1, 1)  # BOTH — the cell the old model could not represent
    assert occ[17] == (0, 1)  # the short alone
    assert sum(1 for lo, sh in occ if lo + sh > 1) == 5


def test_SAME_and_OPPOSITE_stop_partitioning_once_a_bot_holds_two_positions():
    """⚠ They summed to `both` for as long as one bar meant one direction, and they no longer do.

    A holds a long AND a short across bars 10-14; B is long throughout. Those five bars are
    same-side (A's long vs B's long) and opposite (A's short vs B's long) at the same instant, so
    each counts once in both — 5 + 5 against a total of 5. A reader who subtracts one from the
    other gets zero and concludes the bots never share a side, which is the exact wrong answer.
    """
    a = _holds([_T(1, 5, 15), _T(-1, 10, 20)])
    b = _holds([_T(1, 10, 15)])
    both, same, opp = _overlap(a, b, 30)
    assert (both, same, opp) == (5, 5, 5)
    assert same + opp > both


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


# ── two bots on two different bar frames ─────────────────────────────────────────
#
# Added 2026-09-01, when the tool learned to compare a 15-minute bot with a 5-minute one.
# Bar 400 of a 15-minute frame and bar 400 of a 5-minute frame are eleven hours apart, so
# the pre-change tool would have compared two different afternoons and said so in the same
# confident format as the truth. These pin the map that stops it.


def test_the_same_frame_maps_every_trade_onto_its_own_bar_index():
    # The identity case, stated outright rather than left implied by the cases above. The
    # A+/B-LEG numbers in CLAUDE.md were measured before the grid existed; if this ever
    # stops holding, those figures silently stop describing this tool.
    holds = oa._holds([_T(1, 10, 13), _T(-1, 40, 55)], _DF15, _GRID15)
    assert [(h.start, h.end) for h in holds] == [(10, 13), (40, 55)]


def test_a_coarse_trade_lands_on_the_fine_grid_at_the_right_TIME_not_the_same_index():
    # 15-minute bar 10 opens at 02:30. On a 5-minute grid starting the same instant that is
    # unit 30. Reading the index across unchanged would have put it at 00:50.
    fine = _frame(5, 600)
    grid = oa.Grid(fine)
    holds = oa._holds([_T(1, 10, 13)], _DF15, grid)
    assert holds[0].start == 30
    assert holds[0].end == 39


def test_a_one_bar_coarse_trade_occupies_its_WHOLE_width_on_the_fine_grid():
    # A 15-minute trade that opens and closes inside one bar is fifteen minutes of real
    # exposure. Scoring it as one 5-minute unit would report a third of it, and the error
    # is one-directional: every such trade would understate the overlap.
    fine = _frame(5, 600)
    grid = oa.Grid(fine)
    holds = oa._holds([_T(-1, 20, 20)], _DF15, grid)
    assert holds[0].end - holds[0].start == 3


def test_the_grid_reports_the_resolution_of_the_frame_it_was_built_on():
    # Everything downstream divides by this: the cluster window in units, and the span of a
    # coarse bar. A wrong value here mis-scales both at once and neither looks wrong alone.
    assert oa.Grid(_frame(5, 50)).minutes == 5
    assert oa.Grid(_frame(15, 50)).minutes == 15
    assert oa.Grid(_frame(60, 50)).minutes == 60


def test_a_bar_the_fine_FEED_IS_MISSING_falls_forward_and_is_COUNTED():
    # A real 5-minute feed can be missing a candle the 15-minute one has. Dying on it would
    # throw away an eight-year replay, so it falls to the next bar that exists — but a hole
    # in the feed and a clean feed must NOT produce identical output, or the reader cannot
    # tell which one they got. That is the same absence-as-value trap as the dead terminal.
    import pandas as pd

    fine = _frame(5, 600)
    holed = fine.drop(fine.index[30])
    grid = oa.Grid(holed)
    assert grid.misses == 0
    unit = grid.unit(pd.Timestamp("2024-01-01 02:30:00"))
    assert grid.misses == 1
    # 02:30 is gone, so it lands on 02:35 — which, one row lighter, is now index 30.
    assert holed.index[unit] == pd.Timestamp("2024-01-01 02:35:00")


def test_a_bar_the_fine_feed_DOES_hold_is_not_counted_as_a_miss():
    # The other half, and the one that makes the counter worth printing: a clean feed must
    # report zero. A counter that always fired would read exactly like a broken feed.
    import pandas as pd

    grid = oa.Grid(_frame(5, 600))
    grid.unit(pd.Timestamp("2024-01-01 02:30:00"))
    assert grid.misses == 0


def test_the_cluster_window_is_a_DURATION_so_it_means_the_same_on_either_frame():
    # It was 16 bars, which was four hours only while both bots shared a 15-minute frame.
    # On 5-minute bars the same number would have silently narrowed the window to 80
    # minutes — a stricter test reported under the old test's name.
    assert oa._CLUSTER_MINUTES == 240
    per_frame = {m: max(1, oa._CLUSTER_MINUTES // m) for m in (5, 15)}
    assert per_frame[15] == 16, "the recorded A+/B-LEG audit used 16 bars of 15m"
    assert per_frame[5] == 48, "the same four hours, counted in the finer frame's bars"


def test_a_coarse_bar_covers_a_whole_number_of_fine_ones():
    grid = oa.Grid(_frame(5, 600))
    assert grid.span(_DF15) == 3
    assert grid.span(_frame(5, 10)) == 1
    assert grid.span(_frame(60, 10)) == 12
