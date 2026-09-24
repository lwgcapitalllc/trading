"""Setup messages are for EVERY bot — and a bot whose strategy cannot give them SAYS SO in Telegram.

Aaron, 2026-09-16: any bot added must have setup messages on by default, and messaging must not be
SOS-Fade-specific. The live extreme-leg bot logged "Setup alerts: OFF" for days because its
strategy never implemented the contract, and the only trace was a log line.

**Watched RED at HEAD:** `ExtremeLegExecution` had no `live_setups`, so the contract test failed;
the unsupported branch sent nothing, so the health test failed with an empty outbox.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (
    _ROOT,
    _ROOT / "strategies" / "python",
    _ROOT / "algos" / "live",
    _ROOT / "algos" / "shared",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import runner as live_runner  # noqa: E402

from backtest.setups import implements_contract  # noqa: E402


class _Log:
    def __init__(self):
        self.lines = []

    def info(self, m, *a, **k):
        self.lines.append(("info", m))

    def warning(self, m, *a, **k):
        self.lines.append(("warning", m))


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, name, **kw):
        self.events.append((name, kw))


class _Bridge:
    # Both are real `OrderBridge` methods; the start only passes them through.
    def resting_lots(self, side):
        return None

    def resting_order(self, side):
        return None


class _Cfg:
    setup_alert_categories = None  # ABSENT in the bot's config — the default
    digits = 2

    def __init__(self, cls_name, tmp):
        self.strategy_class = cls_name
        self.instance_dir = Path(tmp)


def _runner(strategy, tmp):
    class R(live_runner.LiveRunner):
        _label = "Test Bot (demo)"

        def _signal_room(self):
            return "the shared signals channel"

    r = R.__new__(R)
    r.cfg = _Cfg(type(strategy).__name__, tmp)
    r.log = _Log()
    r.ledger = _Ledger()
    r.bridge = _Bridge()
    r.strategy = strategy
    r.setup_alerts = None
    r.health = []
    r._notify_health = lambda text, **k: r.health.append(text)
    r._notify = lambda *a, **k: None
    return r


class _NoContract:
    class execution:  # noqa: N801 — shaped like a strategy's execution attribute
        pass


def test_a_bot_whose_strategy_cannot_report_setups_SAYS_SO_in_the_health_room(tmp_path):
    """MUTATION: delete the `_notify_health` call in the unsupported branch and this reddens."""
    r = _runner(_NoContract(), tmp_path)
    r._start_setup_alerts()
    assert r.setup_alerts is None
    assert len(r.health) == 1
    assert "no setup messages" in r.health[0] and "Test Bot" in r.health[0]


def test_the_extreme_leg_bot_gets_setup_messages_ON_by_default(tmp_path):
    """The live `extreme_leg_demo` case. No category list in its config means all four.

    MUTATION: remove `live_setups` from `ExtremeLegExecution` and this reddens.
    """
    from extreme_leg import ExtremeLegStrategy

    s = ExtremeLegStrategy()
    assert implements_contract(s.execution)
    r = _runner(s, tmp_path)
    r._start_setup_alerts()
    assert r.setup_alerts is not None
    assert r.health == []
    assert any("Setup alerts: ON" in m for _, m in r.log.lines)
    # The key scheme reaches the alert layer, so a later key change is detected across a promote.
    assert r.setup_alerts._key_scheme == "xleg-time-v1"


def test_every_bot_with_an_ACCOUNT_reports_its_setups():
    """🔴 **The standing rule, enforced where a new bot is REGISTERED rather than where it is found
    silent (2026-09-24).** FFT and realign both reached the demo account without setup messages and
    the only sign was a health-room line after the deploy. A bot folder with an account assigned is
    a bot that will run, so its strategy must answer the setup contract — built exactly as the
    runner builds it, from the folder's own settings. A benched bot (no account) is exempt until it
    is assigned.

    ⚠ Read from the folders, never a hand list, so a bot added next year is covered with no edit.
    Watched RED 2026-09-24 with FFT's `live_setups` removed; realign was red before its own
    `setups.py` existed."""
    import importlib
    import json

    folders = sorted((_ROOT / "algos" / "markets" / "fx" / "instances").glob("*/config.json"))
    checked, silent = [], []
    for path in folders:
        cfg = json.loads(path.read_text())
        if cfg.get("account") is None:
            continue
        lab = importlib.import_module(cfg["strategy_package"]).LAB_STRATEGY
        params = dict(cfg["strategy_params"])
        params.setdefault("symbol", cfg["symbol"])
        strategy = lab["strategy"](lab["config"](**params), initial_capital=10_000.0)
        checked.append(cfg["bot_key"])
        if not implements_contract(getattr(strategy, "execution", strategy)):
            silent.append(f"{cfg['bot_key']} ({cfg['strategy_class']})")
    assert checked, "no bot folder has an account — this test would pass on an empty registry"
    assert not silent, (
        "these bots have an account but their strategy cannot report setups, so the signals room "
        "would stay silent for them: "
        + ", ".join(silent)
        + ". Give the strategy a setups.py (see strategies/python/fft/setups.py) before assigning it."
    )
