"""Constructing the runner, and the order it does things in.

**Why this file exists.** Every other test here exercises a PIECE — the bridge, the feed, the
ledger, the version pin — and each of those passed while `LiveRunner(cfg)` itself raised
`ModuleNotFoundError` on the very first line of `__init__`. The bot could not start on any
machine, and the suite was green. Found on the VPS on 2026-07-31, by running it.

So the point of these tests is unglamorous: build the object, and check the two things that
happen before a bot can report anything about itself. Startup order matters more than it looks —
a failure before the logger exists is a failure with no diagnosis, and a failure before
`verify_pin` is a bot that got further than it should have.

No MT5 here. Everything below stops short of `connect()`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "live"))
import live_config  # noqa: E402
import runner  # noqa: E402


def _cfg(tmp_path, monkeypatch, **overrides):
    body = {"bot_key": "smoke", "mt5_path": "C:/MT5/terminal64.exe", "account": 1,
            "server": "Demo", "symbol": "XAUUSD", "magic": 1}
    body.update(overrides)
    (tmp_path / "smoke").mkdir(parents=True, exist_ok=True)
    (tmp_path / "smoke" / "config.json").write_text(json.dumps(body))
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    return live_config.load("smoke")


def test_the_runner_can_be_constructed(tmp_path, monkeypatch):
    """The test that was missing. `__init__` builds a logger and a ledger — if either import
    path is wrong the bot dies before it can tell anyone why, which is exactly what happened."""
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    assert r.log is not None
    assert r.ledger is not None
    assert r.dry_run is True          # sending orders is never the default


def test_a_broken_logging_dependency_does_not_stop_the_bot(tmp_path, monkeypatch):
    """`bot_utils` is a convenience, not a requirement. If it cannot be imported the runner
    falls back to plain file+stdout logging rather than refusing to run — a logging dependency
    must never be the reason a bot is not trading."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _refuse(name, *a, **k):
        if name == "bot_utils":
            raise ImportError("simulated: not on the path")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", _refuse)
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    assert r.log is not None
    r.log.info("the fallback logger works")


def test_logs_land_in_the_bots_own_instance_dir(tmp_path, monkeypatch):
    """One bot, one directory. Two bots sharing a log file is how you lose the answer to
    "why did this trade not work"."""
    cfg = _cfg(tmp_path, monkeypatch)
    runner.LiveRunner(cfg)
    assert cfg.instance_dir.exists()
    assert cfg.instance_dir == tmp_path / "smoke"


def test_dry_run_is_the_default_and_live_must_be_asked_for(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    assert runner.LiveRunner(cfg).dry_run is True
    assert runner.LiveRunner(cfg, dry_run=False).dry_run is False


def test_the_version_pin_is_checked_before_anything_connects(tmp_path, monkeypatch):
    """`run()` must refuse on a bad pin WITHOUT touching MT5. If connect() ran first, a bot
    running unpromoted code would already be attached to a live account by the time anyone
    found out."""
    cfg = _cfg(tmp_path, monkeypatch, strategy_source_hash="deadbeef" * 4)
    r = runner.LiveRunner(cfg)

    def _boom():
        raise AssertionError("connect() must not be reached when the pin fails")

    monkeypatch.setattr(r, "connect", _boom)
    monkeypatch.setattr(r, "_notify", lambda text: None)
    assert r.run() == 2                      # 2 = version mismatch, a distinct exit code


def test_a_version_mismatch_is_recorded_and_announced(tmp_path, monkeypatch):
    """Refusing silently would look identical to a crash. It has to say which hash it wanted."""
    cfg = _cfg(tmp_path, monkeypatch, strategy_source_hash="deadbeef" * 4)
    r = runner.LiveRunner(cfg)
    sent = []
    monkeypatch.setattr(r, "connect", lambda: pytest.fail("unreachable"))
    monkeypatch.setattr(r, "_notify", sent.append)
    r.run()

    assert sent and "refused to start" in sent[0]
    rows = [json.loads(l) for f in (cfg.instance_dir / "ledger").glob("*.jsonl")
            for l in f.read_text().splitlines()]
    assert any(row.get("event") == "version_mismatch" for row in rows)
