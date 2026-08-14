"""`build_run_candles`'s `hard_edge` — the flag that says "the broker has nothing older".

🔴 **Aaron reported it off the screen on 2026-08-07: drilling to M1 drew ~100 bars behind a red
"No earlier M1 data — all the broker still has" line, on a symbol whose real M1 history runs back
to 2018-09-14 (~2.8M bars).**

MEASURED, and the chart was faithfully reporting a lie told one layer down: `XAUUSD__M1.ranges.json`
claimed coverage of 2018-09-14 → 2026-08-06 while the CSV held NOTHING between 2026-06-22 and
2026-08-05, and the broker served 4,013 bars for a sample day inside that hole when asked directly.
The fetch honestly returned nothing older, and `hard_edge` turned "we have no more" into "there IS
no more" — inferring a fact about the BROKER from a fact about our CACHE.

⚠ **The label was the smaller half. The frontend STOPS PAGING on a hard edge** (`drillOlder`
returns `more: false` and then early-returns on later scrolls), so the claim was self-sealing:
nothing would ever ask for those bars again.

The fix is that `hard_edge` now also requires the oldest bar to sit on the broker's MEASURED
history floor, and an unknown floor answers False — no measurement, no claim.
"""

import pytest
from services import chart_spec

RUN = {"runner": "python", "instrument": "XAUUSD"}
DAY = 86_400_000
# 2018-09-14, the measured Vantage XAUUSD intraday floor.
FLOOR_MS = 1_536_883_200_000


def _candles(first_ms, n=200, step=60_000):
    return [
        {"time": first_ms + i * step, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}
        for i in range(n)
    ]


@pytest.fixture
def drill(monkeypatch):
    """Drive `build_run_candles` with a chosen feed answer and a chosen measured floor."""

    def go(*, first_ms, from_ms, to_ms, floor_date):
        monkeypatch.setattr(chart_spec.lab_db, "get_run", lambda rid: dict(RUN))
        monkeypatch.setattr(
            chart_spec,
            "_fetch_candles",
            lambda *a, **k: (_candles(first_ms), None),
        )
        monkeypatch.setattr(
            chart_spec.history_limits,
            "limits_for",
            lambda *a, **k: {"earliest_date": floor_date} if floor_date else None,
        )
        return chart_spec.build_run_candles("r1", "M1", from_ms, to_ms)

    return go


def test_a_gap_in_our_cache_is_not_reported_as_the_brokers_limit(drill):
    # THE INCIDENT. We asked for 12 days of M1 and got back only the newest day, because the
    # cache had a hole. The broker's real floor is years earlier, so this is OUR edge, not its.
    out = drill(
        first_ms=FLOOR_MS + 2000 * DAY,  # bars start LONG after the broker's floor
        from_ms=FLOOR_MS + 1988 * DAY,  # ...and long after what we asked for
        to_ms=FLOOR_MS + 2001 * DAY,
        floor_date="2018-09-14",
    )
    assert out["candles"], "the feed did answer — this is not the empty case"
    assert out["hard_edge"] is False


def test_the_brokers_real_floor_still_reports_a_hard_edge(drill):
    # The other direction, and the reason this flag exists at all: reaching genuine end-of-history
    # must still draw the line and stop the pager, or every drill-down pages for ever.
    out = drill(
        first_ms=FLOOR_MS,
        from_ms=FLOOR_MS - 20 * DAY,
        to_ms=FLOOR_MS + 20 * DAY,
        floor_date="2018-09-14",
    )
    assert out["hard_edge"] is True


def test_an_unmeasurable_floor_makes_no_claim(drill):
    # `limits_for` answers None for an unreachable terminal, an unknown broker, and every
    # non-python runner. None of those is evidence of a boundary. Same rule as `mt5_link` and
    # `grid_sensitivity_score`: never let "no" and "cannot ask" be the same value — and here the
    # cost of the two mistakes is wildly asymmetric, since a wrong True is unrecoverable (the
    # pager stops for the session) while a wrong False costs one request that returns nothing.
    out = drill(
        first_ms=FLOOR_MS + 2000 * DAY,
        from_ms=FLOOR_MS + 1988 * DAY,
        to_ms=FLOOR_MS + 2001 * DAY,
        floor_date=None,
    )
    assert out["hard_edge"] is False


def test_history_starting_mid_session_still_counts_as_the_floor(drill):
    # ⚠ PIN, not a catch — it passes against the old code too, and is kept because the fix
    # introduced the risk it guards. The floor is a DATE and the first bar is a TIMESTAMP, and
    # real history opens mid-session (Vantage XAUUSD M15 starts 2018-09-13 with 38 bars). An
    # exact-equality comparison would refuse to call the true edge the edge, which is this fix
    # failing in the direction that looks safe and quietly re-breaks the pager's stop.
    out = drill(
        first_ms=FLOOR_MS + int(0.6 * DAY),
        from_ms=FLOOR_MS - 20 * DAY,
        to_ms=FLOOR_MS + 20 * DAY,
        floor_date="2018-09-14",
    )
    assert out["hard_edge"] is True
