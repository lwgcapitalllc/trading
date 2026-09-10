"""
System health — the two indicators that were reporting the wrong thing, plus the
readiness report.

Both bugs here shared a shape: a field whose NAME described one thing while the
code measured another, with no way to tell from the screen. `ssh_tunnel` carried
a fresh SSH connection that has nothing to do with the port forwards, and the
MT5 dot carried the Flask agent's liveness rather than the terminal's.
"""

import pytest
from routers import system
from services import agent_supervisor as sup
from services import readiness


@pytest.fixture(autouse=True)
def no_health_cache():
    """The router caches for 10s; a stale entry would make every test after the
    first assert on the previous one's answer."""
    system._health_cache = None
    system._health_cache_at = 0.0
    system._vps_ok = None
    system._vps_checked_at = 0.0
    system._agent_last_ok.clear()
    yield
    system._health_cache = None
    system._vps_ok = None
    system._agent_last_ok.clear()


def _stub(monkeypatch, *, tunnel, vps, nt8, mt5, terminal=None):
    monkeypatch.setattr(sup, "tunnel_up", lambda: tunnel)
    monkeypatch.setattr(sup, "vps_reachable", lambda: vps)
    monkeypatch.setattr(sup, "mt5_terminal_status", lambda: terminal)
    monkeypatch.setattr(
        "services.runner_dispatch.health", (lambda: {"status": "ok"}) if nt8 else _raiser
    )
    monkeypatch.setattr(
        "services.mt5_agent_client.health", (lambda: {"status": "ok"}) if mt5 else _raiser
    )
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
    assert h["ssh_tunnel"] is False  # the forwards are down…
    assert h["vps_reachable"] is True  # …and the VPS is fine. Two facts, two fields.


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
    _stub(
        monkeypatch,
        tunnel=True,
        vps=True,
        nt8=True,
        mt5=True,
        terminal={"connected": False, "account": None, "server": None, "error": "IPC timeout"},
    )
    h = system._build_health()
    assert h["mt5_agent"] is True
    assert h["mt5_connected"] is False


def test_a_connected_terminal_reports_which_account_it_is_bound_to(monkeypatch):
    """Worth surfacing: the agent binds MT5_Lab ONLY, and a run against the
    wrong account would produce a plausible result off the wrong feed."""
    _stub(
        monkeypatch,
        tunnel=True,
        vps=True,
        nt8=True,
        mt5=True,
        terminal={
            "connected": True,
            "account": 25893735,
            "server": "VantageMarkets-Demo",
            "error": None,
        },
    )
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

    monkeypatch.setitem(__import__("sys").modules, "news", type("m", (), {"EventStore": Store})())


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
    so a bot can be stopped or deployed with nobody told."""
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

    monkeypatch.setitem(__import__("sys").modules, "news", type("m", (), {"EventStore": Boom})())
    msg = readiness._news_calendar()
    assert msg and "unreadable" in msg


# ── A SLOW agent is not a DEAD agent ──────────────────────────────────────────
#
# 🔴 The sidebar showed the MT5 agent "down" while it was answering fine, and a red agent dot is a
# BUTTON: "click to start" restarts the SSH tunnel and cuts every request in flight. MEASURED
# 2026-09-10: the agent answered 22/22 with nothing else running and missed replies whenever the
# box was busy — its terminal link never dropped. A timeout is what a busy healthy agent returns
# too (rule 2), so it may not be read as dead on its own.

import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402


def _timeout_error():
    """The exact shape the agent clients raise on a timeout: a RuntimeError FROM the socket's."""
    try:
        raise socket.timeout("timed out")
    except socket.timeout as inner:
        try:
            raise RuntimeError("MT5 agent /health: timed out") from inner
        except RuntimeError as outer:
            return outer


def _slow():
    raise _timeout_error()


def _refused():
    try:
        raise ConnectionRefusedError(61, "Connection refused")
    except ConnectionRefusedError as inner:
        raise RuntimeError("MT5 agent /health: refused") from inner


def test_a_timeout_just_after_an_ok_answer_is_SLOW_not_down():
    """Watched red against the old rule, which set the dot red on any exception at all."""
    t0 = 1_000_000.0
    assert system._agent_state("mt5", lambda: {"status": "ok"}, now=t0)[0] == "ok"
    state, age = system._agent_state("mt5", _slow, now=t0 + 20)
    assert state == "slow"
    assert age == 20


def test_a_timeout_past_the_grace_window_is_DOWN():
    """A HUNG agent must still go red — grace delays the verdict, it does not cancel it."""
    t0 = 1_000_000.0
    system._agent_state("mt5", lambda: {"status": "ok"}, now=t0)
    state, _ = system._agent_state("mt5", _slow, now=t0 + system._AGENT_GRACE_S + 1)
    assert state == "down"


def test_a_timeout_with_no_earlier_ok_answer_is_DOWN():
    """No recent answer, no benefit of the doubt — a backend started against a dead agent says so."""
    assert system._agent_state("mt5", _slow, now=1_000_000.0)[0] == "down"


def test_a_REFUSED_call_is_down_at_once_even_straight_after_an_ok():
    """Only a dead or broken agent refuses, so a refusal needs no grace.

    Watched red by giving every exception the grace window: this then reads "slow", which would
    hide a crashed agent for 90 seconds behind a yellow dot.
    """
    t0 = 1_000_000.0
    system._agent_state("mt5", lambda: {"status": "ok"}, now=t0)
    assert system._agent_state("mt5", _refused, now=t0 + 5)[0] == "down"


def test_an_agent_that_ANSWERS_not_ok_is_down_with_no_grace():
    """It answered. That is a measurement, not a gap."""
    t0 = 1_000_000.0
    system._agent_state("mt5", lambda: {"status": "ok"}, now=t0)
    assert system._agent_state("mt5", lambda: {"status": "error"}, now=t0 + 5)[0] == "down"


def test_the_two_agents_keep_separate_memories():
    """An NT8 answer must not buy the MT5 agent any grace."""
    t0 = 1_000_000.0
    system._agent_state("nt8", lambda: {"status": "ok"}, now=t0)
    assert system._agent_state("mt5", _slow, now=t0 + 5)[0] == "down"


def _real_agent_get():
    """The agent client's REAL `_get`, in a private copy of its module, for a LOCAL socket only.

    ⚠ **This is not a way round `_no_live_vps`, and it must never be pointed at the VPS.** That
    interlock swaps `mt5_agent_client._get` for a refusal for the whole test run, which is right —
    and it cannot tell that these two tests aim the client at 127.0.0.1. Loading the file a second
    time gives the genuine wrapping code and the genuine urllib exception chain while the shared
    module the app uses stays interlocked. The tunnel URL is set on the private copy's own `cfg`
    reference by the caller, to a port on this machine.
    """
    import importlib.util
    import pathlib as _pl

    src = _pl.Path(__file__).resolve().parents[1] / "services" / "mt5_agent_client.py"
    spec = importlib.util.spec_from_file_location("_mt5_agent_client_private", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SilentServer:
    """Accepts a connection and never answers — exactly what a BUSY agent looks like on the wire."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.conns = []
        self._stop = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                self.conns.append(self.sock.accept()[0])
            except OSError:
                pass

    def close(self):
        self._stop = True
        for c in self.conns:
            c.close()
        self.sock.close()


def test_a_REAL_timeout_through_the_real_client_is_recognised_as_one(monkeypatch):
    """🔴 Rule 13: a hand-built exception proves only that the test's GUESS of the shape is handled.

    This drives the actual agent client at a real socket that accepts and never replies, so the
    exception chain is whatever urllib genuinely raises on this Python. Watched red by removing the
    `socket.timeout` branch from `_is_timeout` — on Python 3.9 it is not a `TimeoutError`.
    """
    srv = _SilentServer()
    client = _real_agent_get()
    try:
        monkeypatch.setattr(client.cfg, "MT5_AGENT_TUNNEL", f"http://127.0.0.1:{srv.port}")
        start = time.time()
        try:
            client._get("/health", timeout=0.3)
        except RuntimeError as exc:
            assert system._is_timeout(exc), f"not recognised as a timeout: {exc!r}"
        else:
            raise AssertionError("a server that never answers must not produce an answer")
        assert time.time() - start < 5
    finally:
        srv.close()


def test_a_REAL_refused_port_through_the_real_client_is_NOT_a_timeout(monkeypatch):
    """The other half, also real: nothing listening. It must read as refused, never as slow."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens on it now
    client = _real_agent_get()
    monkeypatch.setattr(client.cfg, "MT5_AGENT_TUNNEL", f"http://127.0.0.1:{port}")
    try:
        client._get("/health", timeout=0.3)
    except RuntimeError as exc:
        assert not system._is_timeout(exc), f"a refusal was read as a timeout: {exc!r}"
    else:
        raise AssertionError("a closed port must not produce an answer")


def test_health_serves_the_state_and_a_slow_agent_is_not_probed_for_its_terminal(monkeypatch):
    """The state must survive the RESPONSE MODEL — an undeclared field is dropped without a word."""
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=True, terminal=None)
    system._build_health()  # an ok answer to extend grace from
    monkeypatch.setattr("services.mt5_agent_client.health", _slow)
    asked = []
    monkeypatch.setattr(sup, "mt5_terminal_status", lambda: asked.append(1))
    system._health_cache = None
    body = system.system_health().model_dump()
    assert body["mt5_agent"] is False
    assert body["mt5_agent_state"] == "slow"
    assert body["mt5_agent_last_ok_s"] is not None
    assert body["nt8_agent_state"] == "ok"
    assert body["mt5_connected"] is None, "unknown, not disconnected"
    assert asked == [], "the terminal is not asked through an agent that did not answer"


def test_through_health_an_nt8_answer_buys_the_mt5_agent_NO_grace(monkeypatch):
    """The wiring half of "separate memories", which a mutation survived until this existed.

    `test_the_two_agents_keep_separate_memories` pins the helper; it cannot see `_build_health`
    handing the SAME name to both agents — and then a healthy NT8 agent would keep a dead MT5 one
    looking "slow" for ever. Watched red by passing "mt5" as the NT8 agent's name.
    """
    _stub(monkeypatch, tunnel=True, vps=True, nt8=True, mt5=True)
    monkeypatch.setattr("services.mt5_agent_client.health", _slow)  # has never answered ok
    h = system._build_health()
    assert h["nt8_agent_state"] == "ok"
    assert h["mt5_agent_state"] == "down"
