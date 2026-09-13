"""A Bots-page save pushes ITS OWN change, and a rejected push is never reported as a deployment.

🔴 **2026-09-13: the push sent `main`, and `main` carries every commit waiting on this clone.** Two
sessions share the clone, so a save published another session's finished-but-unpushed work with
it. MEASURED that day: one account save sent three commits nobody had asked it to send, and a
fourth session's local commit sat ready to go out on the next save. The change is now rebuilt on
the remote's own tip and pushed by id (`routers/bots.py::_push_own_change`).

🔴 **2026-09-04: a REJECTED push came back as success**, so the page reported a deploy the box never
received and a bot sat on its old config for an hour. That rule stands and is pinned below.

⚠ **Driven on REAL git** — a bare remote, the shared clone this app runs in, and the trading box's
clone pushing its hourly record — never on a stubbed `subprocess`. What is under test is what git
does with a commit graph, and a stub can only restate the author's idea of that. The race with the
box is real too: the box pushes between this clone's fetch and its push, which is when it bites.

⚠ **The old recovery's tests went with it** (the rebase, `--autostash`, the abort). Nothing is
rebased or stashed any more, and `test_nothing_in_the_shared_clone_moves_not_even_on_the_retry`
pins that instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import config as cfg
import pytest
from routers import bots

# Captured at import, before any fixture wraps it: the scene's own git calls must not be counted as
# the app's pushes, nor trigger the box's.
_REAL_RUN = subprocess.run

_MSG = "accounts: probe [command center]"
_REASON = "a registry write made by a test probe"
_EMPTY = '{"accounts": []}'
_OURS = '{"accounts": [1]}'


class _Scene:
    """A bare remote, the shared clone this app runs in, and the trading box's clone."""

    def __init__(self, tmp_path: Path):
        self.remote = tmp_path / "remote.git"
        self.clone = tmp_path / "clone"
        self.box = tmp_path / "box"
        seed = tmp_path / "seed"
        _REAL_RUN(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)], check=True)
        _REAL_RUN(["git", "init", "-q", "-b", "main", str(seed)], check=True)
        self._identity(seed)
        for name, text in (
            ("accounts.json", _EMPTY + "\n"),
            ("other.tsx", "export {}\n"),
            ("notes.md", "notes\n"),
            ("staged.tsx", "export {}\n"),
            ("ledger.jsonl", "seed\n"),
        ):
            (seed / name).write_text(text, encoding="utf-8")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-q", "-m", "seed")
        self.git(seed, "remote", "add", "origin", str(self.remote))
        self.git(seed, "push", "-q", "origin", "main")
        for where in (self.clone, self.box):
            _REAL_RUN(["git", "clone", "-q", str(self.remote), str(where)], check=True)
            self._identity(where)

    def _identity(self, where: Path) -> None:
        self.git(where, "config", "user.email", "probe@example.invalid")
        self.git(where, "config", "user.name", "probe")
        self.git(where, "config", "commit.gpgsign", "false")

    @staticmethod
    def git(where: Path, *argv: str) -> str:
        out = _REAL_RUN(
            ["git", "-C", str(where), *argv], check=True, capture_output=True, text=True
        )
        return out.stdout.strip()

    def _remote(self, *argv: str) -> str:
        out = _REAL_RUN(
            ["git", "--git-dir", str(self.remote), *argv],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    def on_remote(self, rev: str = "main") -> str:
        return self._remote("rev-parse", rev)

    def remote_file(self, rel: str) -> str:
        return self._remote("show", f"main:{rel}")

    def remote_changed(self, since: str) -> list[str]:
        return self._remote("diff", "--name-only", since, "main").split()

    def box_pushes(self, line: str) -> None:
        """The box's hourly decision record, committed and pushed from its own clone."""
        self.git(self.box, "pull", "-q", "--ff-only", "origin", "main")
        with (self.box / "ledger.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.git(self.box, "commit", "-q", "-am", f"chore(ledger): {line}")
        self.git(self.box, "push", "-q", "origin", "main")

    def elsewhere_saves(self, text: str) -> None:
        """Another machine saves the same file and pushes it; this clone has not fetched."""
        self.git(self.box, "pull", "-q", "--ff-only", "origin", "main")
        (self.box / "accounts.json").write_text(text + "\n", encoding="utf-8")
        self.git(self.box, "commit", "-q", "-am", "accounts: saved elsewhere")
        self.git(self.box, "push", "-q", "origin", "main")

    def another_session_commits(self) -> str:
        """A commit another session made here and has not pushed. Returns its id."""
        (self.clone / "other.tsx").write_text("export const x = 1\n", encoding="utf-8")
        self.git(self.clone, "commit", "-q", "-m", "another session's work", "--", "other.tsx")
        return self.git(self.clone, "rev-parse", "HEAD")

    def save(self, text: str) -> str:
        """What every Bots-page write does: the file, then the app's commit-and-push."""
        (self.clone / "accounts.json").write_text(text + "\n", encoding="utf-8")
        return bots._git_commit_push(self.clone / "accounts.json", _MSG, _REASON)


@pytest.fixture
def scene(tmp_path, monkeypatch) -> _Scene:
    s = _Scene(tmp_path)
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", s.clone)
    return s


def _box_races(monkeypatch, scene: _Scene, times: int) -> list[list[str]]:
    """The box pushes its record between this clone's fetch and its push, on the first `times`
    pushes. Returns every push the app attempted."""
    pushes: list[list[str]] = []
    run = subprocess.run

    def racing(argv, *a, **kw):
        if isinstance(argv, list) and argv[3:4] == ["push"]:
            pushes.append(list(argv))
            if len(pushes) <= times:
                scene.box_pushes(f"hour {len(pushes)}")
        return run(argv, *a, **kw)

    monkeypatch.setattr(bots.subprocess, "run", racing)
    return pushes


# ── the defect ────────────────────────────────────────────────────────────────


def test_the_push_carries_THIS_change_and_never_another_sessions_local_commit(scene):
    """🔴 The 2026-09-13 defect. Another session's commit sits here unpushed; a save must send the
    account change and nothing else, and leave that commit exactly where it was."""
    before = scene.on_remote()
    theirs = scene.another_session_commits()

    scene.save(_OURS)

    assert scene.remote_changed(before) == ["accounts.json"]
    assert scene.remote_file("other.tsx") == "export {}"
    assert scene.on_remote("main^") == before
    assert scene.git(scene.clone, "rev-parse", "HEAD^") == theirs
    assert scene.git(scene.clone, "log", "-1", "--format=%s") == _MSG


def test_nothing_in_the_shared_clone_moves_not_even_on_the_retry(scene, monkeypatch):
    """🔴 The recovery this replaced ran `pull --rebase --autostash` in the shared clone: it
    rewrote every session's local commits and stashed their unsaved work. The retry path is the
    one that used to do it, so the box races the first push here to force it."""
    theirs = scene.another_session_commits()
    (scene.clone / "notes.md").write_text("half-written\n", encoding="utf-8")
    (scene.clone / "staged.tsx").write_text("export const y = 2\n", encoding="utf-8")
    scene.git(scene.clone, "add", "staged.tsx")
    pushes = _box_races(monkeypatch, scene, times=1)

    scene.save(_OURS)

    assert len(pushes) == 2, "the race did not force the retry, so this proves nothing"
    assert scene.git(scene.clone, "stash", "list") == ""
    assert scene.git(scene.clone, "rev-parse", "HEAD^") == theirs
    assert scene.git(scene.clone, "diff", "--name-only") == "notes.md"
    assert (scene.clone / "notes.md").read_text(encoding="utf-8") == "half-written\n"
    assert scene.git(scene.clone, "diff", "--cached", "--name-only") == "staged.tsx"


def test_a_lone_change_pushes_the_local_commit_itself_so_no_copy_is_made(scene):
    """With nothing else waiting, the remote gets the very commit made here — the history every
    save produced before, with no second copy to merge later."""
    scene.save(_OURS)
    assert scene.on_remote() == scene.git(scene.clone, "rev-parse", "HEAD")


def test_a_file_the_remote_ALSO_changed_is_refused_never_overwritten(scene):
    """🔴 Building on the remote's tip would otherwise quietly undo another machine's save of the
    same file. The old rebase stopped on that conflict; this must stop too."""
    scene.elsewhere_saves('{"accounts": ["theirs"]}')

    with pytest.raises(subprocess.CalledProcessError) as exc:
        scene.save('{"accounts": ["ours"]}')

    said = exc.value.stderr.decode()
    assert "accounts.json" in said and "changed since" in said
    assert "NOTHING was deployed" in said
    assert scene.remote_file("accounts.json") == '{"accounts": ["theirs"]}'


# ── the race with the box ─────────────────────────────────────────────────────


def test_a_push_that_races_the_box_is_rebuilt_on_the_new_tip_and_sent_ONCE_more(scene, monkeypatch):
    """The box pushes its record hourly, so a rejection is routine. The change is rebuilt on the
    box's new commit and sent again, and the box's record survives."""
    pushes = _box_races(monkeypatch, scene, times=1)

    scene.save(_OURS)

    assert len(pushes) == 2
    assert scene.remote_file("accounts.json") == _OURS
    assert scene.remote_file("ledger.jsonl").splitlines() == ["seed", "hour 1"]
    assert scene._remote("log", "-1", "--format=%s", "main^") == "chore(ledger): hour 1"


def test_a_SECOND_rejection_RAISES_and_nothing_is_forced(scene, monkeypatch):
    """🔴 The 2026-09-04 defect: a rejected push returned as success. Two rejections in a row
    RAISE, with bytes stderr (every caller decodes it), after exactly two attempts, and the box's
    record is still on the remote — nothing forced it off."""
    pushes = _box_races(monkeypatch, scene, times=2)

    with pytest.raises(subprocess.CalledProcessError) as exc:
        scene.save(_OURS)

    assert isinstance(exc.value.stderr, bytes)
    assert "NOTHING was deployed" in exc.value.stderr.decode()
    assert len(pushes) == 2
    forced = ("--force", "-f", "--force-with-lease")
    assert not any(flag in call for call in pushes for flag in forced)
    assert scene.remote_file("ledger.jsonl").splitlines() == ["seed", "hour 1", "hour 2"]
    assert scene.remote_file("accounts.json") == _EMPTY


# ── what is and is not sent ───────────────────────────────────────────────────


def test_a_change_the_remote_already_has_pushes_nothing(scene):
    scene.save(_OURS)
    tip = scene.on_remote()

    assert scene.save(_OURS) == "nothing to commit"
    assert scene.on_remote() == tip


def test_a_change_already_sent_as_a_COPY_is_neither_sent_nor_refused_again(scene):
    """With another session's commit waiting, the remote got a COPY of the save. Saving the same
    thing again must read the remote's copy as already there — not as the remote having changed
    the file under this clone, which would refuse a save that is already deployed."""
    scene.another_session_commits()
    scene.save(_OURS)
    tip = scene.on_remote()

    assert scene.save(_OURS) == "nothing to commit"
    assert scene.on_remote() == tip


def test_a_save_whose_push_failed_before_goes_out_on_the_next_save(scene):
    """A commit left here by an earlier refused push must not read as deployed when the same
    change is saved again — there is nothing new to COMMIT, but the remote still lacks it."""
    (scene.clone / "accounts.json").write_text(_OURS + "\n", encoding="utf-8")
    scene.git(scene.clone, "commit", "-q", "-am", _MSG)

    scene.save(_OURS)

    assert scene.remote_file("accounts.json") == _OURS


def test_a_deleted_file_is_deleted_on_the_remote_too(scene):
    (scene.clone / "accounts.json").unlink()

    bots._git_commit_push(scene.clone / "accounts.json", _MSG, _REASON)

    assert "accounts.json" not in scene._remote("ls-tree", "--name-only", "main").split()
