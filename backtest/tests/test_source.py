"""BarSource orchestration: cache-first fetch, resample path, range slicing."""

import pandas as pd

from backtest.data.cache import BarCache
from backtest.data.source import BarSource
from backtest.data.timeframes import to_minutes


class FakeAgent:
    """Serves deterministic bars at the requested timeframe and counts calls."""

    def __init__(self):
        self.calls: list[tuple] = []

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((symbol, tf_name, start_date, end_date))
        minutes = to_minutes(tf_name)
        idx = pd.date_range(
            start=f"{start_date} 00:00",
            end=f"{end_date} 23:59",
            freq=f"{minutes}min",
            name="time",
        )
        n = len(idx)
        return pd.DataFrame(
            {
                "open": [1.0] * n,
                "high": [2.0] * n,
                "low": [0.0] * n,
                "close": [1.5] * n,
            },
            index=idx,
        )


def _source(tmp_path):
    agent = FakeAgent()
    return BarSource(agent=agent, cache=BarCache(tmp_path)), agent


def test_first_load_fetches_and_caches(tmp_path):
    src, agent = _source(tmp_path)
    bars = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    assert not bars.empty
    assert len(agent.calls) == 1
    assert agent.calls[0][1] == "M15"


def test_second_load_hits_cache_no_refetch(tmp_path):
    src, agent = _source(tmp_path)
    src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-10")
    src.load("XAUUSD.s", "M15", "2026-01-06", "2026-01-08")  # sub-range
    assert len(agent.calls) == 1  # served from cache the second time


def test_resample_reuses_the_base_cache(tmp_path):
    src, agent = _source(tmp_path)
    # Pull 15m first (base M15 fetched + cached).
    src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    # 45m resamples up from the SAME M15 base — no second fetch.
    out = src.load("XAUUSD.s", "45m", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 1
    assert not out.empty
    # 45m windows are 3× fewer than 15m over a full covered day.
    fifteen = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-05")
    fortyfive = src.load("XAUUSD.s", "45m", "2026-01-05", "2026-01-05")
    assert len(fortyfive) <= len(fifteen) // 3 + 1


def test_slice_is_inclusive_of_end_date(tmp_path):
    src, _ = _source(tmp_path)
    bars = src.load("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    assert bars.index.min() >= pd.Timestamp("2026-01-05 00:00")
    assert bars.index.max() < pd.Timestamp("2026-01-07 00:00")
    assert bars.index.max() >= pd.Timestamp("2026-01-06 00:00")


def test_slice_excludes_out_of_range_cached_bars(tmp_path):
    src, agent = _source(tmp_path)
    # Fetch a wide window into cache...
    src.load("XAUUSD.s", "M15", "2026-01-01", "2026-01-31")
    # ...then ask for a narrow slice — only in-range bars come back.
    narrow = src.load("XAUUSD.s", "M15", "2026-01-10", "2026-01-11")
    assert narrow.index.min() >= pd.Timestamp("2026-01-10 00:00")
    assert narrow.index.max() < pd.Timestamp("2026-01-12 00:00")
    assert len(agent.calls) == 1  # wide fetch covered the narrow ask


# ── FEED_VERSION invalidation through the source ──────────────────────────────


def test_stale_cache_forces_a_refetch_and_does_not_strand_the_caller(tmp_path):
    """The 2026-07-16 trap, end to end. `cache.load` refuses a stale file, so if the recorded
    coverage were still honoured the caller would get an EMPTY frame forever instead of a
    re-pull. Coverage must be dropped alongside the cache."""
    import json

    from backtest.data.cache import FEED_VERSION

    agent = FakeAgent()
    cache = BarCache(tmp_path)
    source = BarSource(agent, cache)

    first = source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert not first.empty
    assert len(agent.calls) == 1

    # Second call is served from cache — no refetch.
    source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 1

    # Age the cache: same bars, older meaning.
    cache.meta_path("XAUUSD.s", "M5").write_text(json.dumps({"feed_version": FEED_VERSION - 1}))

    again = source.load("XAUUSD.s", "M5", "2026-01-05", "2026-01-06")
    assert len(agent.calls) == 2, "stale cache must trigger a refetch"
    assert not again.empty, "stale cache must not strand the caller with an empty frame"
    assert not cache.is_stale("XAUUSD.s", "M5"), "refetch must restamp the cache as current"


# ── coverage must record what CAME BACK, not what was asked for ──────────────────
# 🔴 Found 2026-08-04 on the live cache: the sidecar claimed history through 2026-08-06
# while the file held nothing past 2026-08-03 03:45, and the agent was serving the missing
# 170 bars on request the whole time. Recording the REQUEST marks a date fetched even when
# no data for it exists, and every later run then reads a cache HIT and gets a short frame
# with no error. A backtest cannot detect that from its own result.


class ShortAgent(FakeAgent):
    """Serves bars only up to `serves_to`, however far the request reaches.

    This is what a broker does at the live edge every single day: you ask through today and
    get back everything that exists, which stops somewhere earlier.
    """

    def __init__(self, serves_to: str):
        super().__init__()
        self.serves_to = serves_to

    def bars(self, symbol, tf_name, start_date, end_date):
        capped = min(end_date, self.serves_to)
        return super().bars(symbol, tf_name, start_date, capped)


def _yesterday() -> str:
    import datetime as dt

    return str(dt.date.today() - dt.timedelta(days=1))


def _days_ago(n: int) -> str:
    import datetime as dt

    return str(dt.date.today() - dt.timedelta(days=n))


def test_a_short_fetch_does_not_claim_the_dates_it_never_returned(tmp_path):
    agent = ShortAgent(serves_to=_days_ago(3))
    src = BarSource(agent=agent, cache=BarCache(tmp_path))
    src.load("XAUUSD", "15", _days_ago(10), _yesterday())
    assert not src.coverage.covered("XAUUSD", "M15", _days_ago(2), _yesterday())


def test_the_missing_tail_is_refetched_rather_than_served_short_forever(tmp_path):
    # The bug's real cost: the second run is the one that silently lies, because the first
    # run at least returned everything that existed at the time.
    agent = ShortAgent(serves_to=_days_ago(3))
    src = BarSource(agent=agent, cache=BarCache(tmp_path))
    src.load("XAUUSD", "15", _days_ago(10), _yesterday())

    agent.serves_to = _yesterday()  # the broker catches up
    got = src.load("XAUUSD", "15", _days_ago(10), _yesterday())
    assert str(got.index[-1].date()) == _yesterday()


def test_a_window_ending_in_the_past_still_caches_and_does_not_refetch(tmp_path):
    # The fix must not make every historical run pay for an extra agent call.
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    n = len(agent.calls)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    assert len(agent.calls) == n


def test_today_is_never_recorded_as_covered_even_when_bars_reach_it(tmp_path):
    # A day that is still filling looks identical to a complete one from the bars alone: a
    # frame ending 00:15 on the last day is either "the broker stops here" or "it is 00:20
    # right now", and nothing in the frame tells them apart.
    import datetime as dt

    today = str(dt.date.today())
    src, _ = _source(tmp_path)  # FakeAgent serves the whole requested window
    src.load("XAUUSD", "15", _days_ago(5), today)
    assert not src.coverage.covered("XAUUSD", "M15", today, today)


# ── a near-miss must cost a near-miss, not a full refetch ────────────────────────
# 🔴 Found 2026-08-06. `covered_spans` above deliberately never marks TODAY as covered, so a
# window ending today is never fully covered — and `_load_base` answered that by re-pulling
# the ENTIRE window to obtain the one missing day. Measured on the live cache: 27.8s to load
# 155,776 XAUUSD M15 bars for 2020-01-01 -> today, against 0.39s for the same span ending
# yesterday. 72x, paid on every chart open, every backtest and every sweep reaching the live
# edge. The rule above is right; honouring it just has to be cheap.


def test_only_the_missing_tail_is_fetched_not_the_whole_window(tmp_path):
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    agent.calls.clear()

    src.load("XAUUSD", "15", "2024-01-01", "2024-01-20")
    assert len(agent.calls) == 1
    _, _, asked_from, asked_to = agent.calls[0]
    assert (asked_from, asked_to) == ("2024-01-11", "2024-01-20"), (
        "the fetch must start the day after the cached range, not at the window start"
    )


def test_a_window_ending_today_refetches_a_day_not_six_years(tmp_path):
    # The live-edge case, and the one that was costing 27.8s a call. The first load records
    # coverage up to yesterday (today is never claimed), so the second must ask only for today.
    import datetime as dt

    today = str(dt.date.today())
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", _days_ago(400), today)
    agent.calls.clear()

    src.load("XAUUSD", "15", _days_ago(400), today)
    assert len(agent.calls) == 1
    _, _, asked_from, asked_to = agent.calls[0]
    assert asked_from == today and asked_to == today, (
        f"expected a one-day tail fetch, got {asked_from} -> {asked_to}"
    )


def test_a_gap_in_the_middle_is_fetched_without_refetching_either_side(tmp_path):
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-05")
    src.load("XAUUSD", "15", "2024-02-01", "2024-02-05")
    agent.calls.clear()

    src.load("XAUUSD", "15", "2024-01-01", "2024-02-05")
    assert [(c[2], c[3]) for c in agent.calls] == [("2024-01-06", "2024-01-31")]


def test_a_partial_fetch_never_deletes_the_bars_it_did_not_ask_for(tmp_path):
    # ⚠ KEPT, and it PASSES against the old code too — it is a guard, not a catch. The old
    # code refetched everything, so there was never a partial fetch to lose anything. It
    # pins the property the new code now DEPENDS on: `BarCache.save` merges rather than
    # overwrites. If that ever changed, a one-day tail pull would truncate the history to
    # one day and every later run would read the short frame as a clean cache hit.
    import datetime as dt

    today = str(dt.date.today())
    src, _ = _source(tmp_path)
    first = src.load("XAUUSD", "15", _days_ago(30), today)
    again = src.load("XAUUSD", "15", _days_ago(30), today)
    assert len(again) >= len(first)
    assert str(again.index[0].date()) == _days_ago(30)


def test_a_fully_covered_window_still_makes_no_call_at_all(tmp_path):
    # ⚠ Also passes against the old code (its `covered()` fast path did this), and is kept
    # for the direction the new code could break: `missing()` returning a spurious gap would
    # add an agent call to every cached run, which is the regression this change must not buy.
    src, agent = _source(tmp_path)
    src.load("XAUUSD", "15", "2024-01-01", "2024-01-10")
    agent.calls.clear()
    src.load("XAUUSD", "15", "2024-01-03", "2024-01-08")
    assert agent.calls == []


def test_a_fetch_that_returns_nothing_usable_records_no_coverage_at_all(tmp_path):
    # Requesting a window entirely in the future must not mark it fetched. Without the
    # start<=end guard the clamp would record an inverted interval, which _merge_intervals
    # would happily persist and covered() would then answer with nonsense.
    import datetime as dt

    src = BarSource(agent=ShortAgent(serves_to=_days_ago(3)), cache=BarCache(tmp_path))
    fut_a = str(dt.date.today() + dt.timedelta(days=5))
    fut_b = str(dt.date.today() + dt.timedelta(days=9))
    try:
        src.load("XAUUSD", "15", fut_a, fut_b)
    except Exception:
        pass
    assert not src.coverage.covered("XAUUSD", "M15", fut_a, fut_b)


# ---------------------------------------------------------------------------------------------
# `covered_spans` — coverage must DESCRIBE the bars received, never the window requested.
#
# 🔴 Found 2026-08-07 on the live cache. `XAUUSD__M1.ranges.json` claimed 2018-09-14 → 2026-08-06
# while the CSV held NOTHING between 2026-06-22 and 2026-08-05 — 45 days, ~62,000 bars — and the
# broker was serving them the whole time. A covered range is never re-fetched, so the loss was
# permanent, and the price chart drew the hole's edge as "No earlier M1 data".
#
# Both branches below reproduce it, and both were reachable from one transient agent failure.
# ---------------------------------------------------------------------------------------------


class SilentAgent:
    """Answers with an EMPTY frame — a tunnel down, a terminal restarting, an agent mid-deploy."""

    def __init__(self):
        self.calls: list[tuple] = []

    def bars(self, symbol, tf_name, start_date, end_date):
        self.calls.append((symbol, tf_name, start_date, end_date))
        return pd.DataFrame()


class TailOnlyAgent(FakeAgent):
    """Answers a long request with only its last day — a partial serve, no error."""

    def bars(self, symbol, tf_name, start_date, end_date):
        full = super().bars(symbol, tf_name, start_date, end_date)
        return full[full.index >= f"{end_date} 00:00"]


def test_a_fetch_that_returns_nothing_claims_nothing(tmp_path):
    # ⚠ DEFENCE IN DEPTH, and it does NOT bite today — `BarCache.save` raises on a frame with no
    # columns, so a wholly-empty fetch fails the load loudly before it can reach here. Kept
    # because coverage must not depend on another module crashing in order to stay honest, and
    # labelled so nobody reads it as the cause of the incident above. The reachable defect is the
    # PARTIAL serve in the two tests below.
    from backtest.data.source import covered_spans

    assert covered_spans(pd.DataFrame(), "2026-06-22", "2026-08-05") == []


def test_a_fetch_that_returns_only_its_tail_claims_only_that_tail(tmp_path):
    # The mirror of the clamp that already existed. Asking for 45 days and getting one back is
    # one day of coverage, not 45.
    from backtest.data.source import covered_spans

    idx = pd.date_range("2026-08-05 00:00", "2026-08-05 23:45", freq="15min", name="time")
    got = covered_spans(
        pd.DataFrame({"open": [1.0] * len(idx)}, index=idx), "2026-06-22", "2026-08-05"
    )
    assert got == [("2026-08-05", "2026-08-05")]


def test_a_hole_in_the_middle_of_a_fetch_splits_the_coverage(tmp_path):
    # The M15 corruption shape: bars either side, nothing in between. Claiming one span across
    # it is how a cache comes to vouch for bars it does not hold.
    from backtest.data.source import covered_spans

    a = pd.date_range("2026-06-01 00:00", "2026-06-03 23:45", freq="15min", name="time")
    b = pd.date_range("2026-07-20 00:00", "2026-07-22 23:45", freq="15min", name="time")
    idx = a.append(b)
    got = covered_spans(
        pd.DataFrame({"open": [1.0] * len(idx)}, index=idx), "2026-06-01", "2026-07-22"
    )
    assert got == [("2026-06-01", "2026-06-03"), ("2026-07-20", "2026-07-22")]


def test_a_weekend_inside_a_fetch_does_not_split_it(tmp_path):
    # ⚠ PASSES against the old code too (which claimed everything, so it could not over-split) —
    # this is a guard on the NEW code, not a catch. The other direction, and the reason `_MAX_CLOSURE_DAYS` is not zero: the market really is
    # shut at weekends, and splitting there would refetch every weekend on every single load.
    # MEASURED: the longest no-bar run in 7.9 years of cached XAUUSD is 2 days.
    from backtest.data.source import covered_spans

    a = pd.date_range("2026-06-04 00:00", "2026-06-05 23:45", freq="15min", name="time")  # Thu-Fri
    b = pd.date_range("2026-06-08 00:00", "2026-06-09 23:45", freq="15min", name="time")  # Mon-Tue
    idx = a.append(b)
    got = covered_spans(
        pd.DataFrame({"open": [1.0] * len(idx)}, index=idx), "2026-06-04", "2026-06-09"
    )
    assert got == [("2026-06-04", "2026-06-09")]


def test_a_window_opening_on_a_weekend_still_covers_its_weekend(tmp_path):
    # ⚠ Also passes against the old code, and guards the same new risk. Without this the leading empty days are never covered, so every load re-requests them —
    # the 72x refetch tax this package already fixed once, returning in miniature.
    from backtest.data.source import covered_spans

    idx = pd.date_range("2026-06-08 00:00", "2026-06-09 23:45", freq="15min", name="time")
    got = covered_spans(
        pd.DataFrame({"open": [1.0] * len(idx)}, index=idx), "2026-06-06", "2026-06-09"
    )
    assert got == [("2026-06-06", "2026-06-09")]


def test_a_tail_only_serve_is_re_asked_for_the_days_it_missed(tmp_path):
    # A partial serve leaves the rest genuinely missing, so it must still be a GAP next time.
    cache = BarCache(tmp_path)
    BarSource(agent=TailOnlyAgent(), cache=cache).load("XAUUSD", "15", "2024-01-02", "2024-01-10")
    src2 = BarSource(agent=FakeAgent(), cache=BarCache(tmp_path))
    bars = src2.load("XAUUSD", "15", "2024-01-02", "2024-01-10")
    assert str(bars.index[0].date()) == "2024-01-02", "the un-served days were never re-fetched"
