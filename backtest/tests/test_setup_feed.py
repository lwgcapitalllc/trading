"""Tests for `backtest/setup_feed.py` — the point-in-time setup feed studies read.

The strategy here is a stand-in for the CONTRACT only (`run`, an execution with `step`,
`live_setups`, `drain_setups`). It is deliberately no more capable than the real one: it reports
a setup only through the same drain the live runner uses, and steps once per bar as
`SosFadeStrategy.run` does. The real strategy is exercised end to end by the reconciliation in
`backtest/notes/study-reconciliation.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.setup_feed import episodes, leg_side, replay_setups  # noqa: E402
from backtest.setups import WATCHING, SetupSnapshot  # noqa: E402


def _frame(n=6):
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=idx)


class _Ex:
    def __init__(self, script):
        self._script, self._bar = script, -1

    def step(self, *_):
        self._bar += 1

    def live_setups(self):
        return [
            SetupSnapshot(key=k, strategy="T", symbol="X", side=1, state=WATCHING, touched=t)
            for k, t in self._script.get(self._bar, ())
        ]

    def drain_setups(self):
        return self.live_setups()


class _Strat:
    def __init__(self, script, steps_per_bar=1):
        self.execution = _Ex(script)
        self._per = steps_per_bar

    def run(self, df, warmup=0):
        for _ in range(len(df)):
            for _ in range(self._per):
                self.execution.step()


def test_each_row_is_stamped_with_the_bar_that_REPORTED_it_and_known_at_its_close():
    """RED against stamping with the bar's close as `bar_ms`, or dropping the bar length."""
    df = _frame()
    rows = replay_setups(_Strat({2: [("A", True)]}), df)
    assert len(rows) == 1
    r = rows[0]
    assert r.index == 2
    assert r.bar_ms == int(df.index[2].value // 1_000_000)
    assert r.known_ms == r.bar_ms + 15 * 60_000


def test_warm_up_rows_are_drained_but_NOT_returned():
    """RED against filtering warm-up after the loop instead of draining inside it."""
    rows = replay_setups(_Strat({0: [("A", True)], 3: [("B", True)]}), _frame(), warmup=2)
    assert [r.snap.key for r in rows] == ["B"]


def test_a_strategy_without_the_contract_is_REFUSED_rather_than_returning_no_setups():
    """Rule 1 — an empty feed would read as a strategy with no setups. RED against `return []`."""

    class Mute(_Strat):
        pass

    s = Mute({})
    s.execution.reports_setups = False
    with pytest.raises(TypeError, match="cannot answer"):
        replay_setups(s, _frame())


def test_a_run_that_does_not_step_once_per_bar_is_REFUSED():
    """The bar stamp comes from counting steps. RED against dropping the count check."""
    with pytest.raises(RuntimeError, match="stepped its execution 12 times over 6 bars"):
        replay_setups(_Strat({}, steps_per_bar=2), _frame())


def test_the_execution_is_left_as_it_was_found():
    """The listener is an INSTANCE attribute; it must come off so the object replays normally."""
    s = _Strat({})
    replay_setups(s, _frame())
    assert "step" not in vars(s.execution)


def test_an_episode_ends_when_the_setup_stops_qualifying_and_a_return_is_a_NEW_episode():
    """RED against grouping by key alone — the lab's 1m entry reopens a window with fresh levels."""
    script = {1: [("A", True)], 2: [("A", True)], 3: [("A", False)], 4: [("A", True)]}
    rows = replay_setups(_Strat(script), _frame())
    eps = episodes(rows, lambda s: bool(s.touched))
    assert [(e.key, [r.index for r in e.rows]) for e in eps] == [("A", [1, 2]), ("A", [4])]


def test_leg_side_reads_the_direction_off_the_anchors():
    assert leg_side((105.0, 94.0)) == 1
    assert leg_side((94.0, 105.0)) == -1
    assert leg_side(None) == 0
