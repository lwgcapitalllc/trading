"""
System health — the two indicators that were reporting the wrong thing, plus the
readiness report.

Both bugs here shared a shape: a field whose NAME described one thing while the
code measured another, with no way to tell from the screen. `ssh_tunnel` carried
a fresh SSH connection that has nothing to do with the port forwards, and the
MT5 dot carried the Flask agent's liveness rather than the terminal's.
"""

import pytest

from services import agent_supervisor as sup, readiness
from routers import system


@pytest.fixture(autouse=True)
def no_health_cache():
    """The router caches for 10s; a stale entry would make every test after the
    first assert on the previous one's answer."""
    system._health_cache = None
    system._health_cache_at = 0.0
    system._vps_ok = None
    system._vps_checked_at = 0.0
    yield
    system._health_cache = None
    system._vps_ok = None


def _stub(monkeypatch, *, tunnel, vps, nt8, mt5, terminal=None):
    monkeypatch.setattr(sup, "tunnel_up", lambda: tunnel)
    monkeypatch.setattr(sup, "vps_reachable", lambda: vps)
    monkeypatch.setattr(sup, "mt5_terminal_status", lambda: terminal)
    monkeypatch.setattr(
        "services.runner_dispatch.health",
        (lambda: {"status": "ok"}) if nt8 else _raiser)
    monkeypatch.setattr(
        "services.mt5_agent_client.health",
        (lambda: {"status": "ok"}) if mt5 else _raiser)
    monkeypatch.setattr("services.runner_dispatch.nt_health", _raiser)
    monkeypatch.setattr("services.runner_dispatch.nt_compile_status", _raiser)


def _raiser(*_a, **_k):
    raise RuntimeError("unreachable")


# ── ssh_tunnel means the TUNNEL now ───────────────────────────────────────────

def test_ssh_tunnel_reports_the_forwards_not_a_fresh_connection(monkeypatch):
    """The bug this fixes: the dot went green off `ssh forexvps echo ok`, which
    succeeds over a completely dead tunnel — so the one indicator that could
    have named the problem pointed at the VPS instead."""
    _stub(monkeypatch, tunnel=False, vps=True, nt8=False, mt5=False)
    h = system._build_health()
    assert h["ssh_tunnel"] is False      # the forwards are down…
    assert h["vps_reachable"] is True    # …and the VPS is fine. Two facts, two fields.


def test_a_healthy_tunnel_and_a_dead_vps_cannot_both_be_reported(monkeypatch):
    _stub(monkeypatch, tunnel=True, vps=False, nt8=True, mt5=True)
    h = system._build_health()
    assert h["ssh_tunnel"] is True
    assert h["vps_reachable"] is False


# ── MT5: the agent and the terminal are different questions ───────────────────

def test_a_responding_agent_with_a_disconnected_terminal(monkeypatch):
    """The gap: /health answers 'ok' whether or not MT5 is logged in, so a
    terminal that had dropped its broker connection showed green and every
    python run needing uncached bars failed at fetch time."""
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=True,
          terminal={"connected": False, "account": None, "server": None, "error": "IPC timeout"})
    h = system._build_health()
    assert h["mt5_agent"] is True
    assert h["mt5_connected"] is False


def test_a_connected_terminal_reports_which_account_it_is_bound_to(monkeypatch):
    """Worth surfacing: the agent binds MT5_Lab ONLY, and a run against the
    wrong account would produce a plausible result off the wrong feed."""
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=True,
          terminal={"connected": True, "account": 25893735,
                    "server": "VantageMarkets-Demo", "error": None})
    h = system._build_health()
    assert h["mt5_connected"] is True
    assert h["mt5_server"] == "VantageMarkets-Demo"
    assert h["mt5_account"] == 25893735


def test_terminal_fields_stay_None_when_the_agent_is_down(monkeypatch):
    """None is 'not asked', not 'disconnected'. A dot that renders an
    unanswered question as a failure is inventing a measurement."""
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=False)
    h = system._build_health()
    assert h["mt5_agent"] is False
    assert h["mt5_connected"] is None
    assert h["mt5_server"] is None


def test_the_terminal_is_not_probed_when_the_agent_is_down(monkeypatch):
    """No point spending an 8s timeout asking a process that isn't there."""
    calls = []
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=False)
    monkeypatch.setattr(sup, "mt5_terminal_status", lambda: calls.append(1))
    system._build_health()
    assert calls == []


# ── Readiness: the checks whose failure mode is silence ───────────────────────

def _fake_news(monkeypatch, events):
    """Stand in for the canonical engine's EventStore. `_news_calendar` imports
    it inside the function, so patching sys.modules is what reaches it."""
    class Store:
        def load(self):
            return events, []
    monkeypatch.setitem(__import__("sys").modules, "news",
                        type("m", (), {"EventStore": Store})())


def test_an_empty_news_cache_is_reported(monkeypatch):
    """An un-backfilled calendar makes the News & Holiday filter INERT — it tags
    nothing and removes nothing, which looks exactly like a broken filter."""
    _fake_news(monkeypatch, [])
    msg = readiness._news_calendar()
    assert msg and "EMPTY" in msg and "backfill" in msg.lower()


def test_a_stale_news_cache_is_reported_with_the_date_it_stops(monkeypatch):
    """Half-backfilled is the nastier case — the filter works on old trades and
    silently tags nothing on recent ones, so the delta looks like a real result."""
    import time as _t
    old_ms = int((_t.time() - 200 * 86400) * 1000)
    _fake_news(monkeypatch, [type("e", (), {"timestamp_ms": old_ms})()])
    msg = readiness._news_calendar()
    assert msg and "untagged, not unaffected" in msg


def test_a_current_news_cache_is_silent(monkeypatch):
    import time as _t
    _fake_news(monkeypatch, [type("e", (), {"timestamp_ms": int(_t.time() * 1000)})()])
    assert readiness._news_calendar() is None


def test_a_clean_machine_reports_nothing(monkeypatch):
    monkeypatch.setattr(readiness, "_news_calendar", lambda: None)
    monkeypatch.setattr(readiness, "_telegram", lambda: None)
    assert readiness.check() == []


def test_missing_telegram_credentials_are_reported(monkeypatch):
    """Silent by design — a notifier must never be able to stop a trading loop —
    so a stress-test grade can finish with nobody told."""
    monkeypatch.setattr("services.notify.telegram_configured", lambda: False)
    monkeypatch.setattr(readiness, "_news_calendar", lambda: None)
    warnings = readiness.check()
    assert len(warnings) == 1
    assert "Telegram not configured" in warnings[0]


def test_readiness_never_raises_on_an_unreadable_cache(monkeypatch):
    """It runs inside the startup hook. An exception here would stop the backend
    booting over a git-ignored cache file."""
    class Boom:
        def load(self):
            raise OSError("corrupt")
    monkeypatch.setitem(__import__("sys").modules, "news",
                        type("m", (), {"EventStore": Boom})())
    msg = readiness._news_calendar()
    assert msg and "unreadable" in msg
