"""The one-trade-per-leg latch must survive a restart.

🔴 **2026-08-26, on the live demo.** The latch stored the shift bar's NUMBER. A live bot
renumbers every bar each time it re-warms its history on restart, so a restored latch holding
5059 was compared against the SAME leg now numbered 4953, saw no match, and let the trade
through. The bot re-entered a setup it had been scratched out of **three seconds earlier** —
identical stop 4686.32356, identical targets 4640.22772 / 4605.29 — at 0.53 lots.

⚠ **This repo had already written the lesson down, about a different tool.** `shadow_diff` joins
on bar TIMESTAMP and its docstring says why: *"the live index counts on from wherever warm-up
stopped and survives restarts."* The live path was still comparing numbers. **A lesson recorded
against one consumer is not a lesson applied to the others.**

⚠ **The fix is a NO-OP in any single continuous run** — one backtest, one Pine chart, one
uninterrupted session — because within a run a bar number maps to exactly one time. The two can
only disagree across a restart, which exists nowhere but live. Parity was RUN rather than
reasoned: `compare_strategy.py` green at warmups 100 / 200 / 500 / 1000 / 2000 on
`VANTAGE_XAUUSD, 15_6fb2a.csv`, the same five the pre-change code passes.

MUTATION that reddens the restart tests: make `_same_leg` compare numbers only
(`return traded_bar is not None and current_bar == traded_bar`).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# The package, not the bare modules - `execution` imports its siblings relatively, so a
# flat import of it fails at collection. Same convention as every sibling test here.
sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from sos_fade import Execution, SosFadeConfig  # noqa: E402

BAR_MS = 15 * 60 * 1000
FIRST = 1_787_600_000_000


def _ex() -> Execution:
    return Execution(SosFadeConfig(), initial_capital=10_000.0)


def _feed(ex: Execution, first_index: int, n: int, first_ms: int) -> None:
    """Stream `n` bars in, the way a warm-up does — numbering starts wherever it starts."""
    for i in range(n):
        ex._remember_bar(SimpleNamespace(index=first_index + i, time_ms=first_ms + i * BAR_MS))


def test_the_same_leg_is_recognised_after_a_restart_renumbers_the_bars():
    """🔴 THE INCIDENT. The leg is bar 5059 before the restart and 4953 after; both are the same
    moment in time, so the latch must still hold."""
    ex = _ex()
    _feed(ex, 5000, 100, FIRST)
    leg_ms = ex._bar_ms[5059]

    # ...the bot restarts and re-warms. Same bars, numbered 106 lower.
    after = _ex()
    _feed(after, 4894, 100, FIRST)
    after._traded_sos_s, after._traded_sos_s_ms = 5059, leg_ms  # restored from the record

    assert after._bar_ms[4953] == leg_ms, "the fixture does not reproduce the renumbering"
    assert after._same_leg(5059, leg_ms, 4953) is True, (
        "the bot would re-enter a leg it has already traded - this is the live incident"
    )


def test_a_genuinely_different_leg_is_still_allowed():
    """The latch must not become a blanket refusal. A different bar is a different setup."""
    ex = _ex()
    _feed(ex, 4894, 100, FIRST)
    traded_ms = ex._bar_ms[4953]
    assert ex._same_leg(4953, traded_ms, 4954) is False
    assert ex._same_leg(4953, traded_ms, 4970) is False


def test_within_one_run_the_answer_is_unchanged():
    """The property that keeps the parity gate green: in a single continuous run a number maps to
    exactly one time, so old and new agree on every bar."""
    ex = _ex()
    _feed(ex, 0, 200, FIRST)
    for bar in (0, 17, 199):
        ms = ex._bar_ms[bar]
        assert ex._same_leg(bar, ms, bar) is True
        assert ex._same_leg(bar, ms, bar + 1) is False


def test_a_leg_with_no_recorded_time_falls_back_to_the_number():
    """A record written before this field existed, or a shift bar that fell off the tail. The
    fallback is the OLD behaviour and is wrong across a restart - it is kept because refusing to
    answer would disable the latch entirely, which is the same failure with fewer clues."""
    ex = _ex()
    _feed(ex, 0, 50, FIRST)
    assert ex._same_leg(20, None, 20) is True
    assert ex._same_leg(20, None, 21) is False


def test_an_unknown_current_bar_falls_back_rather_than_matching_everything():
    """If the current leg's time is not in the map, comparing `None == None` would make every
    leg look already-traded and the bot would stop entering entirely."""
    ex = _ex()
    _feed(ex, 0, 50, FIRST)
    traded_ms = ex._bar_ms[10]
    assert ex._same_leg(10, traded_ms, 9_999) is False, "an unknown bar matched a traded leg"
    assert ex._same_leg(9_999, traded_ms, 9_999) is True, "the number fallback stopped working"


def test_no_leg_at_all_is_never_a_match():
    ex = _ex()
    assert ex._same_leg(None, None, 5) is False
    assert ex._same_leg(5, None, None) is False


def test_both_leg_times_are_PERSISTED():
    """Without these in the record, a restart restores a bar number from the previous numbering
    and the fix does nothing at all - which is the exact bug, one layer down."""
    fields = Execution._POSITION_FIELDS
    for name in ("_traded_sos_l_ms", "_traded_sos_s_ms", "_traded_sos_l", "_traded_sos_s"):
        assert name in fields, f"{name} is not persisted"


def test_the_bar_map_does_not_grow_without_bound():
    """A bot runs for weeks. An unbounded dict here is a leak with no upside, and the tail is all
    any setup needs."""
    ex = _ex()
    keep = Execution._BAR_MS_KEEP
    _feed(ex, 0, keep + 500, FIRST)
    assert len(ex._bar_ms) <= keep
    assert max(ex._bar_ms) == keep + 499, "it pruned the RECENT end instead of the old one"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
