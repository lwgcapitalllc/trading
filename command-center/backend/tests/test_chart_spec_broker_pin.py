"""The price chart reads the run's OWN broker's bars, never the attached terminal's.

🔴 **Reported from the screen 2026-08-25.** A charged re-run of a run made on one broker completed
with 247 trades and drew an EMPTY price chart. The replay had been pinned to the run's broker when
the bar cache became broker-partitioned; the CHART FEED had not, so it resolved whatever terminal
was attached that day — a different broker, which does not quote that run's symbol at all.

⚠ **The failure shape is the dangerous one.** The trades, the equity curve and every KPI rendered
normally. The only symptom was a blank chart with no reason attached, and nothing on the page could
tell "this broker has no bars there" from "we asked the wrong broker".

⚠ **These pin the ARGUMENT, not the bars.** `get_ohlc` is stubbed and the call is inspected, because
the defect was never in the fetch — it was in what the fetch was asked for. A test that asserted
"some candles came back" would pass against the bug on any machine whose attached terminal happened
to be the right one.

WATCHED RED by mutation: dropping the `server` argument from either `_build_candles` or
`_fetch_candles` turns the pinned cases red and leaves the unpinned one green.
"""

import pandas as pd
import pytest
from services import chart_spec


@pytest.fixture
def seen(monkeypatch):
    """Capture what the chart feed asks the bar source for."""
    calls = []

    def fake_get_ohlc(instrument, start, end, timeframe="daily", runner="ninjatrader", server=None):
        calls.append({"instrument": instrument, "runner": runner, "server": server})
        return pd.DataFrame(
            {"open": [1.5], "high": [2.5], "low": [0.5], "close": [2.0]},
            index=pd.DatetimeIndex(["2026-01-01 00:00"], name="time"),
        )

    monkeypatch.setattr(chart_spec.ohlc_fetcher, "get_ohlc", fake_get_ohlc)
    return calls


def test_the_runs_broker_reaches_the_bar_source(seen):
    chart_spec._build_candles(
        "XAUUSD", "2026-01-01", "2026-01-02", "M15", "python", "VantageMarkets-Demo"
    )
    assert seen[0]["server"] == "VantageMarkets-Demo"


def test_a_run_with_no_broker_profile_pins_nothing(seen):
    # None is not a broker: it means "use whatever is attached", which is what every row predating
    # broker profiles wants. It must never become an empty string — that would name a broker.
    chart_spec._build_candles("XAUUSD", "2026-01-01", "2026-01-02", "M15", "python")
    assert seen[0]["server"] is None


def test_the_drill_down_path_is_pinned_too(seen):
    chart_spec._fetch_candles(
        "XAUUSD", "2026-01-01", "2026-01-02", "M1", "python", "VantageMarkets-Demo"
    )
    assert seen[0]["server"] == "VantageMarkets-Demo"


def test_a_profile_resolves_to_its_server():
    # The lookup is the shared one the REPLAY uses. Two copies of it is how the chart and the
    # replay would drift back apart into disagreeing about which broker a run belongs to.
    assert chart_spec._bar_server({"broker_profile": "vantage_demo"}) == "VantageMarkets-Demo"
    assert chart_spec._bar_server({"broker_profile": "puprime_ecn"}) == "PUPrime-Demo"


def test_an_unknown_or_absent_profile_pins_nothing():
    assert chart_spec._bar_server({}) is None
    assert chart_spec._bar_server({"broker_profile": "not_a_broker"}) is None
