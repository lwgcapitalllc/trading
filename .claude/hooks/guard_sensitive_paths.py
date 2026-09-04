#!/usr/bin/env python3
"""Guard — speak up when Claude touches a file where a mistake is expensive.

Two halves, two hook events, and the split is the point.

  * PreToolUse (Edit|Write|NotebookEdit) — the original. Reads the pending edit's own
    delta out of the tool call and warns BEFORE it lands, while the file is open and the
    context is loaded. That timing is the only reason it ever changes what happens.
  * PostToolUse (any tool) — the backstop, added 2026-08-21. Measures the FILE: current
    bytes on disk against bytes at HEAD. It sees an edit made ANY way at all, including
    the ways the first half is structurally blind to. See the block above `STATE_DIR`.

Why this exists
---------------
Two of this repo's costliest incidents were ordinary-looking edits:

  * A frozen `deployed/` snapshot is what a LIVE bot imports from. Editing it changes what
    a running bot trades, right now, with no promote step and no restart. The whole point of
    the snapshot is that a `git pull` cannot move a deployment — an edit here defeats that.
  * A canonical `engines/` module is imported by every consumer. A "routine tidy-up" of a
    shared default would have silently moved the SOS Fade bot's trades with no test failing.

Nothing here blocks ordinary work. `deployed/` asks first, because it is the one path where
the right answer is almost always "you meant to promote instead". Everything else just puts
the relevant rule in front of Claude at the moment it matters, rather than 40,000 words away.

Wired from `.claude/settings.json` → hooks → PreToolUse (Edit|Write|NotebookEdit) and
PostToolUse (*). Proven by `.claude/hooks/check_guard.py`.
Fails OPEN: any error here allows the edit. A broken guard must not stop the work.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

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

    🔴 It judges the size the file is ABOUT TO BE, not the size it is, and that changed on
    2026-08-21 after an audit of all 33 CLAUDE.md files over their full history. Until then
    it read the size BEFORE the edit — so on the edit that took a doc OVER the ceiling the
    doc was still under it, and this said nothing. **It only ever complained about files
    that were already a problem, which is the moment it can do least good.** MEASURED: every
    one of the 11 oversized docs crossed from below and NOT ONE was warned at the crossing;
    two of those crossings happened with this guard live and silent (the Pine strategy
    sources 38,766 -> 69,605 in one commit on 2026-08-16, and loss_recovery 26,745 -> 41,391
    on 2026-08-21). Adding the pending edit's own bytes is the whole fix, and it costs no
    extra nagging: a file well under the ceiling still has to be handed an edit big enough
    to cross before it hears anything.

    ⚠ A file that does not exist yet counts as 0 bytes rather than being skipped, so a Write
    that CREATES an oversized CLAUDE.md warns. That matches what the PostToolUse half does
    with a doc that has no committed version, deliberately — the two halves disagreeing
    about what a new file means is how somebody ends up trusting the quieter one.
    """
    if os.path.basename(path) != "CLAUDE.md":
        return ""
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0  # does not exist yet — this edit is creating it
    delta = edit_delta(tool_input)
    if delta <= 0:
        return ""  # shrinking or neutral — this is the direction we want, say nothing
    after = size + delta
    if after <= CLAUDE_MD_CEILING_BYTES:
        return ""
    ceiling = CLAUDE_MD_CEILING_BYTES // 1000
    if size > CLAUDE_MD_CEILING_BYTES:
        opening = (
            f"This CLAUDE.md is already {size // 1000} KB, over the {ceiling} KB ceiling, "
            f"and this edit adds roughly {delta} more bytes."
        )
    elif size == 0:
        opening = (
            f"This edit CREATES a CLAUDE.md of roughly {after // 1000} KB, already over the "
            f"{ceiling} KB ceiling."
        )
    else:
        opening = (
            f"This CLAUDE.md is {size // 1000} KB and this edit would take it to roughly "
            f"{after // 1000} KB, CROSSING the {ceiling} KB ceiling. This is the one moment "
            "the crossing can still be prevented."
        )
    return (
        opening + " Every byte of it loads into context whenever anyone works in "
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
    `compare_*.py` gate passes — advice aimed at the OTHER half of that gate. That is still
    the live example: `indicators/engines/` exists and its files must not collect the
    canonical-engine reminder.

    That matters more than the miss itself. A guard that fires on work it should not be
    criticising is a guard people learn to dismiss, and a dismissed guard is worth LESS
    than none, because the next reader takes silence for checked. So a fragment naming a
    top-level subsystem now only matches paths actually under it, and the `.pine` reminder
    — which is about the FILE TYPE, not where it sits — still matches anywhere.

    🔴 THE OTHER HALF OF THAT 2026-08-13 EXAMPLE IS GONE, AND A MOVE IS WHY. `/strategies/`
    used to be the twin case: `indicators/strategies/sos_fade_strategy.pine` contained
    `/strategies/` and was wrongly told it was what a bot actually trades. On 2026-09-02
    those files MOVED to `strategies/tradingview/`, so they are now genuinely under the
    top-level `strategies/` and collect that reminder on purpose — a Pine strategy is half
    of a parity gate, so a default moving in one really does invalidate every baseline
    measured before today.

    ⚠ THE STANDING LESSON SURVIVES ITS OWN EXAMPLE, AND IS NOW TWICE PROVEN: A DIRECTORY
    MOVE SILENTLY RE-AIMS THIS FUNCTION. Nothing fails and no import breaks — the only
    symptom is correct-looking advice about the wrong file, or a case in `check_guard.py`
    that stays green while describing a layout the repo no longer has, which is exactly
    what happened here until that case was pointed at the new path.
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


# ---------------------------------------------------------------------------
# The PostToolUse backstop — measure the FILE, never the tool call.
# ---------------------------------------------------------------------------
#
# 🔴 THE HOLE THIS CLOSES, and it was found by the guard firing on NOTHING.
# `oversized_claude_md` above reads its delta out of the tool call, so it can only see an
# edit made THROUGH Edit or Write. On 2026-08-21 `algos/CLAUDE.md` grew 103,804 -> 106,667
# bytes and `strategies/python/loss_recovery/CLAUDE.md` grew to 41,391 — both already over
# the ceiling — and the guard was silent, because both edits arrived through Bash: a heredoc
# and an in-place rewrite. Nothing failed. The only symptom was silence, and this repo's own
# standing lesson is that the next reader takes silence for checked.
#
# ⚠ THE FIX IS DELIBERATELY NOT A PATTERN MATCH ON THE COMMAND. Sniffing Bash for `>`,
# `sed -i` or a python one-liner is a deny-list against an infinite space of ways to write a
# file: it is wrong quietly, and it goes stale the first time somebody reaches for a tool it
# has never heard of. This measures the FILE — current bytes on disk against the bytes at
# HEAD — which cannot be fooled by HOW the edit was made. That is the whole point.
#
# ⚠ It is a BACKSTOP, not a replacement. The PreToolUse path fires BEFORE the edit, while
# the file is open and the context is loaded, and that timing is the only reason it ever
# changes what happens. This one arrives after the fact, which is worth less — but it is the
# only thing that can see the edits the other path is blind to.

STATE_DIR = os.path.join(tempfile.gettempdir(), "lwg-claude-md-size-guard")


def _git(root: str, *args: str, stdin: str = "") -> str:
    """Run a read-only git command and return stdout, or "" on any failure.

    Every caller treats "" as "cannot ask", and every caller then stays silent — this whole
    path FAILS OPEN. Not a git repo, git missing, no HEAD yet, a timeout: all of them allow
    the action with nothing printed.
    """
    try:
        p = subprocess.run(
            ["git", "-C", root, *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return ""  # git missing, or it hung past the timeout — both mean "cannot ask"
    return p.stdout if p.returncode == 0 else ""


def claude_md_paths(root: str) -> list:
    """Every CLAUDE.md git knows about — tracked AND untracked-but-not-ignored.

    Untracked is included on purpose; see `head_sizes` for what a file with no HEAD version
    is taken to mean.
    """
    out = _git(root, "ls-files", "-c", "-o", "--exclude-standard", "*CLAUDE.md")
    paths = []
    for line in out.splitlines():
        if line and os.path.basename(line) == "CLAUDE.md" and line not in paths:
            paths.append(line)
    return paths


def head_sizes(root: str, paths: list) -> dict:
    """Byte size of each path at HEAD. A path with no HEAD version counts as 0.

    ⚠ THE NEW-FILE DECISION, stated rather than left to be discovered: a CLAUDE.md that has
    never been committed has no previous size, so growth from zero is what it is — a doc
    born over the ceiling costs the next reader exactly the same context a long-bloated one
    does, and "it is new" is not a reason for it to arrive at 50 KB unremarked. So it warns,
    once, the same as any other. The alternative — stay silent until the first commit — puts
    the warning at the one moment the repo has already measured to be useless, when the work
    is finished and nobody stops to refactor a doc.

    One `git cat-file --batch-check` for the whole set, not one call per file. That is not
    tidiness: this runs after EVERY tool call, and a per-file fan-out is the shape that made
    a version endpoint slower every time anybody pushed.
    """
    if not paths:
        return {}
    payload = "".join("HEAD:%s\n" % p for p in paths)
    lines = _git(root, "cat-file", "--batch-check", stdin=payload).splitlines()
    if len(lines) != len(paths):
        return {}  # cannot ask — say nothing rather than guess
    sizes = {}
    for path, line in zip(paths, lines):
        parts = line.split()
        sizes[path] = int(parts[2]) if len(parts) == 3 and parts[1] == "blob" else 0
    return sizes


def _state_file(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "nosession")
    return os.path.join(STATE_DIR, "%s.json" % safe)


def already_warned(session_id: str) -> set:
    try:
        with open(_state_file(session_id), encoding="utf-8") as fh:
            return set(json.load(fh))
    except (OSError, ValueError, TypeError):
        return set()


def remember_warned(session_id: str, warned: set) -> None:
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(_state_file(session_id), "w", encoding="utf-8") as fh:
            json.dump(sorted(warned), fh)
    except (OSError, TypeError):
        pass  # fail open — a guard that cannot remember must not start nagging instead


def grown_oversized_files(root: str, session_id: str) -> list:
    """(path, size_now, size_at_head) for every oversized CLAUDE.md that has GROWN.

    ⚠ GROWTH, never size alone — the same rule the PreToolUse path follows since 2026-08-13.
    A double-figure count of files legitimately sits above the ceiling; warning on size would
    fire on every one of them after every command, including on a trim. A guard that fires on work it should not be
    criticising is one people learn to dismiss.

    ⚠ ONCE PER FILE PER SESSION. This runs after every tool call, so the naive version says
    the same sentence forty times before the file is committed, which is nagging with extra
    steps. The first time is the one that can change anything; the rest is noise. The
    PreToolUse path is still there for every later Edit or Write.
    """
    paths = claude_md_paths(root)
    live = {}
    for path in paths:
        try:
            size = os.path.getsize(os.path.join(root, path))
        except OSError:
            continue
        if size > CLAUDE_MD_CEILING_BYTES:
            live[path] = size
    if not live:
        return []
    head = head_sizes(root, list(live))
    if not head:
        return []
    seen = already_warned(session_id)
    return [(p, s, head[p]) for p, s in sorted(live.items()) if s > head[p] and p not in seen]


def post_tool_use(event: dict) -> None:
    """Report any oversized CLAUDE.md that grew, whatever tool did it."""
    cwd = event.get("cwd") or os.getcwd()
    root = _git(cwd, "rev-parse", "--show-toplevel").strip()
    if not root:
        return
    session_id = event.get("session_id") or "nosession"
    grown = grown_oversized_files(root, session_id)
    if not grown:
        return

    # A never-committed file gets its OWN sentence. Telling somebody a brand-new doc is
    # "N bytes bigger than the committed version" when there is no committed version is the
    # kind of correct-arithmetic-wrong-conclusion line this repo has been bitten by before.
    lines = []
    for path, size, was in grown:
        kb, ceiling = size // 1000, CLAUDE_MD_CEILING_BYTES // 1000
        if was == 0:
            lines.append(
                "%s is NEW and already %d KB, over the %d KB ceiling — there is no committed "
                "version to compare it against." % (path, kb, ceiling)
            )
        else:
            lines.append(
                "%s is now %d KB, over the %d KB ceiling, and %d bytes bigger than the "
                "committed version." % (path, kb, ceiling, size - was)
            )
    remember_warned(session_id, already_warned(session_id) | {p for p, _, _ in grown})

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": (
                        "Documentation size check (this measures the FILE, so it sees edits made "
                        "any way at all — a heredoc, an in-place rewrite, a script):\n\n- "
                        + "\n- ".join(lines)
                        + "\n\nEvery byte loads into context whenever anyone works in that "
                        "subsystem. Before you finish: is what you added a RULE, or is it the "
                        "story of what happened today? The story belongs in the sibling "
                        "BUILD_NOTES/HISTORY file with a pointer left behind. Two hard rules if "
                        "you drain some while you are here — (1) a fact lives in exactly ONE "
                        "CLAUDE.md, the one next to the code it describes; (2) the rule and the "
                        "reason it exists stay together, or the next reader tidies it away. "
                        "Said once per file per session, deliberately — it will not repeat."
                    ),
                }
            }
        )
    )


def pre_tool_use(event: dict) -> None:
    """The original path: warn BEFORE an Edit/Write, from the tool call's own delta."""
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


def main() -> None:
    """One script, two hook events — dispatched on which one fired.

    They are deliberately NOT two files. The ceiling, the "is it a rule or a story" advice
    and the growth rule are one set of facts, and a second copy of any of them is how this
    repo's docs came to disagree with each other in the first place.
    """
    try:
        event = json.loads(sys.stdin.read())
    except (ValueError, TypeError):
        return
    if not isinstance(event, dict):
        return
    if event.get("hook_event_name") == "PostToolUse":
        post_tool_use(event)
        return
    pre_tool_use(event)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # fail open — a broken guard must never stop the work
