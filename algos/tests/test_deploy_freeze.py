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


# ── the ORDER-SENDING code is frozen too (2026-09-17) ───────────────────────────────────────
#
# 🔴 Until this date the runner, the bridge and the sizing check ran from the box's working tree:
# a `git pull` there changed what a live bot sent to the broker, and the pin never looked at them.
import subprocess  # noqa: E402

_REAL = _REPO / "algos"


def _order_path_like(root: Path) -> None:
    for rel, body in (
        ("algos/live/runner.py", "RUNNER = 1\n"),
        ("algos/live/bridge.py", "BRIDGE = 1\n"),
        ("algos/shared/order_sizing.py", "SIZING = 1\n"),
        ("algos/markets/fx/tools/broker_clock.py", "CLOCK = 1\n"),
        ("algos/markets/fx/tools/unrelated_tool.py", "TOOL = 1\n"),
        ("strategies/python/live_contract.py", "CONTRACT = 1\n"),
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)


def _reload(bot):
    return live_config.load(bot.bot_key)


def test_a_new_snapshot_CARRIES_and_PINS_the_order_code(bot):
    repo = promote_tool._REPO
    _order_path_like(repo)
    assert _promote(bot) == 0
    fresh = _reload(bot)
    snap = fresh.deployed_dir
    assert fresh.carries_order_path
    assert (snap / "algos" / "live" / "bridge.py").is_file()
    assert (snap / "algos" / "markets" / "fx" / "tools" / "broker_clock.py").is_file()
    assert not (snap / "algos" / "markets" / "fx" / "tools" / "unrelated_tool.py").exists()
    # 🔴 2026-09-17: the runner's startup gate reads this from beside itself, and a snapshot
    # without it stopped both SOS Fade bots starting on the box.
    assert (snap / "strategies" / "python" / "live_contract.py").is_file()
    assert snap / "algos" / "live" in fresh.source_roots

    # The repo moving changes nothing...
    (repo / "algos" / "live" / "bridge.py").write_text("BRIDGE = 2\n")
    live_version.verify_pin(fresh.source_roots, fresh.strategy_source_hash, frozen=True)

    # ...and an edit to the snapshot's own order code refuses the start.
    for rel in ("algos/live/bridge.py", "algos/markets/fx/tools/broker_clock.py"):
        f = snap / rel
        good = f.read_text()
        f.write_text("TAMPERED = 1\n")
        with pytest.raises(live_version.VersionMismatch):
            live_version.verify_pin(fresh.source_roots, fresh.strategy_source_hash, frozen=True)
        f.write_text(good)


def test_a_snapshot_from_BEFORE_keeps_its_old_pin(bot):
    """A bot promoted before 2026-09-17 must still start — widening its roots would refuse it
    for a mismatch nobody made. It is pinned on the old three until its next promote."""
    assert _promote(bot) == 0  # the fixture repo has no order code, like an old snapshot
    _order_path_like(promote_tool._REPO)  # the repo gains it afterwards
    fresh = _reload(bot)
    assert not fresh.carries_order_path
    assert len(fresh.source_roots) == 3
    live_version.verify_pin(fresh.source_roots, fresh.strategy_source_hash, frozen=True)


def _mini_box(tmp_path: Path, key: str, *, snapshot: bool) -> Path:
    """The real runner.py in a throwaway repo, with (optionally) a snapshot runner that says so."""
    repo = tmp_path / "box"
    (repo / "algos" / "live").mkdir(parents=True)
    (repo / "algos" / "live" / "runner.py").write_text((_REAL / "live" / "runner.py").read_text())
    if snapshot:
        live = repo / "algos" / "markets" / "fx" / "instances" / key / "deployed" / "algos" / "live"
        live.mkdir(parents=True)
        (live / "runner.py").write_text(
            "import sys\nprint('SNAPSHOT', __file__, sys.argv[1:], sys.path[0])\n"
        )
    return repo


def test_the_repo_runner_HANDS_OVER_to_the_snapshot(tmp_path):
    """RED before 2026-09-17: the repo runner imported the repo bridge and ran on."""
    repo = _mini_box(tmp_path, "demo_bot", snapshot=True)
    out = subprocess.run(
        [sys.executable, str(repo / "algos" / "live" / "runner.py"), "--bot", "demo_bot"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    line = out.stdout.strip()
    assert line.startswith("SNAPSHOT"), (out.stdout, out.stderr)
    assert "deployed" in line and "'--bot', 'demo_bot'" in line
    # The repo's own algos/live must not be first on the path the snapshot imports from.
    assert line.split()[-1].endswith(str(Path("deployed") / "algos" / "live"))


def test_without_a_snapshot_runner_the_repo_runner_carries_on(tmp_path):
    """An old snapshot (or none) runs the repo file as before — here it gets as far as its imports."""
    repo = _mini_box(tmp_path, "demo_bot", snapshot=False)
    out = subprocess.run(
        [sys.executable, str(repo / "algos" / "live" / "runner.py"), "--bot", "demo_bot"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "SNAPSHOT" not in out.stdout
    assert "ModuleNotFoundError" in out.stderr  # the throwaway repo has no live_config


def test_a_snapshot_copy_reads_the_REPOS_kill_switch_and_credentials(tmp_path):
    """🔴 A frozen `fleet_halt` that looked beside itself would find no switch and read 'not set'.

    MUTATION: put `Path(__file__).resolve().parent.parent` back in `fleet_halt.py` — this goes
    red, naming the snapshot's own algos folder."""
    repo = tmp_path / "box"
    shared = repo / "algos" / "markets" / "fx" / "instances" / "demo_bot" / "deployed"
    shared = shared / "algos" / "shared"
    shared.mkdir(parents=True)
    for name in ("repo_paths.py", "fleet_halt.py", "credentials.py"):
        (shared / name).write_text((_REAL / "shared" / name).read_text())
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import fleet_halt, credentials;"
            "print(fleet_halt.flag_path()); print(credentials.credentials_path())",
            str(shared),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    flag, creds = out.stdout.split()
    assert Path(flag).resolve() == (repo / "algos" / "FLEET_HALT").resolve()
    assert Path(creds).resolve() == (repo / "algos" / "credentials.json").resolve()
