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
