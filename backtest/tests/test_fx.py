"""Tests for the quote-currency conversion series.

Offline: the bar source is injected, so nothing here touches the MT5 agent.

🔴 **Why this module exists at all.** Every instrument this repo had priced was USD-quoted
against a USD account, so quote and account currency were the same thing and nothing converted.
GBPJPY is quoted in yen: unconverted, its overnight cost reads 156x its real one and every trade
is mis-sized by the same factor, with no error raised because the numbers are the right shape.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from backtest.data.fx import FxRateUnavailable, RateSeries, constant_rate, series_for


def _ms(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


class FakeSource:
    """A bar source with a settable frame — the injection point BarSource fills in production."""

    def __init__(self, frame):
        self._frame = frame
        self.calls = []

    def load(self, symbol, timeframe, start_date, end_date):
        self.calls.append((symbol, timeframe, start_date, end_date))
        return self._frame


def _frame(dates, closes):
    return pd.DataFrame({"close": closes}, index=pd.to_datetime(dates))


# ── the lookup ────────────────────────────────────────────────────────────────


def test_the_rate_in_force_is_the_last_bar_that_had_already_CLOSED():
    s = RateSeries([0, 1_000, 2_000], [100.0, 150.0, 160.0])
    assert s.at(0) == 100.0
    assert s.at(999) == 100.0  # bar 1 has not happened yet
    assert s.at(1_000) == 150.0
    assert s.at(2_500) == 160.0


def test_a_gap_carries_the_rate_FORWARD_because_the_rate_really_did_not_move():
    """A weekend has no bars and the rate genuinely did not move for anyone holding through it,
    so the last close is the right answer rather than a guess. This is the opposite case from
    reaching BACKWARDS, which is extrapolation and refuses."""
    s = RateSeries([_ms("2026-09-11"), _ms("2026-09-14")], [147.0, 149.0])
    assert s.at(_ms("2026-09-12")) == 147.0  # Saturday
    assert s.at(_ms("2026-09-13")) == 147.0  # Sunday
    assert s.at(_ms("2026-09-14")) == 149.0


def test_before_the_series_it_REFUSES_rather_than_extrapolating_backwards():
    """The whole point of the module. A flat extrapolation backwards is a plausible number, no
    error, and a wrong one — which is worse than a stopped run."""
    s = RateSeries([1_000, 2_000], [150.0, 160.0], label="USDJPY")
    with pytest.raises(FxRateUnavailable) as exc:
        s.at(999)
    assert "before the series starts" in str(exc.value)
    assert "USDJPY" in str(exc.value)


def test_invert_turns_a_quoted_pair_into_the_direction_the_ACCOUNT_needs():
    """A dollar account pricing a yen-quoted symbol holds USDJPY bars and needs USD-per-JPY.

    MEASURED cross-check, 2026-09-17: the broker's own tick value for GBPJPY.p implies
    USDJPY 156.026 (0.6409188 USD per 0.001 yen on 100,000 units), and the USDJPY.p daily bar for
    2026-09-15 reads 155.10 — two independent sources, agreeing.
    """
    s = RateSeries([0], [156.026], invert=True)
    assert s.at(0) == pytest.approx(1.0 / 156.026)
    assert s.at(0) == pytest.approx(0.006409, abs=1e-6)


# ── the refusals that stop a bad rate reaching sizing ─────────────────────────


def test_a_non_positive_close_is_refused_at_construction():
    """Sizing DIVIDES by the rate, so a zero is an infinite position. It must die here, where the
    message can name the cause, rather than downstream as a ZeroDivisionError or — worse — as an
    order nobody can explain."""
    with pytest.raises(ValueError) as exc:
        RateSeries([0, 1], [150.0, 0.0])
    assert "infinite position" in str(exc.value)


def test_unsorted_timestamps_are_refused_because_the_lookup_is_a_binary_search():
    with pytest.raises(ValueError) as exc:
        RateSeries([0, 2_000, 1_000], [1.0, 2.0, 3.0])
    assert "ascending" in str(exc.value)


def test_mismatched_lengths_are_refused():
    with pytest.raises(ValueError):
        RateSeries([0, 1_000], [1.0])


def test_an_empty_series_is_refused_because_it_could_only_guess():
    with pytest.raises(ValueError):
        RateSeries([], [])


def test_a_constant_rate_must_be_SAID_and_must_be_positive():
    """ "This instrument needs no conversion" is a thing a caller says, not a thing it omits —
    a silent absence and a deliberate 1.0 read identically at the call site and mean very
    different things. Same reasoning as the cost sentinels in fills.py."""
    assert constant_rate(1.0)(123) == 1.0
    with pytest.raises(ValueError):
        constant_rate(0.0)


# ── building from a frame / a source ──────────────────────────────────────────


def test_from_frame_reads_the_index_as_UTC_bar_OPEN_timestamps():
    df = _frame(["2026-09-14", "2026-09-15"], [149.0, 155.10])
    s = RateSeries.from_frame(df, invert=True, label="USDJPY")
    assert len(s) == 2
    assert s.at(_ms("2026-09-15")) == pytest.approx(1.0 / 155.10)
    # Still inside the first bar's life.
    assert s.at(_ms("2026-09-14") + 3_600_000) == pytest.approx(1.0 / 149.0)


def test_no_bars_REFUSES_rather_than_defaulting_to_1():
    """A default of 1.0 would price a yen-quoted instrument as though it were dollars — exactly
    the bug this module exists to end, reintroduced as a fallback."""
    src = FakeSource(_frame([], []))
    with pytest.raises(FxRateUnavailable) as exc:
        series_for(src, "USDJPY.p", 1440, "2020-01-01", "2026-09-16", invert=True)
    assert "1.0" in str(exc.value)


def test_series_for_asks_the_source_for_exactly_the_window_it_was_given():
    src = FakeSource(_frame(["2026-09-14"], [149.0]))
    series_for(src, "USDJPY.p", 1440, "2020-01-01", "2026-09-16", invert=True)
    assert src.calls == [("USDJPY.p", 1440, "2020-01-01", "2026-09-16")]


def test_the_provider_is_the_shape_set_rate_provider_takes():
    """`Execution.set_rate_provider` takes a `time_ms -> rate` callable and asks it once per bar.
    This is the seam between the two halves, so its shape is pinned here rather than assumed."""
    s = RateSeries([0, 1_000], [100.0, 200.0], invert=True)
    fn = s.provider()
    assert callable(fn)
    assert fn(0) == pytest.approx(0.01)
    assert fn(1_500) == pytest.approx(0.005)
