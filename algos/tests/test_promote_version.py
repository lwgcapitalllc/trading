"""The version a bot REPORTS, and the ways it could report a number nobody measured.

🔴 **The subject is `v0`.** `LiveConfig.strategy_version` was declared `int = 0` and nothing in
this repo ever assigned it, so every bot's ONLINE banner read `v0 (e4137dbb)` on every start —
from the day the field was written until 2026-08-14. Aaron, off the Telegram channel: *"the last
message say V0? Is it missing the version deployed."*

The failure is the repo's own rule in its quietest form: **a declared field with a default is
indistinguishable from a measurement.** `running=False` told every python backtest its platform
was free; `is_compiled` defaulted to 1 and claimed a strategy was compiled; this one printed a
version number in a message whose whole job is saying which version is running.

So most of these tests are about REFUSING. `version_at` answers `None` for anything it cannot
count, and `None` renders `v?` — because `0` is a version somebody could genuinely be on, and it
is exactly the value that was lying.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO / "algos" / "live"), str(_REPO / "algos" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import live_config  # noqa: E402
import promote as promote_tool  # noqa: E402


def _git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert out.returncode == 0, f"git {' '.join(args)} failed: {out.stderr}"
    return out.stdout.strip()


def _commit(root: Path, rel: str, body: str, message: str) -> str:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=T",
        "commit",
        "-q",
        "-m",
        message,
        "--no-verify",
    )
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real git repo holding the three trees a promote copies.

    ⚠ A REAL repo, not a mocked `subprocess`. The whole claim is *this number is the git
    history*, and a fake `git` would let the counting rule be wrong in either direction while
    every assertion here passed — the fixture-more-capable-than-production trap, inverted.
    """
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _commit(root, "README.md", "x\n", "root")
    # The strategy package has to EXIST, because `repo_trees` resolves a package's borrowings by
    # reading its imports rather than formatting its name (2026-09-04). ⚠ Written and NOT
    # committed on purpose: committing it would touch the strategy tree and make every count
    # below start at 1, which is the fixture quietly editing the thing under test.
    pkg = root / "strategies" / "python" / "demo_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(promote_tool, "_REPO", root)
    return root


def _trees(root: Path):
    """The (source, dest) pairs `repo_trees` produces, without needing a LiveConfig."""

    class _Cfg:
        strategy_package = "demo_pkg"

    return promote_tool.repo_trees(_Cfg())


# ── counting ────────────────────────────────────────────────────────────────────


def test_a_version_is_the_count_of_commits_touching_the_promoted_trees(repo):
    trees = _trees(repo)
    assert promote_tool.version_at("HEAD", trees) == 0
    _commit(repo, "engines/market_structure/engine.py", "A = 1\n", "engine")
    assert promote_tool.version_at("HEAD", trees) == 1
    _commit(repo, "strategies/python/demo_pkg/config.py", "B = 1\n", "strategy")
    assert promote_tool.version_at("HEAD", trees) == 2


def test_a_commit_OUTSIDE_the_promoted_trees_does_not_move_the_version(repo):
    """`algos/live/` is not promoted — it reaches a bot on a restart, not on a deploy — so a
    change there must not claim the deployed code moved. This is what makes subtracting two
    versions the work actually waiting to go out."""
    trees = _trees(repo)
    _commit(repo, "engines/e.py", "A = 1\n", "engine")
    before = promote_tool.version_at("HEAD", trees)
    _commit(repo, "algos/live/runner.py", "A = 2\n", "live")
    assert promote_tool.version_at("HEAD", trees) == before


def test_an_older_commit_counts_lower_than_HEAD(repo):
    trees = _trees(repo)
    first = _commit(repo, "engines/e.py", "A = 1\n", "one")
    _commit(repo, "engines/e.py", "A = 2\n", "two")
    assert promote_tool.version_at(first, trees) < promote_tool.version_at("HEAD", trees)


def test_the_counted_trees_ARE_the_trees_promote_copies(repo):
    """One roster. A tree that is COPIED but not COUNTED is a change that deploys while the
    version says nothing happened — silent, and wrong in the reassuring direction."""
    trees = _trees(repo)
    dests = {str(dest).replace("\\", "/") for _, dest in trees}
    assert dests == {"strategies/python/demo_pkg", "engines", "backtest"}


# ── refusing ────────────────────────────────────────────────────────────────────


def test_a_commit_this_clone_does_not_have_is_None_not_zero(repo):
    """0 reads as *version zero*, which is a real answer and is the exact value that has been
    lying on this field. An uncountable commit has no version."""
    assert promote_tool.version_at("0" * 40, _trees(repo)) is None


def test_a_directory_that_is_not_a_git_repo_is_None_not_zero(tmp_path, monkeypatch):
    # The package exists so that the ONLY thing missing here is the git repo. Without it this
    # would go red on an unresolvable package instead, i.e. pass its assertion for a reason that
    # has nothing to do with what it is named after.
    (tmp_path / "strategies" / "python" / "demo_pkg").mkdir(parents=True)
    monkeypatch.setattr(promote_tool, "_REPO", tmp_path)
    assert promote_tool.version_at("HEAD", _trees(tmp_path)) is None


def test_no_commit_and_no_trees_are_both_None(repo):
    assert promote_tool.version_at("", _trees(repo)) is None
    assert promote_tool.version_at("HEAD", []) is None


@pytest.mark.parametrize("n,expected", [(0, "v0"), (165, "v165"), (None, "v?")])
def test_an_uncounted_version_renders_v_question_never_v0(n, expected):
    assert promote_tool.vlabel(n) == expected


# ── what the bot reads back ─────────────────────────────────────────────────────


def _instance(tmp_path, monkeypatch, *, version_in_config=None):
    instances = tmp_path / "instances"
    (instances / "demo_bot").mkdir(parents=True)
    cfg = {
        "bot_key": "demo_bot",
        "display_name": "Demo",
        "mt5_path": "C:/x/terminal64.exe",
        "account": 1,
        "server": "S",
        "symbol": "XAUUSD",
        "magic": 1,
        "strategy_package": "demo_pkg",
        "strategy_class": "DemoStrategy",
        "strategy_params": {},
    }
    if version_in_config is not None:
        cfg["strategy_version"] = version_in_config
    (instances / "demo_bot" / "config.json").write_text(json.dumps(cfg))
    monkeypatch.setattr(live_config, "_INSTANCES", instances)
    return instances


def test_the_stamped_version_is_what_the_bot_reports(tmp_path, monkeypatch):
    """`config.json` states intent and only the machine that promoted knows what landed — the
    same split `promoted_commit` already follows. A stale number in the tracked file must not
    win, or the bot announces a version it is not running."""
    _instance(tmp_path, monkeypatch, version_in_config=3)
    cfg = live_config.load("demo_bot")
    promote_tool.write_pin(cfg, "h" * 32, "abc1234", "2026-08-14", 7, version=165)
    assert live_config.load("demo_bot").strategy_version == 165


def test_a_deployment_stamped_with_no_version_reads_as_UNKNOWN(tmp_path, monkeypatch):
    """A bot promoted before 2026-08-14 has a record with no countable version. It must read
    `v?` — the honest answer — rather than falling back to `config.json`'s dead 0."""
    _instance(tmp_path, monkeypatch, version_in_config=0)
    cfg = live_config.load("demo_bot")
    promote_tool.write_pin(cfg, "h" * 32, "abc1234", "2026-08-14", 7, version=None)
    fresh = live_config.load("demo_bot")
    assert fresh.strategy_version is None
    assert fresh.version_label == "v?"


def test_an_unpromoted_bot_has_no_version_rather_than_v0(tmp_path, monkeypatch):
    _instance(tmp_path, monkeypatch)
    cfg = live_config.load("demo_bot")
    assert cfg.strategy_version is None
    assert cfg.version_label == "v?"


def test_the_label_is_one_rendering_shared_by_every_reporter(tmp_path, monkeypatch):
    """The banner, the ONLINE alert, the ledger and `bot_state.json` all read this. Four
    private renderings is four chances for one of them to print `vNone`."""
    _instance(tmp_path, monkeypatch)
    cfg = live_config.load("demo_bot")
    promote_tool.write_pin(cfg, "h" * 32, "abc1234", "2026-08-14", 7, version=165)
    assert live_config.load("demo_bot").version_label == "v165"
