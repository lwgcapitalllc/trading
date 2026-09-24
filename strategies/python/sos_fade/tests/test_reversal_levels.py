"""The reversal exit's "Level rejected" trigger — price fails at the same major level twice.

Aaron, 2026-09-22: *"if we're hitting that level over and over and over ... that's time to get
out."* The levels are the weekly, daily and 4-hour highs and lows the liquidity engine already
hands this bot; only a level AHEAD of price counts, and consecutive touching bars are one visit.

WATCHED RED against HEAD: the config refused `exec_rev_trigger`, and `Execution` had no
`_rev_track_levels`.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution


class _Bar:
    def __init__(self, high, low, close, index=1, ts=1_700_000_000_000):
        self.index, self.time_ms, self.timestamp_ms = index, ts, ts
        self.open, self.high, self.low, self.close = close, high, low, close


class _M1:
    new_bull_sos = False
    new_bear_sos = False


def _long(**kw):
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, exec_rev_exit="Close",
                                 exec_rev_trigger="Level rejected", exec_rev_arm_r=1.0, **kw))
    ex._pos_dir, ex._entry_kind, ex._entry, ex._init_stop = 1, "primary", 100.0, 95.0
    ex._rev_best = 108.0          # 1.6R in front, so armed
    return ex


REJECT = dict(high=109.9, low=108.0, close=108.2)   # reaches 110 within a quarter-range, closes off
AWAY = dict(high=108.6, low=107.8, close=108.0)     # does not reach it


def _step(ex, bar, levels=(110.0,)):
    ex._rev_track_levels(_Bar(**bar), levels)
    return ex._rev_level_fired


def test_the_default_trigger_is_the_one_already_measured():
    # MUTATION PROOF: change the default and this goes red.
    assert SosFadeConfig().exec_rev_trigger == "Structure shift"


def test_two_separate_failed_visits_fire():
    ex = _long()
    assert _step(ex, REJECT) is False
    assert _step(ex, AWAY) is False
    assert _step(ex, REJECT) is True


def test_consecutive_touching_bars_are_ONE_visit():
    # MUTATION PROOF: count every touching bar and this goes red on the second bar.
    ex = _long()
    assert _step(ex, REJECT) is False
    assert _step(ex, REJECT) is False


def test_support_behind_price_is_not_a_level_it_cannot_get_through():
    # A long whose price is ABOVE the level is being held by it — the trade working. The
    # re-walk counted this and fired on 117 of 129 trades.
    # Two things guard it: the level is dropped as TAKEN, and the rejection test is directional.
    # MUTATION PROOF: disable BOTH and this goes red. Either alone is enough, which is the point.
    ex = _long()
    below = dict(high=108.4, low=107.0, close=108.3)     # low reaches 107.2, closes off above it
    for bar in (below, AWAY, below):
        fired = _step(ex, bar, levels=(107.2,))
    assert fired is False


def test_a_level_price_closes_through_is_dropped():
    # MUTATION PROOF: keep a taken level and the later rejection at the SAME price fires.
    ex = _long()
    _step(ex, REJECT)
    _step(ex, dict(high=111.0, low=109.0, close=110.9))  # closes well through 110
    assert ex._rev_levels == []


def test_a_short_reads_the_level_underneath():
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, exec_rev_exit="Close",
                                 exec_rev_trigger="Level rejected"))
    ex._pos_dir, ex._entry_kind, ex._entry, ex._init_stop = -1, "primary", 100.0, 105.0
    rej = dict(high=92.0, low=90.1, close=91.8)
    away = dict(high=92.2, low=91.4, close=92.0)
    assert [_step(ex, b, levels=(90.0,)) for b in (rej, away, rej)] == [False, False, True]


def test_the_exit_is_decided_through_the_shared_reversal_path():
    # It reuses the reversal exit's arming, pending order and one-bar delay rather than a
    # second exit path. MUTATION PROOF: read the structure event regardless of the trigger and
    # this goes red, because the structure event here is False.
    ex = _long()
    ex.step_reversal(_Bar(**REJECT), _M1(), (110.0,))
    ex.step_reversal(_Bar(**AWAY), _M1(), (110.0,))
    ex.step_reversal(_Bar(**REJECT), _M1(), (110.0,))
    assert ex._pending_rev == "Close"


def test_the_level_memory_survives_a_restart():
    assert "_rev_levels" in Execution._POSITION_FIELDS


def test_a_trigger_that_is_not_a_trigger_is_refused():
    with pytest.raises(ValueError, match="exec_rev_trigger"):
        SosFadeConfig(exec_rev_trigger="Level")


def test_zero_touches_is_refused():
    with pytest.raises(ValueError, match="exec_rev_level_touches"):
        SosFadeConfig(exec_rev_level_touches=0)
