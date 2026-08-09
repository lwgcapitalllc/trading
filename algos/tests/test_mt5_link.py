"""Losing the terminal, and noticing.

**The incident these tests are written from, 2026-08-04.** MetaTrader auto-updated itself on the
VPS — `terminal64.exe` was rewritten at 02:57:53 and the replacement process started two seconds
later — and the live bot's IPC handle died with the old one. It then ran for 50 minutes across an
open session having seen no market at all, and **nothing in the system said so.** The heartbeat
kept stamping, so the watchdog saw a healthy bot; `wmic` still listed the process, so the Bots page
said RUNNING; the log recorded not one warning. The only visible symptom anywhere was a blank
balance on a page nobody had reason to distrust.

**The cause is that every failure on this path returns an ABSENCE rather than raising.**
`copy_rates_from_pos` returns None, so `BotMT5.get_candles` hands back an empty frame (documented:
*"Returns an empty DataFrame on failure, never None"*), which `BarFeed.new_bars` reads as *no bar
has closed yet* and `gap_bars` reads as *no gap*. `account_info` returns None, so the balance was
written as null. Each of those is a defensible local decision; together they make a dead terminal
indistinguishable from a quiet market.

So the tests below are mostly about that distinction, and about the three things that must survive
an outage: **the loop keeps stamping** (a blind bot is still alive, and a missing stamp would
report the wrong failure entirely), **the outage is announced once** rather than every ten seconds,
and **recovery RE-WARMS** — an outage is a hole in the bar stream, so resuming on the next bar
would leave the engines carrying a market history that never happened.
"""

import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import the way runner.py does — bare names off algos/live. Importing `live.runner` instead
# loads a second copy of the module under a different name, and monkeypatching one leaves the
# code under test reading the other (see test_runtime_reload.py's note).
_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import runner as runner_mod                                          # noqa: E402
from runner import LiveRunner                                        # noqa: E402


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))

    def kinds(self):
        return [k for k, _ in self.events]


class _Bridge:
    def __init__(self):
        self._ex = "OLD"
        self.began = 0
        self.state = SimpleNamespace(value="live")
        # The real bridge exposes this and the loop reads it every pass (the FLAT seam that the
        # runtime config reload and the equity re-anchor both hang off). A fake missing it makes
        # the loop raise, which reads as a link failure — the wrong diagnosis entirely.
        self.is_flat = True

    def begin_live(self):
        self.began += 1


class _Feed:
    """Behaves the way the real one does on a dead link: empty, never raising."""

    def __init__(self):
        self.last_bar_time = "2026-08-04 02:30:00+00:00"
        self.gap_calls = 0
        self.bar_calls = 0

    def gap_bars(self):
        self.gap_calls += 1
        return 0

    def new_bars(self):
        self.bar_calls += 1
        import pandas as pd
        return pd.DataFrame()


class _StateModule:
    def __init__(self):
        self.written = {}

    def write_bot(self, bot_key, updates):
        self.written.setdefault(bot_key, {}).update(updates)

    def set_started(self, bot_key):
        pass

    # The two the heartbeat needs to derive total_pnl_pct. A fake that is MISSING a method
    # the real module has fails loudly here (AttributeError) rather than quietly, which is
    # the behaviour to keep: `_heartbeat` deliberately does not hasattr-guard these, or a
    # renamed bot_state function would silently stop reporting P&L on the live box.
    def ensure_starting_balance(self, bot_key, balance):
        self.written.setdefault(bot_key, {}).setdefault("starting_balance", balance)

    def read_bot(self, bot_key):
        return dict(self.written.get(bot_key, {}))


def _runner(monkeypatch, *, account_info):
    """A LiveRunner with only the link path wired.

    `__new__` rather than `__init__`: a real one imports the strategy package and opens a log
    file, and none of this behaviour depends on either.
    """
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", display_name="Bot", account=1, symbol="XAUUSD.s",
                            timeframe="M15", poll_seconds=0, strategy_version="1.0.0",
                            strategy_package="demo_pkg", promoted_commit="abc1234",
                            promoted_at="2026-08-04", is_frozen=True,
                            # A real, empty directory: the loop checks it every pass for a
                            # stop request. A stand-in that does not exist would also work
                            # today and would stop testing the moment the check does anything
                            # more than `.exists()`.
                            instance_dir=Path(tempfile.mkdtemp()))
    r.dry_run = True
    r.source_hash = "0123456789abcdef"
    r.ledger = _Ledger()
    r.bridge = _Bridge()
    # `LiveRunner.__new__` skips __init__, so nothing sets this. The real runner always has it
    # by the time the loop turns; `reanchor_equity` reads it every flat pass.
    r.strategy = None
    r.feed = _Feed()
    r._link_lost_at = None
    r._link_retry_at = 0.0
    # Same reason as `strategy` above — `__new__` skips __init__, and the loop reads this on
    # every pass to decide whether the fleet switch has already fired. Leaving it out does not
    # fail politely: `_check_fleet_halt` raises AttributeError on its first line, the loop's
    # outer handler swallows it as a generic loop error, and the pass silently reads no bars
    # and stamps no heartbeat — which is how it was found.
    r._fleet_halted = False
    r.notes, r.warns, r.errors = [], [], []
    r.log = SimpleNamespace(info=lambda m, *a, **k: r.notes.append(m),
                            warning=lambda m, *a, **k: r.warns.append(m),
                            error=lambda m, *a, **k: r.errors.append(m))
    r.alerts = []
    r._notify_health = lambda m: r.alerts.append(m)

    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        SimpleNamespace(account_info=account_info))
    return r


def _live():
    return lambda: SimpleNamespace(balance=2000.0)


def _dead():
    return lambda: None


def _raises():
    def _f():
        raise RuntimeError("IPC recv failed")
    return _f


# ── the probe ───────────────────────────────────────────────────────────────────

def test_a_live_terminal_answers_with_its_balance(monkeypatch):
    r = _runner(monkeypatch, account_info=_live())
    assert r.probe_link() == (True, 2000.0)


def test_a_dead_terminal_is_reported_as_down_not_as_a_quiet_market(monkeypatch):
    """THE regression. `account_info()` returning None was previously read only as "no balance
    to write" — the loop went on asking the bars whether anything had happened, and an empty
    frame is what a quiet market looks like too."""
    r = _runner(monkeypatch, account_info=_dead())
    assert r.probe_link() == (False, None)


def test_a_probe_that_raises_is_a_dead_link_not_a_crash(monkeypatch):
    """Same answer, different route. The caller's move is identical either way — reconnect —
    so this is logged rather than raised, which also keeps it out of the consecutive-error
    counter that stops the bot at 10."""
    r = _runner(monkeypatch, account_info=_raises())
    assert r.probe_link() == (False, None)
    assert any("Balance read failed" in w for w in r.warns)


# ── what the state file says ────────────────────────────────────────────────────

def test_the_heartbeat_records_the_link_state(monkeypatch):
    """A null balance is not a diagnosis. `mt5_link` is what makes a blank cell on the Bots
    page attributable rather than ambiguous."""
    r = _runner(monkeypatch, account_info=_dead())
    st = _StateModule()
    r._heartbeat(st, link_up=False, balance=None)

    written = st.written["bot"]
    assert written["mt5_link"] is False
    assert written["balance"] is None
    assert abs(written["heartbeat"] - time.time()) < 5


def test_an_unstated_link_is_probed_not_assumed_down(monkeypatch):
    """`link_up=None` means UNSTATED. Recording a failure nobody measured is the same class of
    mistake as the blank balance itself — see `DrawdownMeter`'s refusal to draw an unmeasured
    tail as an absent one."""
    r = _runner(monkeypatch, account_info=_live())
    st = _StateModule()
    r._heartbeat(st)
    assert st.written["bot"]["mt5_link"] is True
    assert st.written["bot"]["balance"] == 2000.0


# ── the outage ──────────────────────────────────────────────────────────────────

def test_the_outage_is_announced_once_not_every_poll(monkeypatch):
    """At a 10s poll, alerting per pass is 6 messages a minute for as long as it lasts, which
    trains you to ignore the channel the arming decision depends on."""
    r = _runner(monkeypatch, account_info=_dead())
    monkeypatch.setattr(r, "connect", lambda: False)

    for _ in range(5):
        r._recover_link()

    assert len(r.alerts) == 1
    assert r.ledger.kinds().count("mt5_link_lost") == 1
    assert any("seeing no market" in a for a in r.alerts)


def test_reconnecting_is_not_hammered(monkeypatch):
    """`BotMT5.connect()` burns up to ~40s on its own five attempts. Firing it every poll
    while a terminal restarts just fills the log with one failure."""
    tries = []
    r = _runner(monkeypatch, account_info=_dead())
    monkeypatch.setattr(r, "connect", lambda: tries.append(1) or False)

    for _ in range(5):
        r._recover_link()

    assert len(tries) == 1, "retried inside the backoff window"


def test_a_failed_reconnect_leaves_the_outage_open(monkeypatch):
    r = _runner(monkeypatch, account_info=_dead())
    monkeypatch.setattr(r, "connect", lambda: False)
    r._recover_link()

    assert r._link_lost_at is not None
    assert r.bridge.began == 0, "began live on a link that never came back"
    assert "mt5_link_restored" not in r.ledger.kinds()


def test_recovery_re_warms_rather_than_resuming(monkeypatch):
    """The load-bearing one. However long the outage lasted, that many bars closed without
    reaching the engines — the same condition `gap_bars() > 4` exists for, arriving by another
    route. Resuming on the next bar leaves structure, fibs and liquidity carrying a market
    history that never happened, and a streaming state machine never recovers from that."""
    r = _runner(monkeypatch, account_info=_dead())
    warmed = []
    monkeypatch.setattr(r, "connect", lambda: True)
    monkeypatch.setattr(r, "_build_strategy",
                        lambda: (SimpleNamespace(execution="NEW"), None))
    monkeypatch.setattr(r, "warm", lambda: warmed.append(1))

    r._recover_link()

    assert warmed == [1], "reconnected without re-warming"
    assert r.bridge._ex == "NEW", "bridge still holding the pre-outage execution object"
    assert r.bridge.began == 1
    assert r._link_lost_at is None
    assert "mt5_link_restored" in r.ledger.kinds()
    assert any("reconnected" in a.lower() for a in r.alerts)


# ── the loop ────────────────────────────────────────────────────────────────────

def _run_one_pass(r, monkeypatch, state):
    """Turn `_loop` exactly once. `_stop_requested` is a module global the signal handler sets;
    flipping it from the probe is what makes a single pass observable."""
    monkeypatch.setitem(sys.modules, "bot_state", state)
    monkeypatch.setattr(runner_mod, "_stop_requested", False)

    real_probe = r.probe_link

    def _probe_then_stop():
        runner_mod._stop_requested = True
        return real_probe()

    monkeypatch.setattr(r, "probe_link", _probe_then_stop)
    try:
        r._loop()
    finally:
        monkeypatch.setattr(runner_mod, "_stop_requested", False)


def test_a_blind_loop_reads_no_bars(monkeypatch):
    """Reading them is not merely wasted: an empty frame from a dead terminal is what a quiet
    market returns, so every downstream check would confirm that all is well."""
    r = _runner(monkeypatch, account_info=_dead())
    monkeypatch.setattr(r, "connect", lambda: False)
    state = _StateModule()
    _run_one_pass(r, monkeypatch, state)

    assert r.feed.bar_calls == 0
    assert r.feed.gap_calls == 0


def test_a_blind_loop_still_stamps_its_heartbeat(monkeypatch):
    """A bot that cannot see is still ALIVE, and the watchdog's stall alert means something
    different from this. Dropping the stamp here would restart a process whose problem is not
    the process — and would hide, behind the wrong alert, the one fact that matters."""
    r = _runner(monkeypatch, account_info=_dead())
    monkeypatch.setattr(r, "connect", lambda: False)
    state = _StateModule()
    _run_one_pass(r, monkeypatch, state)

    written = state.written["bot"]
    assert abs(written["heartbeat"] - time.time()) < 5
    assert written["mt5_link"] is False


def test_a_healthy_loop_reads_bars_and_reports_the_link_up(monkeypatch):
    r = _runner(monkeypatch, account_info=_live())
    monkeypatch.setattr(r, "_maybe_reload_runtime", lambda: None)
    state = _StateModule()
    _run_one_pass(r, monkeypatch, state)

    assert r.feed.bar_calls == 1
    assert state.written["bot"]["mt5_link"] is True
    assert state.written["bot"]["balance"] == 2000.0
    # The only message is the loop's own stop notice — a healthy pass must raise no link alarm.
    assert not any("connection" in a.lower() for a in r.alerts)
    assert "mt5_link_lost" not in r.ledger.kinds()
