"""Drive real commands through the hook-bypass guard and assert what it says.

This guard BLOCKS rather than advises, which cuts both ways and is why every case below
asserts a DIRECTION. A guard that refused everything would stop all work and be switched
off within a day; a guard that refused nothing would read as protection while providing
none. Neither can pass this file -- the refusals and the silences are both load-bearing.

The silences matter more than they look. Most are commands somebody types every day, and
each one is a way an over-eager version of this check would make ordinary work impossible: a commit message that QUOTES the flag, a message whose text happens to be the
letter the short flag uses, a pathspec after the end-of-options marker, the flag on a
subcommand that ignores it, and the repo's own documented pre-push skip -- which is
deliberately allowed, because it prints a loud line and has no silent form. The objection
this guard exists to raise is to skipping WITHOUT A TRACE, never to skipping.

WATCHED RED BY MUTATION -- the measured map, which mutation reddens which cases
------------------------------------------------------------------------------
🔴 RUN, NOT REASONED, AND THAT IS NOT A FORMALITY HERE: the map was first written from
inspection and SIX of its eleven entries were wrong, every one of them claiming a mutation
was more surgical than it is. One was worse than wrong -- it claimed two cases covered a
branch that NO case covered, and the mutation survived the whole file in green.

  never refuse (`_verdict` returns None at the top)   -> 16 red: all 15 refusals, PLUS the
                                                         parse-failure case, which stops
                                                         raising once the parser is skipped
  refuse on any git command (return the refusal
    before reading the subcommand)                    -> 20 red: 12 of the 13 silences --
                                                         only the command with no git in it
                                                         survives -- and 8 refusals too,
                                                         because their asserted wording is
                                                         replaced by the blanket one
  drop the end-of-options break (`word == "--"`)      -> 1 red: the pathspec after `--`
  drop the value-swallowing test for commit
    (`_takes_a_value` always False)                   -> 1 red: the option whose VALUE is
                                                         the flag spelled bare
  anchor the short cluster on the first character
    only (`token[1] == "n"`)                          -> 2 red: `-an` and `-sn`, the two
                                                         shapes that read as a typo
  let the cluster scan run past a value-taking short
    option (drop the `break` on m/F/C/c/t)            -> 1 red: `-mn`, where the n is
                                                         message text
  compare the config name case-sensitively            -> 2 red: BOTH redirect spellings, not
                                                         just the mixed-case one -- the
                                                         setting's own name carries a
                                                         capital, so the "lowercase" case
                                                         was never lowercase
  only match the config name as a separate word
    (drop the attached `-c<name>=` branch)            -> 1 red: the attached redirect
  restrict the subcommand set to commit               -> 5 red: push, merge, cherry-pick,
                                                         the rebase/am pair, AND the
                                                         mixed-case redirect, which happens
                                                         to be spelled on a push
  stop scanning at the first token (never look past
    a chained command)                                -> 2 red: the chain and the
                                                         substitution. NOT the absolute-path
                                                         case, which is already first -- the
                                                         reasoned map claimed it was
  swallow the parse error silently (return 0 with no
    stderr)                                           -> 1 red: the unbalanced quote, which
                                                         asserts the guard SAYS it did not
                                                         check -- allowing quietly and
                                                         allowing loudly must not look alike

🔴 THE SURVIVOR IS THE FINDING, and it is the reason this file has a case that looks
pointless. Dropping the value-swallowing test reddened NOTHING across the first 27 cases.
The quoted-message case does not cover it: the shell tokenizer already makes a quoted
message one word, so that case passes with the test gone. The branch was live, load-bearing
and reading as tested. `git commit -m --no-verify` -- an option whose value is the flag
spelled bare -- is the only shape that reaches it, and it was added afterwards. ⚠ Two
defences over the same rule can leave one of them uncovered while the file stays green,
and only running the mutation shows which.
"""

import json
import os
import subprocess
import sys

# The mutation runs point this at a deliberately-broken copy. Nothing else sets it, and the
# default is the real hook -- so a normal run tests the real thing.
HOOK = os.environ.get(
    "LWG_HOOK_UNDER_TEST", "/Users/alwg/trading/.claude/hooks/block_hook_bypass.py"
)

BLOCKED = 2
ALLOWED = 0


def run(command):
    p = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stderr


# Each case: what it is, the command, and the verdict it must produce.
CASES = [
    # ── The refusals ──────────────────────────────────────────────────────────
    (
        "the flag on commit, long form",
        'git commit -m "x" --no-verify',
        lambda code, err: code == BLOCKED and "NO trace" in err,
    ),
    (
        "the flag on commit, short form",
        'git commit -n -m "x"',
        lambda code, err: code == BLOCKED,
    ),
    (
        "the short form clustered behind another flag -- reads like a typo",
        'git commit -an -m "x"',
        lambda code, err: code == BLOCKED,
    ),
    (
        "the short form clustered behind sign-off",
        'git commit -sn -m "x"',
        lambda code, err: code == BLOCKED,
    ),
    (
        "the flag on push",
        "git push --no-verify origin main",
        lambda code, err: code == BLOCKED and "git push" in err,
    ),
    (
        "the flag on merge",
        "git merge --no-verify feature",
        lambda code, err: code == BLOCKED and "git merge" in err,
    ),
    (
        "the flag on cherry-pick",
        "git cherry-pick --no-verify abc123",
        lambda code, err: code == BLOCKED and "git cherry-pick" in err,
    ),
    (
        "the flag on rebase and on am",
        "git rebase --no-verify main && git am --no-verify p.patch",
        lambda code, err: code == BLOCKED and "git rebase" in err,
    ),
    (
        "the hooks folder redirected for one command",
        "git -c core.hooksPath=/dev/null commit -m x",
        lambda code, err: code == BLOCKED and "different hooks folder" in err,
    ),
    (
        "the same redirect spelled in mixed case -- git reads config names either way",
        "git -c core.HOOKSPATH=/dev/null push",
        lambda code, err: code == BLOCKED and "different hooks folder" in err,
    ),
    (
        "the same redirect with the value attached to the flag",
        "git -ccore.hooksPath=/dev/null commit -m x",
        lambda code, err: code == BLOCKED and "different hooks folder" in err,
    ),
    (
        "the flag on the SECOND command in a chain",
        'ls && git commit --no-verify -m "x"',
        lambda code, err: code == BLOCKED,
    ),
    (
        "the flag inside a command substitution",
        "$(git commit --no-verify)",
        lambda code, err: code == BLOCKED,
    ),
    (
        "git reached by its absolute path",
        "/usr/bin/git commit --no-verify",
        lambda code, err: code == BLOCKED,
    ),
    (
        "the flag after an option that swallows the next word",
        "git commit -F /tmp/msg --no-verify",
        lambda code, err: code == BLOCKED,
    ),
    # ── The silences ──────────────────────────────────────────────────────────
    (
        "an ordinary commit -- must stay silent",
        'git commit -m "fix(chart): correct a typo"',
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "an ordinary push -- must stay silent",
        "git push origin main",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "a commit message that QUOTES the flag -- must stay silent",
        'git commit -m "do not use --no-verify to get past the hook"',
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "a message whose text is the letter the short flag uses -- must stay silent",
        "git commit -mn",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        # The ONLY case the value-swallowing test covers. Without it this mutation survived
        # every other case in the file: the tokenizer already makes a QUOTED message one
        # word, so the quoted-message case below defends a different spelling and left this
        # branch uncovered and reading as tested.
        "an option's value is the flag spelled bare -- must stay silent",
        "git commit -m --no-verify",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "the same, spelled with an equals sign -- must stay silent",
        "git commit --message=--no-verify",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "a pathspec after the end-of-options marker -- must stay silent",
        "git commit -- --no-verify",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "a subcommand that ignores the flag entirely -- must stay silent",
        "git status --no-verify",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "the redirect on a subcommand that runs no hooks anyway -- must stay silent",
        "git -c core.hooksPath=/dev/null status",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "the repo's own documented pre-push skip -- deliberately allowed, it leaves a trace",
        "LWG_SKIP_PREPUSH=1 git push origin main",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "the flag sitting in a shell comment -- must stay silent",
        'git commit -m "x" # never pass --no-verify here',
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "a command with no git in it at all -- must stay silent",
        "npm run build && pytest -q",
        lambda code, err: code == ALLOWED and err == "",
    ),
    (
        "reading the log -- must stay silent",
        "git log --oneline -20",
        lambda code, err: code == ALLOWED and err == "",
    ),
    # ── Failing open, and saying so ───────────────────────────────────────────
    (
        "a command it cannot tokenize -- allowed, and it SAYS it did not check",
        'git commit -m "unbalanced quote',
        lambda code, err: code == ALLOWED and "NOT CHECKED" in err,
    ),
]

fails = 0
for name, command, want in CASES:
    code, err = run(command)
    ok = want(code, err)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails += 1
        print(f"        got: exit={code} stderr={err.strip()[:160]!r}")

print()
sys.exit(1 if fails else print("all cases as expected") or 0)
