"""Picking up a config change under a running bot.

The command center can rewrite `exec_risk_pct` in an instance config while the bot is
live. Three properties have to hold, and each one has a specific failure behind it:

  * only the reloadable field moves — a `git pull` carrying unrelated strategy edits must
    NOT be absorbed, because that is exactly what the source-hash pin exists to prevent;
  * it lands only while flat, so every trade is attributable to one configuration;
  * a change seen but not yet applied stays pending, instead of being noticed once and
    forgotten while the UI shows the new value.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import EXACTLY the way runner.py does — it puts algos/live on sys.path and imports
# `live_config` bare. Importing `live.live_config` instead loads a SECOND copy of the same
# file under a different module name, and monkeypatching one leaves the runner reading the
# other. That cost a debugging round the first time this file was written.
_REPO = Path(__file__).resolve().parent.parent.parent
for p in (str(_REPO), str(_REPO / "algos" / "live")):
    if p not in sys.path:
        sys.path.insert(0, p)

import live_config                                                  # noqa: E402
from bridge import OrderBridge                                      # noqa: E402
from runner import LiveRunner                                       # noqa: E402


class _Bridge:
    def __init__(self, flat=True):
        self.is_flat = flat


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))

    def kinds(self):
        return [k for k, _ in self.events]


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """A LiveRunner with just enough wired to exercise the reload path.

    Built with __new__ rather than __init__: constructing a real one imports the strategy
    package and opens a log file, none of which this behaviour depends on.
    """
    inst = tmp_path / "instances"
    monkeypatch.setattr(live_config, "_INSTANCES", inst)
    (inst / "bot").mkdir(parents=True)

    base = {
        "bot_key": "bot", "display_name": "Bot",
        "mt5_path": r"C:\MT5\terminal64.exe", "account": 1, "server": "S",
        "symbol": "XAUUSD.s", "magic": 7, "timeframe": "M15",
        "strategy_package": "mpc_sos_fade", "strategy_class": "MpcSosFadeStrategy",
        "strategy_source_hash": "abc123",
        "strategy_params": {"exec_risk_pct": 10.0, "aplus_window": 4320},
    }
    path = inst / "bot" / "config.json"
    path.write_text(json.dumps(base))

    r = LiveRunner.__new__(LiveRunner)
    r.cfg = live_config.load("bot")
    r.log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None,
                            error=lambda *a, **k: None)
    r.ledger = _Ledger()
    r.bridge = _Bridge(flat=True)
    r.strategy = SimpleNamespace(
        execution=SimpleNamespace(cfg=SimpleNamespace(exec_risk_pct=10.0)))
    r.notes = []
    r._notify = lambda text, reply_to=None: r.notes.append(text)
    r._cfg_mtime = path.stat().st_mtime
    r._path = path
    return r


def _rewrite(runner, **params):
    """Rewrite the instance config, guaranteeing a changed mtime."""
    data = json.loads(runner._path.read_text())
    data["strategy_params"].update(params)
    runner._path.write_text(json.dumps(data))
    _bump(runner)


def _bump(runner):
    st = runner._path.stat()
    import os
    os.utime(runner._path, (st.st_atime + 10, st.st_mtime + 10))


# ── the happy path ──────────────────────────────────────────────────────────────
def test_a_risk_change_is_applied_while_flat(runner):
    _rewrite(runner, exec_risk_pct=5.0)
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 5.0
    assert runner.cfg.strategy_params["exec_risk_pct"] == 5.0
    assert "config_applied" in runner.ledger.kinds()


def test_applying_it_announces_the_change(runner):
    _rewrite(runner, exec_risk_pct=5.0)
    runner._maybe_reload_runtime()
    assert any("10.0" in n and "5.0" in n for n in runner.notes)


def test_an_unchanged_file_is_not_reapplied(runner):
    _bump(runner)                       # touched but identical
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds() == []


# ── the guard that matters ──────────────────────────────────────────────────────
def test_a_strategy_param_change_is_refused_not_absorbed(runner):
    """This is the `git pull` case. Absorbing it would leave the bot trading code its
    source hash was never checked against."""
    _rewrite(runner, aplus_window=99)
    runner._maybe_reload_runtime()
    assert "config_change_refused" in runner.ledger.kinds()
    assert runner.cfg.strategy_params["aplus_window"] == 4320


def test_a_refused_change_blocks_the_legal_one_travelling_with_it(runner):
    """A risk change bundled with a strategy change is NOT half-applied. Half a config is
    a configuration nobody chose and nobody wrote down."""
    _rewrite(runner, exec_risk_pct=5.0, aplus_window=99)
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0
    assert "config_change_refused" in runner.ledger.kinds()


def test_an_identity_change_is_refused(runner):
    """A changed account or symbol is more dangerous than a changed fib level, because it
    reads as plumbing rather than strategy."""
    data = json.loads(runner._path.read_text())
    data["account"] = 999
    runner._path.write_text(json.dumps(data))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert "config_change_refused" in runner.ledger.kinds()
    assert runner.cfg.account == 1


def test_a_changed_version_pin_is_refused(runner):
    data = json.loads(runner._path.read_text())
    data["strategy_source_hash"] = "deadbeef"
    runner._path.write_text(json.dumps(data))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert "config_change_refused" in runner.ledger.kinds()


def test_a_removed_param_is_refused(runner):
    """A vanished key would silently fall back to the dataclass default — a setting nobody
    chose, arriving with no error."""
    data = json.loads(runner._path.read_text())
    del data["strategy_params"]["aplus_window"]
    runner._path.write_text(json.dumps(data))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert "config_change_refused" in runner.ledger.kinds()


def test_a_refusal_is_reported_once_not_every_poll(runner):
    _rewrite(runner, aplus_window=99)
    runner._maybe_reload_runtime()
    runner._maybe_reload_runtime()
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds().count("config_change_refused") == 1


# ── flat-only ───────────────────────────────────────────────────────────────────
def test_a_change_waits_while_a_position_is_open(runner):
    runner.bridge.is_flat = False
    _rewrite(runner, exec_risk_pct=5.0)
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0
    assert runner.ledger.kinds() == []


def test_a_waiting_change_lands_as_soon_as_the_bot_goes_flat(runner):
    """The mtime must NOT be consumed while pending, or the bot runs the old settings
    forever while the command center shows the new ones."""
    runner.bridge.is_flat = False
    _rewrite(runner, exec_risk_pct=5.0)
    for _ in range(5):
        runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0

    runner.bridge.is_flat = True
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 5.0


def test_a_resting_order_counts_as_not_flat(runner):
    """`is_flat` is position AND resting orders — a resting limit was sized and priced by
    the OLD settings, so filling it under the new ones would misattribute the trade."""
    b = OrderBridge.__new__(OrderBridge)
    b._pos_ticket = None
    b._rest = {1: None, -1: object()}
    assert not b.is_flat
    b._rest = {1: None, -1: None}
    assert b.is_flat
    b._pos_ticket = 5
    assert not b.is_flat


# ── robustness ──────────────────────────────────────────────────────────────────
def test_a_half_written_file_is_ignored_and_retried(runner):
    runner._path.write_text('{"bot_key": "bot", "strategy_par')     # truncated mid-write
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds() == []                              # no refusal, no apply

    runner._path.write_text(json.dumps({
        **json.loads(json.dumps({
            "bot_key": "bot", "display_name": "Bot",
            "mt5_path": r"C:\MT5\terminal64.exe", "account": 1, "server": "S",
            "symbol": "XAUUSD.s", "magic": 7, "timeframe": "M15",
            "strategy_package": "mpc_sos_fade",
            "strategy_class": "MpcSosFadeStrategy",
            "strategy_source_hash": "abc123",
            "strategy_params": {"exec_risk_pct": 5.0, "aplus_window": 4320},
        }))}))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 5.0


def test_a_missing_file_is_survived(runner):
    runner._path.unlink()
    runner._maybe_reload_runtime()                                  # must not raise
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0


def test_a_comment_only_edit_changes_nothing(runner):
    data = json.loads(runner._path.read_text())
    data["_note"] = "why the risk is what it is"
    runner._path.write_text(json.dumps(data))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds() == []
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0
