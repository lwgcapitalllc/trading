#!/usr/bin/env python3
"""Every identifier inside an input's `active =` must be DECLARED ABOVE that input.

Pine resolves top-down, so an `active =` that names an input declared later is
CE10272 — and it only shows up on the paste. `mpc_bos_strategy.pine` shipped
exactly that in the 2026-08-12 panel reorder (`active = not (bosUseFvg and
execReqFVG)` landed above both). Run this after any panel edit.

Watched RED by mutation: swapping two dependent declarations in the file under
test makes it print a FAIL for that pair and nothing else.
"""

import re
import sys

KEYWORDS = {
    "and",
    "or",
    "not",
    "true",
    "false",
    "na",
    "int",
    "float",
    "bool",
    "string",
    "color",
    "input",
    "timeframe",
    "syminfo",
    "math",
    "str",
    "ta",
}


def check(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    decl = {}  # identifier -> line number of its declaration
    for i, ln in enumerate(lines, 1):
        m = re.match(r"\s*(?:var\s+)?(?:int|float|bool|string|color)\s+(\w+)\s*=", ln)
        if m and m.group(1) not in decl:
            decl[m.group(1)] = i

    bad = []
    for i, ln in enumerate(lines, 1):
        # Stop at the next named argument, or the end of the call. Running on past
        # it swallows `step = 0.05` and reports a phantom dependency on `step`.
        m = re.search(r"active\s*=\s*(.+?)(?:,\s*\w+\s*=(?!=)|\)\s*$)", ln)
        if not m:
            continue
        # Strip string literals: `active = execRunnerTrail != "Fixed step"` is not
        # a reference to an identifier called `step`.
        expr = re.sub(r'"[^"]*"', "", m.group(1))
        for name in re.findall(r"\b([A-Za-z_]\w*)\b", expr):
            if name in KEYWORDS or name not in decl:
                continue
            if decl[name] > i:
                bad.append(
                    f"  line {i}: active = ... {name} ... declared later at line {decl[name]}"
                )
    return bad


rc = 0
for path in sys.argv[1:]:
    bad = check(path)
    if bad:
        rc = 1
        print(f"FAIL {path}")
        print("\n".join(bad))
    else:
        print(f"ok   {path}")
sys.exit(rc)
