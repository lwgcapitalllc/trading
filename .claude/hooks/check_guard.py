"""Drive real events through the guard and assert what it says.

The guard FAILS OPEN, so its silence proves nothing on its own — that is exactly why it
has to be exercised rather than trusted. Each case below asserts a specific verdict, so a
guard that always warned and a guard that never warned both fail.

Two groups.

  * The PreToolUse cases send a synthetic tool call and assert on the reminder text. They
    need nothing on disk beyond the repo itself.
  * The PostToolUse cases build a THROWAWAY GIT REPO, mutate a CLAUDE.md in it through a
    real `bash -c` — a heredoc, an in-place rewrite — and then ask the guard. They have to
    be real edits through a real shell, because the whole claim being tested is that the
    check does not care HOW the file was written. A fake tool payload would test nothing.

WATCHED RED BY MUTATION — the measured map, which mutation reddens which cases
-----------------------------------------------------------------------------
Rule 12: a test proves nothing until it has been watched go red for the right reason. All
19 cases below were, and every one of them is covered. ⚠ THE MAP WAS RUN, NOT REASONED —
three of the entries first written here from inspection were WRONG, each in the direction
of claiming a mutation was more surgical than it is.

  PreToolUse half
    drop its ceiling test (`size <= CEILING`)     -> 1 red: under the ceiling + big addition
    drop its growth test (`delta <= 0`)           -> 3 red: the three "must stay silent" edits
    make `edit_delta` always report 0             -> 2 red: the Edit and Write that GROW
    remove the `/deployed/` escalation            -> 1 red: deployed snapshot
    empty `REMINDERS`                             -> 5 red: live path, both Pine cases, the
                                                     real engine, the real strategy

  PostToolUse half
    remove the dispatch (the half never runs)     -> 4 red: heredoc growth, ceiling crossing,
                                                     no-nag, new file
    drop its growth test (`s > head[p]`)          -> 4 red: sed shrink, under-ceiling Bash,
                                                     touched-nothing, AND the new-file case.
                                                     The fixture's oversized file is
                                                     unchanged in all four, so warning on
                                                     size alone fires on it every time
    drop its ceiling test                         -> 1 red: under-ceiling Bash
    drop the session memory (`p not in seen`)     -> 1 red: no-nag
    count a missing HEAD version as huge, not 0   -> 1 red: the new oversized file

Both directions are asserted throughout, so a guard that always warned dies on the silence
cases and a guard that never warned dies on the warning ones. Neither can pass this file.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = "/Users/alwg/trading/.claude/hooks/guard_sensitive_paths.py"
BIG = "/Users/alwg/trading/command-center/backend/CLAUDE.md"  # 282 KB, over the ceiling
SMALL = "/Users/alwg/trading/engines/vwap/CLAUDE.md"  # well under it
LIVE = "/Users/alwg/trading/algos/live/runner.py"


def run(tool_input):
    p = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps({"tool_input": tool_input}),
        capture_output=True,
        text=True,
    )
    if not p.stdout.strip():
        return ""
    out = json.loads(p.stdout)["hookSpecificOutput"]
    return out.get("additionalContext", "") or out.get("permissionDecisionReason", "")


CASES = [
    (
        "oversized + edit GROWS it",
        {"file_path": BIG, "old_string": "x", "new_string": "x" + "y" * 500},
        lambda s: "over the" in s and "adds roughly" in s,
    ),
    (
        "oversized + edit SHRINKS it — must stay silent",
        {"file_path": BIG, "old_string": "y" * 500, "new_string": "y"},
        lambda s: "ceiling" not in s,
    ),
    (
        "oversized + edit is size-NEUTRAL — must stay silent",
        {"file_path": BIG, "old_string": "abcd", "new_string": "wxyz"},
        lambda s: "ceiling" not in s,
    ),
    (
        "oversized + Write that SHRINKS it — must stay silent",
        {"file_path": BIG, "content": "tiny"},
        lambda s: "ceiling" not in s,
    ),
    (
        "oversized + Write that GROWS it",
        {"file_path": BIG, "content": "z" * 400_000},
        lambda s: "adds roughly" in s,
    ),
    (
        "under the ceiling + big addition — must stay silent",
        {"file_path": SMALL, "old_string": "x", "new_string": "x" * 5000},
        lambda s: "ceiling" not in s,
    ),
    (
        "live path still gets its own reminder",
        {"file_path": LIVE, "old_string": "a", "new_string": "b"},
        lambda s: "/live-safety" in s,
    ),
    (
        "deployed snapshot still escalates",
        {
            "file_path": "/Users/alwg/trading/algos/markets/fx/instances/x/deployed/config.py",
            "old_string": "a",
            "new_string": "b",
        },
        lambda s: "FROZEN DEPLOYMENT SNAPSHOT" in s,
    ),
    # The subsystem reminders are anchored at the repo root. Before 2026-08-13 they were a
    # substring test over the absolute path, so the two Pine cases below were told they were
    # canonical Python code. Both halves are asserted: the Pine files must NOT get the Python
    # subsystem advice, and the real Python subsystems must still get it.
    (
        "Pine ENGINE source is not a canonical Python engine",
        {
            "file_path": "/Users/alwg/trading/indicators/engines/fib_export.pine",
            "old_string": "a",
            "new_string": "b",
        },
        lambda s: "CANONICAL engine" not in s and "Pine file" in s,
    ),
    (
        "Pine STRATEGY source is not a deployed Python strategy",
        {
            "file_path": "/Users/alwg/trading/indicators/strategies/mpc_strategy.pine",
            "old_string": "a",
            "new_string": "b",
        },
        lambda s: "what a bot actually trades" not in s and "Pine file" in s,
    ),
    (
        "a real canonical engine still gets its reminder",
        {
            "file_path": "/Users/alwg/trading/engines/vwap/engine.py",
            "old_string": "a",
            "new_string": "b",
        },
        lambda s: "CANONICAL engine" in s,
    ),
    (
        "a real deployed strategy still gets its reminder",
        {
            "file_path": "/Users/alwg/trading/strategies/python/mpc_sos_fade/config.py",
            "old_string": "a",
            "new_string": "b",
        },
        lambda s: "what a bot actually trades" in s,
    ),
]

fails = 0
for name, tool_input, want in CASES:
    got = run(tool_input)
    ok = want(got)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails += 1
        print(f"        got: {got[:180]!r}")


# ---------------------------------------------------------------------------
# PostToolUse — the backstop that measures the FILE, so it sees a Bash edit too.
# ---------------------------------------------------------------------------
#
# These cases build a real throwaway git repo and edit it through a real shell. That is not
# ceremony: the claim under test is precisely that the check does not care HOW the file was
# written, and a synthetic tool payload would prove nothing about a heredoc.

BIG_LINES = 1000  # ~62 KB — comfortably over the ceiling
MID_LINES = 560  # ~34 KB — UNDER the ceiling, and one good session away from crossing it
SMALL_LINES = 80  # ~5 KB — comfortably under it


def _lines(count, tag):
    return "".join("%s %04d %s\n" % (tag, i, "x" * 50) for i in range(count))


def fixture():
    """A throwaway repo: one oversized CLAUDE.md, one small one, one unrelated file.

    Everything is COMMITTED, so HEAD has a size for each and nothing is "grown" until a
    case grows it. A fixture that started dirty would make every silence case vacuous.
    """
    root = tempfile.mkdtemp(prefix="guard-fixture-")
    built = (
        ("big", _lines(BIG_LINES, "line")),
        ("mid", _lines(MID_LINES, "line")),
        ("small", _lines(SMALL_LINES, "line")),
    )
    for sub, body in built:
        os.makedirs(os.path.join(root, sub))
        with open(os.path.join(root, sub, "CLAUDE.md"), "w", encoding="utf-8") as fh:
            fh.write(body)
    with open(os.path.join(root, "note.txt"), "w", encoding="utf-8") as fh:
        fh.write("nothing to do with docs\n")
    git = [
        "git",
        "-C",
        root,
        "-c",
        "user.email=t@t",
        "-c",
        "user.name=t",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
    subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
    subprocess.run(git + ["commit", "-qm", "fixture"], check=True, capture_output=True)
    return root


def shell(root, command):
    """Make the edit the way a person would — through bash, not through a tool payload."""
    subprocess.run(["bash", "-c", command], cwd=root, check=True, capture_output=True)


def run_post(root, session_id):
    p = subprocess.run(
        [sys.executable, HOOK],
        input=json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "session_id": session_id,
                "cwd": root,
                "tool_name": "Bash",
                "tool_input": {"command": "..."},
            }
        ),
        capture_output=True,
        text=True,
        cwd=root,
    )
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"].get("additionalContext", "")


GROW_BIG = "cat >> big/CLAUDE.md <<'EOF'\n" + _lines(200, "added") + "EOF\n"
# `sed -i.bak` rather than a bare `-i`: BSD sed needs the suffix, GNU sed accepts it, so the
# same case runs on either machine. It deletes ~100 lines and the file STAYS oversized —
# a shrink that dropped it under the ceiling would pass for the wrong reason.
SHRINK_BIG = "sed -i.bak '/line 09/d' big/CLAUDE.md && rm -f big/CLAUDE.md.bak"
GROW_SMALL = "cat >> small/CLAUDE.md <<'EOF'\n" + _lines(30, "added") + "EOF\n"
CROSS_MID = "cat >> mid/CLAUDE.md <<'EOF'\n" + _lines(200, "added") + "EOF\n"
BORN_BIG = (
    "mkdir -p brandnew && cat > brandnew/CLAUDE.md <<'EOF'\n" + _lines(BIG_LINES, "line") + "EOF\n"
)


def case_grows(session):
    root = fixture()
    shell(root, GROW_BIG)
    return root, [run_post(root, session)]


def case_shrinks(session):
    root = fixture()
    shell(root, SHRINK_BIG)
    return root, [run_post(root, session)]


def case_small(session):
    root = fixture()
    shell(root, GROW_SMALL)
    return root, [run_post(root, session)]


def case_crosses(session):
    root = fixture()
    shell(root, CROSS_MID)
    return root, [run_post(root, session)]


def case_untouched(session):
    root = fixture()
    shell(root, "echo more >> note.txt")
    return root, [run_post(root, session)]


def case_twice(session):
    root = fixture()
    shell(root, GROW_BIG)
    first = run_post(root, session)
    shell(root, GROW_BIG)  # grew again — still must not repeat itself
    return root, [first, run_post(root, session)]


def case_new_file(session):
    root = fixture()
    shell(root, BORN_BIG)
    return root, [run_post(root, session)]


GREW = "bigger than the committed version"

POST_CASES = [
    (
        "Bash heredoc GROWS an oversized CLAUDE.md — the hole this closes",
        case_grows,
        lambda out: GREW in out[0] and "big/CLAUDE.md" in out[0],
    ),
    (
        "Bash `sed -i` SHRINKS an oversized CLAUDE.md — must stay silent",
        case_shrinks,
        lambda out: out[0] == "",
    ),
    (
        "Bash edit to a CLAUDE.md UNDER the ceiling — must stay silent",
        case_small,
        lambda out: out[0] == "",
    ),
    (
        "an edit that CROSSES the ceiling in one go — the hole the pre-edit check never saw",
        case_crosses,
        lambda out: GREW in out[0] and "mid/CLAUDE.md" in out[0],
    ),
    (
        "Bash command touching no CLAUDE.md at all — must stay silent",
        case_untouched,
        lambda out: out[0] == "",
    ),
    (
        "same oversized file twice in one session — warns once, then silent",
        case_twice,
        lambda out: GREW in out[0] and out[1] == "",
    ),
    (
        "an untracked CLAUDE.md BORN over the ceiling — warns once, and says it is NEW",
        case_new_file,
        lambda out: "brandnew/CLAUDE.md is NEW and already" in out[0] and GREW not in out[0],
    ),
]

for i, (name, build, want) in enumerate(POST_CASES):
    session = "guard-harness-%d-%d" % (os.getpid(), i)
    root = None
    try:
        root, out = build(session)
        ok = want(out)
    finally:
        if root:
            shutil.rmtree(root, ignore_errors=True)
        state = os.path.join(tempfile.gettempdir(), "lwg-claude-md-size-guard", "%s.json" % session)
        if os.path.exists(state):
            os.remove(state)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails += 1
        print(f"        got: {[s[:160] for s in out]!r}")

print()
sys.exit(1 if fails else print("all cases as expected") or 0)
