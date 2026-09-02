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

import pandas as pd
import pytest

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "overlap_audit.py"
_spec = importlib.util.spec_from_file_location("overlap_audit", _TOOL)
oa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oa)


class _T:
    """The Trade fields the tool reads.

    🔴 **THE CASES STILL SPEAK IN BAR NUMBERS AND THE TOOL NO LONGER DOES (2026-09-03).** A bar
    number is only meaningful with the frame it counts, and a bot running a re-entry produces
    trades numbered in TWO frames — so `_holds` now places every trade by its recorded
    millisecond. These doubles therefore STAMP the milliseconds off the frame the case is written
    against, which keeps every hand-traced range readable while pinning what actually runs.

    ⚠ **The double must not be more capable than the real thing.** A real trade cannot carry a bar
    number that disagrees with its timestamp; this one could, so it derives one from the other
    rather than taking both.
    """

    def __init__(self, direction, entry, exit_, r=0.0, df=None, kind="primary"):
        df = _DF15 if df is None else df
        last = len(df.index) - 1
        self.dir = direction
        self.entry_index = entry
        self.exit_index = exit_
        self.kind = kind
        self.entry_ms = int(df.index[min(entry, last)].value // 1_000_000)
        self.exit_ms = int(df.index[min(exit_, last)].value // 1_000_000)
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


# ⚠ These three had their PREMISE moved on 2026-09-02 and moved back on 2026-09-03. `_occupancy`
# briefly returned `(longs, shorts)` per bar, on a reading of A+ that turned out to be an artefact
# of misplaced holds — see `test_two_positions_at_once_within_ONE_strategy_are_REFUSED`. One
# direction per bar again. Half-open ranges, the same-bar round trip and direction being carried
# across the hold are exactly what they always pinned.


def test_a_hold_is_half_open_so_a_trade_occupies_its_entry_bar_not_its_exit_bar():
    # Entering on bar 10 and exiting on bar 13 = exposed on 10, 11, 12.
    holds = _holds([_T(1, 10, 13)])
    assert sum(1 for c in oa._occupancy(holds, 20) if c) == 3


def test_a_same_bar_entry_and_exit_still_occupies_one_bar():
    # A trade that opens and closes inside one bar is real exposure, and a naive
    # half-open range would score it zero and quietly drop it from every count.
    holds = _holds([_T(-1, 5, 5)])
    occ = oa._occupancy(holds, 10)
    assert sum(1 for c in occ if c) == 1
    assert occ[5] == -1


def test_direction_is_carried_onto_every_bar_of_the_hold():
    occ = oa._occupancy(_holds([_T(-1, 2, 5)]), 8)
    assert occ == [0, 0, -1, -1, -1, 0, 0, 0]


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


def test_two_positions_at_once_within_ONE_strategy_are_REFUSED():
    """🔴 THIS ASSERTION HAS NOW BEEN DELETED ONCE AND PUT BACK, AND THE ROUND TRIP IS THE TEST.

    It refused, correctly, for as long as every bot ran one position slot. On 2026-09-02 A+'s
    re-entries were replayed for the first time and it fired — and it was read as a DISCOVERY (*the
    bot holds two at once*), so this case was rewritten to assert counting instead, and a
    doubled-risk warning went into the root `CLAUDE.md`.

    **It was not a discovery. `_holds` was placing every re-entry at the wrong time**, and several
    were landing on top of each other at the end of the frame. Placed by timestamp the same replay
    reports zero doubled bars, and the strategy fills a re-entry only while flat.

    **A guard firing is a question, not an answer. Widening it answers nothing.**

    MUTATION: drop the raise and keep the last writer, and this goes red — which is the version
    that silently halves a bot's own recorded exposure.
    """
    holds = _holds([_T(1, 5, 15), _T(-1, 10, 20)])
    with pytest.raises(SystemExit) as exc:
        oa._occupancy(holds, 30)
    assert "SUSPECT THE PLACEMENT" in str(exc.value), (
        "the message must send the next reader at _holds first — the last one to see this "
        "raise concluded the strategy had changed and rewrote the guard"
    )


def test_SAME_and_OPPOSITE_PARTITION_the_shared_bars():
    """One bar carries one direction each side, so the two halves add up to the total.

    ⚠ They briefly did not, while `_occupancy` counted positions per side. A reader who cannot
    add the two columns to the line above them reads the report as broken.
    """
    a = _holds([_T(1, 10, 20), _T(-1, 30, 40)])
    b = _holds([_T(1, 15, 35)])
    both, same, opp = _overlap(a, b, 50)
    assert (both, same, opp) == (10, 5, 5)
    assert same + opp == both


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


# ── a bot whose trades are numbered in TWO frames ────────────────────────────────
#
# Added 2026-09-03. A re-entry is stepped on the fill clock, so its bar number counts 5-minute
# bars while its primaries count 15-minute ones — in ONE trade list, with nothing in a trade
# saying which. Reading either out of the primary frame's index put re-entries weeks or months
# from where they happened. These pin the placement that replaced it.


def _fast_trade(direction, entry_unit, exit_unit, fine):
    """A re-entry: bar numbers into the FINE frame, timestamps to match."""
    t = _T(direction, entry_unit, exit_unit, df=fine, kind="secondary")
    return t


def test_a_RE_ENTRY_is_placed_by_its_own_TIME_not_by_its_bar_number():
    """🔴 THE BUG THIS FILE MISSED FOR A DAY, and it produced published figures.

    5-minute bar 30 is 02:30 — the same instant as 15-minute bar 10. Looking bar 30 up in the
    15-minute index instead lands on 07:30, five hours away, and over a real replay the error
    ran to months.

    MUTATION: place from `df.index[t.entry_index]` again and this goes red by 20 grid units.
    """
    fine = _frame(5, 600)
    grid = oa.Grid(fine)
    holds = oa._holds([_fast_trade(1, 30, 33, fine)], _DF15, grid, fast_df=fine)
    assert (holds[0].start, holds[0].end) == (30, 33)


def test_a_PRIMARY_and_a_RE_ENTRY_in_ONE_list_are_both_placed_correctly():
    """The case that actually occurs: one book, two numbering systems, no field marking which.

    MUTATION: use one frame's index for every trade and one of the two moves.
    """
    fine = _frame(5, 600)
    grid = oa.Grid(fine)
    trades = [_T(1, 10, 13), _fast_trade(-1, 60, 63, fine)]
    holds = oa._holds(trades, _DF15, grid, fast_df=fine)
    assert (holds[0].start, holds[0].end) == (30, 39), "the 15m primary, at its own time"
    assert (holds[1].start, holds[1].end) == (60, 63), "the 5m re-entry, at its own time"


def test_a_RE_ENTRY_occupies_ONE_FILL_CLOCK_BAR_not_one_of_the_primarys():
    """A re-entry that opens and closes inside one 5-minute bar is five minutes of exposure.

    Giving it the primary's width would report three times its real hold, and the error only ever
    runs one way — it can only overstate the finer leg.

    MUTATION: use the primary span for every trade and this reads 3.
    """
    fine = _frame(5, 600)
    grid = oa.Grid(fine)
    holds = oa._holds([_fast_trade(1, 40, 40, fine)], _DF15, grid, fast_df=fine)
    assert holds[0].end - holds[0].start == 1


def test_MONTHLY_R_is_keyed_on_the_trades_OWN_month():
    """The same defect one function along, and it fed both published correlation figures.

    A re-entry entered in January must be filed under January whichever frame numbered it.

    MUTATION: key it off `df.index[t.entry_index]` again and the fast trade lands in a
    different month.
    """
    # 5-minute bar 3,000 is 10 days in — still January. The SAME number read off a 15-minute
    # index is 31 days in, which is February, so the mutation moves the R into another month.
    jan = _frame(15, 4000, start="2024-01-02 00:00:00")
    fine = _frame(5, 4000, start="2024-01-02 00:00:00")
    slow = _T(1, 10, 13, r=2.0, df=jan)
    fast = _T(-1, 3000, 3003, r=1.0, df=fine, kind="secondary")
    assert jan.index[3000].month == 2, "the frames must disagree, or this pins nothing"
    assert oa._monthly_r([slow, fast]) == {"2024-01": 3.0}


def test_a_FILL_CLOCK_timestamp_lands_on_the_grid_bar_CONTAINING_it():
    """A re-entry fills at 10:05 on a 15-minute grid. It was in the market during the 10:00 bar.

    🔴 `unit`'s fall-FORWARD is right for its own case — a coarse frame's bar open that the fine
    feed is missing — and wrong here: it would mark the trade as in the market from 10:15, ten
    minutes after it opened. 62 re-entry timestamps hit this in one 6.6-year audit, so it is the
    normal case rather than an edge.

    MUTATION: search `left` (fall forward) and this goes red at unit 41.
    """
    grid = oa.Grid(_frame(15, 200, start="2024-01-01 00:00:00"))
    # 10:05 — inside 15-minute bar 40, which opens at 10:00.
    ms = int(pd.Timestamp("2024-01-01 10:05:00").value // 1_000_000)
    assert grid.unit_ms(ms) == 40


def test_a_timestamp_INSIDE_a_bar_is_counted_APART_from_a_feed_hole():
    """⚠ Two different facts. A hole is worth alarming about; a faster leg's fill inside a
    coarser bar is what a two-frame audit does all day. One counter for both printed a feed
    warning on a healthy run, which is a warning nobody can act on.

    MUTATION: increment `misses` here instead and this goes red.
    """
    grid = oa.Grid(_frame(15, 200, start="2024-01-01 00:00:00"))
    grid.unit_ms(int(pd.Timestamp("2024-01-01 10:05:00").value // 1_000_000))
    assert (grid.inside, grid.misses) == (1, 0)


def test_a_bar_OPEN_is_an_exact_hit_and_counts_as_neither():
    """The common case, and it must stay free of both counters — otherwise every single-frame
    audit reports thousands of them and the two lines above become noise."""
    grid = oa.Grid(_frame(15, 200, start="2024-01-01 00:00:00"))
    assert grid.unit_ms(int(pd.Timestamp("2024-01-01 10:00:00").value // 1_000_000)) == 40
    assert (grid.inside, grid.misses) == (0, 0)
