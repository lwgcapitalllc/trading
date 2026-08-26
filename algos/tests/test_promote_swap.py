"""`promote.py` must never leave a bot with no deployed code.

🔴 **2026-08-26.** `activate()` deleted the live snapshot and then renamed the staged one into
its place. On Windows that rename can fail outright — the running bot, an indexer or a virus
scanner holding a handle is enough — and when it did, the bot was left with **no deployment at
all**. It kept trading only because Python already had its modules in memory; a restart would
have found nothing to import.

⚠ **`stage()`'s docstring promised exactly what `activate()` broke**: *"a failed promote must
leave the previous deployment exactly as it was"*. It was true of staging and false of
activation, and the two are three functions apart. **A safety property is only as strong as its
last step.**

Every test here was watched RED against the pre-fix `activate()`.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "promote.py"


@pytest.fixture
def promote():
    spec = importlib.util.spec_from_file_location("promote_under_test", TOOL)
    m = importlib.util.module_from_spec(spec)
    sys.modules["promote_under_test"] = m
    spec.loader.exec_module(m)
    return m


def _tree(root: Path, name: str, marker: str) -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "strategy.py").write_text(f"VERSION = {marker!r}\n")
    return d


def _cfg(root: Path):
    return SimpleNamespace(deployed_dir=root / "deployed", bot_key="bot_test")


def test_a_successful_swap_replaces_the_snapshot(tmp_path, promote):
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed", "old")
    staging = _tree(tmp_path, "deployed.new", "new")

    promote.activate(cfg, staging)

    assert (cfg.deployed_dir / "strategy.py").read_text() == "VERSION = 'new'\n"
    assert not staging.exists()
    assert not (tmp_path / "deployed.old").exists(), "the backup was left behind"


def test_a_failed_swap_leaves_the_OLD_deployment_in_place(tmp_path, promote, monkeypatch):
    """🔴 THE ONE THAT MATTERS. The incident, reproduced: the rename fails.

    WATCHED RED against the old body (`rmtree(dest)` then `rename`) - the deployed directory is
    simply gone, which is what happened on the box.
    """
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed", "old")
    staging = _tree(tmp_path, "deployed.new", "new")

    real_rename = Path.rename

    def flaky(self, target):
        # The realistic lock is on the STAGED tree - a scanner reading files that were written
        # a second ago. Keying on the source rather than the destination also leaves the
        # rollback able to succeed, which is the behaviour under test.
        if Path(self).name == "deployed.new":
            raise PermissionError(32, "The process cannot access the file")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)

    with pytest.raises(PermissionError):
        promote.activate(cfg, staging)

    assert cfg.deployed_dir.exists(), "the bot was left with NO deployed code"
    assert (cfg.deployed_dir / "strategy.py").read_text() == "VERSION = 'old'\n"


def test_the_old_snapshot_is_never_deleted_before_the_new_one_is_in_place(tmp_path, promote):
    """Pins the ORDER rather than the outcome, because the outcome test above can be satisfied by
    a lucky retry while the dangerous window is still there.

    At every moment during the swap, at least one complete snapshot must exist.
    """
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed", "old")
    staging = _tree(tmp_path, "deployed.new", "new")

    seen = []
    real_rename = Path.rename

    def watching(self, target):
        out = real_rename(self, target)
        seen.append(cfg.deployed_dir.exists() or (tmp_path / "deployed.old").exists())
        return out

    import types  # noqa: F401 - kept explicit so the monkeypatch below reads plainly

    Path.rename = watching
    try:
        promote.activate(cfg, staging)
    finally:
        Path.rename = real_rename

    assert seen and all(seen), "there was a moment with no complete snapshot anywhere"


def test_a_dead_promote_is_RECOVERED_on_the_next_run(tmp_path, promote):
    """The state the box was actually left in: no `deployed`, a `deployed.old` beside it."""
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed.old", "old")

    note = promote.recover_interrupted(cfg)

    assert "RECOVERED" in note
    assert (cfg.deployed_dir / "strategy.py").read_text() == "VERSION = 'old'\n"


def test_recovery_never_overwrites_a_LIVE_deployment(tmp_path, promote):
    """If both exist the swap already succeeded and the backup is litter. Preferring the backup
    would roll a good promote back."""
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed", "new")
    _tree(tmp_path, "deployed.old", "old")

    promote.recover_interrupted(cfg)

    assert (cfg.deployed_dir / "strategy.py").read_text() == "VERSION = 'new'\n"
    assert not (tmp_path / "deployed.old").exists()


def test_recovery_is_silent_when_there_is_nothing_to_do(tmp_path, promote):
    """A tool that announces a recovery on every ordinary run is one people stop reading."""
    cfg = _cfg(tmp_path)
    _tree(tmp_path, "deployed", "live")
    assert promote.recover_interrupted(cfg) == ""


def test_a_locked_staging_tree_is_retried_rather_than_fatal(tmp_path, promote, monkeypatch):
    """A transient Windows lock on a leftover staging directory stopped a promote dead on
    2026-08-26. It is transient; one attempt turned it into a failure."""
    import shutil as _sh

    target = _tree(tmp_path, "deployed.new", "stale")
    calls = {"n": 0}
    real = _sh.rmtree

    def flaky(path, *a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError(32, "The process cannot access the file")
        return real(path, *a, **k)

    monkeypatch.setattr(promote.shutil, "rmtree", flaky)
    promote._remove_tree(target)

    assert not target.exists()
    assert calls["n"] >= 3, "it succeeded without ever retrying, so this proves nothing"


def test_remove_tree_never_raises(tmp_path, promote, monkeypatch):
    """Its callers are cleaning up litter. None of them is worth failing a promote over."""
    target = _tree(tmp_path, "deployed.new", "stale")
    monkeypatch.setattr(
        promote.shutil, "rmtree", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    promote._remove_tree(target, attempts=2)  # must not raise


# ── promoting while the bot is IN THE MARKET ─────────────────────────────────
#
# 🔴 2026-08-26: a bot was promoted v168 -> v241 holding a real trade. The newer strategy
# persists 13 more position fields, the record had none of them, the restore refused, and the bot
# HALTED with the position unmanaged - no stop ratcheting, no time exit. **Nothing warned.** The
# dry run reports which SETTINGS would change and said nothing about the one thing that would
# actually stop the bot.


def _rec(tmp_path: Path, fields: dict, ticket: int = 999) -> Path:
    d = tmp_path / "deployed"
    d.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "position.json"
    p.write_text(json.dumps({"ticket": ticket, "strategy": fields}))
    return p


def test_a_record_missing_fields_the_new_version_needs_is_a_gap(tmp_path, promote):
    _rec(tmp_path, {"_sl": 1.0, "_stage": 0})
    gap = promote.open_position_gap(_cfg(tmp_path), ["_sl", "_stage", "_adds", "_base_qty"])
    assert gap and gap["ticket"] == 999
    assert sorted(gap["missing"]) == ["_adds", "_base_qty"]


def test_a_complete_record_is_not_a_gap(tmp_path, promote):
    """It must be silent on the ordinary case, or it is a warning people learn to scroll past -
    which this repo has already measured to be worth less than no warning at all."""
    _rec(tmp_path, {"_sl": 1.0, "_stage": 0})
    assert promote.open_position_gap(_cfg(tmp_path), ["_sl", "_stage"]) is None


def test_no_open_position_is_not_a_gap(tmp_path, promote):
    (tmp_path / "deployed").mkdir(parents=True, exist_ok=True)
    assert promote.open_position_gap(_cfg(tmp_path), ["_sl"]) is None


def test_an_UNREADABLE_record_counts_as_a_gap(tmp_path, promote):
    """A record that will not parse is one the restore would refuse anyway. Reporting it as "no
    position" is the exact shape of error this file exists to stop."""
    (tmp_path / "deployed").mkdir(parents=True, exist_ok=True)
    (tmp_path / "position.json").write_text("{not json")
    gap = promote.open_position_gap(_cfg(tmp_path), ["_sl"])
    assert gap is not None and gap["missing"]


def test_a_version_that_declares_no_position_fields_asks_nothing(tmp_path, promote):
    """An empty list means the question could not be answered, not that the answer is no.

    ⚠ Asserted against an UNREADABLE record on purpose. The first draft used an ordinary one, and
    that version passed with the guard deleted - the field loop finds nothing to miss either way.
    **A test that cannot tell the guard from its absence is not testing the guard**, and only
    running the mutation showed it.
    """
    (tmp_path / "deployed").mkdir(parents=True, exist_ok=True)
    (tmp_path / "position.json").write_text("{not json")
    assert promote.open_position_gap(_cfg(tmp_path), []) is None
