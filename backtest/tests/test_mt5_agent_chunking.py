"""Mt5Agent long-window chunking.

A single /historical_data call cannot exceed the terminal's "Max bars in chart" cap: past it MT5
fails the WHOLE call with (-2, 'Terminal: Invalid params'), which reaches us as a bare 404 "no
data". Measured on PU Prime 2026-07-21, XAUUSD.s M15: 64,837 bars fine, ~70,000 (3 years) dead —
so a 3-year backtest could not load its bars at all. These lock the split-and-stitch fix and the
line between "this chunk is past the start of history" (fine) and "nothing served any data" (an
error). Offline: urlopen is patched, no network.
"""

import json

import pytest

from backtest.data import mt5_agent
from backtest.data.mt5_agent import Mt5Agent, Mt5AgentError, _chunk_windows


# ── Window splitting ───────────────────────────────────────────────────────────

def test_a_short_window_is_still_one_request():
    """The common case must not change shape — one window in, one call out."""
    assert _chunk_windows("2025-07-21", "2026-07-21", "M15") == [("2025-07-21", "2026-07-21")]


def test_three_years_of_m15_is_split():
    windows = _chunk_windows("2023-07-22", "2026-07-22", "M15")
    assert len(windows) > 1
    assert windows[0][0] == "2023-07-22"
    assert windows[-1][1] == "2026-07-22"


def test_windows_are_contiguous_and_cover_the_span():
    """No gap and no overlap between chunks — a hole would silently lose bars."""
    import datetime as dt
    windows = _chunk_windows("2023-01-01", "2026-07-22", "M5")
    for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
        assert dt.date.fromisoformat(next_start) - dt.date.fromisoformat(prev_end) == dt.timedelta(days=1)


@pytest.mark.parametrize("tf,span_days", [("M1", 40), ("M5", 210), ("M15", 630), ("H1", 2600)])
def test_every_chunk_stays_under_the_bar_cap(tf, span_days):
    """Budget is computed against a 24h day, so a real 24/5 market lands further under still."""
    import datetime as dt
    end = dt.date(2026, 7, 22)
    start = end - dt.timedelta(days=span_days * 3)
    per_day = 1440 / mt5_agent.to_minutes(tf)
    for w_start, w_end in _chunk_windows(start.isoformat(), end.isoformat(), tf):
        days = (dt.date.fromisoformat(w_end) - dt.date.fromisoformat(w_start)).days + 1
        assert days * per_day <= mt5_agent._MAX_BARS_PER_REQUEST


# ── Fetch + stitch ─────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _bar(iso):
    return {"time": iso, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}


def _patch_windows(monkeypatch, by_window):
    """Serve a payload per (start_date, end_date) pair pulled off the request URL."""
    import urllib.parse

    def fake_urlopen(url, timeout=None):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        key = (q["start_date"][0], q["end_date"][0])
        return _Resp(by_window.get(key, {"bars": []}))

    monkeypatch.setattr(mt5_agent.urllib.request, "urlopen", fake_urlopen)


def test_chunks_are_stitched_into_one_frame(monkeypatch):
    windows = _chunk_windows("2023-07-22", "2026-07-22", "M15")
    assert len(windows) == 2
    _patch_windows(monkeypatch, {
        windows[0]: {"bars": [_bar("2024-01-01T00:00:00"), _bar("2024-01-01T00:15:00")]},
        windows[1]: {"bars": [_bar("2026-01-01T00:00:00")]},
    })
    df = Mt5Agent().bars("XAUUSD.s", "M15", "2023-07-22", "2026-07-22")
    assert len(df) == 3
    assert df.index.is_monotonic_increasing


def test_a_boundary_bar_served_twice_is_kept_once(monkeypatch):
    """Chunk bounds are inclusive on both ends, so neighbours can repeat a bar."""
    windows = _chunk_windows("2023-07-22", "2026-07-22", "M15")
    shared = _bar("2025-04-07T00:00:00")
    _patch_windows(monkeypatch, {
        windows[0]: {"bars": [_bar("2024-01-01T00:00:00"), shared]},
        windows[1]: {"bars": [shared, _bar("2026-01-01T00:00:00")]},
    })
    df = Mt5Agent().bars("XAUUSD.s", "M15", "2023-07-22", "2026-07-22")
    assert len(df) == 3
    assert not df.index.duplicated().any()


def test_an_empty_early_chunk_returns_the_history_that_exists(monkeypatch):
    """A 3-year request against a symbol whose history starts later must return those later
    years, not fail — the whole point of the fix."""
    windows = _chunk_windows("2023-07-22", "2026-07-22", "M15")
    _patch_windows(monkeypatch, {windows[-1]: {"bars": [_bar("2026-01-01T00:00:00")]}})
    df = Mt5Agent().bars("XAUUSD.s", "M15", "2023-07-22", "2026-07-22")
    assert len(df) == 1


def test_no_data_anywhere_is_still_an_error(monkeypatch):
    """Tolerating empty chunks must not swallow a genuinely dead symbol."""
    _patch_windows(monkeypatch, {})
    with pytest.raises(Mt5AgentError, match="no bars"):
        Mt5Agent().bars("NOSUCH.s", "M15", "2023-07-22", "2026-07-22")


def test_a_single_window_with_no_data_keeps_its_original_error(monkeypatch):
    """Short requests are unchanged: the agent's own message still surfaces."""
    _patch_windows(monkeypatch, {})
    with pytest.raises(Mt5AgentError, match=r"\[2026-01-01, 2026-01-02\]"):
        Mt5Agent().bars("XAUUSD.s", "M15", "2026-01-01", "2026-01-02")
