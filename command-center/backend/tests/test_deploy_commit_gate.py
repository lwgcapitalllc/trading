"""Every commit this app makes has to get PAST the repo's own commit-msg hook.

🔴 **Written after finding the deploy path had been dead since 2026-08-04.** `.githooks/commit-msg`
refuses any commit whose changed files' owning CLAUDE.md is not staged in the same commit, and an
instance config under `algos/markets/fx/instances/` is owned by `algos/CLAUDE.md`. Nothing in
`routers/bots.py` stages that file — nor could it, since the hook exists to demand a paragraph a
human wrote — so **every deploy this router performed died at `git commit` and surfaced to the
browser as 500 "git push failed"**: the risk-cap write, the account move, the runtime-params write.

Measured rather than reasoned about: the hook was run against a staged instance config and refused
with exit 1, and the last commit this app ever made is dated 2026-07-30, five days before the hook
landed.

⚠ **The fix is the hook's own in-band escape, deliberately NOT `--no-verify` and NOT an exemption.**
`--no-verify` is forbidden repo-wide precisely because it leaves no trace; an exemption for
`*/instances/*.json` would also wave through a HUMAN hand-editing one, which is the case the hook is
right about. A `DOCS: none - <reason>` line asks the caller to say why, in the log, where the next
person reads it.

**This is the third time a rule fired on a robot's commit and silently stopped the job** —
`algos/tools/ledger_sync.py` twice on 2026-08-05. A hook has no human to read its message when the
committer is a program: it does not nag, it stops the work and reports something else.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parents[1]
_HOOK = _REPO / ".githooks" / "commit-msg"
_BOTS = _BACKEND / "routers" / "bots.py"


_PROBE_STAGED = "algos/markets/fx/instances/mpc_sos_fade_demo/config.json"


def _probe_paths() -> tuple[Path, Path]:
    """This process's OWN scratch message + index under `.git`, unique per worker.

    🔴 They were two FIXED names, and the suite runs `-n auto`. Three tests here write and then
    `unlink` the same two paths, so under xdist one worker deletes the file another is mid-way
    through using — `grep: .git/COMMIT_EDITMSG_probe: No such file or directory`, and the hook
    exits non-zero for a reason that has nothing to do with what is being tested. MEASURED
    2026-08-21: green 3/3 serially, red 3/3 under `-n auto`, and it is in `run_all_tests.sh`, so
    the gate has been intermittently red for everyone.

    ⚠ This is the exact failure the root CLAUDE.md names — *"a new test that writes a fixed path
    breaks other tests non-deterministically, which is the worst failure shape a suite has"* — and
    it was already in the suite when that line was written.
    ⚠ Keyed on the PID rather than `PYTEST_XDIST_WORKER`, so it is also correct when the file is
    run outside xdist entirely, where that variable does not exist.
    """
    tag = os.getpid()
    return (_REPO / ".git" / f"COMMIT_EDITMSG_probe.{tag}", _REPO / ".git" / f"index_probe.{tag}")


def _run_hook(message: str) -> subprocess.CompletedProcess:
    """Run the REAL hook against a message, with a staged set WE control.

    🔴 **This used to inherit whatever the developer happened to have staged, and that made both
    tests below a coin flip on the state of the working tree (fixed 2026-08-14).** The hook exits
    0 at `[ -z "$STAGED" ] && exit 0` — the FIRST thing it does after the merge/rebase checks —
    so with nothing staged it never reaches the DOCS parser at all, and
    `test_a_message_without_a_docs_line_is_refused_by_the_real_hook` failed by getting exit 0 for
    a reason that has nothing to do with the DOCS line. This docstring previously ASSERTED the
    opposite ("it exercises the DOCS-line parser rather than the pairing rule") — a claim about
    the hook's control flow that nothing checked, which is this repo's most-repeated defect in
    its quietest form. The reverse case is just as bad: run the suite with real code staged and
    the "the hook accepts our message" test fails on the PAIRING rule instead.

    ⚠ **`GIT_INDEX_FILE` points git at a SCRATCH index, so the real one is never touched** — no
    `git add`, no `git reset`, nothing to restore if the process dies mid-test. The scratch index
    is seeded from `HEAD` and then one path is force-removed from it, which shows up as exactly
    one staged deletion. That path is an INSTANCE CONFIG on purpose: it is what this app really
    commits, and `needs_proof` does not match it, so the hook reaches the DOCS parser rather than
    stopping at the money-path evidence rule one branch earlier.

    ⚠ **`--force-remove` rather than staging a modification**, because writing a blob to stage a
    change would put a loose object in `.git/objects` for a test that claims to commit nothing.
    """
    msg, index = _probe_paths()
    msg.write_text(message, encoding="utf-8")
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    try:
        _seed_probe_index(env, index)
        return subprocess.run(
            [str(_HOOK), str(msg)], cwd=_REPO, env=env, capture_output=True, text=True, timeout=30
        )
    finally:
        msg.unlink(missing_ok=True)
        index.unlink(missing_ok=True)


def _git(env, *argv) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *argv], cwd=_REPO, env=env, check=True, capture_output=True, text=True, timeout=30
    )


def _seed_probe_index(env: dict, index: Path) -> None:
    """Put exactly `_PROBE_STAGED` in the scratch index and nothing else.

    ⚠ **Both `_run_hook` and the non-vacuity test below go through THIS function**, rather than
    each holding its own copy of the two git calls. A guard that restates the thing it guards
    cannot fail when that thing breaks — it just agrees with itself, which is how the first
    version of this fix was written and why it is worth a named helper for two lines.
    """
    index.unlink(missing_ok=True)
    _git(env, "read-tree", "HEAD")
    _git(env, "update-index", "--force-remove", _PROBE_STAGED)


@pytest.mark.skipif(not _HOOK.exists(), reason="hook not present in this checkout")
def test_the_probe_really_stages_something():
    """Non-vacuity for `_run_hook` itself: an empty staged set makes both tests below meaningless.

    ✅ Watched RED by MUTATION — dropping the `--force-remove` call from `_seed_probe_index`
    turns this red AND `test_a_message_without_a_docs_line_is_refused_by_the_real_hook` with it,
    which is exactly the state the suite was silently in before 2026-08-14.
    """
    _, index = _probe_paths()
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    try:
        _seed_probe_index(env, index)
        staged = _git(env, "diff", "--cached", "--name-only", "--diff-filter=ACMRD")
    finally:
        index.unlink(missing_ok=True)

    assert staged.stdout.split() == [_PROBE_STAGED]


@pytest.mark.skipif(not _HOOK.exists(), reason="hook not present in this checkout")
def test_the_real_hook_accepts_the_message_shape_this_app_produces():
    """The end-to-end claim. If this goes red, every Deploy button in the app is broken."""
    import routers.bots as bots

    captured: list[str] = []

    def _fake_run(argv, **kw):
        if argv[:2] == ["git", "-C"] and "commit" in argv:
            captured.append(argv[argv.index("-m") + 1])
        return subprocess.CompletedProcess(argv, 0, stdout="M x", stderr="")

    orig = subprocess.run
    subprocess.run = _fake_run  # type: ignore[assignment]
    try:
        bots._git_commit_push(
            _REPO / "algos" / "markets" / "fx" / "instances" / "mpc_sos_fade_demo" / "config.json",
            "bots: probe [command center]",
            "a bot moved between accounts from the Bots page; an operational deployment",
        )
    finally:
        subprocess.run = orig  # type: ignore[assignment]

    assert captured, "no commit was attempted"
    result = _run_hook(captured[0] + "\n")
    assert result.returncode == 0, (
        f"the real commit-msg hook REFUSED this app's own message:\n{result.stdout}{result.stderr}"
    )


def test_a_message_without_a_docs_line_is_refused_by_the_real_hook():
    """Non-vacuity for the test above: the hook must actually be capable of saying no here.

    Without this, a hook that had been disabled or that ignored the message entirely would make the
    green above meaningless.
    """
    if not _HOOK.exists():
        pytest.skip("hook not present in this checkout")

    # `_run_hook` stages one instance config, so the hook gets past its empty-staged early exit
    # and past `needs_proof` (an instance config is not a money path) and lands on the DOCS
    # parser — the part this app's message has to satisfy.
    result = _run_hook("bots: probe [command center]\n\nDOCS: none - short\n")
    assert result.returncode != 0, "the hook accepted a DOCS reason under ten characters"
    assert "reason" in (result.stdout + result.stderr).lower()


def test_a_missing_reason_is_refused_here_rather_than_at_the_hook():
    """The hook's refusal arrives as a CalledProcessError two lines later and is reported to the
    browser as "git push failed" — which names the wrong step. This says what is actually wrong."""
    import routers.bots as bots

    with pytest.raises(ValueError, match="docs_reason"):
        bots._git_commit_push(Path("/tmp/x"), "bots: probe [command center]", "")
    with pytest.raises(ValueError, match="docs_reason"):
        bots._git_commit_push(Path("/tmp/x"), "bots: probe [command center]", "too short")


def test_every_call_site_passes_a_reason():
    """A SOURCE test, for `test_bot_kill_scope.py`'s reason: a behavioural test only covers the
    routes somebody remembered to write one for, and a new deploy path added next month is exactly
    the one nobody will. The signature makes it a TypeError, and this names it in the suite."""
    tree = ast.parse(_BOTS.read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_git_commit_push"
    ]

    assert calls, "no _git_commit_push call sites found — has it been renamed?"
    for call in calls:
        assert len(call.args) >= 3, (
            f"_git_commit_push at line {call.lineno} passes no docs_reason. The commit-msg hook "
            f"will refuse the commit and the endpoint will report 'git push failed'."
        )


def test_no_call_site_reaches_for_no_verify():
    """`--no-verify` leaves no trace, so the next person cannot tell a deliberate skip from a
    forgotten one — which is the whole problem the hook exists to fix. Repo rule, pinned here
    because this is the one module that commits unattended.

    ⚠ It walks the AST rather than grepping the text: the prose above this function explains WHY
    the flag is banned, and a substring search over the source cannot tell an explanation from an
    argument. The first version of this test failed on its own docstring.
    """
    tree = ast.parse(_BOTS.read_text(encoding="utf-8"))
    literals = [
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    offenders = [s for s in literals if s.strip() == "--no-verify"]
    assert not offenders, f"a git call passes {offenders} — it leaves no trace of the skip"
    assert any(s == "commit" for s in literals), (
        "no 'commit' argument found — the git call shape changed, re-check this guard"
    )
