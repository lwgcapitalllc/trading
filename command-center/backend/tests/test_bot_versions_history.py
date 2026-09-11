"""The version maths on a SCRIPTED repo — the two histories this repo's own cannot promise.

`test_bot_versions.py` checks the counting rule against THIS repo's history, which is the
strongest evidence there is, and also the reason two cases were never pinned. Whether the range
under test holds a MERGE, or crosses a package RENAME, depends on what happened to be committed
that week:

* a merge was checked only when one landed inside the window — the 2026-08-21 incident was found
  exactly that way, as an intermittent red that would have left again on its own;
* the rename path (`_path_before_renames`, 2026-09-03) had NO test at all, and it is the one the
  FIRST promote after a rename depends on.

Here both are built on purpose, so they are checked on every run.

⚠ **A REAL git repo, never a mocked `subprocess`.** The claim under test is *this number IS the
git history*; a fake git lets the counting rule be wrong in either direction while every
assertion passes. `cfg.MONOREPO_ROOT` is pointed at the scratch repo, which is the only thing
`bot_versions._git` reads.

Mutation map, RUN 2026-09-10 through scripts/testing/mutate.py (5 planted, 5 killed):
  the rename lookup matches the OLD name instead of the new     -> renamed_path / setting_moved
  the rename branch in setting_changes never taken               -> setting_moved_across_a_rename
  a merge never flagged                                          -> merge_is_counted_listed_flagged
  merges dropped from the change LIST only                       -> merge_is_counted_listed_flagged
  merges dropped from the version COUNT only                     -> merge_is_counted_listed_flagged
"""

from __future__ import annotations

import subprocess

import config as cfg
import pytest
from services import bot_versions as bv

_IDENTITY = ("-c", "user.email=t@t", "-c", "user.name=T", "-c", "commit.gpgsign=false")


def _git(root, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert out.returncode == 0, f"git {' '.join(args)} failed: {out.stderr}"
    return out.stdout.strip()


def _commit(root, files: dict, message: str) -> str:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, *_IDENTITY, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _config(time_stop: str) -> str:
    """A config module shaped like a real one: many fields, one of which moves.

    ⚠ Long on purpose. git calls a file RENAMED only above 50% similarity, and a two-line config
    with one line changed can fall under it — the test would then be about git's threshold."""
    fields = "\n".join(f"    setting_{i}: int = {i}" for i in range(20))
    return (
        "from dataclasses import dataclass\n\n\n@dataclass\nclass Cfg:\n"
        f"{fields}\n    exec_time_stop_mode: str = {time_stop!r}\n"
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", root)
    return root


def test_a_renamed_package_is_found_under_its_OLD_name(repo):
    before = _commit(repo, {"strategies/python/old_name/config.py": _config("Off")}, "old")
    _git(repo, "mv", "strategies/python/old_name", "strategies/python/new_name")
    _git(repo, *_IDENTITY, "commit", "-q", "-m", "rename the package")
    after = _git(repo, "rev-parse", "HEAD")

    was = bv._path_before_renames(before, after, "strategies/python/new_name/config.py")
    assert was == "strategies/python/old_name/config.py"
    # A path that was never renamed has no older name — never a guess.
    assert bv._path_before_renames(before, after, "strategies/python/other/config.py") is None


def test_a_setting_that_moved_ACROSS_a_package_rename_is_still_reported(repo):
    """The first promote after a rename: the deployed commit knows only the old name.

    Without the rename lookup the older side is unreadable and the whole preview answers `None`,
    which renders as *not checked* — blank at the one moment somebody decides whether to deploy.
    """
    before = _commit(repo, {"strategies/python/old_name/config.py": _config("Off")}, "old")
    _git(repo, "mv", "strategies/python/old_name", "strategies/python/new_name")
    _git(repo, *_IDENTITY, "commit", "-q", "-m", "rename the package")
    after = _commit(
        repo, {"strategies/python/new_name/config.py": _config("Before TP1 only")}, "move default"
    )

    changes = bv.setting_changes("new_name", before, after, {})
    assert changes is not None, "the rename made the deployed side unreadable"
    assert [(c["name"], c["was"], c["now"], c["is_new"]) for c in changes] == [
        ("exec_time_stop_mode", "Off", "Before TP1 only", False)
    ]


def test_a_MERGE_in_range_is_counted_listed_and_flagged(repo):
    """The headline number and the list under it must agree, with a merge in between.

    `version_at` counts a merge (the promote tool stamps a live bot's version with the same
    count), so the list keeps it too — flagged, because `--name-only` prints no file list for a
    merge and an empty `areas` would otherwise read as *a shared engine moved underneath it*.
    """
    base = _commit(repo, {"engines/a/engine.py": "A = 1\n", "engines/b/engine.py": "B = 1\n"}, "b")
    first_branch = _git(repo, "symbolic-ref", "--short", "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, {"engines/a/engine.py": "A = 2\n"}, "side change")
    _git(repo, "checkout", "-q", first_branch)
    _commit(repo, {"engines/b/engine.py": "B = 2\n"}, "main change")
    _git(repo, *_IDENTITY, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    head = _git(repo, "rev-parse", "HEAD")

    trees = ["engines"]
    changes = bv.changes_between(base, head, trees)
    gap = bv.version_at(head, trees) - bv.version_at(base, trees)
    assert gap == 3, "side change + main change + the merge"
    assert len(changes) == gap, "the banner's count and its list disagree"

    merges = [c for c in changes if c["merge"]]
    assert [m["subject"] for m in merges] == ["merge side"]
    assert merges[0]["areas"] == []
    assert all(c["areas"] == ["engines"] for c in changes if not c["merge"])
