"""Mt5Agent transient-drop retry.

A tick-mode backtest makes thousands of sequential calls over an SSH tunnel. One dropped
connection killed a 40-minute year-long run mid-flight; these lock the fix, and — just as
important — lock the line between "transient, ask again" and "the agent answered, stop asking".
Offline: urlopen is patched, no network.
"""

import io
import json
import urllib.error

import pytest

from backtest.data import mt5_agent
from backtest.data.mt5_agent import Mt5Agent, Mt5AgentError


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Retries back off with sleeps; tests must not actually wait them out."""
    monkeypatch.setattr(mt5_agent.time, "sleep", lambda _s: None)


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(monkeypatch, side_effects):
    """urlopen returns/raises the next side effect per call; records the call count."""
    calls = {"n": 0}

    def fake_urlopen(url, timeout=None):
        i = calls["n"]
        calls["n"] += 1
        effect = side_effects[min(i, len(side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return _Resp(effect)

    monkeypatch.setattr(mt5_agent.urllib.request, "urlopen", fake_urlopen)
    return calls


def test_a_dropped_connection_is_retried_and_succeeds(monkeypatch):
    """The exact failure that killed the year run: RemoteDisconnected on one call."""
    import http.client

    drop = urllib.error.URLError(http.client.RemoteDisconnected("closed"))
    calls = _patch(
        monkeypatch,
        [drop, drop, {"ticks": [{"time": "2026-01-01T00:00:00", "bid": 1.0, "ask": 1.1}]}],
    )
    ticks = Mt5Agent().ticks("XAUUSD.s", "2026-01-01T00:00:00", "2026-01-01T01:00:00")
    assert len(ticks) == 1
    assert calls["n"] == 3  # failed twice, third answered


def test_it_gives_up_after_the_retry_budget(monkeypatch):
    """Retrying forever would hang a run on a genuinely-down agent. It must eventually raise."""
    calls = _patch(monkeypatch, [urllib.error.URLError("down")])
    with pytest.raises(Mt5AgentError, match="after 4 attempts"):
        Mt5Agent().ticks("XAUUSD.s", "2026-01-01T00:00:00", "2026-01-01T01:00:00")
    assert calls["n"] == 4


def test_an_http_error_is_NOT_retried(monkeypatch):
    """A 4xx/5xx is the agent ANSWERING — asking a refused question again just gets refused.
    Retrying it would turn one honest error into four, and hide the real message behind a
    connection-shaped one."""
    err = urllib.error.HTTPError("u", 413, "Too many ticks", {}, io.BytesIO(b'{"error":"cap"}'))
    calls = _patch(monkeypatch, [err])
    with pytest.raises(Mt5AgentError, match="413"):
        Mt5Agent().ticks("XAUUSD.s", "2026-01-01T00:00:00", "2026-01-01T01:00:00")
    assert calls["n"] == 1  # asked exactly once


def test_bars_retry_too(monkeypatch):
    """A cold cache pulls a year of bars in one call — the same drop would lose it."""
    bar = {"time": "2026-01-01T00:00:00", "open": 1, "high": 2, "low": 0.5, "close": 1.5}
    calls = _patch(monkeypatch, [urllib.error.URLError("blip"), {"bars": [bar]}])
    df = Mt5Agent().bars("XAUUSD.s", "M15", "2026-01-01", "2026-01-02")
    assert len(df) == 1
    assert calls["n"] == 2


def test_a_truncated_body_is_retried(monkeypatch):
    """A half-delivered response is a transport failure wearing a JSON error's clothes."""
    calls = _patch(monkeypatch, [json.JSONDecodeError("cut", "", 0), {"ticks": []}])
    assert Mt5Agent().ticks("XAUUSD.s", "2026-01-01T00:00:00", "2026-01-01T01:00:00") == []
    assert calls["n"] == 2
