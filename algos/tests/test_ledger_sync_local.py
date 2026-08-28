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


# ── the alarm has to say WHY ────────────────────────────────────────────────


@pytest.fixture
def box(repo, monkeypatch):
    """`repo`, shaped like the trading box mid-run: one record waiting to be backed up.

    ⚠ `remote_files` is stubbed rather than left to shell out. Unstubbed it would ssh to the real
    trading box, and a unit test may never touch the machine carrying the live bot.
    ⚠ `_authenticated_remote` is forced to None so nothing here can reach for a token or a network.
    """
    live = repo / "algos" / "markets" / "fx" / "instances" / "b" / "ledger"
    live.mkdir(parents=True)
    (live / "decisions-2026-08-27.jsonl").write_text('{"a":1}\n')
    monkeypatch.setattr(ls, "LOCAL_INSTANCES", repo / "algos" / "markets" / "fx" / "instances")
    monkeypatch.setattr(ls, "LOCAL_ARCHIVE", repo / "algos" / "ledger_archive")
    monkeypatch.setattr(
        ls,
        "remote_files",
        lambda host, which: ["b/ledger/decisions-2026-08-27.jsonl"] if which == "closed" else [],
    )
    monkeypatch.setattr(ls, "_authenticated_remote", lambda: None)
    return repo


@pytest.fixture
def alerts(monkeypatch):
    """Everything the job would have sent to the health channel."""
    sent = []
    monkeypatch.setattr(ls, "_alert", sent.append)
    return sent


def test_the_alarm_NAMES_the_file_that_stood_the_push_down(box, alerts):
    """🔴 The night of 2026-08-27: ten identical alerts, not one of which said what to do.

    A hand edit to a bot's settings file on the box makes `_foreign_changes` non-empty, so the
    push stands down every hour exactly as designed. The refusal named the file — to the
    scheduled task's console, which nobody reads — while the message that actually reached a
    human carried only *"did NOT reach origin"*. **Ten of those are worth less than one, because
    the reader learns there is nothing in them to read.**

    **Watched RED against HEAD**, this whole file copied into a worktree at HEAD: the alert there
    is the two generic lines, so the path assertion fails on text that never contained it.
    """
    (box / "algos" / "tools" / "promote.py").write_text("# edited mid-deployment\n")

    rc = ls.main(["--local", "--alert-on-failure"])

    assert rc == 1
    assert len(alerts) == 1, f"expected exactly one alert, got {alerts}"
    assert "Why:" in alerts[0]
    assert "algos/tools/promote.py" in alerts[0], f"the alarm did not name the blocker: {alerts[0]}"


def test_a_run_that_REACHES_origin_says_nothing_at_all(box, alerts, monkeypatch):
    """Mutation guard: alerting unconditionally reddens this.

    An alarm that fires on a good run fails the same way as one carrying no reason — the reader
    stops reading it, and then the real one arrives and is scrolled past.
    """
    monkeypatch.setattr(ls, "_push", lambda: (True, ""))

    rc = ls.main(["--local", "--alert-on-failure"])

    assert rc == 0
    assert alerts == []


def test_the_alarm_NAMES_a_record_git_is_configured_to_IGNORE(box, alerts, monkeypatch):
    """The other failure that fires this alert, and it needs a completely different action.

    A `.gitignore` match means the file can never be backed up at all, so waiting for the next
    hourly run is pointless — which is exactly what the old message could not distinguish from a
    working tree that will be clean in ten minutes.
    """
    (box / ".gitignore").write_text("*.log\n")
    (box / "algos" / "markets" / "fx" / "instances" / "b" / "b-2026-08-27.log").write_text("x\n")
    monkeypatch.setattr(
        ls,
        "remote_files",
        lambda host, which: (
            ["b/ledger/decisions-2026-08-27.jsonl", "b/b-2026-08-27.log"]
            if which == "closed"
            else []
        ),
    )
    monkeypatch.setattr(ls, "_push", lambda: (True, ""))

    rc = ls.main(["--local", "--alert-on-failure"])

    assert rc == 1
    assert len(alerts) == 1, f"expected exactly one alert, got {alerts}"
    assert "b-2026-08-27.log" in alerts[0]
    assert ".gitignore" in alerts[0], f"the alarm did not say a retry is useless: {alerts[0]}"


def test_a_failure_with_NO_recorded_reason_SAYS_it_has_none(box, alerts, monkeypatch):
    """Rule 1 arriving through a message rather than a value.

    A blank *"Why:"* line reads exactly like a clean failure with nothing to add. Cannot-ask and
    nothing-to-say must never share a form, so an unexplained failure has to name itself as one —
    otherwise the next silent branch added below reads as an explained failure for ever.
    """
    monkeypatch.setattr(ls, "_push", lambda: (False, ""))

    rc = ls.main(["--local", "--alert-on-failure"])

    assert rc == 1
    assert "reason not recorded" in alerts[0], alerts[0]


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


# ---------------------------------------------------------------------------
# Only the machine that WROTE the record may commit it (2026-08-28).
#
# 🔴 These four cases exist because the rule was previously written at the PUSH layer, where the
# hazard is not. The Mac agent ran `--no-push`, committed to `main`, and its commit reached
# origin on the next human `git push` of unrelated code — so the box's hourly job had to merge
# two APPENDS to the end of one file. Git cannot do that at any content: the 3-way merge sees a
# single changed region and conflicts. It aborted correctly, re-failed identically for eight
# hours, stacked a commit each time, and the record stayed on one disk.
#
# ⚠ The assertion that matters is `fetch` never running, not the return code. A refusal that
# still copies files into the working tree leaves them for the next `git add -A` to commit, which
# is the same defect one session later.
# ---------------------------------------------------------------------------


@pytest.fixture
def never_fetches(monkeypatch):
    """Records any fetch attempt. Empty is the only passing state for a refused run."""
    calls = []
    monkeypatch.setattr(ls, "fetch", lambda *a, **k: calls.append(a) or [])
    return calls


def test_a_machine_that_did_not_write_the_record_may_not_commit_it(box, never_fetches):
    """Watched RED against HEAD: without the guard this returns 0 and fetches a file."""
    rc = ls.main([])

    assert rc == 1
    assert never_fetches == [], "a refused run must not copy records into the working tree"


def test_the_refusal_is_at_the_COMMIT_layer_not_the_PUSH_layer(box, never_fetches):
    """The exact command the removed Mac agent ran, twice a day, for weeks.

    `--no-push` looked safe and was not: a local commit on a shared branch is a push with a
    delay. Mutating the guard to `if not args.local and not args.no_push` reddens this and
    nothing else in the file, which is the point of keeping it separate from the case above.
    """
    rc = ls.main(["--no-push"])

    assert rc == 1
    assert never_fetches == []


def test_the_box_that_OWNS_the_record_is_not_refused(box, monkeypatch):
    """Mutation guard: a guard that refuses everybody backs nothing up.

    ⚠ This is the half that a refusal-only test cannot cover, and this repo has already shipped
    a checker whose every case asserted a refusal — it certified two tools that had never once
    worked (root CLAUDE.md, the promote tools, 2026-08-26).
    """
    monkeypatch.setattr(ls, "_push", lambda: (True, ""))

    assert ls.main(["--local"]) == 0


def test_a_dry_run_is_still_allowed_from_anywhere_and_writes_NOTHING(box):
    """Inspecting the record from a Mac stays possible, and leaves no file behind.

    ⚠ The assertion is on the DISK, not on whether `fetch` was called. It is called on a dry run
    and returns the paths it would have written without writing them — so a call-counter here
    passes on code that copies and fails on code that does not, i.e. exactly backwards. The
    first version of this test was wrong that way.
    """
    assert ls.main(["--dry-run"]) == 0

    landed = list((box / "algos" / "ledger_archive").rglob("*.jsonl"))
    assert landed == [], f"a dry run left files in the working tree: {landed}"
