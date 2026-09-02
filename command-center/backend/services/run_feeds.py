"""Which BAR FEEDS a python run will actually load — the one place that decides.

WHY THIS EXISTS
---------------
A python run loads its chart timeframe, and it may load MORE. `exec_secondary` turns on a
faster sniper feed alongside the 15m primary, so the run touches two timeframes with two
different broker history floors.

That fact used to live in exactly one place — `python_runner`, at fetch time — and the
pre-flight floor check knew nothing about it. Measured 2026-08-15 on run `50331c7cbe96`:
Vantage XAUUSD M15 goes back to 2018-09-13 and M1 only to 2018-09-14. The date picker read
the M15 floor, offered 2018-09-13, the router's `validate_window` agreed, a run row was
inserted, the lock was taken, the 15m frame loaded — and the run died at 8% on the 1m load,
one day short. The identical window with `exec_secondary` OFF had completed four days
earlier, which made it look like a date bug. It was a FEED bug.

🔴 The lesson is not about `exec_secondary`. Two places independently decided what a run
loads, and only one of them was ever updated. So this module is the answer for BOTH: the
runner asks it what to fetch, and the floor check asks it what to bound. They cannot drift
apart, because there is nothing to keep in sync.

Adding a feed is one row in `EXTRA_FEEDS`. Nothing else changes — the runner loads it, the
pre-flight bounds it, the date picker moves, and the retry modal explains itself.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, NamedTuple, Optional


# param flag -> the timeframe (minutes) it makes the run ALSO load.
#
# ⚠ Keyed on BOOLEAN params. A future feed selected by a string or a number ("bias_tf":
# "H1") needs its own branch in `required_timeframes`, not a row here — and the frontend
# sends only truthy flag NAMES, so a non-boolean would never arrive.
class FeedSpec(NamedTuple):
    """How to work out ONE extra feed's timeframe: the run's own setting, or a default.

    🔴 **`default` USED TO BE THE WHOLE ANSWER, AND THAT MADE A LIVE CONTROL DEAD (2026-09-01).**
    The strategy declares "Re-entry fill clock (minutes)" as a 1–15 number widget whose own
    description tells the reader it changes how accurate the test is. This module ignored it and
    `python_runner` fetched at the constant, so a run set to 1 or to 15 still bounded and still
    replayed 5m bars — the stored params saying one thing and the measurement being another. The
    command-line tool honoured it the whole time, so the two sides disagreed about what a run had
    been measured at, and nothing said so.

    ⚠ **`default` is still load-bearing and is NOT the strategy's field read at import.** This
    module bounds the window before any strategy is constructed, so it cannot import the value; a
    run that never states the setting has to be bounded at something, and that something is a
    COPY pinned to the strategy's own default by `tests/test_run_feeds.py`.
    """

    param: Optional[str]  # the run param that OVERRIDES it, or None if the feed is fixed
    default: int  # what a run that does not state that param loads


EXTRA_FEEDS: dict[str, FeedSpec] = {
    # The re-entry's FILL CLOCK. `python_runner` replays the 15m PRIMARY and the re-entry on one
    # merged clock via `strategy.run_dual`, so this feed's measured history floor bounds the run's
    # window just as hard as the chart's does.
    #
    # 🔴 5, not 1, since 2026-08-21, and the OWNER of that number is the strategy
    # (`mpc_sos_fade/config.py::exec_sec_fill_tf_min`) — this is a copy, and
    # `tests/test_run_feeds.py` fails if the two ever disagree. It is a copy rather than an import
    # because this module bounds the WINDOW before any strategy is constructed, and a value it
    # cannot read is a value it would have to guess.
    # ⚠ It is a measurement-accuracy figure, not a strategy one: live, the broker fills a resting
    # limit at the price that trades. MEASURED over 7.9 years — 1m +147.56R, 5m +145.61R (1/5 the
    # bars), 15m +136.36R. Full table in the strategy's config beside the field.
    "exec_secondary": FeedSpec(param="exec_sec_fill_tf_min", default=5),
}

# The one extra feed the runner knows how to LOAD (`strategy.run_dual`). Adding a row to
# EXTRA_FEEDS gets that feed BOUNDED without teaching the runner to fetch it — the window
# then narrows more than it needs to, which refuses honestly rather than replaying a feed
# nobody loaded. Wire the runner in the same change; this is the name it keys off.
#
# ⚠ The runner must test THIS FLAG, never `1 in required_timeframes(...)`. A run whose
# CHART is 1m puts 1 in the feed set on its own, so the membership test would fire the
# dual-replay branch with the secondary switched off.
SECONDARY_FLAG = "exec_secondary"


def timeframe_minutes(bar_type: Optional[str], bar_value: Optional[int]) -> int:
    """job_spec `bar_type`/`bar_value` -> minutes.

    The ONE mapping. `python_runner._timeframe_minutes` and `history_limits._tf_minutes`
    were two hand-copied versions of this; they happened to agree, which is not the same
    as being one thing.
    """
    bt = bar_type or "Minute"
    bv = int(bar_value or 15)
    if bt == "Day":
        return 1440
    if bt != "Minute":
        return 60
    return max(1, bv)


def extra_feed_minutes(flag: str, params: Any = None) -> int:
    """The timeframe one extra feed loads for THIS run — its own setting, or the default.

    ⚠ **The one place that decides, and both the FETCH and the FLOOR ask it.** They used to read
    `EXTRA_FEEDS[flag]` separately, which was fine only while the answer was a constant. Two
    call sites independently resolving a value is the shape this module was created to end.

    ⚠ **A stated value that is not a positive whole number falls back to the default** rather
    than raising. This runs inside a date-picker request as well as a run, and a picker that
    500s because somebody is mid-typing in a number box is worse than one bounded at the
    default — the RUN still refuses properly, because the strategy's own config validates it.
    """
    spec = EXTRA_FEEDS[flag]
    if spec.param is None:
        return spec.default
    raw = _value(params, spec.param)
    try:
        got = int(raw)
    except (TypeError, ValueError):
        return spec.default
    return got if got > 0 else spec.default


def _value(params: Any, name: str):
    """One param off a params dict OR a built config object. `None` when it is not stated."""
    if params is None:
        return None
    if isinstance(params, Mapping):
        return params.get(name)
    return getattr(params, name, None)


def _flag(params: Any, name: str) -> bool:
    """Read one flag off a params dict OR a built config object.

    Both shapes are real and they arrive from different ends: the routers hold the stored
    `params` dict (pre-flight, before a config exists), and `python_runner` holds the built
    config (post-merge, which is the more authoritative of the two — a strategy default
    that the spec never overrode is only visible there).
    """
    if params is None:
        return False
    if isinstance(params, Mapping):
        return bool(params.get(name, False))
    return bool(getattr(params, name, False))


def required_timeframes(
    bar_type: Optional[str] = "Minute",
    bar_value: Optional[int] = 15,
    params: Any = None,
) -> list[int]:
    """Every timeframe this run will LOAD, ascending. Always includes the chart's.

    `params` may be the stored params dict, a built config object, or None. None means
    "no extra feeds declared" — it is not a claim that none are on, so a caller that HAS
    params must pass them. Every call site in this repo does; the default exists so the
    chart timeframe alone is still a valid question to ask.
    """
    minutes = {timeframe_minutes(bar_type, bar_value)}
    for name in EXTRA_FEEDS:
        if _flag(params, name):
            minutes.add(extra_feed_minutes(name, params))
    return sorted(minutes)


def uses_secondary(params: Any) -> bool:
    """Does this run replay a faster SECONDARY feed alongside its chart?

    The runner's dual-replay branch asks this and nothing else. It exists as a named
    function rather than an inline test because the obvious inline test is WRONG in a way
    that reads fine: `1 in required_timeframes(...)` is true for a run whose CHART is 1m,
    so it would fire `run_dual` with the secondary switched off. Naming the question puts
    that mistake somewhere a test can hold it.
    """
    return _flag(params, SECONDARY_FLAG)


def enabled_feed_flags(params: Any) -> list[str]:
    """The `EXTRA_FEEDS` flags that are ON, sorted — what the frontend sends back as
    `flags` so the API can rebuild the same feed set without the UI shipping its own copy
    of this table."""
    return sorted(name for name in EXTRA_FEEDS if _flag(params, name))


def feeds_from_flags(
    flags: Optional[Iterable[str]], values: Optional[Iterable[str]] = None
) -> dict:
    """`flags` (+ optional `name:value` pairs) -> a params-shaped mapping for `required_timeframes`.

    Unknown names are dropped rather than rejected: the UI sends every truthy param name it
    happens to hold, so most of what arrives here is not a feed flag at all.

    ⚠ **`values` exists because a flag alone stopped being enough (2026-09-01).** A feed's
    timeframe can now come from a run param, and the picker was sending names only — so it would
    have bounded every run at the DEFAULT while the run itself loaded something else, which is
    the 2026-08-15 defect arriving one level down. The UI sends its numeric params the same way
    it sends its flags — everything it holds — and this keeps only the ones a feed reads, so the
    frontend still carries no copy of that list.
    """
    names = {f.strip() for f in (flags or []) if f and f.strip()}
    out: dict = {name: True for name in EXTRA_FEEDS if name in names}
    wanted = {spec.param for spec in EXTRA_FEEDS.values() if spec.param}
    for pair in values or []:
        key, _, raw = (pair or "").partition(":")
        key = key.strip()
        if key in wanted:
            try:
                out[key] = int(raw)
            except (TypeError, ValueError):
                pass  # mid-typing, or a non-numeric: the default stands
    return out
