"""A stacked leg may trade on TWO bar frames.

`mpc_sos_fade`'s re-entry fills on a faster clock than its primary, and until 2026-09-02 a stack
refused that config outright — a leg was one frame, so the only honest thing to do was refuse
rather than return a primary-only book beside controls that had the re-entries in them.

🔴 **The refusal is KEPT and only its CONDITION moved**: from *this switch is on* to *this switch
is on and nobody gave me the second frame*. That is the half worth guarding, because the failure
it prevents is silent — a leg quietly missing a whole class of its own trades looks exactly like a
leg that found fewer setups.

⚠ The merge itself is NOT tested here. It lives in `DualClock` on the strategy, is driven
bar-at-a-time by the live runner too, and has its own tests; these cover the SEAM — which class
gets built, what order the two streams arrive in, whose bar duration wins, and the tail.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.legs import DualFeedLeg, FeedBar, build_leg  # noqa: E402
from backtest.replay import EngineConfig  # noqa: E402


@dataclass
class _Bar:
    index: int
    timestamp_ms: int
    open: float = 1.0
    high: float = 1.0
    low: float = 1.0
    close: float = 1.0


class _Cfg:
    """A config that WANTS a second feed."""

    exec_secondary = True
    exec_recovery = False


class _Execution:
    def __init__(self) -> None:
        self.bar_ms = 0
        self.trades: list = []
        self.is_flat = True


class _Clock:
    """Records what it was handed, in order. Stands in for `DualClock`."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, int]] = []
        self.drained = 0

    def push_primary(self, bar) -> None:
        self.seen.append(("primary", bar.timestamp_ms))

    def step_fast(self, bar) -> None:
        self.seen.append(("fast", bar.timestamp_ms))

    def drain_primary(self) -> list:
        self.drained += 1
        return []


class _Strategy:
    def __init__(self, *_a, **_k) -> None:
        self.execution = _Execution()
        self.clock = _Clock()

    def stack_config(self):
        return EngineConfig()

    def make_dual_clock(self, stack, *, tf_primary_ms: int, engine_config=None):
        self.tf_primary_ms = tf_primary_ms
        return self.clock


def _leg(df_primary, df_fast) -> DualFeedLeg:
    """Build without running `EngineStack`, which needs a real engine config."""
    leg = DualFeedLeg.__new__(DualFeedLeg)
    leg.name = "leg"
    leg.strategy = _Strategy()
    leg._df_primary = df_primary
    leg._df_fast = df_fast
    leg._stack = None
    leg._clock = leg.strategy.clock
    return leg


def _frame(step_ms: int, n: int, start: int = 0):
    import pandas as pd

    idx = pd.to_datetime([start + i * step_ms for i in range(n)], unit="ms", utc=True)
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


# ── the refusal, which is the half that must not weaken ──────────────────────


def test_a_second_feed_config_with_NO_fast_frame_is_still_refused():
    """The original safety property. Watched RED by inverting the added half of the condition
    to `df_fast is not None`, which stops it refusing in exactly the case it exists for."""
    with pytest.raises(ValueError, match="no second bar frame"):
        build_leg(
            "leg",
            _Strategy,
            _Cfg(),
            _frame(900_000, 3),
            account=None,
            initial_capital=1000.0,
        )


def test_the_refusal_NAMES_the_way_out():
    """A refusal that does not say what to do gets worked around by whatever is nearest — which
    here means switching the feature off to make the stack run. Watched RED by shortening the
    message."""
    with pytest.raises(ValueError) as e:
        build_leg(
            "leg",
            _Strategy,
            _Cfg(),
            _frame(900_000, 3),
            account=None,
            initial_capital=1000.0,
        )
    assert "df_fast" in str(e.value)


# ── the seam ─────────────────────────────────────────────────────────────────


def test_the_two_frames_arrive_PRIMARY_FIRST_at_an_equal_timestamp():
    """🔴 The ordering contract, and the one thing here that can be wrong in silence.

    A fast bar is stepped against the last CLOSED primary context, so a primary sharing its open
    time must be QUEUED before it. Reversed, the fast bar reads a context one bar stale and the
    book is subtly wrong with nothing to show for it.

    Watched RED by swapping the merge's tie-break key from (ts, 0)/(ts, 1) to (ts, 1)/(ts, 0).
    """
    leg = _leg(_frame(900_000, 2), _frame(300_000, 6))
    got = [(fb.fast, fb.timestamp_ms) for fb in leg.bars()]
    assert got[0] == (False, 0), "the primary must come first at t=0"
    assert got[1] == (True, 0), "the fast bar sharing that open time comes second"
    # and at the next primary open, the same again
    at_900k = [f for (f, ts) in got if ts == 900_000]
    assert at_900k == [False, True]


def test_every_bar_of_BOTH_frames_reaches_the_clock_exactly_once():
    """A merge that drops or repeats a bar produces a book nobody can trace. Watched RED by
    slicing either stream in `bars()`."""
    leg = _leg(_frame(900_000, 4), _frame(300_000, 12))
    for fb in leg.bars():
        leg.step(fb)
    kinds = [k for (k, _) in leg.strategy.clock.seen]
    assert kinds.count("primary") == 4
    assert kinds.count("fast") == 12


def test_a_bar_is_ROUTED_by_its_frame_and_never_by_its_timestamp():
    """The reason `FeedBar` carries a flag at all: a 15m and a 5m bar share an open time four
    times an hour, so the timestamp cannot answer which frame a bar came from.

    Watched RED by routing on `fb.timestamp_ms % 900_000 == 0`, which sends every fast bar
    landing on a 15m boundary down the primary path.
    """
    leg = _leg(_frame(900_000, 2), _frame(300_000, 6))
    for fb in leg.bars():
        leg.step(fb)
    at_zero = [k for (k, ts) in leg.strategy.clock.seen if ts == 0]
    assert at_zero == ["primary", "fast"], "both frames have a bar at t=0 and both must route"


def test_the_leg_reports_the_PRIMARY_bar_duration_not_the_fast_one():
    """⚠ The strategy's swap clock and time stop are counted in PRIMARY bars. Taking the merged
    stream's minimum gap would put both on the fast frame and silently shorten every hold — a
    change to what the strategy DOES, arriving through a field that looks like reporting.

    🔴 It drives the REAL constructor. An earlier version called `_frame_ms` itself and then
    asserted the value it had just assigned, which is a test of arithmetic that cannot see the
    constructor at all — it passed against every mutation of the line it claimed to cover.

    Watched RED by handing `_frame_ms(df_fast)` to the execution instead.
    """
    df_primary, df_fast = _frame(900_000, 4), _frame(300_000, 12)
    leg = DualFeedLeg("leg", _Strategy(), df_primary, df_fast)
    assert leg.strategy.execution.bar_ms == 900_000, "must be the 15m frame, not the 5m one"
    assert leg.strategy.tf_primary_ms == 900_000, "and the merge is built on the same figure"


def test_finish_drains_the_primary_bars_the_fast_clock_never_reached():
    """The window's tail. The last primary bars close after the final fast bar, so nothing
    flushes them — without this the leg silently drops its last bars, and a book that stops a few
    bars early reads exactly like a book that found no more setups.

    Watched RED by deleting `finish` from the class.
    """
    leg = _leg(_frame(900_000, 4), _frame(300_000, 6))
    for fb in leg.bars():
        leg.step(fb)
    assert leg.strategy.clock.drained == 0
    leg.finish()
    assert leg.strategy.clock.drained == 1


def test_a_FeedBar_reports_its_underlying_bar_time():
    """The clock merges legs on `timestamp_ms` alone, so a wrapper that did not forward it would
    put this leg's bars in the wrong tick of a multi-leg stack. Watched RED by returning 0."""
    b = _Bar(index=3, timestamp_ms=987_000)
    assert FeedBar(b, fast=True).timestamp_ms == 987_000
    assert FeedBar(b, fast=False).timestamp_ms == 987_000
