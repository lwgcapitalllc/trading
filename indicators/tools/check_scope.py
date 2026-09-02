#!/usr/bin/env python3
"""check_scope.py — catch a read of an identifier that nothing in scope declares.

Pine reports this as `CE10272: Undeclared identifier`, and **it only appears on the paste** —
there is no local Pine compiler, so a file can sit in the repo looking finished for days.
`mpc_extreme_leg_strategy.pine` shipped exactly that on 2026-08-24: its higher-timeframe engine
is GENERATED from the chart-frame one, the generator swapped the bar globals for passed-in
values, and two helper methods got the swap without getting the parameter. Nothing failed until
Aaron pasted it.

WHAT IT CHECKS, and it is deliberately narrow: inside every function and method body, an
identifier beginning with `_` must be a parameter of that body or assigned inside it. That
prefix is this repo's convention for a value handed IN to a derived engine instance, so the
check covers the whole class of defect the generator can produce and nothing else.

⚠ It is NOT a Pine parser and will not find an undeclared identifier that has no underscore —
that needs the language's own builtin list, which we do not have. Its silence is not a clean
bill of health, it is one specific question answered.

✅ WATCHED RED BY MUTATION rather than trusted: putting `_bi` back into `create_ash15`'s line
drawing reddens exactly that line (and its chart-frame twin, which shares the text), and
nothing else. Re-run that mutation if this file is ever changed.

Usage:  python3 indicators/tools/check_scope.py strategies/tradingview/*.pine
"""

from __future__ import annotations

import re
import sys

HEADER = re.compile(r"^(?:method\s+)?([A-Za-z_]\w*)\s*\((.*?)\)\s*=>")
PARAM = re.compile(r"([A-Za-z_]\w*)\s*(?:,|$)")
TYPED = re.compile(
    r"^\s*(?:var(?:ip)?\s+)?(?:float|int|bool|string|color|line|label|box|table|array)\s+(\w+)\s*="
)
ASSIGN = re.compile(r"^\s*(\w+)\s*(?::=|=)\s")
LOOPVAR = re.compile(r"for\s+(\w+)\s*=")
UNDERSCORED = re.compile(r"(?<![\w.])(_\w+)")


def check(path: str) -> list[tuple[int, str, str, str]]:
    lines = open(path).read().splitlines()
    bad: list[tuple[int, str, str, str]] = []
    i = 0
    while i < len(lines):
        head = HEADER.match(lines[i])
        if not head:
            i += 1
            continue
        params = set(PARAM.findall(head.group(2)))
        body: list[tuple[int, str]] = []
        j = i + 1
        while j < len(lines) and (lines[j].strip() == "" or lines[j].startswith((" ", "\t"))):
            body.append((j, lines[j]))
            j += 1
        local: set[str] = set()
        for _, text in body:
            local |= set(TYPED.findall(text))
            local |= set(ASSIGN.findall(text))
            local |= set(LOOPVAR.findall(text))
        for ln, text in body:
            for name in UNDERSCORED.findall(text):
                if name not in params and name not in local:
                    bad.append((ln + 1, head.group(1), name, text.strip()[:70]))
        i = j
    return bad


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: check_scope.py <file.pine> [...]")
    failed = False
    for path in sys.argv[1:]:
        bad = check(path)
        if bad:
            failed = True
            for ln, fn, name, text in bad:
                print(f"FAIL {path}:{ln}  `{name}` is read in {fn}() and declared nowhere in it")
                print(f"       {text}")
        else:
            print(f"ok   {path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
