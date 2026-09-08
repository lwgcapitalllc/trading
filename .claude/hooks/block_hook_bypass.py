#!/usr/bin/env python3
"""Refuse a git command that switches this repo's own git hooks off.

CLAUDE.md has said "never bypass the commit hook" since 2026-08-04, and until now nothing
could enforce it. Git cannot: the bypass flag tells git to skip its hooks, so the hook that
would object never runs. A pre-commit refusal is unreachable by construction. The only
place left is BEFORE git is invoked at all, which is here.

Why it is worth a hook rather than a rule. The docs check and the evidence-line check are
the two things standing between a code change and a doc nobody wrote, and both live in
`commit-msg`. A bypass skips both, leaves NO trace in the history, and the next reader
cannot tell a deliberate skip from a forgotten one -- which is the entire failure the hooks
were built to stop. The honest skip has always been a "DOCS: none - <reason>" line in the
message, and it costs one sentence.

Two spellings are refused, because they do the same damage:

  * the flag on commit / push / merge / cherry-pick / rebase / am, in its long form and in
    the short form that clusters with other short flags -- `git commit -an` is `-a` plus
    the bypass, and reads like a typo rather than a decision;
  * pointing git at a different hooks folder for one command, which runs no hook at all
    while looking perfectly innocent in the shell history.

NOT refused, deliberately: the repo's own documented pre-push skip, which is an environment
variable that prints a loud line and has no silent form. The objection here is to skipping
WITHOUT A TRACE, never to skipping.

⚠ It FAILS OPEN, and it says so out loud when it does. A guard that cannot parse a command
must not stop the work -- but this one BLOCKS rather than advises, so a silent failure would
leave "the check passed" and "the check never ran" looking identical, which is the mistake
this repo has already paid for twice. On any unexpected error it allows the command and
writes one line saying it did not check.

Ported from `block-no-verify.js` in github.com/affaan-m/ecc (MIT), rewritten against the
standard library's shell tokenizer rather than the original's hand-rolled scanner. Python
because the other two hooks here are, and a hook is a bad place to acquire a second runtime.
Proof: `.claude/hooks/check_no_verify.py`, step 13 of `scripts/run_all_tests.sh`.
"""

import json
import os
import shlex
import sys

# The subcommands that accept the bypass flag. Everything else git can do ignores it, and a
# guard that fires on a command the flag does not even apply to is a guard people switch off.
BYPASSABLE = {"commit", "push", "merge", "cherry-pick", "rebase", "am"}

# Git's own options, before the subcommand, that swallow the following word. They matter
# because the word they swallow must not be read as the subcommand.
GLOBAL_FLAGS_TAKING_A_VALUE = {
    "-c",
    "-C",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--exec-path",
    "--super-prefix",
}

# Git config names are case-insensitive, so the candidate is lowercased before comparing.
HOOKS_PATH_SETTING = "core.hookspath="

# Options of `git commit` that swallow the following word. Without these, a commit message
# quoting the flag would be read as the flag itself.
COMMIT_FLAGS_TAKING_A_VALUE = {
    "-m",
    "--message",
    "-F",
    "--file",
    "-C",
    "--reuse-message",
    "-c",
    "--reedit-message",
    "-t",
    "--template",
    "--author",
    "--date",
    "--fixup",
    "--squash",
    "--pathspec-from-file",
    "--trailer",
    "--cleanup",
    "--gpg-sign",
}

# The short forms of the above. A cluster stops being flags at the first of these, because
# git reads the remainder of the cluster as that option's value -- the n in `-mn` is message
# text, not the bypass.
COMMIT_SHORT_FLAGS_TAKING_A_VALUE = set("mFCct")

# Characters a shell may leave attached to a command word: substitution, grouping, quoting.
CLINGING = "$`(){}<>;|&"

BLOCK_EXIT = 2


def _looks_like_git(token):
    """Is this token an invocation of git, however it was spelled or wrapped?"""
    word = token.strip(CLINGING)
    word = os.path.basename(word.replace("\\", "/"))
    if word.lower().endswith(".exe"):
        word = word[:-4]
    return word.lower() == "git"


def _is_operator(token):
    """Does this token end the current command?"""
    return token != "" and all(c in ";|&()\n" for c in token)


def _short_cluster_is_the_bypass(token):
    """Is `-n` hiding inside a cluster of short flags?

    It need not lead: `git commit -an` is `-a` plus the bypass and reads like a typo.
    Scanning stops at the first short option that takes a value, because git reads
    everything after it as that value.
    """
    if not token.startswith("-") or token.startswith("--") or token == "-":
        return False
    for char in token[1:]:
        if char == "n":
            return True
        if char in COMMIT_SHORT_FLAGS_TAKING_A_VALUE:
            return False
    return False


def _short_cluster_takes_a_value(token):
    """Does this cluster of short flags swallow the following word?

    Only when the value-taking option is LAST -- `-mn` carries its own value inline, so the
    next word is a fresh argument rather than the message.
    """
    if not token.startswith("-") or token.startswith("--") or token == "-":
        return False
    for i, char in enumerate(token[1:]):
        if char in COMMIT_SHORT_FLAGS_TAKING_A_VALUE:
            return i == len(token) - 2
    return False


def _takes_a_value(token, subcommand):
    """Does this option swallow the following word?"""
    if subcommand != "commit":
        return False
    if _short_cluster_is_the_bypass(token):
        return False
    if token in COMMIT_FLAGS_TAKING_A_VALUE:
        return True
    return _short_cluster_takes_a_value(token)


def _carries_its_value_inline(token, subcommand):
    """Is this option's value attached with an equals sign, or inside the cluster?"""
    if subcommand != "commit":
        return False
    if _short_cluster_is_the_bypass(token):
        return False
    if token.startswith("--") and "=" in token:
        return token.split("=", 1)[0] in COMMIT_FLAGS_TAKING_A_VALUE
    if token.startswith("-") and not token.startswith("--"):
        for i, char in enumerate(token[1:]):
            if char in COMMIT_SHORT_FLAGS_TAKING_A_VALUE:
                return i < len(token) - 2
    return False


def _verdict(command):
    """Return the refusal for this shell command, or None to allow it.

    Raises on a command it cannot tokenize, so the caller can fail open LOUDLY rather than
    letting an unparseable command read as a checked one.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    tokens = list(lexer)

    for start, token in enumerate(tokens):
        if not _looks_like_git(token):
            continue

        end = len(tokens)
        for j in range(start + 1, len(tokens)):
            if _is_operator(tokens[j]):
                end = j
                break

        # Walk git's own options to find the subcommand, and notice a redirected hooks
        # folder on the way past.
        hooks_path_redirected = False
        subcommand = None
        k = start + 1
        while k < end:
            word = tokens[k]
            if word in GLOBAL_FLAGS_TAKING_A_VALUE:
                value = tokens[k + 1] if k + 1 < end else ""
                if word == "-c" and value.lower().startswith(HOOKS_PATH_SETTING):
                    hooks_path_redirected = True
                k += 2
                continue
            if word.startswith("-c") and word[2:].lower().startswith(HOOKS_PATH_SETTING):
                hooks_path_redirected = True
                k += 1
                continue
            if word.startswith("-"):
                k += 1
                continue
            subcommand = word
            k += 1
            break

        if subcommand not in BYPASSABLE:
            continue

        if hooks_path_redirected:
            return (
                "REFUSED: this points git at a different hooks folder, so `git %s` would "
                "run none of this repo's hooks and leave nothing in the history to say so.\n"
                "The docs check and the evidence-line check both live in that folder. If "
                "this commit genuinely needs no doc update, say so IN the message with a "
                "`DOCS: none - <reason>` line -- that is the skip that leaves a trace." % subcommand
            )

        skip_next = False
        for word in tokens[k:end]:
            if skip_next:
                skip_next = False
                continue
            if word == "--":
                break
            if _takes_a_value(word, subcommand):
                skip_next = True
                continue
            if _carries_its_value_inline(word, subcommand):
                continue
            if word == "--no-verify" or (
                subcommand == "commit" and _short_cluster_is_the_bypass(word)
            ):
                return (
                    "REFUSED: `git %s` here would skip this repo's git hooks and leave NO "
                    "trace that it did.\nThe next reader cannot tell a deliberate skip from "
                    "a forgotten one, which is the whole reason the hooks exist. If this "
                    "commit genuinely needs no doc update, say so IN the message with a "
                    "`DOCS: none - <reason>` line." % subcommand
                )

    return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        command = payload.get("tool_input", {}).get("command", "")
    except Exception:
        sys.stderr.write(
            "[hook-bypass guard] could not read the command - NOT CHECKED, allowing.\n"
        )
        return 0

    if not command:
        return 0

    try:
        refusal = _verdict(command)
    except Exception as exc:
        # Fails open, and says so. "Passed" and "never ran" must never look the same.
        sys.stderr.write(
            "[hook-bypass guard] could not parse this command (%s) - NOT CHECKED, allowing.\n" % exc
        )
        return 0

    if refusal:
        sys.stderr.write(refusal + "\n")
        return BLOCK_EXIT
    return 0


if __name__ == "__main__":
    sys.exit(main())
