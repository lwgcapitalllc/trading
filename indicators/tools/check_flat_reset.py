#!/usr/bin/env python3
"""Refuse a strategy that clears its own bracket on the bar it opens a trade.

WHAT IT CATCHES, and it cost an account on the first run of `extreme_leg_strategy.pine`:
with `process_orders_on_close = true` an entry is filled AFTER the script has finished running
for that bar, so `strategy.position_size` still reads flat everywhere below the entry. A block
guarded by nothing but `strategy.position_size == 0` therefore fires on the bar the trade was
just opened. If that block clears the stop and target the entry block had just set, the bracket
goes out empty on the following bar: no stop, no target, and — because a new entry needs a flat
book — a position that can never close. Nothing errors and nothing goes red.

THE RULE: a variable given a live value inside a block that calls `strategy.entry`, and set back
to `na` under a bare flat test, is that bug. The fix is a per-bar "just entered" flag in the
reset's guard, which is what `h4_sweep_strategy.pine` has always carried.

DELIBERATELY NARROW. It reads top-level blocks only, it knows nothing about intervening logic,
and it cannot tell you whether a bracket is correct — only that this one shape is absent. Its
silence is one question answered, not a clean bill of health.

WATCHED RED by running it against the version of the strategy that blew the account.

    python3 indicators/tools/check_flat_reset.py strategies/tradingview/*.pine
"""

import re
import sys
from pathlib import Path

# A guard that tests the flat book and nothing that could distinguish the entry bar.
BARE_FLAT = re.compile(r"^if\s+strategy\.position_size\s*==\s*0\s*$")
ASSIGN_NA = re.compile(r"^\s+(\w+)\s*:=\s*na\s*$")
ASSIGN_LIVE = re.compile(r"^\s+(\w+)\s*:=\s*(?!na\s*$)\S")


def blocks(lines):
    """Yield (header, body_lines) for every top-level `if` in the file."""
    i = 0
    while i < len(lines):
        if lines[i].startswith("if "):
            head, body, i = lines[i], [], i + 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                body.append(lines[i])
                i += 1
            yield head, body
        else:
            i += 1


def check(path):
    lines = Path(path).read_text().splitlines()
    if not any(ln.startswith("strategy(") for ln in lines):
        return []

    armed, faults = set(), []
    for head, body in blocks(lines):
        if any("strategy.entry(" in ln for ln in body):
            for ln in body:
                m = ASSIGN_LIVE.match(ln)
                if m:
                    armed.add(m.group(1))
        elif BARE_FLAT.match(head.rstrip()):
            for ln in body:
                m = ASSIGN_NA.match(ln)
                if m and m.group(1) in armed:
                    faults.append(
                        f"{path}:{lines.index(ln) + 1}: '{m.group(1)}' is set by an entry block "
                        f"and cleared here under a bare flat test, which is true on the entry "
                        f"bar too. Add a just-entered flag to the guard."
                    )
    return faults


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    bad = 0
    for path in argv:
        faults = check(path)
        for f in faults:
            print(f, file=sys.stderr)
        bad += bool(faults)
        if not faults:
            print(f"ok   {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
