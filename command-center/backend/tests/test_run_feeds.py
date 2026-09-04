"""A run's history floor is bounded by EVERY feed it loads, not just the chart's.

THE BUG, measured 2026-08-15 on run `50331c7cbe96` (XAUUSD M15, 2018-09-13 → 2026-08-15,
`exec_secondary: true`): Vantage's XAUUSD history starts 2018-09-13 at M15 and 2018-09-14 at
M1. The secondary loads a 1m feed. `history_limits` only ever asked about the chart
timeframe, so the date picker offered 2018-09-13, the router's pre-flight agreed, a run row
was inserted, the lock was taken, the 15m frame loaded — and the run died at 8% on the 1m
load, one day short. The identical window with the secondary OFF had completed four days
earlier, which made it read as a date bug. It was a FEED bug.

⚠ Retry could not fix it either, which is the half that made it a wall: the rerun modal read
the same chart-only floor, re-offered the same illegal date, and the retry failed identically.
So the only way out was deleting the run and building a new one by hand.

The danger in fixing it is the opposite failure: bounding a window by a feed the run does NOT
load would refuse a legal date. So half these tests exist to prove nothing was narrowed —
`exec_secondary` OFF must still reach 2018-09-13.

Every test here was watched RED against the pre-fix code, EXCEPT where a docstring says
otherwise and names the mutation that turns it red instead.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from services import history_limits, run_feeds

# The production shape, and the whole reason this module exists: two feeds, one day apart.
FLOORS = {1: "2018-09-14", 15: "2018-09-13"}

# 🔴 The floor tests below PIN the extra feed to 1m rather than reading whatever the re-entry
# happens to use today, and that is deliberate. They prove a MECHANISM — the window is bounded by
# the shallowest feed the run loads — and they used the re-entry as their vehicle. When its fill
# clock moved 1m → 5m on 2026-08-21 four of them went red, not because the mechanism broke but
# because they had quietly become assertions about a number that lives somewhere else. A test that
# fails on an unrelated config change is a test nobody trusts the next time it speaks.
# ⚠ The REAL value is asserted once, at the bottom, against the strategy that owns it.
SHALLOW_FEED = {"exec_secondary": run_feeds.FeedSpec(param="exec_sec_fill_tf_min", default=1)}


def _describe(symbol, minutes, refresh=False):
    """Stands in for `backtest.data.history.describe` — no live terminal, no probe."""
    if minutes not in FLOORS:
        return None
    return {
        "symbol": symbol,
        "timeframe_minutes": minutes,
        "earliest_date": FLOORS[minutes],
        "broker": "VantageMarkets-Demo",
        "verified": "2026-07-25",
        "source": "probed",
        "note": f"{symbol} has no real {minutes}-minute bars before {FLOORS[minutes]}.",
    }


@pytest.fixture()
def floors():
    with patch("backtest.data.history.describe", side_effect=_describe):
        yield


@pytest.fixture()
def assert_window():
    """The real refusal, driven off `FLOORS` so the two cannot disagree."""
    from backtest.data.history import HistoryFloorError

    def _assert(symbol, timeframe, start_date, end_date=None):
        floor = FLOORS.get(int(timeframe))
        if floor and str(start_date)[:10] < floor:
            raise HistoryFloorError(
                f"{symbol} has no real {timeframe}-minute history before {floor}. "
                f"You asked for {start_date}."
            )

    with patch("backtest.data.history.assert_window", side_effect=_assert):
        yield


# ── which feeds a run loads ────────────────────────────────────────────────────────


def test_the_chart_timeframe_is_always_a_feed():
    assert run_feeds.required_timeframes("Minute", 15, {"exec_secondary": False}) == [15]


def test_the_secondary_adds_its_own_fill_feed():
    """Named for the MECHANISM, not the number. It read `== [1, 15]` and went red on
    2026-08-21 when the re-entry's fill clock moved to 5m — an assertion about a value that
    lives in the strategy, wearing the clothes of an assertion about this module."""
    tf = run_feeds.EXTRA_FEEDS[run_feeds.SECONDARY_FLAG].default
    assert run_feeds.required_timeframes("Minute", 15, {"exec_secondary": True}) == [tf, 15]
    assert tf != 15, "a fill feed equal to the chart proves nothing here"


def test_a_built_config_object_answers_the_same_as_a_params_dict():
    """The routers hold a params DICT and `python_runner` holds a built CONFIG. Both are real
    and they arrive from different ends, so a reader that only understood one would leave the
    runner and the pre-flight disagreeing again — which is the whole defect."""

    class Cfg:
        exec_secondary = True

    tf = run_feeds.EXTRA_FEEDS[run_feeds.SECONDARY_FLAG].default
    assert run_feeds.required_timeframes("Minute", 15, Cfg()) == [tf, 15]


def test_a_one_minute_chart_does_not_imply_the_secondary_is_on():
    """🔴 Caught while writing the fix, not by a report. `required_timeframes` always includes
    the chart, so a 1m-chart run puts 1 in the feed set on its own — and the runner's branch
    was first written as `1 in feeds`, which would have fired the dual replay with the
    secondary switched OFF, on a run that never asked for it.

    ⚠ Vacuous against HEAD (the module did not exist). Turned red by rewriting
    `uses_secondary` as the membership test it must not be:
        `return EXTRA_FEEDS[SECONDARY_FLAG] in required_timeframes(...)`
    ⚠ This asserts on `uses_secondary` because that is what the RUNNER calls. An earlier
    version of this test asserted on `required_timeframes` and `enabled_feed_flags`, and it
    stayed GREEN through that exact mutation — it was checking a function the defect could
    not reach. That is why the runner's question has a name."""
    assert run_feeds.required_timeframes("Minute", 1, {"exec_secondary": False}) == [1]
    assert run_feeds.uses_secondary({"exec_secondary": False}) is False
    assert run_feeds.uses_secondary({"exec_secondary": True}) is True


def test_the_runner_asks_run_feeds_rather_than_deciding_for_itself():
    """The two places that decide what a run loads are this module and the pre-flight floor
    check. `python_runner` reading the flag off the config directly is how they drifted apart
    in the first place, so the branch is pinned to the shared question by reading the source —
    the same arrangement `test_notification_routing.py` uses for its own cross-module rule.

    ⚠ It walks the AST rather than grepping, and the first version did grep and went RED on
    the COMMENT that explains the rule — the same trap `test_deploy_commit_gate.py` records
    for its `--no-verify` guard. The prose naming the old code lives beside the new code.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "services" / "python_runner.py"
    tree = ast.parse(src.read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    asks_run_feeds = any(
        isinstance(c.func, ast.Attribute) and c.func.attr == "uses_secondary" for c in calls
    )
    reads_the_flag_itself = any(
        isinstance(c.func, ast.Name)
        and c.func.id == "getattr"
        and any(isinstance(a, ast.Constant) and a.value == "exec_secondary" for a in c.args)
        for c in calls
    )
    assert asks_run_feeds, "the runner must ask run_feeds which feeds this run loads"
    assert not reads_the_flag_itself, "the runner is deciding for itself again"


def test_flags_survive_the_round_trip_through_the_query_param():
    """The UI sends truthy param NAMES and the API rebuilds the feed set. It must keep the
    feed flags and drop everything else — most of what arrives is not a feed flag at all."""
    sent = run_feeds.enabled_feed_flags(
        {"exec_secondary": True, "exec_sl_deep": True, "exec_req_fvg": False}
    )
    assert sent == ["exec_secondary"]
    assert run_feeds.feeds_from_flags(sent + ["exec_sl_deep", "nonsense"]) == {
        "exec_secondary": True
    }


# ── the floor is the latest across the feeds ───────────────────────────────────────


def test_the_floor_follows_the_shallowest_feed(floors):
    """THE REPORTED BUG. Same instrument, same chart timeframe, one flag apart."""
    with patch.dict(run_feeds.EXTRA_FEEDS, SHALLOW_FEED, clear=False):
        off = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": False})
        on = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": True})
    assert off["earliest_date"] == "2018-09-13"
    assert on["earliest_date"] == "2018-09-14"


def test_the_floor_names_the_feed_that_set_it(floors):
    """A picker that jumps a day has to be able to say why, or it reads as broken."""
    with patch.dict(run_feeds.EXTRA_FEEDS, SHALLOW_FEED, clear=False):
        on = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": True})
    assert on["timeframe_minutes"] == 1
    assert "1m" in on["note"] and "15m" in on["note"]


def test_nothing_is_narrowed_when_the_extra_feed_is_off(floors):
    """The guard against fixing this in the dangerous direction: bounding by a feed the run
    does not load would refuse a window that is perfectly legal."""
    off = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": False})
    assert off["earliest_date"] == "2018-09-13"
    assert off["timeframe_minutes"] == 15
    assert "also loads" not in off["note"]


def test_a_window_the_extra_feed_cannot_serve_is_refused(floors, assert_window):
    with patch.dict(run_feeds.EXTRA_FEEDS, SHALLOW_FEED, clear=False):
        history_limits.validate_window(
            "XAUUSD", "2018-09-13", "2026-08-15", params={"exec_secondary": False}
        )  # legal, and must stay legal
        with pytest.raises(ValueError):
            history_limits.validate_window(
                "XAUUSD", "2018-09-13", "2026-08-15", params={"exec_secondary": True}
            )


def test_a_non_python_runner_is_still_unbounded(floors, assert_window):
    """NT8 and MT5 read history from their own terminals, so a Vantage floor must never be
    imposed on them — the lie in the more dangerous direction."""
    assert history_limits.limits_for("XAUUSD", "Minute", 15, "mt5", params={}) is None
    history_limits.validate_window(
        "XAUUSD", "1990-01-01", "2026-08-15", runner="mt5", params={"exec_secondary": True}
    )


def test_an_unmeasurable_feed_does_not_silently_drop_the_floor(floors):
    """A timeframe `describe` cannot answer for yields no meta at all, so the floor is built
    from a SUBSET of the feeds. The remaining feeds must still bound the window — answering
    None because one feed is unknown would leave the run unbounded, which is the reassuring
    direction and the wrong one."""
    with patch.dict(
        run_feeds.EXTRA_FEEDS,
        {**SHALLOW_FEED, "exec_bias_h4": run_feeds.FeedSpec(param=None, default=240)},
        clear=False,
    ):
        lim = history_limits.limits_for(
            "XAUUSD", "Minute", 15, params={"exec_secondary": True, "exec_bias_h4": True}
        )
    assert lim["earliest_date"] == "2018-09-14"  # 240m is unknown; 1m still binds


# ── the fill clock is a COPY, and a copy needs a test ─────────────────────────


def test_the_reentry_fill_clock_matches_the_strategy_that_owns_it():
    """`EXTRA_FEEDS` bounds the run's WINDOW before any strategy is constructed, so it cannot
    import the number it needs — it holds a copy. The strategy owns it, and the two disagreeing
    means the window was checked against one feed and the replay walked another.

    ✅ Watched RED by setting the registry to 1 while the strategy says 5 — which is exactly the
    state this repo was in until 2026-08-21, loading 2.8M bars a run for 1.3% of accuracy.
    """
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from strategies.python.sos_fade.config import SosFadeConfig

    spec = run_feeds.EXTRA_FEEDS[run_feeds.SECONDARY_FLAG]
    assert spec.default == SosFadeConfig().exec_sec_fill_tf_min
    # The override's NAME is pinned too. A typo here would not fail anything on its own — the
    # resolver would simply never find the param and fall back to the default, which is the
    # dead-control defect this table was changed to fix, silently restored.
    assert spec.param in SosFadeConfig.__dataclass_fields__


# ── the run's OWN fill clock, not the registry's default (2026-09-01) ─────────
#
# 🔴 The strategy declares "Re-entry fill clock (minutes)" as a 1-15 number widget whose own
# description says it changes how accurate the test is. This module ignored it and
# `python_runner` fetched at the constant, so a run set to 1 or to 15 still bounded and still
# replayed 5m bars while its stored params claimed otherwise. The command-line tool
# (`backtest/tools/run_report.py`) honoured it the whole time, so the two sides disagreed about
# what a run had been measured at and nothing said so.
#
# ⚠ Every test below was watched RED against the module as it stood before that date: each one
# returned the DEFAULT whatever the run asked for.


def test_a_run_that_states_a_faster_fill_clock_is_bounded_at_it():
    assert run_feeds.required_timeframes(
        "Minute", 15, {"exec_secondary": True, "exec_sec_fill_tf_min": 1}
    ) == [1, 15]


def test_a_run_that_states_a_slower_fill_clock_is_bounded_at_it():
    """The widget's other end. 15 is legal in the LAB (the live bot separately refuses a clock
    that is not faster than the stream it trades) and it must not be read as the default."""
    assert run_feeds.required_timeframes(
        "Minute", 15, {"exec_secondary": True, "exec_sec_fill_tf_min": 15}
    ) == [15]


def test_a_run_that_states_nothing_still_gets_the_default():
    """The whole reason the default stays: this module bounds the window before a strategy
    exists, so a run that never stated the setting has to be bounded at something."""
    assert run_feeds.required_timeframes("Minute", 15, {"exec_secondary": True}) == [5, 15]


def test_the_fill_clock_is_ignored_when_the_feed_itself_is_OFF():
    """A value with its flag off must not conjure a feed the run never loads."""
    assert run_feeds.required_timeframes(
        "Minute", 15, {"exec_secondary": False, "exec_sec_fill_tf_min": 1}
    ) == [15]


def test_a_nonsense_fill_clock_falls_back_rather_than_raising():
    """This runs inside a date-picker request too. A picker that 500s because somebody is
    mid-typing in a number box is worse than one bounded at the default — and the RUN still
    refuses properly, because the strategy's own config validates the value."""
    for bad in ("", "abc", None, 0, -3):
        assert (
            run_feeds.extra_feed_minutes(run_feeds.SECONDARY_FLAG, {"exec_sec_fill_tf_min": bad})
            == 5
        )


def test_a_built_config_object_answers_the_same_as_a_params_dict_for_the_clock():
    class Cfg:
        exec_secondary = True
        exec_sec_fill_tf_min = 1

    assert run_feeds.required_timeframes("Minute", 15, Cfg()) == [1, 15]


def test_the_picker_carries_the_VALUE_and_not_only_the_flag():
    """`flags` alone bounded every run at the default while the run loaded something else — the
    2026-08-15 defect one level down."""
    params = run_feeds.feeds_from_flags(["exec_secondary"], ["exec_sec_fill_tf_min:1"])
    assert params == {"exec_secondary": True, "exec_sec_fill_tf_min": 1}
    assert run_feeds.required_timeframes("Minute", 15, params) == [1, 15]


def test_the_picker_drops_numeric_params_no_feed_reads():
    """Same rule as `flags`: the UI sends everything it holds and this keeps what matters, so
    the frontend never carries its own copy of the feed list."""
    params = run_feeds.feeds_from_flags(
        ["exec_secondary"], ["exec_risk_pct:12.5", "exec_sec_fill_tf_min:1", "junk:9"]
    )
    assert params == {"exec_secondary": True, "exec_sec_fill_tf_min": 1}


def test_a_malformed_value_pair_is_dropped_rather_than_breaking_the_picker():
    params = run_feeds.feeds_from_flags(
        ["exec_secondary"], ["exec_sec_fill_tf_min", "exec_sec_fill_tf_min:x", ""]
    )
    assert params == {"exec_secondary": True}
    assert run_feeds.required_timeframes("Minute", 15, params) == [5, 15]
