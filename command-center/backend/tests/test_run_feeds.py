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


def test_the_secondary_adds_the_one_minute_feed():
    assert run_feeds.required_timeframes("Minute", 15, {"exec_secondary": True}) == [1, 15]


def test_a_built_config_object_answers_the_same_as_a_params_dict():
    """The routers hold a params DICT and `python_runner` holds a built CONFIG. Both are real
    and they arrive from different ends, so a reader that only understood one would leave the
    runner and the pre-flight disagreeing again — which is the whole defect."""

    class Cfg:
        exec_secondary = True

    assert run_feeds.required_timeframes("Minute", 15, Cfg()) == [1, 15]


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
    off = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": False})
    on = history_limits.limits_for("XAUUSD", "Minute", 15, params={"exec_secondary": True})
    assert off["earliest_date"] == "2018-09-13"
    assert on["earliest_date"] == "2018-09-14"


def test_the_floor_names_the_feed_that_set_it(floors):
    """A picker that jumps a day has to be able to say why, or it reads as broken."""
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
    with patch.dict(run_feeds.EXTRA_FEEDS, {"exec_bias_h4": 240}, clear=False):
        lim = history_limits.limits_for(
            "XAUUSD", "Minute", 15, params={"exec_secondary": True, "exec_bias_h4": True}
        )
    assert lim["earliest_date"] == "2018-09-14"  # 240m is unknown; 1m still binds
