"""A bar that raises while being processed must not vanish.

🔴 **The defect this file exists for, found 2026-08-05 by auditing the live ledger's one
`loop_error` record.** `BarFeed.new_bars` advances `last_bar_time` at the moment it HANDS the
rows out, not when the caller has finished with them. So an exception inside `_on_bar` left the
bookmark past a bar the engines never saw — and every mechanism that could have noticed was
reading that same bookmark:

  * `gap_bars()` compares the newest broker bar against `last_bar_time`, so it reported **0**;
  * the next `new_bars()` returned nothing, because that bar was no longer "fresh";
  * the outer loop handler only alerts after **ten consecutive** loop errors, and one lost bar
    is one error.

The engines are a streaming state machine. A missing bar is not a missing datapoint — from that
point on, every structure break, every fib leg and every gap is computed over a market history
that never happened, silently, for the rest of the session.

**Re-delivering the bar is deliberately NOT the fix, and that is the part worth understanding.**
`_on_bar` steps the strategy and then mirrors its intent onto the broker; a failure part-way
through leaves the engines already advanced, so replaying the bar would step them twice. That is
the same desync arriving from the other side. The only known-good recovery is the one the gap
branch already performs — rebuild the strategy and re-warm from history — so a bar error routes
into it.

The tests below are mostly about the FIRST half of that: proving the drop is real against the
actual `BarFeed`, because a fix for a bug nobody has demonstrated is a fix for a guess.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

# MetaTrader5 is Windows-only and is imported lazily inside `_tf_const`. A stub keeps this file
# runnable on the Mac, which is where these tests actually get run.
sys.modules.setdefault("MetaTrader5", types.SimpleNamespace(
    TIMEFRAME_M1=1, TIMEFRAME_M5=5, TIMEFRAME_M15=15, TIMEFRAME_M30=30,
    TIMEFRAME_H1=60, TIMEFRAME_H4=240, TIMEFRAME_D1=1440))

_REPO = Path(__file__).resolve().parent.parent.parent
for p in (str(_REPO), str(_REPO / "algos" / "live")):
    if p not in sys.path:
        sys.path.insert(0, p)

from feed import BarFeed                                              # noqa: E402


_IDX = pd.date_range("2026-08-01", periods=8, freq="15min", tz="UTC")


class _FakeMT5:
    """Serves a fixed frame the way the live MT5 wrapper does — newest bars last."""

    symbol = "XAUUSD.s"

    def __init__(self, n_bars: int = 8):
        self._raw = pd.DataFrame({
            "time": _IDX[:n_bars], "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
        })

    def get_candles(self, tf, count, symbol=None):
        return self._raw.tail(count).copy()


def _feed(n_bars: int = 8) -> BarFeed:
    return BarFeed(_FakeMT5(n_bars), "M15", "XAUUSD.s")


# ── the drop itself ──────────────────────────────────────────────────────────────

def test_new_bars_advances_its_bookmark_before_the_caller_has_processed_anything():
    """The mechanism, stated plainly. Everything else in this file follows from it."""
    feed = _feed()
    feed.last_bar_time = _IDX[3]

    fresh = feed.new_bars()
    assert len(fresh) >= 1
    # The bookmark is already past what was handed out — before `_on_bar` has run once.
    assert feed.last_bar_time == fresh.index[-1]


def test_a_bar_the_caller_never_processed_is_NOT_reported_as_a_gap():
    """`gap_bars` reads the same bookmark, so it cannot see this hole. This is why the runner
    needs its own flag rather than another question to the feed."""
    feed = _feed()
    feed.last_bar_time = _IDX[3]

    feed.new_bars()          # handed out; imagine the caller raised on the first row
    assert feed.gap_bars() == 0


def test_the_dropped_bar_is_never_offered_again():
    """The other half of the silence: no error, no gap, and no second chance."""
    feed = _feed()
    feed.last_bar_time = _IDX[3]

    feed.new_bars()
    assert feed.new_bars().empty


def test_a_genuine_lag_IS_still_reported_as_a_gap():
    """The guard against over-reading the above: `gap_bars` works fine for the case it was
    built for — bars that closed while nobody was asking. Only the dropped-bar case is blind."""
    feed = _feed()
    feed.last_bar_time = _IDX[0]
    assert feed.gap_bars() >= 5


# ── what the runner must do about it ─────────────────────────────────────────────

def _loop_source() -> str:
    import inspect
    import runner
    return inspect.getsource(runner.LiveRunner._loop)


def test_the_bar_loop_catches_per_bar_rather_than_per_poll():
    """A source check, deliberately.

    The behavioural alternative is to drive a whole `LiveRunner._loop` with a raising
    `_on_bar`, and that needs a live MT5 handle, a bridge, a ledger and a strategy — a test
    whose own scaffolding is larger than the thing it checks, and which would keep passing if
    the `try` moved back outside the `for`. What must hold is structural: the handler is INSIDE
    the row loop, so one bad bar cannot be mistaken for one bad poll.
    """
    src = _loop_source()
    body = src[src.index("for _, row in self.feed.new_bars()"):]
    assert "try:" in body[:200], "the per-bar try must sit immediately inside the row loop"


def test_a_bar_error_routes_into_the_existing_rewarm():
    """It must reuse the gap branch, not invent a second recovery. Two recovery paths for one
    condition is how they drift, and this one has to rebuild the strategy AND the bridge's
    reference to it AND re-warm AND re-arm the bridge, in that order."""
    src = _loop_source()
    assert "gap > 4 or stream_broken" in src
    assert "stream_broken = True" in src


def test_the_loop_BREAKS_rather_than_continuing_to_the_next_row():
    """Continuing would feed the rows after the failure into engines that are already carrying
    a hole — the bug, applied to every remaining bar in the frame."""
    src = _loop_source()
    body = src[src.index("bar_errors += 1"):]
    assert "break" in body


def test_a_bar_error_is_recorded_in_the_ledger_under_its_own_name():
    """`loop_error` already exists and means something different — a poll that failed. A dropped
    BAR is a data-integrity event and has to be countable on its own, or an audit like the one
    that found this cannot tell them apart."""
    assert '"bar_error"' in _loop_source() or "'bar_error'" in _loop_source()


def test_the_rewarm_event_says_whether_it_followed_a_bar_error():
    """A re-warm after a 5-bar lag and a re-warm after a dropped bar look identical in the
    ledger otherwise — and only one of them is a defect on our side."""
    assert "after_bar_error" in _loop_source()


def test_it_alerts_ONCE_per_outage_not_every_poll():
    """The repo's standing rule about alert channels: one that repeats every poll is one people
    mute, and this channel also carries the trade alerts."""
    src = _loop_source()
    assert "if bar_errors == 1:" in src


def test_a_clean_bar_resets_the_counter():
    """Without this, `bar_errors` is a lifetime total: ten unrelated bad bars across six months
    would stop a healthy bot, and the second outage would never alert."""
    src = _loop_source()
    body = src[src.index("self._on_bar(row)"):]
    assert "bar_errors = 0" in body[:120]


def test_it_gives_up_after_ten_bars_it_cannot_process():
    """A re-warm that is not fixing it will not start fixing it on the eleventh try, and a bot
    silently processing no bars is worse than a stopped one — the watchdog can see stopped."""
    src = _loop_source()
    assert "bar_errors >= 10" in src


@pytest.mark.parametrize("name", ["probe_link", "_recover_link"])
def test_the_link_probe_is_untouched_by_this_change(name):
    """The MT5-link recovery is a different failure with its own tested path (2026-08-04). This
    change must not have absorbed or reordered it — a bar error is a defect on our side, a dead
    link is the terminal's, and conflating them would send the wrong recovery to both."""
    import runner
    assert hasattr(runner.LiveRunner, name)
    assert "if not link_up:" in _loop_source()
