"""Drive real events through the guard and assert what it says.

The guard FAILS OPEN, so its silence proves nothing on its own — that is exactly why it
has to be exercised rather than trusted. Each case below asserts a specific verdict, so a
guard that always warned and a guard that never warned both fail.
"""
import json
import subprocess
import sys
from pathlib import Path

HOOK = "/Users/alwg/trading/.claude/hooks/guard_sensitive_paths.py"
BIG = "/Users/alwg/trading/command-center/backend/CLAUDE.md"    # 282 KB, over the ceiling
SMALL = "/Users/alwg/trading/engines/vwap/CLAUDE.md"            # well under it
LIVE = "/Users/alwg/trading/algos/live/runner.py"


def run(tool_input):
    p = subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"tool_input": tool_input}),
                       capture_output=True, text=True)
    if not p.stdout.strip():
        return ""
    out = json.loads(p.stdout)["hookSpecificOutput"]
    return out.get("additionalContext", "") or out.get("permissionDecisionReason", "")


CASES = [
    ("oversized + edit GROWS it",
     {"file_path": BIG, "old_string": "x", "new_string": "x" + "y" * 500},
     lambda s: "over the" in s and "adds roughly" in s),

    ("oversized + edit SHRINKS it — must stay silent",
     {"file_path": BIG, "old_string": "y" * 500, "new_string": "y"},
     lambda s: "ceiling" not in s),

    ("oversized + edit is size-NEUTRAL — must stay silent",
     {"file_path": BIG, "old_string": "abcd", "new_string": "wxyz"},
     lambda s: "ceiling" not in s),

    ("oversized + Write that SHRINKS it — must stay silent",
     {"file_path": BIG, "content": "tiny"},
     lambda s: "ceiling" not in s),

    ("oversized + Write that GROWS it",
     {"file_path": BIG, "content": "z" * 400_000},
     lambda s: "adds roughly" in s),

    ("under the ceiling + big addition — must stay silent",
     {"file_path": SMALL, "old_string": "x", "new_string": "x" * 5000},
     lambda s: "ceiling" not in s),

    ("live path still gets its own reminder",
     {"file_path": LIVE, "old_string": "a", "new_string": "b"},
     lambda s: "/live-safety" in s),

    ("deployed snapshot still escalates",
     {"file_path": "/Users/alwg/trading/algos/markets/fx/instances/x/deployed/config.py",
      "old_string": "a", "new_string": "b"},
     lambda s: "FROZEN DEPLOYMENT SNAPSHOT" in s),
]

fails = 0
for name, tool_input, want in CASES:
    got = run(tool_input)
    ok = want(got)
    print(f"{'ok  ' if ok else 'FAIL'} {name}")
    if not ok:
        fails += 1
        print(f"        got: {got[:180]!r}")

print()
sys.exit(1 if fails else print("all cases as expected") or 0)
