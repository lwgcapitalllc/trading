#!/usr/bin/env python3
"""check_continuation.py — a wrapped Pine expression may not be indented a multiple of four.

🔴 **THIS EXISTS BECAUSE IT SHIPPED TWICE IN ONE SESSION AND ONLY TRADINGVIEW CAUGHT IT.**
Aaron, 2026-09-16, pasting `realign_strategy.pine` in: *"Mismatched input 'end of line without
line continuation' expecting set ':'"*. The refusal-reason ternary was wrapped onto continuation
lines indented 16 — which Pine reads as the start of a NEW BLOCK, not as more of the expression
above — so the parser reported the previous line as ending unfinished. The twin is generated from
the parent, so the same break arrived in both halves of the parity gate.

**The rule, from the Pine reference:** a line that continues the expression above it must be
indented by a number of spaces that is NOT a multiple of four. Four, eight, twelve and sixteen
all mean "new block". Every other wrapped expression in these files already sits on 5, 14, 23 or
26 for exactly this reason — the convention existed and was followed by accident rather than
checked.

⚠ **It only looks OUTSIDE brackets.** An expression inside an unclosed `(`, `[` or `{` may wrap
freely at any indent, and flagging those would light up every multi-line `plot(` and `label.new(`
call in the folder — a check with false positives gets ignored, which is the failure the
conventions checker next door already had to be rescued from.

⚠ **It can only catch the operator-first shape** — a continuation line beginning `?`, `:`, `or`,
`and`, `+`, `-`, `*` or `/`. A wrap that breaks after a `(` is inside brackets and is fine; a
wrap that breaks mid-name is not something anyone writes. It catches the failure that actually
happened and claims nothing beyond that.

    python3 indicators/tools/check_continuation.py strategies/tradingview/*.pine
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Tokens that CANNOT begin a Pine statement, so a line starting with one is continuing the line
# above it. `not` is deliberately absent — `not na(x)` opens plenty of real statements.
_CONT = re.compile(r"^(\?|:|or\b|and\b|\+|-|\*|/)")


def _strip(line: str) -> str:
    """The line with string literals and the trailing comment removed.

    ⚠ Needed for the bracket count, not for the indent: a `//` inside a string literal is not a
    comment, and a `(` inside one is not an open bracket. Getting this wrong would desynchronise
    the depth and mis-scope every line after it.
    """
    out, i, quote = [], 0, ""
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "/" and line[i : i + 2] == "//":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def check(path: str) -> list:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    faults, depth = [], 0
    for n, raw in enumerate(lines, 1):
        body = _strip(raw)
        stripped = raw.strip()
        if depth == 0 and stripped and not stripped.startswith("//"):
            indent = len(raw) - len(raw.lstrip(" "))
            if indent and indent % 4 == 0 and _CONT.match(stripped):
                faults.append(
                    f"{path}:{n}: continuation line indented {indent}, a multiple of four — "
                    f"Pine reads that as a new block and reports the line above as unfinished. "
                    f"Use {indent + 1}."
                )
        depth += sum(body.count(c) for c in "([{") - sum(body.count(c) for c in ")]}")
        depth = max(depth, 0)
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
