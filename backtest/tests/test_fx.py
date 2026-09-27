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

from backtest.data.fx import (
    FxRateUnavailable,
    QuoteConversion,
    RateSeries,
    UnknownQuoteCurrency,
    constant_rate,
    conversion_symbol,
    quote_currency,
    rate_provider_for,
    series_for,
)


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


def test_from_frame_keys_each_close_at_its_bar_CLOSE_not_its_open():
    """RED BEFORE 2026-09-27: keyed at the OPEN, the 15th's daily close (155.10) answered at
    00:00 on the 15th — a rate nobody could know until that evening. That is lookahead."""
    df = _frame(["2026-09-14", "2026-09-15", "2026-09-16"], [149.0, 155.10, 156.0])
    s = RateSeries.from_frame(df, invert=True, label="USDJPY")
    assert len(s) == 3
    # Midday on the 15th the 15th has not closed, so the rate in force is the 14th's close.
    assert s.at(_ms("2026-09-15") + 12 * 3_600_000) == pytest.approx(1.0 / 149.0)
    assert s.at(_ms("2026-09-16")) == pytest.approx(1.0 / 155.10)
    # Before any bar has closed there is no rate, and it refuses rather than reaching forward.
    with pytest.raises(FxRateUnavailable):
        s.at(_ms("2026-09-14") + 3_600_000)


def test_from_frame_refuses_to_guess_the_spacing_of_a_single_bar():
    with pytest.raises(ValueError):
        RateSeries.from_frame(_frame(["2026-09-14"], [149.0]))
    s = RateSeries.from_frame(_frame(["2026-09-14"], [149.0]), bar_minutes=1440)
    assert s.at(_ms("2026-09-15")) == 149.0


def test_no_bars_REFUSES_rather_than_defaulting_to_1():
    """A default of 1.0 would price a yen-quoted instrument as though it were dollars — exactly
    the bug this module exists to end, reintroduced as a fallback."""
    src = FakeSource(_frame([], []))
    with pytest.raises(FxRateUnavailable) as exc:
        series_for(src, "USDJPY.p", 1440, "2020-01-01", "2026-09-16", invert=True)
    assert "1.0" in str(exc.value)


def test_series_for_asks_the_source_for_exactly_the_window_it_was_given():
    src = FakeSource(_frame(["2026-09-14", "2026-09-15"], [149.0, 150.0]))
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


# ── which symbols convert, and through what ──────────────────────────────────


@pytest.mark.parametrize(
    "symbol, quote",
    [
        ("GBPJPY.p", "JPY"),
        ("XAUUSD.p", "USD"),
        ("XAUUSD", "USD"),
        ("EURGBP", "GBP"),
        ("GBPJPYm", "JPY"),
        ("USDCAD.p", "CAD"),
    ],
)
def test_the_quote_currency_is_the_second_three_letters(symbol, quote):
    assert quote_currency(symbol) == quote


@pytest.mark.parametrize("symbol", ["US30", "USTEC", "MNQ 06-26", "GBPJPYX", "", "ABCXYZ"])
def test_a_name_that_is_not_a_readable_pair_REFUSES_rather_than_meaning_dollars(symbol):
    with pytest.raises(UnknownQuoteCurrency):
        quote_currency(symbol)


def test_the_conversion_pair_carries_the_traded_symbols_broker_suffix_and_direction():
    assert conversion_symbol("GBPJPY.p") == ("USDJPY.p", True)  # dollars per yen: invert
    assert conversion_symbol("EURGBP.p") == ("GBPUSD.p", False)  # dollars per pound: as quoted
    assert conversion_symbol("AUDCAD") == ("USDCAD", True)
    assert conversion_symbol("XAUUSD.p") is None  # already dollars


def test_a_dollar_quoted_run_gets_NO_provider_and_asks_the_feed_for_nothing():
    """None is what keeps every gold run byte-identical — nothing is installed."""
    src = FakeSource(_frame(["2026-09-14"], [149.0]))
    assert rate_provider_for(src, "XAUUSD.p", "2020-01-01", "2026-09-01") is None
    assert src.calls == []


def test_a_yen_run_converts_through_hourly_USDJPY_starting_BEFORE_the_run():
    """The pad is what gives the run's first bar a closed rate behind it."""
    src = FakeSource(_frame(["2019-12-30 00:00", "2019-12-30 01:00"], [108.0, 109.0]))
    fn = rate_provider_for(src, "GBPJPY.p", "2020-01-01", "2026-09-01")
    assert src.calls == [("USDJPY.p", 60, "2019-12-18", "2026-09-01")]
    assert fn(_ms("2020-01-01")) == pytest.approx(1.0 / 109.0)


def test_an_unreadable_symbol_refuses_at_the_run_rather_than_pricing_in_dollars():
    with pytest.raises(UnknownQuoteCurrency):
        rate_provider_for(FakeSource(None), "US30", "2020-01-01", "2026-09-01")


# ── the holder each strategy's execution layer carries ────────────────────────


def test_quote_conversion_with_nothing_installed_is_the_configured_constant():
    q = QuoteConversion(1.0)
    assert not q.installed
    assert q.at(123) == 1.0
    assert q.at(None) == 1.0  # a constant needs no moment


def test_quote_conversion_reads_an_installed_rate_at_the_moment_asked():
    q = QuoteConversion(0.0064)
    q.install(lambda t: 0.01 if t < 1_000 else 0.005)
    assert q.at(0) == 0.01
    assert q.at(1_000) == 0.005


def test_quote_conversion_REFUSES_a_non_positive_rate_rather_than_falling_back():
    """Falling back would present a snapshot as a measured rate; sizing divides by it."""
    q = QuoteConversion(0.0064)
    q.install(lambda t: 0.0)
    with pytest.raises(FxRateUnavailable):
        q.at(0)


def test_quote_conversion_REFUSES_a_figure_that_did_not_say_when_it_happened():
    q = QuoteConversion(0.0064)
    q.install(lambda t: 0.01)
    with pytest.raises(FxRateUnavailable):
        q.at(None)
