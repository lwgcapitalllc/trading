"""A REJECTED push must not be reported as a deployment.

🔴 **`_git_commit_push` ran `git push` without `check=True` and never read its return code**, so
it returned git's own rejection text as its SUCCESS value. Every caller wraps it in
`except subprocess.CalledProcessError` and reports *git push failed* — an exception the push could
not raise. The endpoint then pulled on the VPS (which succeeded, pulling nothing), announced the
deploy on Telegram and returned 200.

**MEASURED 2026-09-04.** An account move and a risk-share change were made from the Bots page,
both pushes were rejected as non-fast-forward, and the page reported both deployed. The box kept
reading the old config for an hour — one bot benched, its sibling on its old risk share — and
nothing in the system disagreed.

⚠ **A rejection here is the NORMAL case.** The trading box pushes its own decision record hourly,
so any deploy landing between the box's push and this clone's next fetch is a non-fast-forward.
That is why these tests cover the RECOVERY as well as the refusal: failing loudly alone would
turn an hourly race into an hourly manual recovery.

⚠ **Written against the `subprocess.run` contract — return code, stdout, stderr — not against a
stubbed helper**, exactly as `test_bot_ssh_failure.py` is, because the bug lived in how that
contract was read. A test that stubbed the push itself would have passed against the defect.

🔴 **THE FIRST VERSION OF THIS FILE WENT RED AGAINST HEAD FOR THE WRONG REASON, AND ALL 8 CASES
DID IT AT ONCE.** They drove `_push_with_one_rebase`, which does not exist at HEAD, so every one
failed with `AttributeError` — a result identical to the one a genuine behaviour difference would
produce, and evidence of nothing. **A test that reds because its subject is missing has not
watched anything.** The regression case below therefore drives `_git_commit_push`, which exists in
BOTH versions, so the old code runs its old push path and the failure is about the behaviour.

**Watched RED. The map was RUN, and the first two entries were written from inspection as "3 red"
each — they are 7 and 6.** Nearly every case here drives the rejected path, so a mutation to the
rejection branch takes most of the file with it; reading the list and counting the cases whose
NAME mentions the mutated behaviour undercounts badly.

    the regression case, against HEAD          -> red: HEAD RETURNS the rejection text,
                                                  `DID NOT RAISE subprocess.CalledProcessError`
    drop the `returncode` check on the push    -> 7 red
    raise on the first rejection, no retry     -> 6 red
    drop `--autostash`                         -> 1 red
    drop the `rebase --abort`                  -> 1 red
    retry in a loop instead of once            -> 1 red
    rebase on EVERY push, not just a rejection -> 1 red

⚠ **The restore was re-run after every mutation and gives 9 green**, so a mutation that failed to
apply cannot be read here as a mutation the suite survived.
"""

import subprocess

import config as cfg
import pytest
from routers import bots


class _Res:
    """What `subprocess.run(..., capture_output=True, text=True)` hands back."""

    def __init__(self, code: int, out: str = "", err: str = ""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


class _Git:
    """Records every git command and replays queued results in order."""

    def __init__(self, *results: _Res):
        self.queue = list(results)
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **_kw):
        self.calls.append(list(cmd))
        return self.queue.pop(0) if self.queue else _Res(0)

    def verbs(self) -> list[str]:
        """The git subcommand of each call — `push`, `pull`, `rebase`."""
        return [c[3] for c in self.calls if len(c) > 3]


def _run(monkeypatch, git: _Git) -> _Git:
    monkeypatch.setattr(bots.subprocess, "run", git)
    return git


REJECTED = _Res(1, err="! [rejected] main -> main (fetch first)\nerror: failed to push some refs")


# ── the regression, driven through the function HEAD also has ─────────────────


def test_a_rejected_deploy_RAISES_rather_than_returning_the_rejection_as_success(monkeypatch):
    """🔴 The defect, through the public helper, which is what makes this case able to red on the
    OLD code: `_git_commit_push` exists in both versions and the four endpoints all call it.

    Against HEAD this fails with *DID NOT RAISE* — the old push path returns git's rejection text
    as the function's return value, and the caller's `except CalledProcessError` never fires. The
    endpoint then pulls on the VPS, announces the deploy and answers 200 while the box still holds
    the old config.
    """
    path = cfg.MONOREPO_ROOT / "algos" / "markets" / "fx" / "instances" / "x" / "config.json"
    git = _run(
        monkeypatch,
        _Git(
            _Res(0),  # add
            _Res(0, out=" M config.json"),  # status --porcelain: something to commit
            _Res(0),  # commit
            REJECTED,  # push
            _Res(1, err="could not rebase"),  # pull --rebase
            _Res(0),  # rebase --abort
        ),
    )
    with pytest.raises(subprocess.CalledProcessError):
        bots._git_commit_push(path, "msg", "a reason long enough for the hook")


def test_a_rejected_push_RAISES_rather_than_returning_its_rejection_text(monkeypatch):
    """🔴 The defect itself, in one line: the old code returned the text above as a success value.

    MUTATION: drop the `returncode` check and this goes red — the call returns a string instead
    of raising, and nothing downstream can tell a rejection from a deploy.
    """
    git = _run(monkeypatch, _Git(REJECTED, _Res(1, err="could not rebase"), _Res(0)))
    with pytest.raises(subprocess.CalledProcessError):
        bots._push_with_one_rebase("/repo")


def test_the_raised_error_carries_BYTES_stderr_because_every_caller_decodes_it(monkeypatch):
    """All four call sites do `e.stderr.decode(errors='replace')`. A str stderr would turn the
    report of a failed deploy into an AttributeError inside the error handler."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(1, err="could not rebase"), _Res(0)))
    with pytest.raises(subprocess.CalledProcessError) as exc:
        bots._push_with_one_rebase("/repo")
    assert isinstance(exc.value.stderr, bytes)
    assert "NOTHING was deployed" in exc.value.stderr.decode()


# ── the recovery ──────────────────────────────────────────────────────────────


def test_a_rejected_push_is_rebased_onto_the_remote_and_pushed_AGAIN(monkeypatch):
    """The box pushes its decision record hourly, so a non-fast-forward is routine rather than
    exceptional. MUTATION: raise on the first rejection without retrying and this goes red."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(0), _Res(0, out="main -> main")))
    assert "main -> main" in bots._push_with_one_rebase("/repo")
    assert git.verbs() == ["push", "pull", "push"]


def test_the_rebase_AUTOSTASHES_because_this_clone_is_usually_dirty(monkeypatch):
    """Two sessions share the clone and a per-machine settings file is nearly always modified.
    Without this the rebase refuses on unstaged changes and the recovery fails for a reason that
    has nothing to do with the push. MUTATION: drop the flag and this goes red."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(0), _Res(0)))
    bots._push_with_one_rebase("/repo")
    pull = next(c for c in git.calls if len(c) > 3 and c[3] == "pull")
    assert "--rebase" in pull
    assert "--autostash" in pull


def test_a_failed_rebase_is_ABORTED_before_the_error_is_raised(monkeypatch):
    """Otherwise the shared clone is left mid-rebase for whoever opens it next, and the symptom
    is a detached HEAD nobody can explain. MUTATION: drop the abort and this goes red."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(1, err="conflict"), _Res(0)))
    with pytest.raises(subprocess.CalledProcessError):
        bots._push_with_one_rebase("/repo")
    assert "rebase" in git.verbs()
    assert any("--abort" in c for c in git.calls)


# ── the limits on the recovery ────────────────────────────────────────────────


def test_a_SECOND_rejection_raises_rather_than_looping(monkeypatch):
    """A loop would keep racing a box that pushes on a schedule. Exactly one retry; a second
    rejection is a real disagreement and needs a person."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(0), REJECTED))
    with pytest.raises(subprocess.CalledProcessError):
        bots._push_with_one_rebase("/repo")
    assert git.verbs().count("push") == 2


def test_the_push_is_NEVER_forced(monkeypatch):
    """A force would discard whatever the push raced with — here, the live bot's own decision
    record, which no broker statement contains and which exists in one copy."""
    git = _run(monkeypatch, _Git(REJECTED, _Res(0), _Res(0)))
    bots._push_with_one_rebase("/repo")
    for call in git.calls:
        assert not any(a in ("--force", "-f", "--force-with-lease") for a in call)


# ── the healthy path still works ──────────────────────────────────────────────


def test_a_push_that_SUCCEEDS_does_not_rebase_anything(monkeypatch):
    """Kept deliberately: a fix that made every push rebase would be caught here rather than by
    somebody noticing their branch had moved."""
    git = _run(monkeypatch, _Git(_Res(0, out="main -> main")))
    assert "main -> main" in bots._push_with_one_rebase("/repo")
    assert git.verbs() == ["push"]
