"""Tests for `chart_spec.reversal_anchors` — WHERE the Candlestick Reversals layer may paint.

This is the one rule of that layer that has already been wrong once on a real chart, and it is not
derivable from anything else on the spec: **trades, win or lose, and 3/3 misses. Nothing else.**
Which candle inside an anchor's window gets the mark is a different question and lives in
`test_candle_overlays.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.chart_spec import reversal_anchors  # noqa: E402


def _trade(t: int, pnl: float, *, exit_t: int = 0, direction: str = "long") -> dict:
    return {"entryTime": t, "exitTime": exit_t or t + 1000, "pnl": pnl, "dir": direction}


def _miss(t: int, met: int, of: int, direction: str = "long") -> dict:
    return {"time": t, "met": met, "of": of, "dir": direction}


def test_a_trade_is_an_anchor_whether_it_won_or_lost():
    out = reversal_anchors([_trade(100, 5.0), _trade(200, -1.0)], [])
    assert [a[0] for a in out] == [100, 200]


def test_a_winner_carries_its_exit_and_a_loser_does_NOT():
    """The hold end is what switches the search from "3 bars past the entry" to "the whole hold".
    A loser never reversed in his favour, so searching its hold would mark its stop-out."""
    won, lost = reversal_anchors([_trade(100, 5.0, exit_t=900), _trade(200, -1.0, exit_t=950)], [])
    assert won[2] == 900
    assert lost[2] is None


def test_a_three_of_three_miss_is_an_anchor():
    out = reversal_anchors([], [_miss(300, 3, 3)])
    assert [a[0] for a in out] == [300]
    assert out[0][2] is None, "a miss has no hold to search"


def test_a_two_of_three_miss_is_NOT_an_anchor():
    """It was never a setup, so there is no "which candle turned it" to ask of it."""
    assert reversal_anchors([], [_miss(300, 2, 3)]) == []


def test_a_miss_stating_no_score_is_NOT_an_anchor():
    """`of == 0` is a record that never counted confluences. Without the guard `0 >= 0` admits it,
    which is the most permissive reading of the least informative record."""
    assert reversal_anchors([], [_miss(300, 0, 0)]) == []


def test_the_direction_rides_along():
    """The reversal is measured against the way the setup was POINTING — the adverse extreme is the
    lowest low on a long and the highest high on a short, so an anchor with no side is unusable."""
    out = reversal_anchors([_trade(100, 5.0, direction="short")], [_miss(300, 3, 3, "short")])
    assert [a[1] for a in out] == ["short", "short"]


def test_BLOCKED_setups_are_not_even_reachable_from_here():
    """The layer anchored on blocks until 2026-08-08 and it is what made it look random: 324 of them
    on the reference run against 159 trades, painting navy candles under a Blocked layer that
    defaults OFF, so the reader saw marks where there was no visible setup at all.

    ⚠ This asserts the SIGNATURE, deliberately. There is no value to pass that would produce a
    block-anchored mark, so a behavioural test cannot exist — the only way blocks come back is
    somebody adding the parameter, and this fails in front of them with the reason."""
    import inspect
    assert list(inspect.signature(reversal_anchors).parameters) == ["trades", "misses"]


def test_nothing_at_all_produces_no_anchors():
    """An NT8/MT5 run reports neither, and the layer's toggle correctly never appears."""
    assert reversal_anchors([], []) == []
