"""The box backs up its OWN record — the pieces that only ever run unattended.

**Why this file exists.** The record used to leave the trading box only when a Mac happened to be
awake, because the box's scheduled task runs as SYSTEM and `git push` BLOCKED there rather than
failing (`ledger_sync.py`'s own header, measured 2026-08-05). With a repo-scoped token on the box
it pushes itself — and every line of that path runs with nobody watching, which is the shape this
repo has already been bitten by twice.

**So these cases are weighted toward what the job must REFUSE**, not what it does on a good day:

  - it must never push from a working tree carrying changes outside the ledger archive, because
    `algos/tools/promote.py` freezes a bot's snapshot out of that same checkout;
  - it must never let the token reach a console, a log or a Telegram message;
  - it must never write the token into `.git/config`, where `git remote -v` would show it;
  - a machine with no token must carry on working, not fail — that is every Mac.

**Watched RED by MUTATION**, each named in its own test. A fail-watch against HEAD is vacuous:
none of these functions existed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent

_spec = importlib.util.spec_from_file_location(
    "ledger_sync_under_test", _REPO / "algos" / "tools" / "ledger_sync.py"
)
ls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ls)

TOKEN = "github_pat_11ABCDEFG_notarealtokenatall"


class _Empty:
    """A `git config --get` that found nothing — what SYSTEM sees."""

    stdout = ""
    stderr = ""
    returncode = 1


def _git(repo: Path, *args: str):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway git repo standing in for the trading box's checkout.

    ⚠ Never the real one. `_foreign_changes` reads a working tree and the real one is this
    developer's — a test that inspected it would pass or fail on whatever happened to be open.
    """
    r = tmp_path / "trading"
    (r / "algos" / "ledger_archive" / "mpc_sos_fade_demo" / "ledger").mkdir(parents=True)
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "seed.txt").write_text("seed\n")
    (r / "algos" / "tools").mkdir(parents=True, exist_ok=True)
    (r / "algos" / "tools" / "promote.py").write_text("# stand-in\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "seed")
    monkeypatch.setattr(ls, "REPO_ROOT", r)
    return r


# ── the guard that keeps a backup away from a deployment ────────────────────


def test_a_clean_tree_has_no_foreign_changes(repo):
    assert ls._foreign_changes() == []


def test_a_ledger_file_is_NOT_foreign(repo):
    """The archive is exactly what this job is allowed to be changing."""
    p = repo / "algos" / "ledger_archive" / "mpc_sos_fade_demo" / "ledger" / "decisions-x.jsonl"
    p.write_text('{"a":1}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add")
    p.write_text('{"a":1}\n{"b":2}\n')
    assert ls._foreign_changes() == []


def test_an_edit_ANYWHERE_ELSE_stops_the_push(repo):
    """Mutation: dropping the `ledger_archive` prefix test reddens this.

    🔴 The case that matters. A rebase rewrites the working tree, and `promote.py` builds a live
    bot's frozen snapshot out of that tree — so a backup job rebasing under a half-finished
    deployment would change what is about to be frozen.
    """
    (repo / "algos" / "tools" / "promote.py").write_text("# edited mid-deployment\n")
    assert ls._foreign_changes() == ["algos/tools/promote.py"]


def test_an_untracked_file_does_NOT_stop_the_push(repo):
    """A rebase does not move an untracked file, so refusing on one is refusing for ever.

    ⚠ Measured on the real box: it permanently carries two untracked files
    (`algos/log_review_state.json`, `start_mt5_agent.bat`). Counting those would have meant the
    push NEVER ran, and the job would have looked installed and done nothing.
    """
    (repo / "scratch_notes.txt").write_text("notes\n")
    assert ls._foreign_changes() == []


def test_a_tree_that_cannot_be_READ_stops_the_push(tmp_path, monkeypatch):
    """Cannot-ask is not the same as nothing-there, and only one wrong answer is recoverable."""
    monkeypatch.setattr(ls, "REPO_ROOT", tmp_path / "not-a-repo")
    assert ls._foreign_changes() != []


# ── the token ───────────────────────────────────────────────────────────────


def test_the_token_is_spliced_into_the_url_and_never_stored(repo, monkeypatch):
    """Mutation: writing the URL to the `origin` remote instead reddens the config assertion."""
    _git(repo, "remote", "add", "origin", "https://github.com/lwgcapitalllc/trading.git")
    monkeypatch.setitem(sys.modules, "credentials", type(sys)("credentials"))
    sys.modules["credentials"].get = lambda k: TOKEN if k == "github_token" else None

    url = ls._authenticated_remote()

    assert url == f"https://x-access-token:{TOKEN}@github.com/lwgcapitalllc/trading.git"
    cfg = (repo / ".git" / "config").read_text()
    assert TOKEN not in cfg, "the token reached .git/config, where `git remote -v` shows it"


def test_no_token_means_this_machine_simply_does_not_push(repo, monkeypatch):
    """Every Mac is this case. It is a supported state, not a failure."""
    _git(repo, "remote", "add", "origin", "https://github.com/lwgcapitalllc/trading.git")
    monkeypatch.setitem(sys.modules, "credentials", type(sys)("credentials"))
    sys.modules["credentials"].get = lambda k: None
    assert ls._authenticated_remote() is None


def test_an_ssh_remote_is_left_alone(repo, monkeypatch):
    """An ssh remote carries its own auth; rewriting it would break a working push."""
    _git(repo, "remote", "add", "origin", "git@github.com:lwgcapitalllc/trading.git")
    monkeypatch.setitem(sys.modules, "credentials", type(sys)("credentials"))
    sys.modules["credentials"].get = lambda k: TOKEN if k == "github_token" else None
    assert ls._authenticated_remote() is None


def test_the_token_is_redacted_from_anything_printed():
    """Mutation: returning `text` unchanged reddens this.

    git puts the whole remote URL in its error text, so an un-redacted failure message prints the
    token into the task's log — and then into whatever a reader pastes when asking why it broke.
    """
    msg = f"fatal: unable to access 'https://x-access-token:{TOKEN}@github.com/x/y.git/'"
    out = ls._redact(msg, TOKEN)
    assert TOKEN not in out
    assert "REDACTED" in out


def test_redaction_survives_having_no_secret():
    """The no-token path still prints errors, and must not crash on the way."""
    assert ls._redact("plain failure", None) == "plain failure"


# ── git can never be allowed to block ───────────────────────────────────────


def test_git_is_invoked_with_no_credential_helper_at_all():
    """🔴 The reason the box could not push before.

    Git Credential Manager under the SYSTEM account has no cached token, no interactive session
    and an unwritable store, so it HANGS rather than failing — and a scheduled task that hangs
    holds its slot for ever while reporting nothing. Measured 2026-08-24: with the helper live a
    plain `ls-remote` still printed *"Unable to persist credentials with the 'wincredman'
    credential store"*; with it disabled the same call is silent.
    """
    assert "credential.helper=" in ls._GIT_NO_PROMPT
    assert "credential.interactive=false" in ls._GIT_NO_PROMPT


# ── local mode ──────────────────────────────────────────────────────────────


def test_local_mode_copies_rather_than_moving_the_live_file(repo, monkeypatch, capsys):
    """The bot holds the live file open and keeps appending to it.

    ⚠ It must stay a COPY into the archive. Committing into the bot's own instance directory made
    `git pull` on the box abort outright (2026-08-05) — git refuses to overwrite an untracked file,
    which is correct, and the box is the one machine that has to stay current.
    """
    live = repo / "algos" / "markets" / "fx" / "instances" / "b" / "ledger"
    live.mkdir(parents=True)
    src = live / "decisions-2026-08-24.jsonl"
    src.write_text('{"a":1}\n')
    monkeypatch.setattr(ls, "LOCAL_INSTANCES", repo / "algos" / "markets" / "fx" / "instances")
    monkeypatch.setattr(ls, "LOCAL_ARCHIVE", repo / "algos" / "ledger_archive")

    got = ls.fetch(None, ["b/ledger/decisions-2026-08-24.jsonl"])

    assert len(got) == 1 and got[0].read_text() == '{"a":1}\n'
    assert src.exists(), "the bot's live file was moved instead of copied"


def test_local_mode_truncates_a_half_written_record(repo, monkeypatch):
    """A file copied mid-append can end in half a line, and half a record is not a record."""
    live = repo / "algos" / "markets" / "fx" / "instances" / "b" / "ledger"
    live.mkdir(parents=True)
    (live / "decisions-2026-08-24.jsonl").write_text('{"a":1}\n{"b":2')
    monkeypatch.setattr(ls, "LOCAL_INSTANCES", repo / "algos" / "markets" / "fx" / "instances")
    monkeypatch.setattr(ls, "LOCAL_ARCHIVE", repo / "algos" / "ledger_archive")

    got = ls.fetch(None, ["b/ledger/decisions-2026-08-24.jsonl"])

    assert got[0].read_text() == '{"a":1}\n'


def test_a_missing_source_is_reported_and_skipped_not_raised(repo, monkeypatch, capsys):
    """One unreadable day must not cost the other days their backup."""
    monkeypatch.setattr(ls, "LOCAL_INSTANCES", repo / "algos" / "markets" / "fx" / "instances")
    monkeypatch.setattr(ls, "LOCAL_ARCHIVE", repo / "algos" / "ledger_archive")

    got = ls.fetch(None, ["b/ledger/nope.jsonl"])

    assert got == []
    assert "copy failed" in capsys.readouterr().out


# ── the path separator, which is why the first live run committed nothing ───


def test_a_repo_relative_path_is_spelled_the_way_GIT_spells_it(repo):
    """🔴 The defect that made the first real run on the box a silent no-op.

    `Path.relative_to` returns the HOST's separator. On Windows that is a backslash, while
    `git status --porcelain` always prints forward slashes — so every membership test against
    git's output missed, `pending()` returned nothing, and the job printed *"up to date — all
    already committed"* while committing nothing. Task result 0, exit 0, two modified record
    files left in the working tree.

    ⚠ **It is asserted on a WINDOWS-shaped string rather than on a real local path**, because a
    real path on this Mac has no backslash in it and the assertion would pass without testing
    anything. That is the trap that hid the bug in the first place: the code was correct on the
    only machine it had ever run on.
    """
    assert "algos\\ledger_archive\\x\\decisions-2026-08-24.jsonl".replace("\\", "/") == (
        "algos/ledger_archive/x/decisions-2026-08-24.jsonl"
    )
    p = repo / "algos" / "ledger_archive" / "b" / "decisions-2026-08-24.jsonl"
    assert "\\" not in ls._rel(p)
    assert ls._rel(p) == "algos/ledger_archive/b/decisions-2026-08-24.jsonl"


def test_a_changed_record_is_actually_SEEN_as_pending(repo):
    """Mutation: dropping the normalisation in `pending` reddens this on Windows.

    ⚠ On a Mac it stays green either way — the separators already agree — so this case is here
    for the BOX, and its honest limit is stated rather than left implied. `_rel`'s own test
    above is the one that bites on every platform.
    """
    d = repo / "algos" / "ledger_archive" / "b" / "ledger"
    d.mkdir(parents=True)
    f = d / "decisions-2026-08-24.jsonl"
    f.write_text('{"a":1}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "first")
    f.write_text('{"a":1}\n{"b":2}\n')

    assert ls.pending([f]) == [f], "a modified record was reported as already committed"


def test_an_unchanged_record_is_NOT_pending(repo):
    """The other direction: re-committing an identical file every hour is its own noise."""
    d = repo / "algos" / "ledger_archive" / "b" / "ledger"
    d.mkdir(parents=True)
    f = d / "decisions-2026-08-24.jsonl"
    f.write_text('{"a":1}\n')
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "first")

    assert ls.pending([f]) == []


# ── the identity, which SYSTEM does not have ────────────────────────────────


def test_an_account_with_no_git_identity_gets_the_box_one(repo, monkeypatch):
    """🔴 Why the first scheduled run exited 1 while the hand-run worked.

    The task runs as SYSTEM, which does not share the interactive user's global git config.
    MEASURED with a throwaway SYSTEM task: `git config --get user.email` returned nothing, so
    `git commit` refused with *"Please tell me who you are"* — after the files had been copied,
    so the working tree looked half-done. The same command as Administrator succeeded.
    """
    # ⚠ Simulated rather than `git config --unset`, and that mattered: unsetting the LOCAL value
    # still finds this developer's GLOBAL one, so the first version of this test failed for a
    # reason that has nothing to do with SYSTEM. The condition under test is "git reports no
    # identity", which is what is faked here.
    monkeypatch.setattr(ls, "_run", lambda *a: _Empty())

    args = ls._identity()

    assert f"user.email={ls._BOX_EMAIL}" in args
    assert f"user.name={ls._BOX_NAME}" in args


def test_an_account_that_HAS_one_keeps_it(repo):
    """Mutation: returning the box identity unconditionally reddens this.

    ⚠ A Mac running this has its own identity, and overriding it would attribute every manual
    sync to the trading box — a history that says a machine did work a person did.
    """
    assert ls._identity() == ()


def test_the_identity_is_never_written_into_the_repo_config(repo, monkeypatch):
    """It is passed per-command. A write would touch a checkout `promote.py` also reads."""
    monkeypatch.setattr(ls, "_run", lambda *a: _Empty())

    ls._identity()

    assert ls._BOX_EMAIL not in (repo / ".git" / "config").read_text()


# ── the push path needs the identity too ────────────────────────────────────


class _NoIdentityCleanTree:
    """SYSTEM's answers: no git identity, and a clean working tree.

    ⚠ Deliberately NOT `_Empty`. That stub returns 1 for everything, which `_foreign_changes`
    reads as *cannot read the tree* and stands the push down — so the test would pass without
    ever reaching the code under test. The two questions need two different answers.
    """

    def __init__(self, args):
        self.args = args
        self.stderr = ""
        wants_identity = "config" in args
        self.stdout = ""
        self.returncode = 1 if wants_identity else 0


class _HasIdentityCleanTree(_NoIdentityCleanTree):
    """A machine that DOES have a git identity — a Mac, or an interactive Windows login."""

    def __init__(self, args):
        super().__init__(args)
        if "config" in args:
            self.stdout = "someone@example.com\n"
            self.returncode = 0


def test_the_REBASE_carries_the_box_identity_too(repo, monkeypatch):
    """🔴 The defect that failed every hourly run on the night of 2026-08-24.

    `_identity()` was applied to the commit and NOT to the push path. A rebase REPLAYS commits,
    so it needs a committer exactly as a commit does. While the box was merely ahead of origin
    the push fast-forwarded, nothing was replayed, and the omission was invisible — it broke the
    instant the other machine pushed and a real rebase became necessary. The bot committed
    locally every hour, failed to push, and the alert fired thirteen times.

    ⚠ The assertion is on the ARGUMENTS actually handed to git, not on a constant. A test that
    checked `_identity()` alone would have stayed green through the whole outage — the helper was
    never broken, its caller was.

    **Watched RED against the previous line** (`git = ("git", "-C", ...) + _GIT_NO_PROMPT`):
    the pull argv carries no `user.email` and this fails. Confirmed as SYSTEM on an isolated
    fixture as well — `Committer identity unknown`, exit 128, and exit 0 once the arguments land.
    """
    monkeypatch.setattr(ls, "_run", lambda *a: _NoIdentityCleanTree(a))
    monkeypatch.setattr(ls, "_authenticated_remote", lambda: None)

    seen = []

    def fake_run(args, **kw):
        seen.append(list(args))
        return _NoIdentityCleanTree(tuple(args))

    monkeypatch.setattr(ls.subprocess, "run", fake_run)

    ls._push()

    rebase = [a for a in seen if "pull" in a and "--rebase" in a]
    assert rebase, f"the rebase never ran; git was called with {seen}"
    assert f"user.email={ls._BOX_EMAIL}" in rebase[0]
    assert f"user.name={ls._BOX_NAME}" in rebase[0]


def test_the_identity_is_NOT_forced_when_the_machine_has_one(repo, monkeypatch):
    """Mutation guard: hardcoding the box identity into the push path reddens this.

    A Mac runs this by hand and must keep its own attribution — see `_identity`.

    ⚠ `_run` is stubbed SEPARATELY from `subprocess.run` here, and the first version of this test
    was wrong for want of it: `_run` is a thin wrapper over `subprocess.run`, so patching the
    latter to capture argv also answered the identity question — with no identity. The test then
    failed against correct code. Two questions, two stubs.
    """
    monkeypatch.setattr(ls, "_authenticated_remote", lambda: None)
    monkeypatch.setattr(ls, "_run", lambda *a: _HasIdentityCleanTree(a))

    seen = []

    def fake_run(args, **kw):
        seen.append(list(args))
        return _NoIdentityCleanTree(tuple(args))

    monkeypatch.setattr(ls.subprocess, "run", fake_run)

    ls._push()

    rebase = [a for a in seen if "pull" in a and "--rebase" in a]
    assert rebase, f"the rebase never ran; git was called with {seen}"
    assert not [x for x in rebase[0] if str(x).startswith("user.email=")]
