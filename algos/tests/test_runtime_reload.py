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

import live_config  # noqa: E402
from bridge import BridgeState, OrderBridge  # noqa: E402
from runner import LiveRunner  # noqa: E402


class _Bridge:
    def __init__(self, flat=True, state=None):
        self.is_flat = flat
        self._ex = None
        self.began = 0
        # A REAL `BridgeState`, not a stand-in with a `.value`. The reload path asks whether
        # this bot is halted before it claims the new settings are in force, and an identity
        # check (`is BridgeState.HALTED`) against a look-alike is False for every value —
        # so a fake that only quacked would pass the halted test while never entering the
        # branch. The halt latch is exactly the kind of thing that trap hides.
        self.state = state or BridgeState.LIVE
        self.halt_reason = "" if self.state is not BridgeState.HALTED else "test halt"

    def begin_live(self):
        self.began += 1
        # Mirrors the real one: the halt LATCHES, so a re-warm cannot put a halted bridge
        # back to live. Kept in step deliberately — a double that resumed here would let
        # the runner's own all-clear message go on being tested against a bot that is
        # halted in production and live in the test.
        if self.state is BridgeState.HALTED:
            return


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
        "bot_key": "bot",
        "display_name": "Bot",
        "mt5_path": r"C:\MT5\terminal64.exe",
        "account": 1,
        "server": "S",
        "symbol": "XAUUSD.s",
        "magic": 7,
        "timeframe": "M15",
        "strategy_package": "sos_fade",
        "strategy_class": "SosFadeStrategy",
        "strategy_source_hash": "abc123",
        "strategy_params": {"exec_risk_pct": 10.0, "aplus_window": 4320},
    }
    path = inst / "bot" / "config.json"
    path.write_text(json.dumps(base))

    r = LiveRunner.__new__(LiveRunner)
    r.cfg = live_config.load("bot")
    r.log = SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    r.ledger = _Ledger()
    r.bridge = _Bridge(flat=True)
    r.notes = []
    r._notify = lambda text, kind, reply_to=None: r.notes.append(text)
    r._notify_health = lambda text: r.notes.append(text)
    r._cfg_mtime = path.stat().st_mtime
    r._path = path
    r.warmed = 0

    # Applying a change REBUILDS the strategy and re-warms (the config is frozen — see
    # test_the_strategy_config_is_frozen_...). Both are stubbed: this file is about which
    # changes get applied and when, not about the strategy or the engines.
    def _build():
        s = SimpleNamespace(
            execution=SimpleNamespace(
                cfg=SimpleNamespace(exec_risk_pct=r.cfg.strategy_params["exec_risk_pct"])
            )
        )
        return s, s.execution.cfg

    def _warm():
        r.warmed += 1

    r._build_strategy = _build
    r.warm = _warm
    r.strategy, _ = _build()
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
    _bump(runner)  # touched but identical
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


# ── the contract with the real strategy ─────────────────────────────────────────
def test_the_real_execution_object_exposes_its_config():
    """Every test above uses a stand-in with a `.cfg`. The REAL `Execution` kept it private
    as `_cfg`, so the live reload crashed the loop on the VPS and the ledger's `risk_pct`
    silently recorded None — with a green suite the whole way.

    This is the one test that touches the actual strategy class, and it lives here rather
    than with the strategy because `algos/live/` is what depends on the attribute.
    """
    from strategies.python.sos_fade import LAB_STRATEGY

    ex = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"](), initial_capital=1000).execution
    assert hasattr(ex, "cfg"), "Execution.cfg is gone — the ledger cannot record risk_pct"
    assert ex.cfg.exec_risk_pct == LAB_STRATEGY["config"]().exec_risk_pct


def test_the_strategy_config_is_frozen_which_is_why_a_reload_rebuilds():
    """Pins the reason `_maybe_reload_runtime` rebuilds instead of assigning.

    If this ever starts passing as mutable, the rebuild is still correct — ONE config
    instance is shared by signals, sequence, execution and the secondary arm, so setting an
    attribute on one holder is not the same as changing the strategy's settings.
    """
    import dataclasses

    from strategies.python.sos_fade import LAB_STRATEGY

    cfg = LAB_STRATEGY["config"]()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.exec_risk_pct = 5.0


def test_one_config_object_is_shared_by_every_component():
    """The other half of the reason. Four holders, one object — a per-holder edit would let
    them disagree about what the strategy is set to."""
    from strategies.python.sos_fade import LAB_STRATEGY

    s = LAB_STRATEGY["strategy"](LAB_STRATEGY["config"](), initial_capital=1000)
    assert s.execution.cfg is s.config
    assert s.signals._cfg is s.config
    assert s.sequence._cfg is s.config


# ── robustness ──────────────────────────────────────────────────────────────────
def test_a_half_written_file_is_ignored_and_retried(runner):
    runner._path.write_text('{"bot_key": "bot", "strategy_par')  # truncated mid-write
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds() == []  # no refusal, no apply

    runner._path.write_text(
        json.dumps(
            {
                **json.loads(
                    json.dumps(
                        {
                            "bot_key": "bot",
                            "display_name": "Bot",
                            "mt5_path": r"C:\MT5\terminal64.exe",
                            "account": 1,
                            "server": "S",
                            "symbol": "XAUUSD.s",
                            "magic": 7,
                            "timeframe": "M15",
                            "strategy_package": "sos_fade",
                            "strategy_class": "SosFadeStrategy",
                            "strategy_source_hash": "abc123",
                            "strategy_params": {"exec_risk_pct": 5.0, "aplus_window": 4320},
                        }
                    )
                )
            }
        )
    )
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.strategy.execution.cfg.exec_risk_pct == 5.0


def test_a_missing_file_is_survived(runner):
    runner._path.unlink()
    runner._maybe_reload_runtime()  # must not raise
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0


def test_a_comment_only_edit_changes_nothing(runner):
    data = json.loads(runner._path.read_text())
    data["_note"] = "why the risk is what it is"
    runner._path.write_text(json.dumps(data))
    _bump(runner)
    runner._maybe_reload_runtime()
    assert runner.ledger.kinds() == []
    assert runner.strategy.execution.cfg.exec_risk_pct == 10.0


# ── the halt is not lifted by a settings change ──────────────────────────────────
# 🔴 The reload rebuilds the strategy and calls `begin_live`, which ASSIGNED the state — so an
# edit to this bot's own config file put a halted bot back to trading. Owned by
# `bridge.begin_live`; these pin that the reload path honours it and says so.
# ⚠ **The latch itself is pinned in `test_live_bridge.py`, not here.** A test at this level
# asserting the state stays halted would be VACUOUS — the double above latches too, so it would be
# the fixture enforcing the property rather than the code. Measured, not reasoned: written that
# way it passed against the bug. What this file can honestly pin is what the runner SAYS.
def test_the_settings_message_SAYS_the_new_values_cannot_reach_an_order(runner):
    """The values really are loaded, so the change is not refused — but a message reading
    "Applied straight away. Nothing to do." on a bot that will place nothing is the shape this
    repo has already measured to be worse than no message."""
    runner.bridge = _Bridge(flat=True, state=BridgeState.HALTED)
    _rewrite(runner, exec_risk_pct=5.0)

    runner._maybe_reload_runtime()

    said = " ".join(str(n) for n in runner.notes)
    assert "HALTED" in said
    assert "Nothing to do" not in said


def test_a_healthy_bot_still_gets_the_plain_applied_message(runner):
    """The control. A message that always warns is one nobody reads."""
    _rewrite(runner, exec_risk_pct=5.0)

    runner._maybe_reload_runtime()

    said = " ".join(str(n) for n in runner.notes)
    assert "Nothing to do" in said
    assert "HALTED" not in said
