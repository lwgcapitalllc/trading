#!/usr/bin/env python3
"""PreToolUse guard — speak up before Claude edits a file where a mistake is expensive.

Why this exists
---------------
Two of this repo's costliest incidents were ordinary-looking edits:

  * A frozen `deployed/` snapshot is what a LIVE bot imports from. Editing it changes what
    a running bot trades, right now, with no promote step and no restart. The whole point of
    the snapshot is that a `git pull` cannot move a deployment — an edit here defeats that.
  * A canonical `engines/` module is imported by every consumer. A "routine tidy-up" of a
    shared default would have silently moved the A+ bot's trades with no test failing.

Nothing here blocks ordinary work. `deployed/` asks first, because it is the one path where
the right answer is almost always "you meant to promote instead". Everything else just puts
the relevant rule in front of Claude at the moment it matters, rather than 40,000 words away.

Wired from `.claude/settings.json` → hooks → PreToolUse (Edit|Write|NotebookEdit).
Fails OPEN: any error here allows the edit. A broken guard must not stop the work.
"""

import json
import os
import sys

# A CLAUDE.md over this many bytes gets a "drain it into HISTORY.md" reminder.
#
# MEASURED, not guessed (2026-08-12, `wc -c` over all 28 CLAUDE.md files). The sizes fall
# into two clumps with a wide empty gap between them: every engine and small subsystem file
# lands at 27 KB or below, and the next file up is 63 KB. Nothing sits between. 40 KB is the
# middle of that gap, so a file has to be genuinely in the bloated clump to trip it — no file
# is near enough the line for a paragraph or two to flip it either way.
CLAUDE_MD_CEILING_BYTES = 40_000


def relative(path: str) -> str:
    marker = "/trading/"
    i = path.find(marker)
    return path[i + len(marker) :] if i != -1 else path


def edit_delta(tool_input: dict) -> int:
    """How many bytes this edit ADDS to the file. Negative means it shrinks.

    Returns 0 when the shape is unknown, which reads as "not growing" and stays quiet —
    the guard's job is to catch growth, and guessing on an unfamiliar tool shape would
    reintroduce exactly the nagging this replaced.
    """
    if "content" in tool_input:  # Write — full replacement
        try:
            old = os.path.getsize(tool_input.get("file_path", ""))
        except OSError:
            old = 0
        return len(str(tool_input["content"]).encode("utf-8")) - old
    if "new_string" in tool_input:  # Edit
        new = len(str(tool_input.get("new_string", "")).encode("utf-8"))
        old = len(str(tool_input.get("old_string", "")).encode("utf-8"))
        n = 1
        if tool_input.get("replace_all"):
            try:
                with open(tool_input.get("file_path", ""), encoding="utf-8") as fh:
                    n = max(1, fh.read().count(str(tool_input.get("old_string", ""))))
            except (OSError, ValueError):
                n = 1
        return (new - old) * n
    return 0


def oversized_claude_md(path: str, tool_input: dict) -> str:
    """The reminder for an oversized CLAUDE.md that this edit is about to make BIGGER.

    Fires at the moment of the EDIT, deliberately. A commit-time warning arrives when the
    work is finished and nobody stops to refactor a doc; this one arrives while the file is
    open and the context is already loaded.

    🔴 It fires on GROWTH, not on size, and that changed on 2026-08-13 after the ceiling's
    first real cleanup. Warning on size alone meant ten files tripped it on every single
    edit, including the ones that are legitimately large: ChartPanel/CLAUDE.md is 122 KB and
    only ~3% of it is movable narrative — the rest is dense engineering reference with
    measured reasons attached. A guard that fires on work it should not be criticising is a
    guard people learn to dismiss, and a dismissed guard is worth less than none, because
    the next reader assumes silence means checked. So a trim now passes in silence and only
    an edit that ADDS bytes to an already-oversized file has to justify itself.
    """
    if os.path.basename(path) != "CLAUDE.md":
        return ""
    try:
        size = os.path.getsize(path)
    except OSError:
        return ""  # a new file, or unreadable — nothing to complain about
    if size <= CLAUDE_MD_CEILING_BYTES:
        return ""
    delta = edit_delta(tool_input)
    if delta <= 0:
        return ""  # shrinking or neutral — this is the direction we want, say nothing
    return (
        f"This CLAUDE.md is already {size // 1000} KB, over the "
        f"{CLAUDE_MD_CEILING_BYTES // 1000} KB ceiling, and this edit adds roughly "
        f"{delta} more bytes. Every one of them loads into context whenever anyone works in "
        "this subsystem. Before adding: is what you are writing a RULE, or is it the story "
        "of what happened today? The story belongs in the sibling BUILD_NOTES/HISTORY file "
        "with a pointer left behind. Two hard rules if you drain some while you are here — "
        "(1) a fact lives in exactly ONE CLAUDE.md, the one next to the code it describes, "
        "because a parent keeping its own copy is how three files came to disagree about "
        "whether a bot was live; (2) the rule and the reason it exists stay together, since "
        "a rule with no incident behind it reads as arbitrary and gets 'tidied up' by the "
        "next reader."
    )


def subsystem_matches(fragment: str, rel: str) -> bool:
    """Does this repo-relative path live under the subsystem this fragment names?

    ANCHORED at the repo root, deliberately, and that is not a tidy-up. Until 2026-08-13
    this was a plain `fragment in path` substring test over the ABSOLUTE path, which was
    fine only because no two subsystems shared a directory name. Splitting the Pine sources
    into `indicators/strategies/` and `indicators/engines/` broke that assumption instantly:
    `indicators/engines/fib_export.pine` contains `/engines/`, so a Pine file would have
    been told it is a canonical Python engine and must not be committed until its
    `compare_*.py` gate passes — advice aimed at the OTHER half of that gate. Same for
    `/strategies/` and the "what a bot actually trades" reminder.

    That matters more than the miss itself. A guard that fires on work it should not be
    criticising is a guard people learn to dismiss, and a dismissed guard is worth LESS
    than none, because the next reader takes silence for checked. So a fragment naming a
    top-level subsystem now only matches paths actually under it, and the `.pine` reminder
    — which is about the FILE TYPE, not where it sits — still matches anywhere.
    """
    if fragment.startswith("/"):
        return ("/" + rel).startswith(fragment)
    return fragment in rel


# path fragment -> the reminder that belongs with it.
# A fragment starting with "/" names a TOP-LEVEL subsystem and is anchored at the repo root
# (see `subsystem_matches`). Anything else is a plain substring test — `.pine` is about what
# the file IS, so it fires wherever the file lives.
REMINDERS = [
    (
        "/engines/",
        "This is a CANONICAL engine — every consumer imports it, and a strategy's trades can "
        "move without any test failing. Rule 22: it does not get committed until its "
        "`compare_*.py` gate has actually RUN and passed on a real TradingView export. If no "
        "export exists, say so and stop rather than committing on unit tests alone.",
    ),
    (
        "/algos/live/",
        "This is the LIVE trading loop. Run /live-safety before you finish — units at every "
        "boundary (rule 15), None vs 0.0 (rule 1), what re-checks after startup (rule 16), "
        "and refusal never rounding to fit (rule 17).",
    ),
    (
        "/algos/shared/",
        "This is shared live-path code — order sizing, mt5_ops, account risk. Run /live-safety. "
        "`order_sizing.py` is the ONLY place in the live path a lot count is produced; keep it "
        "that way.",
    ),
    (
        "/backtest/",
        "This decides what every number in the repo MEANS — fills, costs, replay. A change here "
        "can re-price stored runs. Say explicitly whether any documented baseline moves.",
    ),
    (
        ".pine",
        "Pine file. TradingView keys a chart's saved input values off DECLARATION ORDER within "
        "each type — renaming a title is safe, INSERTING or REORDERING an `input.*` call "
        "silently resets every later input on Aaron's live charts. Add new inputs after the "
        "last one of their type. This is also half of a parity gate: the export twin has to "
        "move with its parent.",
    ),
    (
        "/strategies/",
        "This is what a bot actually trades. If a default moves, every documented baseline "
        "measured before today needs pinning or re-measuring — and whoever moves the inputs "
        "owns re-running the cross-cutting audits (overlap, jitter, parity).",
    ),
]


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return

    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or ""
    if not path:
        return

    rel = relative(path)

    # The one path that asks first. A frozen snapshot is a running bot's source of truth.
    if "/deployed/" in path:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "escalate",
                        "permissionDecisionReason": (
                            f"{rel} is a FROZEN DEPLOYMENT SNAPSHOT — a live bot imports from it. "
                            "Editing it changes what a running bot trades immediately, with no promote "
                            "and no restart, and it defeats the isolation that makes `git pull` safe. "
                            "The deliberate path is: edit the repo, then run algos/tools/promote.py. "
                            "Only allow this if you genuinely mean to hand-patch a live bot."
                        ),
                    }
                }
            )
        )
        return

    notes = [note for fragment, note in REMINDERS if subsystem_matches(fragment, rel)]

    bloat = oversized_claude_md(path, tool_input)
    if bloat:
        notes.append(bloat)

    if not notes:
        return

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "sensitive path — reminder attached",
                    "additionalContext": (
                        f"Editing {rel}. Before you call this done:\n\n- " + "\n- ".join(notes)
                    ),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail open — a broken guard must never stop the work
