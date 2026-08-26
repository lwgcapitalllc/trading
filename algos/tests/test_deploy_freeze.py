"""A deployed bot runs the code you deployed, and nothing else can move it.

**The failure this exists to prevent, measured.** Until 2026-08-03 a bot imported its strategy
straight out of `strategies/python/<pkg>` in the repo working tree. The repo and the deployment
were the same files. So a `git pull` on the VPS — for a lab fix, an agent update, anything —
rewrote the code under a running bot, the version pin then refused to restart it, and nothing
restarted it anyway. The live bot sat dead for three days. Aaron's rule, and it is the right
one: *a bot runs what you last deployed until you deploy something else.*

The headline test is `test_editing_the_repo_does_not_move_a_deployed_bot`. Everything else here
exists to stop that property being true by accident — a snapshot that silently falls back to the
repo, a pin that does not cover the engines, a failed promote that takes out a working
deployment.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO / "algos" / "live"), str(_REPO / "algos" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config  # noqa: E402
import promote as promote_tool  # noqa: E402
import version as live_version  # noqa: E402


def _repo_like(root: Path) -> None:
    """A miniature of the three trees a promote copies, importable and buildable."""
    pkg = root / "strategies" / "python" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "from .strategy import DemoStrategy, DemoConfig\n"
        "LAB_STRATEGY = {'strategy': DemoStrategy, 'config': DemoConfig}\n"
    )
    (pkg / "strategy.py").write_text(
        "from dataclasses import dataclass\n"
        "import engines.structure as _s\n"
        "import backtest.replay as _r\n"
        "@dataclass\n"
        "class DemoConfig:\n"
        "    symbol: str = 'XAUUSD'\n"
        "    exec_risk_pct: float = 10.0\n"
        "class DemoStrategy:\n"
        "    def __init__(self, cfg, initial_capital=0.0):\n"
        "        self.cfg = cfg\n"
    )
    for tree, body in (("engines", "SWING = 15\n"), ("backtest", "MODE = 'bar'\n")):
        d = root / tree
        d.mkdir(parents=True)
        (d / "__init__.py").write_text("")
    (root / "engines" / "structure.py").write_text("SWING = 15\n")
    (root / "backtest" / "replay.py").write_text("MODE = 'bar'\n")


@pytest.fixture
def bot(tmp_path, monkeypatch):
    """A bot whose repo, instances dir and config are all disposable."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_like(repo)

    instances = tmp_path / "instances"
    (instances / "demo_bot").mkdir(parents=True)
    (instances / "demo_bot" / "config.json").write_text(
        json.dumps(
            {
                "bot_key": "demo_bot",
                "display_name": "Demo",
                "mt5_path": "C:/x/terminal64.exe",
                "account": 1,
                "server": "S",
                "symbol": "XAUUSD",
                "magic": 1,
                "strategy_package": "demo_pkg",
                "strategy_class": "DemoStrategy",
                "strategy_params": {"exec_risk_pct": 10.0},
            }
        )
    )

    monkeypatch.setattr(live_config, "_REPO_ROOT", repo)
    monkeypatch.setattr(live_config, "_INSTANCES", instances)
    monkeypatch.setattr(promote_tool, "_REPO", repo)
    return live_config.load("demo_bot")


def _promote(bot, **kw) -> int:
    trees = promote_tool.repo_trees(bot)
    staging, n = promote_tool.stage(bot, trees)
    ok, detail = promote_tool.verify(bot, staging)
    if not ok:
        return 1
    promote_tool.activate(bot, staging)
    promote_tool.write_pin(
        bot, live_version.deployment_hash(bot.source_roots), "abc1234", "2026-08-03", n
    )
    return 0


# ── the headline ────────────────────────────────────────────────────────────────
def test_editing_the_repo_does_not_move_a_deployed_bot(bot):
    """Backtest a new version, refactor an engine, pull whatever you like — the deployment does
    not notice. This is the whole feature."""
    assert _promote(bot) == 0
    fresh = live_config.load("demo_bot")
    before = live_version.deployment_hash(fresh.source_roots)

    (bot.repo_root / "strategies" / "python" / "demo_pkg" / "strategy.py").write_text("BROKEN(")
    (bot.repo_root / "engines" / "structure.py").write_text("SWING = 9\n")

    assert live_version.deployment_hash(fresh.source_roots) == before
    assert live_version.verify_pin(fresh.source_roots, fresh.strategy_source_hash) == before


def test_a_deployed_bot_imports_from_its_own_copy_not_the_repo(bot):
    assert _promote(bot) == 0
    fresh = live_config.load("demo_bot")
    assert fresh.is_frozen
    assert fresh.deployed_dir in fresh.strategy_dir.parents
    assert fresh.repo_root not in fresh.strategy_dir.parents
    for root in fresh.source_roots:
        assert fresh.deployed_dir in root.parents or root == fresh.deployed_dir


def test_an_unpromoted_bot_falls_back_to_the_repo_and_says_so(bot):
    """Deliberate: a bot has to run unfrozen once to become promotable, so refusing outright
    would make the first promotion impossible. It must be VISIBLE, not silent — the runner logs
    NOT FROZEN and verify_pin's message names the remedy."""
    assert not bot.is_frozen
    assert bot.strategy_dir == bot.repo_root / "strategies" / "python" / "demo_pkg"


# ── what the pin covers ─────────────────────────────────────────────────────────
def test_the_snapshot_pin_covers_the_engines(bot):
    """Editing the snapshot's ENGINE — not its strategy — must still trip the pin. The old pin
    hashed the strategy package only, so this exact edit was invisible to it."""
    assert _promote(bot) == 0
    fresh = live_config.load("demo_bot")
    (fresh.deployed_dir / "engines" / "structure.py").write_text("SWING = 9\n")
    with pytest.raises(live_version.VersionMismatch):
        live_version.verify_pin(fresh.source_roots, fresh.strategy_source_hash, frozen=True)


# ── promoting is the only thing that changes a deployment ───────────────────────
def test_a_failed_promote_leaves_the_running_deployment_untouched(bot):
    """A promote can fail — that is what verify is for. It must not take out a working bot in
    order to report that the new version is broken."""
    assert _promote(bot) == 0
    fresh = live_config.load("demo_bot")
    good_hash = live_version.deployment_hash(fresh.source_roots)

    (bot.repo_root / "strategies" / "python" / "demo_pkg" / "strategy.py").write_text(
        "import nonexistent_module_xyz\n"
    )
    trees = promote_tool.repo_trees(bot)
    staging, _ = promote_tool.stage(bot, trees)
    ok, _ = promote_tool.verify(bot, staging)

    assert ok is False
    assert live_version.deployment_hash(fresh.source_roots) == good_hash


def test_a_param_the_new_version_dropped_is_refused(bot):
    """Caught at promote time, not at the next restart. `exec_fvg_50` was removed from the
    strategy on 2026-08-02 and left sitting in the live instance config — this is the real case,
    and without the check it surfaces as a bot that will not start, days later."""
    cfg_path = live_config.config_path("demo_bot")
    raw = json.loads(cfg_path.read_text())
    raw["strategy_params"]["exec_fvg_50"] = False
    cfg_path.write_text(json.dumps(raw))
    fresh = live_config.load("demo_bot")

    staging, _ = promote_tool.stage(fresh, promote_tool.repo_trees(fresh))
    ok, detail = promote_tool.verify(fresh, staging)
    assert ok is False
    assert "exec_fvg_50" in detail


def test_settings_the_deployment_does_not_state_are_reported(bot):
    """A new version's new settings take its DEFAULTS. That is the quiet way behaviour changes
    between versions, so promote names them while there is still a decision to make."""
    assert _promote(bot) == 0
    pkg = bot.repo_root / "strategies" / "python" / "demo_pkg" / "strategy.py"
    pkg.write_text(
        pkg.read_text().replace(
            "    exec_risk_pct: float = 10.0\n",
            "    exec_risk_pct: float = 10.0\n    exec_fib_nearest: bool = True\n",
        )
    )

    staging, _ = promote_tool.stage(bot, promote_tool.repo_trees(bot))
    ok, detail = promote_tool.verify(bot, staging)
    assert ok is True
    # `verify` reports two things since 2026-08-26: the settings this deployment does not
    # state, and the fields an open-position record would need. Read through `defaulted`
    # rather than the top level - the second one is what makes a promote refuse while a bot
    # is in the market, and it must not be squeezed out to keep this line shorter.
    assert "exec_fib_nearest" in json.loads(detail)["defaulted"]


# ── the version record ──────────────────────────────────────────────────────────
def test_the_deployment_record_is_what_the_bot_reports(bot):
    """`config.json` states intent; `deployed.json` states what is actually on this disk. The
    second wins, or a bot reports a version it is not running the moment the repo moves."""
    assert _promote(bot) == 0
    fresh = live_config.load("demo_bot")
    assert fresh.promoted_commit == "abc1234"
    assert fresh.promoted_at == "2026-08-03"
    assert fresh.strategy_source_hash == live_version.deployment_hash(fresh.source_roots)


def test_the_record_keeps_the_params_the_version_was_deployed_with(bot):
    """`config.json` is edited between promotes — the Bots page writes `exec_risk_pct` to it on
    a running bot — so the params a version was DEPLOYED with are not recoverable from it
    afterwards. Recording them is what makes "show me that version's settings" answerable."""
    assert _promote(bot) == 0
    record = live_config.deployed_record("demo_bot")
    assert record["strategy_params"] == {"exec_risk_pct": 10.0}

    cfg_path = live_config.config_path("demo_bot")
    raw = json.loads(cfg_path.read_text())
    raw["strategy_params"]["exec_risk_pct"] = 2.0
    cfg_path.write_text(json.dumps(raw))

    assert live_config.deployed_record("demo_bot")["strategy_params"]["exec_risk_pct"] == 10.0
    assert live_config.load("demo_bot").strategy_params["exec_risk_pct"] == 2.0


def test_a_corrupt_record_reads_as_unpromoted_not_a_crash(bot):
    """The snapshot is hash-checked regardless, which is the guarantee that matters. A bad JSON
    file must not be the thing that stops an otherwise healthy bot."""
    assert _promote(bot) == 0
    live_config.deployed_path("demo_bot").write_text("{not json")
    assert live_config.deployed_record("demo_bot") == {}
    assert live_config.load("demo_bot").bot_key == "demo_bot"


def test_the_snapshot_drops_files_deleted_upstream(bot):
    """The old snapshot is REMOVED, not merged over. A module deleted upstream that lingers in
    the deployment is still importable, and the hash would then describe a tree that exists
    nowhere in git."""
    assert _promote(bot) == 0
    stale = bot.deployed_dir / "engines" / "gone.py"
    stale.write_text("X = 1")
    assert _promote(bot) == 0
    assert not stale.exists()
