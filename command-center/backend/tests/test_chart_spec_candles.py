"""`_build_candles` — the DataFrame → chart-candle conversion.

Rewritten 2026-08-06 from `df.iterrows()` to column-at-a-time extraction. MEASURED on a real
155,715-bar XAUUSD M15 frame: **8.73s by iterrows against 0.13s here, 67x, byte-identical
output** — a cost paid on every chart-spec build and every paged window.

These tests exist for the one thing the rewrite could break silently: the TIMESTAMP. `iterrows`
handed each index value to `_ts_to_epoch_ms`, which treats a naive timestamp as UTC and converts
an aware one, and getting the aware case wrong shifts every bar by the zone's offset — a clean
frame, no error, and every session boundary on the chart in the wrong place.

⚠ **`test_a_tz_aware_index_is_converted_not_stripped` is a PIN, not a catch, and it is labelled
so because mutation testing proved it.** The rewrite originally carried an explicit
`tz_convert("UTC")` branch; deleting that branch left this test GREEN, because
`DatetimeIndex.astype("int64")` is already UTC epoch nanos for aware indexes — pandas stores
them as UTC internally and the zone is display only. So the branch was dead code and was
removed. The test stays: it pins the PROPERTY (naive and aware agree) rather than the branch,
and it would catch a future rewrite that read wall-clock digits instead.
"""

import pandas as pd
import pytest
from services import chart_spec


def _frame(index, n=3):
    return pd.DataFrame(
        {"open": [1.5] * n, "high": [2.5] * n, "low": [0.5] * n, "close": [2.0] * n},
        index=pd.DatetimeIndex(index, name="time"),
    )


def _rows(monkeypatch, df):
    monkeypatch.setattr(chart_spec.ohlc_fetcher, "get_ohlc", lambda *a, **k: df)
    return chart_spec._build_candles("XAUUSD", "2026-01-01", "2026-01-02", "M15", "python")


def test_a_naive_index_is_read_as_utc(monkeypatch):
    df = _frame(["2026-01-01 00:00", "2026-01-01 00:15", "2026-01-01 00:30"])
    got = _rows(monkeypatch, df)
    assert [c["time"] for c in got] == [1767225600000, 1767226500000, 1767227400000]
    assert got[0] == {"time": 1767225600000, "open": 1.5, "high": 2.5, "low": 0.5, "close": 2.0}


def test_a_tz_aware_index_is_converted_not_stripped(monkeypatch):
    # The bug the rewrite could have introduced: 05:00 in New York IS 10:00 UTC, and reading
    # the wall-clock digits would put every bar five hours early — a clean frame, no error,
    # and every session boundary on the chart in the wrong place.
    naive = _frame(["2026-01-01 10:00"], n=1)
    aware = _frame(["2026-01-01 10:00"], n=1).tz_localize("UTC").tz_convert("America/New_York")
    assert _rows(monkeypatch, aware) == _rows(monkeypatch, naive)


def test_rows_come_back_in_time_order_whatever_the_frame_did(monkeypatch):
    df = _frame(["2026-01-01 00:30", "2026-01-01 00:00", "2026-01-01 00:15"])
    times = [c["time"] for c in _rows(monkeypatch, df)]
    assert times == sorted(times)


def test_prices_are_floats_even_when_the_frame_stores_ints(monkeypatch):
    # JSON would serialise an int silently and the chart would still draw; this pins the
    # contract rather than the appearance.
    df = _frame(["2026-01-01 00:00"], n=1).astype(
        {"open": "int64", "high": "int64", "low": "int64", "close": "int64"}
    )
    c = _rows(monkeypatch, df)[0]
    assert all(isinstance(c[k], float) for k in ("open", "high", "low", "close"))


@pytest.mark.parametrize("df", [None, pd.DataFrame()])
def test_no_bars_degrades_to_an_empty_list(monkeypatch, df):
    assert _rows(monkeypatch, df) == []


def test_a_fetch_that_raises_degrades_to_an_empty_list(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("agent down")

    monkeypatch.setattr(chart_spec.ohlc_fetcher, "get_ohlc", boom)
    assert chart_spec._build_candles("XAUUSD", "2026-01-01", "2026-01-02", "M15", "python") == []
